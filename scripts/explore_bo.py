#!/usr/bin/env python3
"""Script to generate new material proposals using Bayesian optimization suggestions."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from traceback import print_exc
from typing import Iterable

from agents import Agent, Runner
from agents.model_settings import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel
import litellm
from monty.serialization import loadfn

from experiment_design import (
    ExperimentDesignWorkflow,
    NewMaterialProposalResponse,
)
from run_bo import run_bayesian_optimization

DATA_PATH = Path(__file__).parent.parent / "data" / "dataset.json"
TIMEOUT = 3600

litellm.timeout = TIMEOUT
litellm.streaming_timeout = TIMEOUT
litellm.request_timeout = TIMEOUT


def remove_sample_id(data: Iterable[dict]) -> list[dict]:
    """Return a deep-copied list with sample_id stripped from each entry."""
    from copy import deepcopy

    sanitized = deepcopy(list(data))
    for entry in sanitized:
        entry.pop("sample_id", None)
    return sanitized


async def run_new_material_proposal_with_bo(
    data_path: Path | str = DATA_PATH,
    bo_num_candidates: int = 5000,
    bo_top_n: int = 40,
    bo_ucb_beta: float = 1.0,
    bo_complexity_penalty: float = 1.0,
    bo_seed: int | None = None,
    model: str = "gpt-5",
    distance_threshold: float = 5,
) -> NewMaterialProposalResponse:
    """Run new-material proposal workflow with Bayesian optimization suggestions."""
    print(f"Loading data from {data_path}...")
    data = loadfn(data_path)
    data = remove_sample_id(data)

    print(f"Running Bayesian optimization with {bo_num_candidates} candidates...")
    bo_results = run_bayesian_optimization(
        data_path=str(data_path),
        num_candidates=bo_num_candidates,
        k_diverse=bo_top_n,
        ucb_beta=bo_ucb_beta,
        complexity_penalty=bo_complexity_penalty,
        seed=bo_seed,
        verbose=True,
    )

    print(f"Extracting top {bo_top_n} compositions from BO results...")
    bo_results_sorted = bo_results.sort_values("ucb_score", ascending=False)
    top_bo_compositions = bo_results_sorted["composition"].tolist()

    print(f"\nTop {bo_top_n} BO compositions:")
    for i, comp in enumerate(top_bo_compositions[:10], 1):
        print(f"  {i}. {comp}")
    if len(top_bo_compositions) > 10:
        print(f"  ... and {len(top_bo_compositions) - 10} more")

    print("\nInitializing workflow...")
    workflow = ExperimentDesignWorkflow(data=data, model=model)

    print("Creating agent with BO prompt...")
    if os.getenv("OPENAI_BASE_URL") is not None and "cborg" in os.getenv(
        "OPENAI_BASE_URL"
    ):
        model_instance = LitellmModel(model=f"openai/{model}")
    else:
        model_instance = model

    bo_agent = Agent(
        name="New Material Proposing Agent (with BO)",
        instructions=workflow.get_new_material_proposal_with_bo_prompt(
            bo_compositions=top_bo_compositions
        ),
        model=model_instance,
        output_type=NewMaterialProposalResponse,
        model_settings=ModelSettings(
            reasoning={"effort": "high"},
        ),
    )

    print("Running material proposal workflow with BO suggestions...")
    all_material_proposals = []

    all_compositions = list(
        set([row.get("composition") for row in data if row.get("composition")])
    )

    composition_clusters = workflow._get_compositional_clusters(
        all_compositions,
        distance_threshold=distance_threshold,
        embedding_type="compositional",
    )

    for cluster_idx, cluster in enumerate(composition_clusters, 1):
        print(f"\nProcessing cluster {cluster_idx}/{len(composition_clusters)}...")
        cluster_data = workflow._filter_by_compositions(set(cluster))

        if len(cluster_data) > 0:
            prompt_input = f"""Experimental Data:
{workflow._serialize_data_to_json(cluster_data)}
"""

            for i in range(5):
                try:
                    result = await Runner.run(bo_agent, prompt_input)
                    break
                except litellm.RateLimitError:
                    print("Rate limit error encountered, sleeping for 90 seconds.")
                    print_exc()
                    time.sleep(90)
            else:
                raise Exception(
                    "Failed to run new material proposal agent with BO after 5 attempts."
                )

            if result.final_output and result.final_output.material_proposals:
                all_material_proposals.extend(result.final_output.material_proposals)
                print(
                    f"  Generated {len(result.final_output.material_proposals)} proposals"
                )

    combined_proposal_response = NewMaterialProposalResponse(
        material_proposals=all_material_proposals
    )

    print(f"\nTotal proposals generated: {len(combined_proposal_response.material_proposals)}")
    return combined_proposal_response


async def main() -> None:
    """Main entry point."""
    result = await run_new_material_proposal_with_bo()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(__file__).parent / f"bo_new_material_proposal_{timestamp}.json"
    with output_path.open("w") as fh:
        json.dump(result.model_dump(), fh, indent=2)
    print(f"\nSaved result to {output_path}")

    return result


if __name__ == "__main__":
    result = asyncio.run(main())
