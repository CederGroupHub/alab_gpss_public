"""
LLM Classifier for Unverified Claims

Classifies unverified claims into two categories:
1. Contradicted: Claims where evidence exists but contradicts the claim
2. No evidence: Claims where no supporting evidence could be found

Uses LLM to analyze the claim text and explanation to determine the category.
"""

import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Literal
import litellm

# Load environment variables
import os
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Map ANTHROPIC_AUTH_TOKEN to ANTHROPIC_API_KEY if needed
if os.getenv("ANTHROPIC_AUTH_TOKEN") and not os.getenv("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_AUTH_TOKEN")

# Fix encoding for Windows console
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Configuration
ROOT_DIR = Path(__file__).parent
RESULTS_FILE = ROOT_DIR / "results" / "fact_check_results.json"
OUTPUT_FILE = ROOT_DIR / "results" / "classified_unverified_claims.json"
CHECKPOINT_DIR = ROOT_DIR / "results" / "checkpoints" / "unverified_classification"

# LLM Model
CLASSIFICATION_MODEL = "anthropic/claude-sonnet"


@dataclass
class ClassifiedClaim:
    """A classified unverified claim."""
    claim_text: str
    claim_type: str  # dataset_referenced or external_referenced
    source_field: str
    sample_id: str
    batch_number: int | None
    provenance: str
    original_explanation: str
    original_confidence: float
    classification: Literal["contradicted", "no_evidence"]
    classification_reasoning: str
    classification_confidence: float


def get_claim_id(claim: dict) -> str:
    """Generate a unique ID for a claim based on its content."""
    import hashlib
    content = f"{claim.get('sample_id', '')}:{claim.get('source_field', '')}:{claim.get('claim_text', '')[:100]}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def save_checkpoint(item_id: str, data: dict):
    """Save a checkpoint for a specific item."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_file = CHECKPOINT_DIR / f"{item_id}.json"
    with open(checkpoint_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def load_checkpoint(item_id: str) -> dict | None:
    """Load a checkpoint if it exists."""
    checkpoint_file = CHECKPOINT_DIR / f"{item_id}.json"
    if checkpoint_file.exists():
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


CLASSIFICATION_PROMPT = """You are analyzing an unverified scientific claim to classify WHY it was not verified.

## Classification Categories

1. **contradicted**: The claim was DIRECTLY CONTRADICTED by evidence IN THE SAME CONTEXT. This ONLY includes:
   - Specific value mismatches for the SAME composition/sample (claimed X but actual data shows Y for the SAME material)
   - Direct property conflicts for the SAME system (claimed property A but data shows property B for the SAME material)
   - Literature that explicitly addresses THE EXACT SAME claim and says the opposite

   IMPORTANT: Do NOT classify as "contradicted" if:
   - Literature discusses a DIFFERENT but related system (different composition, different conditions)
   - The "contradiction" requires extrapolation or inference
   - The claim is about a specific system but literature is about a general principle that may not apply

2. **no_evidence**: The claim could NOT be verified due to LACK of DIRECT evidence. This includes:
   - "No direct literature evidence" or similar phrases
   - "No peer-reviewed sources" or "no specific sources found"
   - "Insufficient literature support"
   - Composition or sample not found in dataset
   - Property not available for the specific claim
   - Literature found is about DIFFERENT systems/contexts (even if related)
   - Claims that are too specific to find exact matches
   - General principles cited but no direct evidence for the specific claim

## Claim Information

Claim text: {claim_text}

Claim type: {claim_type}

Verification explanation: {explanation}

Evidence collected: {evidence}

## Instructions

Be CONSERVATIVE about "contradicted" classification. Only use it when:
1. The evidence directly addresses THE EXACT SAME system/composition/conditions
2. The contradiction is explicit, not inferred from related systems

Default to "no_evidence" when:
- Explanation mentions "no direct evidence", "insufficient support", "could not find specific sources"
- Literature cited is about different compositions or conditions
- The contradiction requires assuming the general principle applies to this specific case

Respond ONLY with valid JSON:
{{
    "classification": "contradicted" or "no_evidence",
    "reasoning": "Brief explanation of why this classification was chosen",
    "confidence": 0.0 to 1.0
}}
"""


def classify_unverified_claim(claim: dict, explanation: str, evidence: list) -> dict:
    """Use LLM to classify an unverified claim."""

    prompt = CLASSIFICATION_PROMPT.format(
        claim_text=claim.get("claim_text", ""),
        claim_type=claim.get("claim_type", ""),
        explanation=explanation,
        evidence="\n".join(evidence) if evidence else "No evidence collected"
    )

    try:
        response = litellm.completion(
            model=CLASSIFICATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )

        content = response.choices[0].message.content
        if not content:
            return {
                "classification": "no_evidence",
                "reasoning": "Empty LLM response",
                "confidence": 0.0
            }

        # Try to extract JSON from the response
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if json_match:
            content = json_match.group(1).strip()

        # Find JSON object
        json_start = content.find('{')
        json_end = content.rfind('}')
        if json_start != -1 and json_end != -1:
            content = content[json_start:json_end + 1]

        result = json.loads(content)
        return {
            "classification": result.get("classification", "no_evidence"),
            "reasoning": result.get("reasoning", ""),
            "confidence": float(result.get("confidence", 0.5))
        }

    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        # Fallback: try to infer from keywords in the explanation
        explanation_lower = explanation.lower()
        if any(kw in explanation_lower for kw in ["mismatch", "conflict", "claimed", "actual"]):
            return {
                "classification": "contradicted",
                "reasoning": "Inferred from mismatch keywords in explanation",
                "confidence": 0.6
            }
        return {
            "classification": "no_evidence",
            "reasoning": "Inferred from lack of contradiction keywords",
            "confidence": 0.6
        }
    except Exception as e:
        print(f"  Error classifying claim: {e}")
        return {
            "classification": "no_evidence",
            "reasoning": f"Classification error: {str(e)}",
            "confidence": 0.0
        }


def run_classification(
    max_claims: int | None = None,
    use_checkpoints: bool = True,
    include_dataset: bool = True,
    include_external: bool = True
) -> dict:
    """
    Run classification on all unverified claims.

    Args:
        max_claims: Maximum number of claims to classify (for testing)
        use_checkpoints: Whether to use checkpoint caching
        include_dataset: Include dataset-referenced claims
        include_external: Include external-referenced claims

    Returns:
        Dictionary with classification results
    """
    print("=" * 60)
    print("CLASSIFYING UNVERIFIED CLAIMS")
    print("=" * 60)

    # Load results
    print("\nLoading fact check results...")
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        results = json.load(f)

    # Collect unverified claims
    unverified_claims = []

    if include_dataset:
        dataset_unverified = [
            r for r in results.get("dataset_verification_results", [])
            if not r.get("is_verified", False)
        ]
        for r in dataset_unverified:
            unverified_claims.append({
                "result": r,
                "source": "dataset"
            })
        print(f"  Dataset unverified: {len(dataset_unverified)}")

    if include_external:
        external_unverified = [
            r for r in results.get("external_verification_results", [])
            if not r.get("is_verified", False)
        ]
        for r in external_unverified:
            unverified_claims.append({
                "result": r,
                "source": "external"
            })
        print(f"  External unverified: {len(external_unverified)}")

    print(f"  Total unverified: {len(unverified_claims)}")

    if max_claims:
        unverified_claims = unverified_claims[:max_claims]
        print(f"  Limited to: {max_claims}")

    # Classify each claim
    classified_results = {
        "summary": {
            "total": len(unverified_claims),
            "contradicted": 0,
            "no_evidence": 0,
            "by_source": {
                "dataset": {"contradicted": 0, "no_evidence": 0},
                "external": {"contradicted": 0, "no_evidence": 0}
            }
        },
        "contradicted_claims": [],
        "no_evidence_claims": []
    }

    skipped = 0

    print("\nClassifying claims...")
    for i, item in enumerate(unverified_claims):
        result = item["result"]
        source = item["source"]
        claim = result.get("claim", {})
        claim_id = get_claim_id(claim)

        # Check checkpoint
        if use_checkpoints:
            checkpoint = load_checkpoint(claim_id)
            if checkpoint:
                classification = checkpoint["classification"]
                classified_claim = checkpoint
                skipped += 1

                # Add to results
                if classification == "contradicted":
                    classified_results["contradicted_claims"].append(classified_claim)
                    classified_results["summary"]["contradicted"] += 1
                    classified_results["summary"]["by_source"][source]["contradicted"] += 1
                else:
                    classified_results["no_evidence_claims"].append(classified_claim)
                    classified_results["summary"]["no_evidence"] += 1
                    classified_results["summary"]["by_source"][source]["no_evidence"] += 1

                if (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{len(unverified_claims)}] (from checkpoint)")
                continue

        print(f"  [{i+1}/{len(unverified_claims)}] Classifying: {claim.get('claim_text', '')[:60]}...")

        # Classify
        classification_result = classify_unverified_claim(
            claim=claim,
            explanation=result.get("explanation", ""),
            evidence=result.get("evidence", [])
        )

        # Build classified claim
        classified_claim = {
            "claim_text": claim.get("claim_text", ""),
            "claim_type": claim.get("claim_type", ""),
            "source_field": claim.get("source_field", ""),
            "sample_id": claim.get("sample_id", ""),
            "batch_number": claim.get("batch_number"),
            "provenance": claim.get("provenance", ""),
            "original_explanation": result.get("explanation", ""),
            "original_confidence": result.get("confidence", 0.0),
            "original_evidence": result.get("evidence", []),
            "classification": classification_result["classification"],
            "classification_reasoning": classification_result["reasoning"],
            "classification_confidence": classification_result["confidence"],
            "verification_source": source
        }

        # Save checkpoint
        if use_checkpoints:
            save_checkpoint(claim_id, classified_claim)

        # Add to results
        classification = classification_result["classification"]
        if classification == "contradicted":
            classified_results["contradicted_claims"].append(classified_claim)
            classified_results["summary"]["contradicted"] += 1
            classified_results["summary"]["by_source"][source]["contradicted"] += 1
        else:
            classified_results["no_evidence_claims"].append(classified_claim)
            classified_results["summary"]["no_evidence"] += 1
            classified_results["summary"]["by_source"][source]["no_evidence"] += 1

    if skipped > 0:
        print(f"  Loaded {skipped} from checkpoints")

    # Save results
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(classified_results, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to {OUTPUT_FILE}")

    # Print summary
    print("\n" + "=" * 60)
    print("CLASSIFICATION SUMMARY")
    print("=" * 60)

    summary = classified_results["summary"]
    print(f"\nTotal unverified claims classified: {summary['total']}")
    print(f"\nOverall breakdown:")
    print(f"  Contradicted: {summary['contradicted']} ({summary['contradicted']/summary['total']*100:.1f}%)")
    print(f"  No Evidence:  {summary['no_evidence']} ({summary['no_evidence']/summary['total']*100:.1f}%)")

    print(f"\nBy source:")
    for source in ["dataset", "external"]:
        source_stats = summary["by_source"][source]
        total = source_stats["contradicted"] + source_stats["no_evidence"]
        if total > 0:
            print(f"  {source.capitalize()}:")
            print(f"    Contradicted: {source_stats['contradicted']} ({source_stats['contradicted']/total*100:.1f}%)")
            print(f"    No Evidence:  {source_stats['no_evidence']} ({source_stats['no_evidence']/total*100:.1f}%)")

    # Show sample classified claims
    print("\n" + "-" * 60)
    print("SAMPLE CONTRADICTED CLAIMS")
    print("-" * 60)
    for i, claim in enumerate(classified_results["contradicted_claims"][:3]):
        print(f"\n[{i+1}] {claim['claim_text'][:100]}...")
        print(f"    Reasoning: {claim['classification_reasoning']}")

    print("\n" + "-" * 60)
    print("SAMPLE NO EVIDENCE CLAIMS")
    print("-" * 60)
    for i, claim in enumerate(classified_results["no_evidence_claims"][:3]):
        print(f"\n[{i+1}] {claim['claim_text'][:100]}...")
        print(f"    Reasoning: {claim['classification_reasoning']}")

    return classified_results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Classify unverified claims into contradicted vs no_evidence")
    parser.add_argument("--max-claims", type=int, default=None,
                       help="Maximum number of claims to classify (for testing)")
    parser.add_argument("--no-checkpoints", action="store_true",
                       help="Disable checkpoint caching")
    parser.add_argument("--dataset-only", action="store_true",
                       help="Only classify dataset-referenced claims")
    parser.add_argument("--external-only", action="store_true",
                       help="Only classify external-referenced claims")

    args = parser.parse_args()

    include_dataset = not args.external_only
    include_external = not args.dataset_only

    run_classification(
        max_claims=args.max_claims,
        use_checkpoints=not args.no_checkpoints,
        include_dataset=include_dataset,
        include_external=include_external
    )
