"""
LLM Workflow for Fact-Checking Claims in Materials Science Dataset

This workflow:
1. Extracts all text fields (hypothesis, justification, etc.) from the dataset
2. Uses LLM to extract and classify claims into:
   - dataset_referenced: claims citing data from the dataset
   - external_referenced: claims citing external scientific knowledge
3. Verifies only external_referenced claims using web search (Claude Sonnet)
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Literal
from monty.serialization import loadfn
import litellm

# Load environment variables
import os
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Configuration
ROOT_DIR = Path(__file__).parent.parent
DATA_PATH = ROOT_DIR / "hi_spin_tabulated_data_with_metadata.json"
OUTPUT_DIR = ROOT_DIR / "fact_checking" / "results"
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"

# LLM Models
CLAIM_EXTRACTION_MODEL = "anthropic/claude-sonnet-4-5"
EXTERNAL_VERIFICATION_MODEL = "anthropic/claude-sonnet-4-5"  # Must use sonnet for web search


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


def load_checkpoint(checkpoint_type: str, item_id: str) -> dict | None:
    """Load a checkpoint if it exists."""
    checkpoint_file = CHECKPOINT_DIR / checkpoint_type / f"{item_id}.json"
    if checkpoint_file.exists():
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            return json.load(f)
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
    status: Literal["verified", "contradicted", "no_support"]  # Three-way classification
    confidence: float  # 0-1
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

        if sample_info["texts"]:  # Only include if there are text fields
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
        response = litellm.completion(
            model=CLAIM_EXTRACTION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )

        content = response.choices[0].message.content
        if not content:
            print(f"Empty response for {sample_index}/{source_field}")
            return []

        # Try to extract JSON from the response (may be wrapped in markdown)
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if json_match:
            content = json_match.group(1).strip()

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
        print(f"  Response content (first 200 chars): {content[:200] if content else 'None'}")
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
            checkpoint = load_checkpoint("claims", sample_index)
            if checkpoint:
                # Load claims from checkpoint
                for c in checkpoint.get("claims", []):
                    all_claims.append(ExtractedClaim(**c))
                skipped += 1
                print(f"  [{i+1}/{len(extracted_texts)}] {sample_index[:8]}... (loaded from checkpoint)")
                continue

        print(f"Processing sample {i+1}/{len(extracted_texts)}: {sample_index}")

        sample_claims = []
        for field_name, text in sample["texts"].items():
            if text:
                try:
                    claims = extract_claims_from_text(
                        text=text,
                        source_field=field_name,
                        sample_index=sample_index,
                        batch_number=sample["batch_number"],
                        provenance=sample["provenance"]
                    )
                    sample_claims.extend(claims)
                except Exception as e:
                    print(f"  Error extracting from {field_name}: {e}")

        # Save checkpoint for this sample
        if use_checkpoints and sample_claims:
            save_checkpoint("claims", sample_index, {
                "sample_index": sample_index,
                "claims": [asdict(c) for c in sample_claims]
            })

        all_claims.extend(sample_claims)

    if skipped > 0:
        print(f"  Loaded {skipped} samples from checkpoints")

    return all_claims


EXTERNAL_VERIFICATION_PROMPT = """You are a scientific fact-checker. Use web search to verify the following claim with REAL literature sources.

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

# Search effort levels for external verification
SEARCH_EFFORT_LOW = "low"
SEARCH_EFFORT_MEDIUM = "medium"
SEARCH_EFFORT_HIGH = "high"


def verify_external_claim(claim: ExtractedClaim, search_effort: str = SEARCH_EFFORT_LOW) -> VerificationResult:
    """Verify an external-referenced claim using web search.

    Args:
        claim: The claim to verify
        search_effort: Search effort level - "low", "medium", or "high"
    """

    prompt = EXTERNAL_VERIFICATION_PROMPT.format(claim_text=claim.claim_text)

    try:
        response = litellm.completion(
            model=EXTERNAL_VERIFICATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            web_search_options={
                "search_context_size": search_effort,
            }
        )
        content = response.choices[0].message.content
    except Exception as e:
        print(f"Error verifying external claim: {e}")
        return VerificationResult(
            claim=claim,
            status="no_support",
            confidence=0.0,
            explanation=f"Verification failed: {str(e)}",
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

    # Try to extract JSON from the response (may be wrapped in markdown)
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
    if json_match:
        content = json_match.group(1).strip()

    # Try to find JSON object in the content
    json_start = content.find('{')
    json_end = content.rfind('}')
    if json_start != -1 and json_end != -1:
        content = content[json_start:json_end + 1]

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

    result = parse_nested_json(content)

    if result:
        explanation = result.get("explanation", "")
        confidence = result.get("confidence", 0.0)

        # Handle new 'status' field or legacy 'is_verified' field
        status = result.get("status")
        if status is None:
            # Legacy format: convert is_verified to status
            is_verified = result.get("is_verified", False)
            status = "verified" if is_verified else "no_support"
        # Validate status
        if status not in ("verified", "contradicted", "no_support"):
            status = "no_support"

        if isinstance(explanation, dict):
            confidence = explanation.get("confidence", confidence)
            explanation = explanation.get("explanation", str(explanation))

        # Build evidence list
        evidence = []

        # Add verification status
        if status == "verified":
            evidence.append("[VERIFIED] Verified with web search")
        elif status == "contradicted":
            evidence.append("[CONTRADICTED] Contradicted by literature")
        else:
            evidence.append("[NO_SUPPORT] No supporting or contradicting evidence found")

        # Add scientific basis
        if result.get("scientific_basis"):
            evidence.append(f"Scientific basis: {result['scientific_basis']}")

        # Add references from web search
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
        # If not JSON, analyze the text response
        has_support = any(word in content.lower() for word in ["verified", "confirmed", "supported"])
        has_contradiction = any(word in content.lower() for word in ["contradicted", "contradicts", "opposite", "incorrect"])
        has_no_support = any(word in content.lower() for word in ["not verified", "unverified", "no evidence", "cannot verify"])

        if has_contradiction:
            status = "contradicted"
            confidence = 0.5
        elif has_support and not has_no_support:
            status = "verified"
            confidence = 0.5
        else:
            status = "no_support"
            confidence = 0.3

        return VerificationResult(
            claim=claim,
            status=status,
            confidence=confidence,
            explanation=content[:500] if content else "No explanation provided",
            evidence=["[!] Could not parse structured response"]
        )


def reverify_unverified_external_claims(
    results_file: str | None = None,
    search_effort: str = SEARCH_EFFORT_MEDIUM,
    max_claims: int | None = None,
    start_from_claim: int = 0
) -> dict:
    """
    Re-verify external claims that were not verified in a previous run.

    This function reads the existing results file, identifies external claims
    that were marked as "no_support" or "contradicted", and re-searches them
    with higher search effort.

    Args:
        results_file: Path to previous results JSON file. Defaults to standard output location.
        search_effort: Search effort level - "low", "medium", or "high". Defaults to "medium".
        max_claims: Maximum number of claims to re-verify (for testing).
        start_from_claim: Index to start re-verification from (0-based). Use this to resume
            if a previous re-verification was interrupted.

    Returns:
        Dictionary with updated results
    """
    # Load previous results
    if results_file is None:
        results_file = OUTPUT_DIR / "fact_check_results.json"
    else:
        results_file = Path(results_file)

    if not results_file.exists():
        raise FileNotFoundError(f"Results file not found: {results_file}")

    print("=" * 60)
    print(f"RE-VERIFYING NON-VERIFIED EXTERNAL CLAIMS (effort: {search_effort})")
    print("=" * 60)

    with open(results_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    # Find claims to re-verify: "no_support" and "contradicted" (or legacy is_verified=False)
    external_results = results.get("external_verification_results", [])

    def needs_reverification(r: dict) -> bool:
        """Check if a result needs re-verification."""
        status = r.get("status")
        if status is not None:
            # New format: re-verify "no_support" and "contradicted"
            return status in ("no_support", "contradicted")
        else:
            # Legacy format: re-verify all that are not verified
            return not r.get("is_verified", False)

    to_reverify = [r for r in external_results if needs_reverification(r)]

    # Count by status
    no_support_count = sum(1 for r in to_reverify if r.get("status") == "no_support" or (r.get("status") is None and not r.get("is_verified", False)))
    contradicted_count = sum(1 for r in to_reverify if r.get("status") == "contradicted")

    print(f"\nFound {len(to_reverify)} claims to re-verify out of {len(external_results)} total")
    print(f"  - no_support: {no_support_count}")
    print(f"  - contradicted: {contradicted_count}")

    if start_from_claim > 0:
        if start_from_claim >= len(to_reverify):
            print(f"start_from_claim ({start_from_claim}) is >= total claims to re-verify ({len(to_reverify)}). Nothing to process.")
            return results
        to_reverify = to_reverify[start_from_claim:]
        print(f"Starting from claim index {start_from_claim} ({len(to_reverify)} remaining)")

    if max_claims:
        to_reverify = to_reverify[:max_claims]
        print(f"Limited to {max_claims} claims for re-verification")

    if not to_reverify:
        print("No claims to process.")
        return results

    # Re-verify each claim
    updated_count = 0
    status_changes = {"to_verified": 0, "to_contradicted": 0, "to_no_support": 0}

    # Fields expected by ExtractedClaim dataclass
    claim_fields = {"claim_text", "claim_type", "source_field", "batch_number", "provenance", "sample_index"}

    total_to_process = len(to_reverify)
    skipped_from_checkpoint = 0
    for i, result_dict in enumerate(to_reverify):
        claim_data = result_dict.get("claim", {})
        # Filter to only include fields expected by ExtractedClaim
        filtered_claim_data = {k: v for k, v in claim_data.items() if k in claim_fields}
        claim = ExtractedClaim(**filtered_claim_data)
        claim_id = get_claim_id(claim)

        # Check for existing checkpoint with status
        checkpoint = load_checkpoint("external_verification", claim_id)
        if checkpoint and checkpoint.get("status") and checkpoint["status"] != "contradicted":
            # Use cached result from checkpoint
            skipped_from_checkpoint += 1
            cached_status = checkpoint["status"]
            print(f"  [{i+1}/{total_to_process}] {claim_id}... (loaded from checkpoint, status: {cached_status})")

            # Update the result in the original list with checkpoint data
            for j, orig_result in enumerate(external_results):
                orig_claim_data = {k: v for k, v in orig_result["claim"].items() if k in claim_fields}
                orig_claim_id = get_claim_id(ExtractedClaim(**orig_claim_data))
                if orig_claim_id == claim_id:
                    external_results[j] = {
                        "claim": orig_result["claim"],
                        "status": checkpoint["status"],
                        "is_verified": checkpoint.get("is_verified", checkpoint["status"] == "verified"),
                        "confidence": checkpoint.get("confidence", 0.0),
                        "explanation": checkpoint.get("explanation", ""),
                        "evidence": checkpoint.get("evidence", [])
                    }
                    updated_count += 1
                    status_changes[f"to_{checkpoint['status']}"] = status_changes.get(f"to_{checkpoint['status']}", 0) + 1
                    break
            continue

        old_status = result_dict.get("status", "no_support" if not result_dict.get("is_verified", False) else "verified")
        global_index = start_from_claim + i
        # Handle non-ASCII characters for Windows console
        claim_preview = claim.claim_text[:80].encode('ascii', 'replace').decode('ascii')
        print(f"\n[{i+1}/{total_to_process}] (index {global_index}) [{old_status}] Re-verifying: {claim_preview}...")

        try:
            new_result = verify_external_claim(claim, search_effort=search_effort)

            # Update the result in the original list
            for j, orig_result in enumerate(external_results):
                orig_claim_data = {k: v for k, v in orig_result["claim"].items() if k in claim_fields}
                orig_claim_id = get_claim_id(ExtractedClaim(**orig_claim_data))
                if orig_claim_id == claim_id:
                    external_results[j] = {
                        "claim": orig_result["claim"],  # Preserve original claim data with extra fields
                        "status": new_result.status,
                        "is_verified": new_result.is_verified,  # Keep for backwards compatibility
                        "confidence": new_result.confidence,
                        "explanation": new_result.explanation,
                        "evidence": new_result.evidence
                    }
                    updated_count += 1

                    # Track status changes
                    status_changes[f"to_{new_result.status}"] = status_changes.get(f"to_{new_result.status}", 0) + 1

                    status_symbol = {"verified": "+", "contradicted": "X", "no_support": "?"}
                    print(f"  [{status_symbol.get(new_result.status, '?')}] {old_status} -> {new_result.status} (confidence: {new_result.confidence:.2f})")

                    # Update checkpoint
                    save_checkpoint("external_verification", claim_id, {
                        "claim_id": claim_id,
                        "status": new_result.status,
                        "is_verified": new_result.is_verified,
                        "confidence": new_result.confidence,
                        "explanation": new_result.explanation,
                        "evidence": new_result.evidence,
                        "search_effort": search_effort
                    })
                    break

        except Exception as e:
            print(f"  [!] Error: {e}")

    # Update summary with new three-way classification
    results["external_verification_results"] = external_results
    verified_count = sum(1 for r in external_results if r.get("status") == "verified" or (r.get("status") is None and r.get("is_verified", False)))
    contradicted_count = sum(1 for r in external_results if r.get("status") == "contradicted")
    no_support_count = sum(1 for r in external_results if r.get("status") == "no_support" or (r.get("status") is None and not r.get("is_verified", False)))

    results["summary"]["external_referenced"]["verified"] = verified_count
    results["summary"]["external_referenced"]["contradicted"] = contradicted_count
    results["summary"]["external_referenced"]["no_support"] = no_support_count
    # Keep legacy field for backwards compatibility
    results["summary"]["external_referenced"]["not_verified"] = contradicted_count + no_support_count
    results["summary"]["external_referenced"]["avg_confidence"] = (
        sum(r.get("confidence", 0) for r in external_results) / len(external_results)
        if external_results else 0
    )

    # Save updated results
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print("RE-VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Claims processed: {updated_count}")
    if skipped_from_checkpoint > 0:
        print(f"  - Loaded from checkpoints: {skipped_from_checkpoint}")
    print(f"Status changes:")
    print(f"  - Now verified: {status_changes.get('to_verified', 0)}")
    print(f"  - Now contradicted: {status_changes.get('to_contradicted', 0)}")
    print(f"  - Still no_support: {status_changes.get('to_no_support', 0)}")
    print(f"\nFinal totals:")
    print(f"  - Verified: {verified_count}/{len(external_results)}")
    print(f"  - Contradicted: {contradicted_count}/{len(external_results)}")
    print(f"  - No support: {no_support_count}/{len(external_results)}")
    print(f"\nResults saved to {results_file}")

    return results


def run_fact_check_workflow(
    max_samples: int | None = None,
    skip_extraction: bool = False,
    claims_file: str | None = None,
    resume: bool = True,
    clear_existing_checkpoints: bool = False
) -> dict:
    """
    Run the complete fact-checking workflow with checkpoint support.

    Args:
        max_samples: Limit number of samples to process (for testing)
        skip_extraction: If True, load claims from file instead of extracting
        claims_file: Path to pre-extracted claims JSON file
        resume: If True, resume from checkpoints (default: True)
        clear_existing_checkpoints: If True, clear all checkpoints before starting

    Returns:
        Dictionary with all results
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if clear_existing_checkpoints:
        clear_checkpoints()

    print("=" * 60)
    print("FACT-CHECKING WORKFLOW")
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
        claims_output = OUTPUT_DIR / "extracted_claims.json"
        with open(claims_output, 'w', encoding='utf-8') as f:
            json.dump([asdict(c) for c in all_claims], f, indent=2)
        print(f"Saved {len(all_claims)} claims to {claims_output}")

    # Categorize claims
    dataset_claims = [c for c in all_claims if c.claim_type == "dataset_referenced"]
    external_claims = [c for c in all_claims if c.claim_type == "external_referenced"]

    print(f"\nClaim summary:")
    print(f"  - Dataset-referenced: {len(dataset_claims)}")
    print(f"  - External-referenced: {len(external_claims)}")

    # Step 4: Verify external-referenced claims using web search
    print("\n[4/4] Verifying external-referenced claims (web search enabled)...")
    external_results = []
    skipped_external = 0
    for i, claim in enumerate(external_claims):
        claim_id = get_claim_id(claim)

        # Check for existing checkpoint
        if resume:
            checkpoint = load_checkpoint("external_verification", claim_id)
            if checkpoint:
                # Handle both new 'status' field and legacy 'is_verified'
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

        print(f"  Verifying {i+1}/{len(external_claims)} with web search...", end="\r")
        try:
            result = verify_external_claim(claim)
            external_results.append(result)

            # Save checkpoint
            if resume:
                save_checkpoint("external_verification", claim_id, {
                    "claim_id": claim_id,
                    "status": result.status,
                    "is_verified": result.is_verified,
                    "confidence": result.confidence,
                    "explanation": result.explanation,
                    "evidence": result.evidence
                })
        except Exception as e:
            print(f"\n  Error verifying claim {claim_id}: {e}")
            external_results.append(VerificationResult(
                claim=claim,
                status="no_support",
                confidence=0.0,
                explanation=f"Verification error: {str(e)}",
                evidence=["[!] Error during verification"]
            ))

    print(f"  Verified {len(external_results)} external claims with web search" +
          (f" ({skipped_external} from checkpoints)" if skipped_external > 0 else ""))

    # Compile results with three-way classification
    verified_count = sum(1 for r in external_results if r.status == "verified")
    contradicted_count = sum(1 for r in external_results if r.status == "contradicted")
    no_support_count = sum(1 for r in external_results if r.status == "no_support")

    results = {
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
                "is_verified": r.is_verified,  # Keep for backwards compatibility
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
                "not_verified": contradicted_count + no_support_count,  # Legacy field
                "avg_confidence": sum(r.confidence for r in external_results) / len(external_results) if external_results else 0
            }
        }
    }

    # Save results
    results_output = OUTPUT_DIR / "fact_check_results.json"
    with open(results_output, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {results_output}")

    # Print summary
    print("\n" + "=" * 60)
    print("FACT-CHECK SUMMARY")
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

    parser = argparse.ArgumentParser(description="Run fact-checking workflow on materials science dataset")

    # Mode selection
    parser.add_argument("--reverify-external", action="store_true",
                       help="Re-verify unverified external claims with higher search effort")
    parser.add_argument("--search-effort", type=str, default="medium",
                       choices=["low", "medium", "high"],
                       help="Search effort level for external verification (default: medium)")
    parser.add_argument("--max-claims", type=int, default=None,
                       help="Limit number of claims to re-verify (for --reverify-external mode)")
    parser.add_argument("--start-from-claim", type=int, default=0,
                       help="Index to start re-verification from (0-based, for --reverify-external mode)")
    parser.add_argument("--results-file", type=str, default=None,
                       help="Path to existing results file (for --reverify-external mode)")

    # Original workflow arguments
    parser.add_argument("--max-samples", type=int, default=None, help="Limit number of samples to process")
    parser.add_argument("--skip-extraction", action="store_true", help="Skip claim extraction, load from file")
    parser.add_argument("--claims-file", type=str, default=None, help="Path to pre-extracted claims file")
    parser.add_argument("--no-resume", action="store_true", help="Disable checkpoint resumption (start fresh)")
    parser.add_argument("--clear-checkpoints", action="store_true", help="Clear all checkpoints before starting")

    args = parser.parse_args()

    if args.reverify_external:
        # Run re-verification mode for unverified external claims
        reverify_unverified_external_claims(
            results_file=args.results_file,
            search_effort=args.search_effort,
            max_claims=args.max_claims,
            start_from_claim=args.start_from_claim
        )
    else:
        # Run standard fact-checking workflow
        run_fact_check_workflow(
            max_samples=args.max_samples,
            skip_extraction=args.skip_extraction,
            claims_file=args.claims_file,
            resume=not args.no_resume,
            clear_existing_checkpoints=args.clear_checkpoints
        )
