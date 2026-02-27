#!/usr/bin/env python3
"""Find abnormalities from tabulated high-spin data."""

import asyncio
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Iterable

from experiment_design import ExperimentDesignWorkflow
from monty.serialization import loadfn


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = PROJECT_ROOT / "data" / "dataset.json"


def remove_sample_id(data: Iterable[dict]) -> list[dict]:
    """Return a deep-copied list with `sample_id` removed from each record."""
    sanitized = deepcopy(list(data))
    for entry in sanitized:
        entry.pop("sample_id", None)
        entry.pop("batch_number", None)
        entry.pop("sample_index", None)
        entry.pop("provenance", None)
    return sanitized


def main() -> None:
    """Main function to run the abnormality finding workflow."""
    print(f"Loading data from {DATASET_PATH}")
    data = loadfn(str(DATASET_PATH))
    print(f"Loaded {len(data)} samples")

    processed_data = remove_sample_id(data)

    print("\nAnalyzing compositional clusters...")
    workflow = ExperimentDesignWorkflow(data=processed_data)
    compositions = list({sample["composition"] for sample in data})
    clusters = workflow._get_compositional_clusters(
        compositions,
        embedding_type="compositional",
        distance_threshold=5,
    )

    print(f"\nFound {len(clusters)} compositional clusters:")
    for i, cluster in enumerate(clusters, 1):
        print(f"  Cluster {i}: {len(cluster)} compositions")
        if len(cluster) <= 10:
            print(f"    {cluster}")
        else:
            print(f"    {cluster[:5]} ... ({len(cluster) - 5} more)")

    print("\nRunning experiment design workflow...")
    workflow_async = ExperimentDesignWorkflow(data=processed_data, model="openai/gpt-5")
    result = asyncio.run(workflow_async.run_experiment_design_workflow())

    output_file = (
        Path(__file__).parent
        / f"experiment_design_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    print(f"\nSaving results to {output_file}")
    with open(output_file, "w") as f:
        json.dump(
            list(x.model_dump() for x in result),
            f,
            indent=1,
        )
    print("Done!")


if __name__ == "__main__":
    main()
