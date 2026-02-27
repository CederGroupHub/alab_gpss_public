from pymatgen.core import Composition
import numpy as np
from matminer.featurizers.composition import ElementProperty
from matminer.featurizers.base import MultipleFeaturizer
import json
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import Normalizer
from sklearn.decomposition import PCA
import torch
from botorch.models import SingleTaskGP
from botorch.fit import fit_gpytorch_mll_torch
from gpytorch.mlls import ExactMarginalLogLikelihood
from gpytorch.kernels import MaternKernel
import random
from pymatgen.core.periodic_table import get_el_sp
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "dataset.json"

element_featurizer = ElementProperty.from_preset("matscholar_el")
multiple_featurizer = MultipleFeaturizer(
    [
        element_featurizer,
    ]
)


def featurize(*args) -> np.ndarray:
    composition, *_ = args
    elem_feat = multiple_featurizer.featurize(Composition(composition))
    return np.array(elem_feat)


def featurize_many(comps: list[str]) -> np.ndarray:
    comps = [Composition(comp) for comp in comps]
    return multiple_featurizer.featurize_many(comps)


def rbf_kernel(X, lengthscale=1.0):
    X = np.asarray(X, dtype=float)
    dists = np.sum(X**2, axis=1)[:, None] + np.sum(X**2, axis=1)[None, :] - 2 * np.dot(X, X.T)
    return np.exp(-0.5 * dists / (lengthscale ** 2))


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
    """
    Greedy MAP inference for a *weighted* k-DPP.

    - Build similarity K from X (RBF kernel).
    - Convert acquisition scores into quality weights w.
    - Construct L = diag(w) K diag(w) (PSD).
    - Greedily pick items maximizing marginal gain in det(L_S).
    """
    rng = np.random.default_rng(random_state)

    X = np.asarray(X, dtype=float)
    scores = np.asarray(scores, dtype=float).reshape(-1)
    assert X.shape[0] == scores.shape[0], "X and scores must have same N"
    N = X.shape[0]
    if k <= 0:
        return np.array([], dtype=int)
    if k >= N:
        return np.arange(N, dtype=int)

    # Optional speed: restrict to top-M by score first
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

    # Turn scores into positive weights w.
    s = (scores_sub - np.max(scores_sub)) * float(score_temperature)
    w = np.exp(s) + 1e-12  # avoid exact zeros

    # Similarity kernel and L-ensemble
    K = rbf_kernel(X_sub, lengthscale=lengthscale)
    L = (w[:, None] * K) * w[None, :]
    L = L + np.eye(n) * float(jitter)

    # Greedy k-DPP MAP:
    d = np.diag(L).copy()  # (n,)
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
            residual = L[j, :] - (C[:t, j] @ C[:t, :])  # (n,)

        C[t, :] = residual / dj_sqrt
        d = d - C[t, :] ** 2
        d[j] = -np.inf  # prevent reselection

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
    allowed_stoich=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
    elem_range=(4, 6),
    num_samples=10000,
    li_content_range=(1.2, 2.0),
    metal_content_range=(0.9, 1.2),
    max_trials=20000000,
    seed=None,
):
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

        Li_content = 4.0 - sum(
            get_el_sp(s).oxi_state * v for s, v in zip(sps, stoichiometry)
        )

        if not li_content_range[0] <= Li_content <= li_content_range[1]:
            continue
        
        composition_dict = {}
        composition_dict["Li+"] = Li_content
        composition_dict.update({s: v for s, v in zip(sps, stoichiometry)})
        composition_dict["Cl-"] = 4.0
        compositions.add(Composition(composition_dict))

    return list(comp for comp in compositions)


def run_bayesian_optimization(
    data_path: str | Path = DEFAULT_DATASET_PATH,
    num_candidates=10000,
    k_diverse=40,
    ucb_beta=1.5,
    phase_purity_weight=5.0,
    complexity_penalty=1.2,
    seed=42,
    verbose=True,
) -> pd.DataFrame:
    """
    Run Bayesian Optimization for material discovery.

    Parameters:
    -----------
    data_path : str
        Path to the training data JSON file
    num_candidates : int
        Number of candidate compositions to generate and evaluate
    k_diverse : int
        Number of diverse compositions to select
    ucb_beta : float
        Beta parameter for UCB acquisition function (exploration-exploitation tradeoff)
    phase_purity_weight : float
        Weight for phase purity in the objective function
    complexity_penalty : float
        Penalty factor for number of elements in composition
    seed : int, optional
        Random seed for reproducibility
    verbose : bool
        Whether to print progress information

    Returns:
    --------
    pd.DataFrame
        DataFrame with columns: composition, mean, std, ucb_score
    """
    with Path(data_path).open() as f:
        results = json.load(f)

    # Filter results to keep only the entry with highest ionic conductivity for each composition
    filtered_results = {}
    for entry in results:
        comp = entry["composition"]
        y = entry.get("ionic_conductivity_room_temperature (S/cm)", None)
        if y is not None:
            if (
                comp not in filtered_results
                or filtered_results[comp].get(
                    "ionic_conductivity_room_temperature (S/cm)", float("-inf")
                )
                < y
            ):
                filtered_results[comp] = entry
        else:
            if comp not in filtered_results:
                filtered_results[comp] = entry

    results = list(filtered_results.values())

    # Prepare training data
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

    # Featurize training data
    train_X = featurize_many(compositions)

    # Construct and fit data pipeline
    data_pipeline = Pipeline([("pca", PCA(n_components=0.9)), ("scaler", Normalizer())])
    train_X = data_pipeline.fit_transform(train_X)
    train_X = torch.tensor(train_X)

    train_Y = torch.stack([torch.log10(ionic_conductivity), phase_purity * 1], dim=1)
    train_Y = torch.tensor(train_Y, dtype=torch.float64)

    # Fit GP model
    if verbose:
        print("Fitting GP model...")
    gp = SingleTaskGP(train_X, train_Y, covar_module=MaternKernel(nu=2.5))
    mll = ExactMarginalLogLikelihood(gp.likelihood, gp)
    fit_result = fit_gpytorch_mll_torch(mll)
    if verbose:
        print(f"GP fitting completed: {fit_result}")

    # Generate candidate compositions
    if verbose:
        print(f"Generating {num_candidates} candidate compositions...")
    all_compositions = generate_random_compositions_discrete(
        num_samples=num_candidates, seed=seed
    )

    # Featurize and predict
    num_of_elems = torch.tensor(
        [len(Composition(comp).elements) for comp in all_compositions]
    )
    test_X = featurize_many(all_compositions)
    test_X = data_pipeline.transform(test_X)
    test_X = torch.tensor(test_X).unsqueeze(1)

    with torch.no_grad():
        prediction_dist = gp.posterior(test_X)
        mean_test, sigma_test = prediction_dist.mean, torch.sqrt(prediction_dist.variance)
        mean_test = mean_test.reshape(-1, 2)
        sigma_test = sigma_test.reshape(-1, 2)
        predicted_conductivity = mean_test[:, 0].reshape(-1)
        predicted_conductivity_uncertainty = sigma_test[:, 0].reshape(-1)
        predicted_phase_purity = mean_test[:, 1].reshape(-1).clamp(0, 1)
        predicted_phase_purity = predicted_phase_purity * (predicted_phase_purity > 0.9)
        predicted_phase_purity_uncertainty = sigma_test[:, 1].reshape(-1)

    prediction_score = predicted_conductivity + predicted_phase_purity * phase_purity_weight
    prediction_score_uncertainty = torch.sqrt(predicted_conductivity_uncertainty**2 + predicted_phase_purity_uncertainty**2 * phase_purity_weight**2)
    # Compute UCB scores
    ucb_scores = (
        prediction_score
        + ucb_beta * prediction_score_uncertainty
        - complexity_penalty * num_of_elems
    )

    # Create results DataFrame
    results_df = pd.DataFrame(
        {
            "composition": [
                comp.remove_charges().to_pretty_string() for comp in all_compositions
            ],
            "predicted_conductivity": predicted_conductivity,
            "predicted_conductivity_uncertainty": predicted_conductivity_uncertainty,
            "predicted_phase_purity": predicted_phase_purity,
            "predicted_phase_purity_uncertainty": predicted_phase_purity_uncertainty,
            "predicted_score": prediction_score,
            "predicted_score_uncertainty": prediction_score_uncertainty,
            "ucb_score": ucb_scores.numpy(),
        }
    )

    # Compute the features and scores to use for selection
    features_np = np.array(test_X.squeeze().numpy())
    ucb_scores_np = np.array(ucb_scores.numpy())

    # Run greedy weighted k-DPP selection
    kdpp_indices = greedy_weighted_kdpp(
        X=features_np,
        scores=ucb_scores_np,
        k=k_diverse,
        lengthscale=1.0,
        score_temperature=1.0,
        jitter=1e-10,
        max_candidates=None,
        random_state=seed,
    )

    # Get the selected diverse compositions and scores
    kdpp_diverse_df = results_df.iloc[kdpp_indices].copy()

    # Optionally, display the diverse set
    kdpp_diverse_df.reset_index(drop=True, inplace=True)
    print(f"\nTop {k_diverse} diverse compositions selected by weighted k-DPP:")
    print(kdpp_diverse_df.head(k_diverse))

    return kdpp_diverse_df


if __name__ == "__main__":
    results_df = run_bayesian_optimization(data_path=DEFAULT_DATASET_PATH)
