"""
LLM Workflow for Fact-Checking Claims in Materials Science Dataset (OpenAI GPT-5-mini)

This workflow:
1. Extracts all text fields (hypothesis, justification, etc.) from the dataset
2. Uses LLM to extract and classify claims into:
   - dataset_referenced: claims citing data from the dataset
   - external_referenced: claims citing external scientific knowledge
3. Verifies only external_referenced claims using OpenAI's web search tool
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Literal
from concurrent.futures import ThreadPoolExecutor, as_completed
from monty.serialization import loadfn
from openai import OpenAI

# Load environment variables
import os
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Configuration
ROOT_DIR = Path(__file__).parent.parent
DATA_PATH = ROOT_DIR / "data" / "hi_spin_tabulated_data_with_metadata.json"
OUTPUT_DIR = ROOT_DIR / "fact_checking" / "results"
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints_openai"

# OpenAI Model
MODEL = "gpt-5-mini"
REASONING_EFFORT = "low"
MAX_RETRIES = 3
PARALLEL_WORKERS = 5  # Number of parallel verification calls

# Initialize OpenAI client
client = OpenAI()


def get_claim_id(claim: "ExtractedClaim") -> str:
    """Generate a unique ID for a claim based on its content."""
    import hashlib
    content = f"{claim.sample_index}:{claim.source_field}:{claim.claim_text[:100]}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def save_checkpoint(checkpoint_type: str, item_id: str, data: dict):
    """Save a checkpoint for a specific item."""
    checkpoint_subdir = CHECKPOINT_DIR / checkpoint_type
    checkpoint_subdir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = checkpoint_subdir / f"{item_id}.json"
    with open(checkpoint_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def is_checkpoint_valid(checkpoint: dict) -> bool:
    """Check if a checkpoint contains valid results (not parse errors)."""
    if not checkpoint:
        return False
    evidence = checkpoint.get("evidence", [])
    # Invalidate checkpoints with parse errors
    invalid_markers = [
        "[!] Could not parse structured response",
        "[!] Response was truncated",
        "[!] Error during verification",
        "[!] Unable to verify - API error",
    ]
    for marker in invalid_markers:
        if any(marker in str(e) for e in evidence):
            return False
    return True


def load_checkpoint(checkpoint_type: str, item_id: str, validate: bool = False) -> dict | None:
    """Load a checkpoint if it exists.

    Args:
        checkpoint_type: Type of checkpoint (e.g., 'external_verification')
        item_id: Unique ID for the checkpoint
        validate: If True, check if checkpoint is valid (no parse errors)

    Returns:
        Checkpoint data or None if not found or invalid
    """
    checkpoint_file = CHECKPOINT_DIR / checkpoint_type / f"{item_id}.json"
    if checkpoint_file.exists():
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            checkpoint = json.load(f)
        if validate and not is_checkpoint_valid(checkpoint):
            return None
        return checkpoint
    return None


def list_checkpoints(checkpoint_type: str) -> list[str]:
    """List all checkpoint IDs for a given type."""
    checkpoint_subdir = CHECKPOINT_DIR / checkpoint_type
    if not checkpoint_subdir.exists():
        return []
    return [f.stem for f in checkpoint_subdir.glob("*.json")]


def clear_checkpoints():
    """Clear all checkpoints."""
    import shutil
    if CHECKPOINT_DIR.exists():
        shutil.rmtree(CHECKPOINT_DIR)
        print("Cleared all checkpoints")


@dataclass
class ExtractedClaim:
    """A single extracted claim from the text."""
    claim_text: str
    claim_type: Literal["dataset_referenced", "external_referenced"]
    source_field: str
    batch_number: int | None
    provenance: str
    sample_index: str


@dataclass
class VerificationResult:
    """Result of verifying a claim."""
    claim: ExtractedClaim
    status: Literal["verified", "contradicted", "no_support"]
    confidence: float
    explanation: str
    evidence: list[str] = field(default_factory=list)

    @property
    def is_verified(self) -> bool:
        """Backwards compatibility: return True if status is 'verified'."""
        return self.status == "verified"


def load_dataset() -> list[dict]:
    """Load the main dataset."""
    all_data = loadfn(DATA_PATH)
    for i in range(len(all_data)):
        all_data[i]["sample_index"] = i
    return all_data


def extract_text_fields(data: list[dict]) -> list[dict]:
    """Extract all text fields from the dataset that may contain claims."""
    extracted = []

    for sample in data:
        sample_info = {
            "batch_number": sample.get("batch_number"),
            "provenance": sample.get("provenance", "unknown"),
            "texts": {},
            "sample_index": sample["sample_index"],
        }

        # Extract from prev_exp (abnormal provenance)
        if "prev_exp" in sample:
            if "hypothesis" in sample["prev_exp"]:
                sample_info["texts"]["hypothesis"] = sample["prev_exp"]["hypothesis"]
            if "justification" in sample["prev_exp"]:
                sample_info["texts"]["justification"] = sample["prev_exp"]["justification"]

        # Extract abnormality_results
        if "abnormality_results" in sample:
            if "justification" in sample["abnormality_results"]:
                sample_info["texts"]["abnormality_justification"] = sample["abnormality_results"]["justification"]

        # Extract from material_proposal (novelty provenance)
        if "material_proposal" in sample:
            if "justification" in sample["material_proposal"]:
                sample_info["texts"]["material_proposal_justification"] = sample["material_proposal"]["justification"]

        if sample_info["texts"]:
            extracted.append(sample_info)

    return extracted


CLAIM_EXTRACTION_PROMPT = """You are a scientific claim extractor for materials science texts. Extract ONLY verifiable factual claims that can be checked against data or scientific literature.

## What IS a Claim (Extract These)
A claim is a statement asserting a fact that can be independently verified:
- **Data claims**: "Li2MnCl4 synthesized at 400°C has conductivity of 8.81e-07 S/cm"
- **Scientific facts**: "In spinel Li2MCl4 structures, grain boundaries impede Li-ion migration and increase ionic resistance"
- **Property assertions**: "Hf4+ has an octahedral ionic radius of approximately 0.71 Å"
- **Causal relationships**: "Aliovalent doping in Li2MCl4 spinels creates Li vacancies through charge compensation"

## What is NOT a Claim (Do NOT Extract)
- **Calculations/Derivations**: "Zr4+ at 20% yields Li=1.6" - This is just arithmetic, not a claim
- **Design choices**: "We chose 400°C for synthesis" - This is a decision, not a claim
- **Goals/Plans**: "To test whether..." - These are intentions, not claims
- **Vague statements**: "The conductivity is low" without specific values
- **Tautologies**: Restating definitions without asserting new facts

## Claim Categories

1. **dataset_referenced**: Claims citing specific experimental data from THIS dataset
   - Must include specific compositions AND measured values
   - Example: "Li1.6Mn0.9V0.2Cl4 exhibits ionic conductivity of 2.04e-05 S/cm"

2. **external_referenced**: Claims citing external scientific knowledge
   - General scientific principles applied to this material system
   - Literature values (ionic radii, known crystal structures, etc.)
   - Example: "In spinel chloride electrolytes, Li vacancies on octahedral sites enhance ionic conductivity by providing mobile charge carrier sites"

## IMPORTANT: Include Context
Each claim MUST include sufficient context for verification. Do NOT extract context-free fragments.

BAD (lacks context): "grain boundaries increase resistance"
GOOD (has context): "In polycrystalline Li2MCl4 spinel solid electrolytes, grain boundaries increase ionic resistance by disrupting Li-ion migration pathways"

Text to analyze:
---
Source field: {source_field}

Text:
{text}
---

Respond in JSON format:
{{
    "claims": [
        {{
            "claim_text": "Full claim with context (not a fragment)",
            "claim_type": "dataset_referenced" or "external_referenced",
        }}
    ]
}}

Extract only concrete, verifiable claims with proper context. Skip reasoning steps, calculations, and design choices.
"""


def extract_claims_from_text(
    text: str,
    source_field: str,
    sample_index: str,
    batch_number: int | None,
    provenance: str
) -> list[ExtractedClaim]:
    """Use LLM to extract claims from a single text field."""

    prompt = CLAIM_EXTRACTION_PROMPT.format(
        source_field=source_field,
        sample_index=sample_index,
        batch_number=batch_number,
        provenance=provenance,
        text=text
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            print(f"Empty response for {sample_index}/{source_field}")
            return []

        result = json.loads(content)
        claims = []
        for c in result.get("claims", []):
            claim = ExtractedClaim(
                claim_text=c["claim_text"],
                claim_type=c["claim_type"],
                source_field=source_field,
                sample_index=sample_index,
                batch_number=batch_number,
                provenance=provenance,
            )
            claims.append(claim)
        return claims
    except json.JSONDecodeError as e:
        print(f"JSON parse error for {sample_index}/{source_field}: {e}")
        return []
    except Exception as e:
        print(f"Error extracting claims for {sample_index}/{source_field}: {e}")
        return []


def extract_all_claims(extracted_texts: list[dict], use_checkpoints: bool = True) -> list[ExtractedClaim]:
    """Extract claims from all text fields in the dataset with checkpoint support."""
    all_claims = []
    skipped = 0

    for i, sample in enumerate(extracted_texts):
        sample_index = sample['sample_index']

        # Check for existing checkpoint
        if use_checkpoints:
            checkpoint = load_checkpoint("claims", str(sample_index))
            if checkpoint:
                for c in checkpoint.get("claims", []):
                    all_claims.append(ExtractedClaim(**c))
                skipped += 1
                print(f"  [{i+1}/{len(extracted_texts)}] {str(sample_index)[:8]}... (loaded from checkpoint)")
                continue

        print(f"Processing sample {i+1}/{len(extracted_texts)}: {sample_index}")

        sample_claims = []
        for field_name, text in sample["texts"].items():
            if text:
                try:
                    claims = extract_claims_from_text(
                        text=text,
                        source_field=field_name,
                        sample_index=str(sample_index),
                        batch_number=sample["batch_number"],
                        provenance=sample["provenance"]
                    )
                    sample_claims.extend(claims)
                except Exception as e:
                    print(f"  Error extracting from {field_name}: {e}")

        # Save checkpoint for this sample
        if use_checkpoints and sample_claims:
            save_checkpoint("claims", str(sample_index), {
                "sample_index": sample_index,
                "claims": [asdict(c) for c in sample_claims]
            })

        all_claims.extend(sample_claims)

    if skipped > 0:
        print(f"  Loaded {skipped} samples from checkpoints")

    return all_claims


EXTERNAL_VERIFICATION_PROMPT = """You are a scientific fact-checker. Verify the following claim using web search to find REAL literature sources.

Claim: {claim_text}

Context: This claim is from a materials science study on Li-ion solid electrolytes (spinel chlorides like Li2MCl4).

Instructions:
1. Search for authoritative sources (peer-reviewed papers, textbooks) to verify this claim
2. Focus on: ionic radii, crystal structures, doping effects, vacancy formation, ionic conductivity
3. Only cite REAL sources that you found via web search - do NOT fabricate references
4. Include DOIs, URLs, or publication details where possible
5. Classify the claim into one of THREE categories:
   - "verified": The claim is SUPPORTED by literature evidence
   - "contradicted": The claim is CONTRADICTED by literature evidence (literature says the opposite)
   - "no_support": Cannot find sufficient evidence to support OR contradict the claim

Respond ONLY with a valid JSON object:
{{
    "status": "verified",
    "confidence": 0.9,
    "explanation": "Explanation of verification result",
    "scientific_basis": "The underlying principle",
    "references": [
        {{"title": "Paper title", "authors": "Author names", "journal": "Journal name", "year": 2020, "doi": "10.xxxx/xxxxx", "url": "https://...", "relevant_quote": "Quote supporting the claim"}}
    ]
}}

Note:
IMPORTANT: Do NOT classify as "contradicted" if:
- Literature discusses a DIFFERENT but related system (different composition, different conditions)
- The "contradiction" requires extrapolation or inference
- The claim is about a specific system but literature is about a general principle that may not apply
"""


def is_response_truncated(content: str) -> bool:
    """Check if a response appears to be truncated."""
    if not content:
        return True
    content = content.strip()
    # Check if it looks like JSON but doesn't end properly
    if '{' in content:
        # Count braces
        open_braces = content.count('{')
        close_braces = content.count('}')
        if open_braces > close_braces:
            return True
        # Check if it ends mid-sentence (common truncation patterns)
        if content.endswith(('...', ' ', ',', ':', '"', "'")):
            return True
        # Check for incomplete JSON (ends without closing brace)
        last_brace = content.rfind('}')
        if last_brace == -1 or last_brace < content.rfind('{'):
            return True
    return False


def parse_nested_json(text: str) -> dict | None:
    """Recursively parse JSON, handling nested JSON strings in fields."""
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            for key, value in result.items():
                if isinstance(value, str) and value.strip().startswith('{'):
                    try:
                        nested = json.loads(value)
                        result[key] = nested
                    except json.JSONDecodeError:
                        pass
        return result
    except json.JSONDecodeError:
        return None


def extract_json_from_response(content: str) -> str:
    """Extract JSON object from response content."""
    # Try to extract JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
    if json_match:
        content = json_match.group(1).strip()

    # Try to find JSON object in the content
    json_start = content.find('{')
    json_end = content.rfind('}')
    if json_start != -1 and json_end != -1:
        content = content[json_start:json_end + 1]

    return content


def verify_external_claim(claim: ExtractedClaim) -> VerificationResult:
    """Verify an external-referenced claim using OpenAI's web search tool."""

    prompt = EXTERNAL_VERIFICATION_PROMPT.format(claim_text=claim.claim_text)

    content = None
    result = None
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            # Use OpenAI's web search tool with responses API
            response = client.responses.create(
                model=MODEL,
                input=prompt,
                tools=[{"type": "web_search_preview"}],
                reasoning={"effort": REASONING_EFFORT},
            )

            # Extract text content from response
            content = None
            for item in response.output:
                if item.type == "message":
                    for content_item in item.content:
                        if content_item.type == "output_text":
                            content = content_item.text
                            break
                    if content:
                        break

            # Check for truncation and retry if needed
            if is_response_truncated(content):
                if attempt < MAX_RETRIES - 1:
                    print(f"\n  [Retry {attempt + 1}/{MAX_RETRIES}] Response appears truncated, retrying...")
                    continue
                else:
                    print(f"\n  [Warning] Response still truncated after {MAX_RETRIES} attempts")
                    break

            # Try to parse JSON from the response
            json_content = extract_json_from_response(content)
            result = parse_nested_json(json_content)

            if result is None:
                # JSON parsing failed, retry
                if attempt < MAX_RETRIES - 1:
                    print(f"\n  [Retry {attempt + 1}/{MAX_RETRIES}] Could not parse JSON response, retrying...")
                    continue
                else:
                    print(f"\n  [Warning] Could not parse JSON after {MAX_RETRIES} attempts")
                    break
            else:
                # Successfully parsed, break out of retry loop
                break

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                print(f"\n  [Retry {attempt + 1}/{MAX_RETRIES}] API error: {e}, retrying...")
                continue
            else:
                print(f"Error verifying external claim after {MAX_RETRIES} attempts: {e}")
                return VerificationResult(
                    claim=claim,
                    status="no_support",
                    confidence=0.0,
                    explanation=f"Verification failed after {MAX_RETRIES} attempts: {str(e)}",
                    evidence=["[!] Unable to verify - API error"]
                )

    if not content:
        return VerificationResult(
            claim=claim,
            status="no_support",
            confidence=0.0,
            explanation="Empty response from LLM",
            evidence=[]
        )

    if result:
        explanation = result.get("explanation", "")
        confidence = result.get("confidence", 0.0)

        status = result.get("status")
        if status is None:
            is_verified = result.get("is_verified", False)
            status = "verified" if is_verified else "no_support"
        if status not in ("verified", "contradicted", "no_support"):
            status = "no_support"

        if isinstance(explanation, dict):
            confidence = explanation.get("confidence", confidence)
            explanation = explanation.get("explanation", str(explanation))

        # Build evidence list
        evidence = []

        if status == "verified":
            evidence.append("[VERIFIED] Verified with web search")
        elif status == "contradicted":
            evidence.append("[CONTRADICTED] Contradicted by literature")
        else:
            evidence.append("[NO_SUPPORT] No supporting or contradicting evidence found")

        if result.get("scientific_basis"):
            evidence.append(f"Scientific basis: {result['scientific_basis']}")

        if result.get("references"):
            refs = result["references"]
            if isinstance(refs, list):
                for ref in refs:
                    if isinstance(ref, dict):
                        ref_str = ""
                        if ref.get("authors"):
                            ref_str += f"{ref['authors']} "
                        if ref.get("year"):
                            ref_str += f"({ref['year']}). "
                        if ref.get("title"):
                            ref_str += f"{ref['title']}. "
                        if ref.get("journal"):
                            ref_str += f"{ref['journal']}. "
                        if ref.get("doi"):
                            ref_str += f"DOI: {ref['doi']} "
                        if ref.get("url"):
                            ref_str += f"URL: {ref['url']}"
                        evidence.append(f"Reference: {ref_str.strip()}")
                    else:
                        evidence.append(f"Reference: {ref}")

        return VerificationResult(
            claim=claim,
            status=status,
            confidence=float(confidence) if confidence else 0.0,
            explanation=explanation if isinstance(explanation, str) else str(explanation),
            evidence=evidence
        )
    else:
        # Check if this is a truncation issue
        truncated = is_response_truncated(content)

        # If not JSON, analyze the text response
        has_support = any(word in content.lower() for word in ["verified", "confirmed", "supported"])
        has_contradiction = any(word in content.lower() for word in ["contradicted", "contradicts", "opposite", "incorrect"])
        has_no_support = any(word in content.lower() for word in ["not verified", "unverified", "no evidence", "cannot verify"])

        if has_contradiction:
            status = "contradicted"
            confidence = 0.4 if truncated else 0.5
        elif has_support and not has_no_support:
            status = "verified"
            confidence = 0.4 if truncated else 0.5
        else:
            status = "no_support"
            confidence = 0.2 if truncated else 0.3

        # Build a cleaner explanation from truncated content
        if truncated:
            # Try to extract just the explanation text from truncated JSON
            explanation_match = re.search(r'"explanation":\s*"([^"]*)', content)
            if explanation_match:
                explanation = explanation_match.group(1) + " [TRUNCATED]"
            else:
                explanation = content[:500] + " [TRUNCATED]" if content else "No explanation provided"
            evidence = ["[!] Response was truncated - parsed from incomplete data"]
        else:
            explanation = content[:500] if content else "No explanation provided"
            evidence = ["[!] Could not parse structured response"]

        return VerificationResult(
            claim=claim,
            status=status,
            confidence=confidence,
            explanation=explanation,
            evidence=evidence
        )


def run_fact_check_workflow(
    max_samples: int | None = None,
    skip_extraction: bool = False,
    claims_file: str | None = None,
    resume: bool = True,
    clear_existing_checkpoints: bool = False,
    parallel_workers: int = PARALLEL_WORKERS
) -> dict:
    """
    Run the complete fact-checking workflow with checkpoint support.

    Args:
        max_samples: Limit number of samples to process (for testing)
        skip_extraction: If True, load claims from file instead of extracting
        claims_file: Path to pre-extracted claims JSON file
        resume: If True, resume from checkpoints (default: True)
        clear_existing_checkpoints: If True, clear all checkpoints before starting
        parallel_workers: Number of parallel verification calls (default: 5)

    Returns:
        Dictionary with all results
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if clear_existing_checkpoints:
        clear_checkpoints()

    print("=" * 60)
    print("FACT-CHECKING WORKFLOW (OpenAI GPT-5-mini)")
    print(f"  Model: {MODEL}")
    print(f"  Reasoning effort: {REASONING_EFFORT}")
    print(f"  Max retries: {MAX_RETRIES}")
    print(f"  Parallel workers: {parallel_workers}")
    if resume:
        print("  (Checkpoint mode: will resume from previous progress)")
    print("=" * 60)

    # Step 1: Load dataset
    print("\n[1/4] Loading dataset...")
    data = load_dataset()
    print(f"Loaded {len(data)} samples")

    # Step 2: Extract text fields
    print("\n[2/4] Extracting text fields...")
    extracted_texts = extract_text_fields(data)
    print(f"Found {len(extracted_texts)} samples with text fields")

    if max_samples:
        extracted_texts = extracted_texts[:max_samples]
        print(f"Limited to {max_samples} samples for processing")

    # Step 3: Extract claims
    if skip_extraction and claims_file:
        print(f"\n[3/4] Loading pre-extracted claims from {claims_file}...")
        with open(claims_file, 'r') as f:
            claims_data = json.load(f)
        all_claims = [ExtractedClaim(**c) for c in claims_data]
    else:
        print("\n[3/4] Extracting claims using LLM...")
        all_claims = extract_all_claims(extracted_texts, use_checkpoints=resume)

        # Save extracted claims
        claims_output = OUTPUT_DIR / "extracted_claims_openai.json"
        with open(claims_output, 'w', encoding='utf-8') as f:
            json.dump([asdict(c) for c in all_claims], f, indent=2)
        print(f"Saved {len(all_claims)} claims to {claims_output}")

    # Categorize claims
    dataset_claims = [c for c in all_claims if c.claim_type == "dataset_referenced"]
    external_claims = [c for c in all_claims if c.claim_type == "external_referenced"]

    print(f"\nClaim summary:")
    print(f"  - Dataset-referenced: {len(dataset_claims)}")
    print(f"  - External-referenced: {len(external_claims)}")

    # Step 4: Verify external-referenced claims using web search (parallel)
    print(f"\n[4/4] Verifying external-referenced claims (OpenAI web search, {parallel_workers} parallel workers)...")
    external_results = []
    skipped_external = 0
    claims_to_verify = []

    # First, check checkpoints and separate cached vs. new claims
    revalidate_count = 0
    for claim in external_claims:
        claim_id = get_claim_id(claim)

        if resume:
            # Use validate=True to skip checkpoints with parse errors
            checkpoint = load_checkpoint("external_verification", claim_id, validate=True)
            if checkpoint:
                status = checkpoint.get("status")
                if status is None:
                    status = "verified" if checkpoint.get("is_verified", False) else "no_support"
                external_results.append(VerificationResult(
                    claim=claim,
                    status=status,
                    confidence=checkpoint["confidence"],
                    explanation=checkpoint["explanation"],
                    evidence=checkpoint["evidence"]
                ))
                skipped_external += 1
                continue
            else:
                # Check if checkpoint exists but was invalid (parse error)
                invalid_checkpoint = load_checkpoint("external_verification", claim_id, validate=False)
                if invalid_checkpoint:
                    revalidate_count += 1

        claims_to_verify.append((claim, claim_id))

    print(f"  Loaded {skipped_external} from checkpoints, {len(claims_to_verify)} to verify...")
    if revalidate_count > 0:
        print(f"  (Re-running {revalidate_count} claims with previous parse errors)")

    def verify_and_save(claim_and_id: tuple) -> VerificationResult:
        """Verify a single claim and save checkpoint."""
        claim, claim_id = claim_and_id
        try:
            result = verify_external_claim(claim)

            # Save checkpoint (thread-safe file write)
            if resume:
                save_checkpoint("external_verification", claim_id, {
                    "claim_id": claim_id,
                    "status": result.status,
                    "is_verified": result.is_verified,
                    "confidence": result.confidence,
                    "explanation": result.explanation,
                    "evidence": result.evidence
                })
            return result
        except Exception as e:
            print(f"\n  Error verifying claim {claim_id}: {e}")
            return VerificationResult(
                claim=claim,
                status="no_support",
                confidence=0.0,
                explanation=f"Verification error: {str(e)}",
                evidence=["[!] Error during verification"]
            )

    # Run parallel verification
    if claims_to_verify:
        completed = 0
        total_to_verify = len(claims_to_verify)

        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            future_to_claim = {
                executor.submit(verify_and_save, item): item
                for item in claims_to_verify
            }

            for future in as_completed(future_to_claim):
                result = future.result()
                external_results.append(result)
                completed += 1
                print(f"  Verified {completed}/{total_to_verify} claims ({parallel_workers} parallel)...", end="\r")

        print()  # New line after progress

    print(f"  Verified {len(external_results)} external claims with web search" +
          (f" ({skipped_external} from checkpoints)" if skipped_external > 0 else ""))

    # Compile results
    verified_count = sum(1 for r in external_results if r.status == "verified")
    contradicted_count = sum(1 for r in external_results if r.status == "contradicted")
    no_support_count = sum(1 for r in external_results if r.status == "no_support")

    results = {
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "dataset_verification_results": [
            {
                "claim": asdict(c)
            }
            for c in dataset_claims
        ],
        "external_verification_results": [
            {
                "claim": asdict(r.claim),
                "status": r.status,
                "is_verified": r.is_verified,
                "confidence": r.confidence,
                "explanation": r.explanation,
                "evidence": r.evidence
            }
            for r in external_results
        ],
        "summary": {
            "total_claims": len(all_claims),
            "dataset_referenced": {
                "total": len(dataset_claims)
            },
            "external_referenced": {
                "total": len(external_claims),
                "verified": verified_count,
                "contradicted": contradicted_count,
                "no_support": no_support_count,
                "not_verified": contradicted_count + no_support_count,
                "avg_confidence": sum(r.confidence for r in external_results) / len(external_results) if external_results else 0
            }
        }
    }

    # Save results
    results_output = OUTPUT_DIR / "fact_check_results_openai.json"
    with open(results_output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {results_output}")

    # Print summary
    print("\n" + "=" * 60)
    print("FACT-CHECK SUMMARY (OpenAI GPT-5-mini)")
    print("=" * 60)
    print(f"\nTotal claims extracted: {results['summary']['total_claims']}")
    print(f"\nDataset-referenced claims: {results['summary']['dataset_referenced']['total']} (not verified in this workflow)")
    print(f"\nExternal-referenced claims:")
    print(f"  - Verified: {results['summary']['external_referenced']['verified']}/{results['summary']['external_referenced']['total']}")
    print(f"  - Contradicted: {results['summary']['external_referenced']['contradicted']}/{results['summary']['external_referenced']['total']}")
    print(f"  - No support: {results['summary']['external_referenced']['no_support']}/{results['summary']['external_referenced']['total']}")
    print(f"  - Avg confidence: {results['summary']['external_referenced']['avg_confidence']:.2%}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run fact-checking workflow using OpenAI GPT-5-mini")

    parser.add_argument("--max-samples", type=int, default=None, help="Limit number of samples to process")
    parser.add_argument("--skip-extraction", action="store_true", help="Skip claim extraction, load from file")
    parser.add_argument("--claims-file", type=str, default=None, help="Path to pre-extracted claims file")
    parser.add_argument("--no-resume", action="store_true", help="Disable checkpoint resumption (start fresh)")
    parser.add_argument("--clear-checkpoints", action="store_true", help="Clear all checkpoints before starting")
    parser.add_argument("--parallel", type=int, default=PARALLEL_WORKERS,
                        help=f"Number of parallel verification workers (default: {PARALLEL_WORKERS})")

    args = parser.parse_args()

    run_fact_check_workflow(
        max_samples=args.max_samples,
        skip_extraction=args.skip_extraction,
        claims_file=args.claims_file,
        resume=not args.no_resume,
        clear_existing_checkpoints=args.clear_checkpoints,
        parallel_workers=args.parallel
    )
