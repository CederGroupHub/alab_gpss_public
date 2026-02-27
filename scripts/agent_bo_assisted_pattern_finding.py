#!/usr/bin/env python3
"""Script to generate new material proposals using Bayesian optimization suggestions."""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from datetime import datetime
from pathlib import Path
from traceback import print_exc
from typing import Iterable

import litellm
import numpy as np
import pandas as pd
import torch
from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
from agents.model_settings import ModelSettings
from botorch.fit import fit_gpytorch_mll_torch
from botorch.models import SingleTaskGP
from gpytorch.kernels import MaternKernel
from gpytorch.mlls import ExactMarginalLogLikelihood
from matminer.featurizers.base import MultipleFeaturizer
from matminer.featurizers.composition import ElementProperty
from monty.serialization import loadfn
from pymatgen.core import Composition
from pymatgen.core.periodic_table import get_el_sp
from sklearn.decomposition import PCA
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import Normalizer

from agent_prompts import (
    ExperimentDesignWorkflow,
    NewMaterialProposalResponse,
)

DATA_PATH = Path(__file__).parent.parent / "data" / "dataset.json"
TIMEOUT = 3600

litellm.timeout = TIMEOUT
litellm.streaming_timeout = TIMEOUT
litellm.request_timeout = TIMEOUT


def remove_sample_id(data: Iterable[dict]) -> list[dict]:
    """Return a deep-copied list with sample_id, batch_number, sample_index, and provenance stripped from each entry."""
    from copy import deepcopy

    sanitized = deepcopy(list(data))
    for entry in sanitized:
        entry.pop("sample_id", None)
        entry.pop("batch_number", None)
        entry.pop("sample_index", None)
        entry.pop("provenance", None)
    return sanitized


element_featurizer = ElementProperty.from_preset("matscholar_el")
multiple_featurizer = MultipleFeaturizer([element_featurizer])


def featurize_many(comps: list[str]) -> np.ndarray:
    composition_list = [Composition(comp) for comp in comps]
    return multiple_featurizer.featurize_many(composition_list)


def rbf_kernel(X: np.ndarray, lengthscale: float = 1.0) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    dists = np.sum(X**2, axis=1)[:, None] + np.sum(X**2, axis=1)[None, :] - 2 * np.dot(
        X, X.T
    )
    return np.exp(-0.5 * dists / (lengthscale**2))


def greedy_weighted_kdpp(
    X: np.ndarray,
    scores: np.ndarray,
    k: int,
    lengthscale: float = 1.0,
    score_temperature: float = 1.0,
    jitter: float = 1e-10,
    max_candidates: int | None = None,
    random_state: int | None = None,
) -> np.ndarray:
    """Greedy MAP inference for a weighted k-DPP."""
    rng = np.random.default_rng(random_state)

    X = np.asarray(X, dtype=float)
    scores = np.asarray(scores, dtype=float).reshape(-1)
    assert X.shape[0] == scores.shape[0], "X and scores must have same N"
    N = X.shape[0]
    if k <= 0:
        return np.array([], dtype=int)
    if k >= N:
        return np.arange(N, dtype=int)

    if max_candidates is not None and max_candidates < N:
        top = np.argpartition(scores, -max_candidates)[-max_candidates:]
        top = top[np.argsort(scores[top])[::-1]]
        X_sub = X[top]
        scores_sub = scores[top]
        orig_index = top
    else:
        X_sub = X
        scores_sub = scores
        orig_index = np.arange(N, dtype=int)

    n = X_sub.shape[0]
    k_eff = min(k, n)

    s = (scores_sub - np.max(scores_sub)) * float(score_temperature)
    w = np.exp(s) + 1e-12

    K = rbf_kernel(X_sub, lengthscale=lengthscale)
    L = (w[:, None] * K) * w[None, :]
    L = L + np.eye(n) * float(jitter)

    d = np.diag(L).copy()
    C = np.zeros((k_eff, n), dtype=float)
    selected = []

    tie_noise = (rng.standard_normal(n) * 1e-14) if random_state is not None else 0.0

    for t in range(k_eff):
        j = int(np.argmax(d + tie_noise))
        if d[j] <= 1e-18:
            break
        selected.append(j)
        if t == k_eff - 1:
            break

        dj_sqrt = np.sqrt(d[j])
        if t == 0:
            residual = L[j, :]
        else:
            residual = L[j, :] - (C[:t, j] @ C[:t, :])

        C[t, :] = residual / dj_sqrt
        d = d - C[t, :] ** 2
        d[j] = -np.inf

    selected = np.array(selected, dtype=int)
    return orig_index[selected]


available_species = [
    "Mg2+",
    "V3+",
    "Cr2+",
    "Cr3+",
    "Mn2+",
    "Fe2+",
    "Co2+",
    "Ni2+",
    "Cu+",
    "Cu2+",
    "Zn2+",
    "Y3+",
    "Zr4+",
    "Nb5+",
    "Hf4+",
    "Ta5+",
    "In3+",
    "Sn2+",
    "Bi3+",
]


def generate_random_compositions_discrete(
    allowed_stoich: tuple[float, ...] = (
        0.1,
        0.2,
        0.3,
        0.4,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        1.0,
    ),
    elem_range: tuple[int, int] = (4, 6),
    num_samples: int = 5000,
    li_content_range: tuple[float, float] = (1.2, 2.0),
    metal_content_range: tuple[float, float] = (0.9, 1.2),
    max_trials: int = 20000000,
    seed: int | None = None,
) -> list[Composition]:
    if seed is not None:
        random.seed(seed)

    compositions = set()
    trials = 0
    N = random.randint(elem_range[0], elem_range[1])

    while len(compositions) < num_samples and trials < max_trials:
        trials += 1

        sps = random.sample(available_species, N)
        stoichiometry = random.choices(allowed_stoich, k=N)

        if not metal_content_range[0] <= sum(stoichiometry) <= metal_content_range[1]:
            continue

        li_content = 4.0 - sum(
            get_el_sp(s).oxi_state * v for s, v in zip(sps, stoichiometry)
        )
        if not li_content_range[0] <= li_content <= li_content_range[1]:
            continue

        composition_dict = {
            "Li+": li_content,
            **{s: v for s, v in zip(sps, stoichiometry)},
            "Cl-": 4.0,
        }
        compositions.add(Composition(composition_dict))

    return list(compositions)


def run_bayesian_optimization(
    data_path: str | Path = DATA_PATH,
    num_candidates: int = 5000,
    k_diverse: int = 40,
    ucb_beta: float = 1.5,
    phase_purity_weight: float = 5.0,
    complexity_penalty: float = 1.2,
    seed: int = 42,
    verbose: bool = True,
) -> pd.DataFrame:
    """Run Bayesian optimization and return diverse high-UCB candidates."""
    with Path(data_path).open() as f:
        results = json.load(f)

    filtered_results = {}
    for entry in results:
        comp = entry["composition"]
        y = entry.get("ionic_conductivity_room_temperature (S/cm)")
        if y is not None:
            if (
                comp not in filtered_results
                or filtered_results[comp].get(
                    "ionic_conductivity_room_temperature (S/cm)", float("-inf")
                )
                < y
            ):
                filtered_results[comp] = entry
        elif comp not in filtered_results:
            filtered_results[comp] = entry

    results = list(filtered_results.values())
    compositions = [Composition(entry["composition"]) for entry in results]
    ionic_conductivity = torch.tensor(
        [entry["ionic_conductivity_room_temperature (S/cm)"] for entry in results]
    )
    phase_purity = torch.tensor(
        [
            entry["xrd_analysis_result"]["weight_fractions_of_each_phases"].get(
                "spinel (Fd-3m)", 0
            )
            for entry in results
        ]
    )

    train_X = featurize_many(compositions)
    data_pipeline = Pipeline([("pca", PCA(n_components=0.9)), ("scaler", Normalizer())])
    train_X = torch.tensor(data_pipeline.fit_transform(train_X))
    train_Y = torch.stack([torch.log10(ionic_conductivity), phase_purity], dim=1)
    train_Y = torch.tensor(train_Y, dtype=torch.float64)

    if verbose:
        print("Fitting GP model...")
    gp = SingleTaskGP(train_X, train_Y, covar_module=MaternKernel(nu=2.5))
    mll = ExactMarginalLogLikelihood(gp.likelihood, gp)
    fit_result = fit_gpytorch_mll_torch(mll)
    if verbose:
        print(f"GP fitting completed: {fit_result}")
        print(f"Generating {num_candidates} candidate compositions...")

    all_compositions = generate_random_compositions_discrete(
        num_samples=num_candidates, seed=seed
    )
    num_of_elems = torch.tensor([len(Composition(comp).elements) for comp in all_compositions])
    test_X = torch.tensor(data_pipeline.transform(featurize_many(all_compositions))).unsqueeze(1)

    with torch.no_grad():
        prediction_dist = gp.posterior(test_X)
        mean_test = prediction_dist.mean.reshape(-1, 2)
        sigma_test = torch.sqrt(prediction_dist.variance).reshape(-1, 2)
        predicted_conductivity = mean_test[:, 0].reshape(-1)
        predicted_conductivity_uncertainty = sigma_test[:, 0].reshape(-1)
        predicted_phase_purity = mean_test[:, 1].reshape(-1).clamp(0, 1)
        predicted_phase_purity = predicted_phase_purity * (predicted_phase_purity > 0.9)
        predicted_phase_purity_uncertainty = sigma_test[:, 1].reshape(-1)

    prediction_score = predicted_conductivity + predicted_phase_purity * phase_purity_weight
    prediction_score_uncertainty = torch.sqrt(
        predicted_conductivity_uncertainty**2
        + predicted_phase_purity_uncertainty**2 * phase_purity_weight**2
    )
    ucb_scores = prediction_score + ucb_beta * prediction_score_uncertainty - complexity_penalty * num_of_elems

    results_df = pd.DataFrame(
        {
            "composition": [comp.remove_charges().to_pretty_string() for comp in all_compositions],
            "predicted_conductivity": predicted_conductivity,
            "predicted_conductivity_uncertainty": predicted_conductivity_uncertainty,
            "predicted_phase_purity": predicted_phase_purity,
            "predicted_phase_purity_uncertainty": predicted_phase_purity_uncertainty,
            "predicted_score": prediction_score,
            "predicted_score_uncertainty": prediction_score_uncertainty,
            "ucb_score": ucb_scores.numpy(),
        }
    )

    kdpp_indices = greedy_weighted_kdpp(
        X=np.array(test_X.squeeze().numpy()),
        scores=np.array(ucb_scores.numpy()),
        k=k_diverse,
        lengthscale=1.0,
        score_temperature=1.0,
        jitter=1e-10,
        max_candidates=None,
        random_state=seed,
    )
    kdpp_diverse_df = results_df.iloc[kdpp_indices].copy()
    kdpp_diverse_df.reset_index(drop=True, inplace=True)
    print(f"\nTop {k_diverse} diverse compositions selected by weighted k-DPP:")
    print(kdpp_diverse_df.head(k_diverse))
    return kdpp_diverse_df


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
