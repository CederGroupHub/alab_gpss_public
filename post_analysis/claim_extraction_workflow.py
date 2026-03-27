"""
Claim extraction workflow.

This script:
1. Extracts text fields (hypothesis, justification, etc.) from the dataset
2. Uses an LLM to extract and classify claims into:
   - dataset_referenced
   - external_referenced
3. Writes a flat JSON list matching post_analysis/results/extracted_claims.json
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from monty.serialization import loadfn
from openai import OpenAI

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Paths
REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "data" / "dataset.json"
OUTPUT_DIR = Path(__file__).parent / "results"
OUTPUT_PATH = OUTPUT_DIR / "extracted_claims.json"
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints_claim_extraction"

# OpenAI model
MODEL = "gpt-5-mini"

# Initialize OpenAI client
client = OpenAI()


def save_checkpoint(item_id: str, data: dict) -> None:
    """Save extraction checkpoint for one sample."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_file = CHECKPOINT_DIR / f"{item_id}.json"
    with open(checkpoint_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_checkpoint(item_id: str) -> dict | None:
    """Load extraction checkpoint for one sample."""
    checkpoint_file = CHECKPOINT_DIR / f"{item_id}.json"
    if not checkpoint_file.exists():
        return None
    with open(checkpoint_file, "r", encoding="utf-8") as f:
        return json.load(f)


def clear_checkpoints() -> None:
    """Clear extraction checkpoints."""
    import shutil

    if CHECKPOINT_DIR.exists():
        shutil.rmtree(CHECKPOINT_DIR)
        print("Cleared extraction checkpoints")


@dataclass
class ExtractedClaim:
    """A single extracted claim from text."""

    claim_text: str
    claim_type: Literal["dataset_referenced", "external_referenced"]
    source_field: str
    batch_number: int | None
    provenance: str
    sample_index: str


def load_dataset() -> list[dict]:
    """Load dataset and attach sample_index."""
    all_data = loadfn(DATA_PATH)
    for i in range(len(all_data)):
        all_data[i]["sample_index"] = i
    return all_data


def extract_text_fields(data: list[dict]) -> list[dict]:
    """Extract text fields that may contain claims."""
    extracted: list[dict] = []

    for sample in data:
        sample_info = {
            "batch_number": sample.get("batch_number"),
            "provenance": sample.get("provenance", "unknown"),
            "texts": {},
            "sample_index": sample["sample_index"],
        }

        if "prev_exp" in sample:
            if "hypothesis" in sample["prev_exp"]:
                sample_info["texts"]["hypothesis"] = sample["prev_exp"]["hypothesis"]
            if "justification" in sample["prev_exp"]:
                sample_info["texts"]["justification"] = sample["prev_exp"]["justification"]

        if "abnormality_results" in sample:
            if "justification" in sample["abnormality_results"]:
                sample_info["texts"]["abnormality_justification"] = sample["abnormality_results"][
                    "justification"
                ]

        if "material_proposal" in sample:
            if "justification" in sample["material_proposal"]:
                sample_info["texts"]["material_proposal_justification"] = sample["material_proposal"][
                    "justification"
                ]

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
    provenance: str,
) -> list[ExtractedClaim]:
    """Use LLM to extract claims from one text field."""

    prompt = CLAIM_EXTRACTION_PROMPT.format(
        source_field=source_field,
        sample_index=sample_index,
        batch_number=batch_number,
        provenance=provenance,
        text=text,
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
        claims: list[ExtractedClaim] = []
        for c in result.get("claims", []):
            claims.append(
                ExtractedClaim(
                    claim_text=c["claim_text"],
                    claim_type=c["claim_type"],
                    source_field=source_field,
                    sample_index=sample_index,
                    batch_number=batch_number,
                    provenance=provenance,
                )
            )
        return claims
    except json.JSONDecodeError as e:
        print(f"JSON parse error for {sample_index}/{source_field}: {e}")
        return []
    except Exception as e:
        print(f"Error extracting claims for {sample_index}/{source_field}: {e}")
        return []


def extract_all_claims(extracted_texts: list[dict], use_checkpoints: bool = True) -> list[ExtractedClaim]:
    """Extract claims from all samples, optionally using checkpoints."""
    all_claims: list[ExtractedClaim] = []
    skipped = 0

    for i, sample in enumerate(extracted_texts):
        sample_index = sample["sample_index"]

        if use_checkpoints:
            checkpoint = load_checkpoint(str(sample_index))
            if checkpoint:
                for c in checkpoint.get("claims", []):
                    all_claims.append(ExtractedClaim(**c))
                skipped += 1
                print(f"  [{i + 1}/{len(extracted_texts)}] {str(sample_index)[:8]}... (loaded from checkpoint)")
                continue

        print(f"Processing sample {i + 1}/{len(extracted_texts)}: {sample_index}")

        sample_claims: list[ExtractedClaim] = []
        for field_name, text in sample["texts"].items():
            if text:
                claims = extract_claims_from_text(
                    text=text,
                    source_field=field_name,
                    sample_index=str(sample_index),
                    batch_number=sample["batch_number"],
                    provenance=sample["provenance"],
                )
                sample_claims.extend(claims)

        if use_checkpoints and sample_claims:
            save_checkpoint(
                str(sample_index),
                {
                    "sample_index": sample_index,
                    "claims": [asdict(c) for c in sample_claims],
                },
            )

        all_claims.extend(sample_claims)

    if skipped > 0:
        print(f"Loaded {skipped} samples from checkpoints")

    return all_claims


def run_claim_extraction(
    max_samples: int | None = None,
    resume: bool = True,
    clear_existing_checkpoints: bool = False,
) -> list[dict]:
    """Run claim extraction only and save flat JSON list output."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if clear_existing_checkpoints:
        clear_checkpoints()

    print("=" * 60)
    print("CLAIM EXTRACTION WORKFLOW (OpenAI GPT-5-mini)")
    print(f"Model: {MODEL}")
    if resume:
        print("Checkpoint mode enabled")
    print("=" * 60)

    print("\n[1/3] Loading dataset...")
    data = load_dataset()
    print(f"Loaded {len(data)} samples")

    print("\n[2/3] Extracting text fields...")
    extracted_texts = extract_text_fields(data)
    print(f"Found {len(extracted_texts)} samples with text fields")

    if max_samples:
        extracted_texts = extracted_texts[:max_samples]
        print(f"Limited to {max_samples} samples")

    print("\n[3/3] Extracting claims...")
    all_claims = extract_all_claims(extracted_texts, use_checkpoints=resume)

    output_data = [asdict(c) for c in all_claims]
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    dataset_count = sum(1 for c in all_claims if c.claim_type == "dataset_referenced")
    external_count = sum(1 for c in all_claims if c.claim_type == "external_referenced")

    print(f"\nSaved {len(output_data)} claims to {OUTPUT_PATH}")
    print("\nSummary:")
    print(f"  dataset_referenced: {dataset_count}")
    print(f"  external_referenced: {external_count}")

    return output_data


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run claim extraction workflow using OpenAI GPT-5-mini")
    parser.add_argument("--max-samples", type=int, default=None, help="Limit number of samples to process")
    parser.add_argument("--no-resume", action="store_true", help="Disable checkpoint reuse")
    parser.add_argument("--clear-checkpoints", action="store_true", help="Clear extraction checkpoints before starting")

    args = parser.parse_args()

    run_claim_extraction(
        max_samples=args.max_samples,
        resume=not args.no_resume,
        clear_existing_checkpoints=args.clear_checkpoints,
    )
