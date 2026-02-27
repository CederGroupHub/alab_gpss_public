#!/usr/bin/env python3
"""Standalone script converted from explore.ipynb."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from monty.serialization import loadfn

from agent_prompts import ExperimentDesignWorkflow

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = PROJECT_ROOT / "data" / "dataset.json"


def remove_sample_id(data: Iterable[dict]) -> list[dict]:
    """Return a deep-copied list with sample_id stripped from each entry."""
    from copy import deepcopy

    sanitized = deepcopy(list(data))
    for entry in sanitized:
        entry.pop("sample_id", None)
        entry.pop("batch_number", None)
        entry.pop("sample_index", None)
        entry.pop("provenance", None)
    return sanitized


async def main() -> None:
    data = loadfn(DATASET_PATH)
    workflow = ExperimentDesignWorkflow(data=remove_sample_id(data))
    result = await workflow.run_new_material_proposal_workflow()

    return result


if __name__ == "__main__":
    result = asyncio.run(main())

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(__file__).parent / f"new_material_proposal_result_{timestamp}.json"
    with output_path.open("w") as fh:
        json.dump(result.model_dump(), fh, indent=1)
    print(f"Saved result to {output_path}")
