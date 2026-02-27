from __future__ import annotations

import json
from typing import Literal
import os
import asyncio

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.neighbors import kneighbors_graph
from pymatgen.core import Composition
from pydantic import BaseModel, Field
from agents import Agent, Runner
from agents.model_settings import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel
import litellm
import dotenv
import random
import time
from traceback import print_exc
from agents import WebSearchTool
dotenv.load_dotenv()

TIMEOUT = 3600
# Configure litellm timeouts
litellm.timeout = TIMEOUT
litellm.streaming_timeout = TIMEOUT
litellm.request_timeout = TIMEOUT


def _fit_agglom(X, threshold, linkage="ward", metric="euclidean", connectivity=None):
    """
    Fits AgglomerativeClustering with only distance_threshold set.
    Returns labels (0..k-1) for X.
    """
    # Note: n_clusters must be None when distance_threshold is used.
    model = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=threshold,
        linkage=linkage,
        metric=metric,
        connectivity=connectivity,
        compute_full_tree=True,
    )
    return model.fit_predict(X)


def _refine_cluster(
    X,
    idxs,
    threshold,
    max_size,
    min_threshold,
    shrink_factor,
    linkage,
    metric,
    connectivity_builder,
):
    """
    Recursively splits the subset X[idxs] by decreasing threshold until all parts <= max_size
    or min_threshold is hit. Returns a list of arrays of indices (relative to original X).
    """
    if len(idxs) <= max_size:
        return [idxs]

    Xsub = X[idxs]

    # Optional local connectivity for this subset (keeps merges local)
    connectivity = None
    if connectivity_builder is not None:
        connectivity = connectivity_builder(Xsub)

    labels = _fit_agglom(
        Xsub,
        threshold=threshold,
        linkage=linkage,
        metric=metric,
        connectivity=connectivity,
    )

    # If clustering didn’t split (still one cluster), tighten threshold
    if labels.max() == 0:
        if threshold <= min_threshold:
            # Can't split further by threshold alone; return as is
            return [idxs]
        return _refine_cluster(
            X,
            idxs,
            threshold * shrink_factor,
            max_size,
            min_threshold,
            shrink_factor,
            linkage,
            metric,
            connectivity_builder,
        )

    # Recurse on each child cluster
    out = []
    for lab in range(labels.max() + 1):
        child = idxs[labels == lab]
        if len(child) <= max_size:
            out.append(child)
        else:
            # Tighten threshold for this child
            t = max(threshold * shrink_factor, min_threshold)
            out.extend(
                _refine_cluster(
                    X,
                    child,
                    t,
                    max_size,
                    min_threshold,
                    shrink_factor,
                    linkage,
                    metric,
                    connectivity_builder,
                )
            )
    return out


def hierarchical_with_maxsize(
    X,
    base_distance_threshold,
    max_size,
    linkage="ward",
    metric="euclidean",
    min_distance_threshold=None,
    shrink_factor=0.9,
    use_local_connectivity=True,
    n_neighbors=10,
):
    """
    Top-level routine:
      1) Run agglomerative at base_distance_threshold
      2) Any cluster > max_size is recursively re-clustered with smaller threshold
      3) Stops when all clusters <= max_size or min_distance_threshold reached

    Returns: labels (np.ndarray of shape (n_samples,))
    """
    X = np.asarray(X)
    n = X.shape[0]

    # Build a callable to make a local connectivity graph per subset (optional)
    connectivity_builder = None
    if use_local_connectivity:

        def connectivity_builder(Xsub):
            # mutual kNN graph tends to reduce chaining; you can switch to mode='distance' if desired
            return kneighbors_graph(
                Xsub,
                n_neighbors=min(n_neighbors, len(Xsub) - 1),
                mode="connectivity",
                include_self=False,
            )

    # Set a minimum threshold to avoid infinite shrinking
    if min_distance_threshold is None:
        # Heuristic: allow ~1e-3 of base to avoid getting stuck
        min_distance_threshold = max(1e-6, base_distance_threshold * 1e-3)

    # First pass
    global_labels = _fit_agglom(
        X,
        threshold=base_distance_threshold,
        linkage=linkage,
        metric=metric,
        connectivity=connectivity_builder(X) if connectivity_builder else None,
    )

    # Refine each initial cluster if oversized
    final_blocks = []
    for lab in range(global_labels.max() + 1):
        idxs = np.flatnonzero(global_labels == lab)
        if len(idxs) <= max_size:
            final_blocks.append(idxs)
        else:
            final_blocks.extend(
                _refine_cluster(
                    X,
                    idxs,
                    base_distance_threshold,
                    max_size,
                    min_distance_threshold,
                    shrink_factor,
                    linkage,
                    metric,
                    connectivity_builder,
                )
            )

    # Assemble final labels
    labels = np.empty(n, dtype=int)
    for new_lab, idxs in enumerate(final_blocks):
        labels[idxs] = new_lab
    return labels


class MaterialDataAbnormalityResult(BaseModel):
    composition: str
    justification: str
    related_compositions: list[str]


class MaterialDataAbnormalityResponse(BaseModel):
    abnormality_results: list[MaterialDataAbnormalityResult]


class NewExperiment(BaseModel):
    target_composition: str
    max_heating_temperature: float | None
    justification: str
    hypothesis: str


ExperimentDesignResponse = NewExperiment


class ExperimentDesignResults(BaseModel):
    experiments: list[list[NewExperiment]]


class ExperimentReflectionResponse(BaseModel):
    reflection: str


class DesignPattern(BaseModel):
    pattern: str = Field(description="A detailed description of the design pattern, explaining what it is and how it works")
    evidence_from_reflections: str = Field(description="Summary of the reflections that support this pattern, showing how it is grounded in the data")


class DesignPatternResponse(BaseModel):
    design_patterns: list[DesignPattern]


class NewMaterialProposal(BaseModel):
    composition: str
    justification: str


class NewMaterialProposalResponse(BaseModel):
    material_proposals: list[NewMaterialProposal]


class ExperimentDesignWorkflow:
    """Workflow for designing experiments based on material science data."""

    def __init__(
        self,
        data: list[dict],
        model="gpt-5",
    ):
        """
        Initialize the abnormality detection agent.

        Args:
            data: The data to use for the abnormality detection
            temperature: Model temperature setting (default: 0.5)
        """
        self.data = data
        self.model = model
        self._init_agents()

    def _serialize_data_to_json(
        self, data_subset: list[dict] | None = None
    ) -> str:
        """
        Serialize the provided dataset (or subset) to a JSON string in records format.
        Supports either a pandas DataFrame or a list of dicts.
        """
        dataset = data_subset if data_subset is not None else self.data
        return json.dumps(dataset)

    def _filter_by_compositions(self, compositions: set[str]) -> list[dict]:
        """
        Subset the stored data to only entries whose 'composition' value is in the provided set.
        """
        return [row for row in self.data if row.get("composition") in compositions]

    def _compositions_to_array(
        self,
        compositions: list[str] | list[Composition],
        embedding_type: Literal[
            "matscholar_el", "magpie", "compositional"
        ] = "compositional",
    ) -> np.ndarray:
        """
        Convert a list of compositions/formulas to an array of their fractional
        elemental components.
        """
        if embedding_type != "compositional":
            from matminer.featurizers.composition import ElementProperty

            featurizer = ElementProperty.from_preset(embedding_type)
            pymatgen_comps = [
                Composition(c) if not isinstance(c, Composition) else c
                for c in compositions
            ]
            arr = featurizer.featurize_many(pymatgen_comps, ignore_errors=True)
            return np.array(arr)
        else:
            comps = [Composition(c).fractional_composition for c in compositions]
            elems = sorted({e for comp in comps for e in comp.elements})
            arr = np.zeros((len(compositions), len(elems)))
            for idx, comp in enumerate(comps):
                vec = [comp[el] for el in elems]
                arr[idx] = vec
            return arr

    def _get_compositional_clusters(
        self,
        compositions: list[str],
        embedding_type: Literal[
            "matscholar_el", "magpie", "compositional"
        ] = "compositional",
        distance_threshold: float = 5,
        max_cluster_size: int = 80,
    ) -> list[list[str]]:
        """
        Get similar clusters of compositions based on their compositional similarity.
        Uses hierarchical agglomerative clustering with a cap on maximum cluster size.
        """
        if len(compositions) == 0:
            return []
        if len(compositions) == 1:
            return [[compositions[0]]]

        X = self._compositions_to_array(compositions, embedding_type)
        labels = hierarchical_with_maxsize(
            X,
            base_distance_threshold=distance_threshold,
            max_size=max_cluster_size,
            linkage="ward",
            metric="euclidean",
            min_distance_threshold=None,
            shrink_factor=0.9,
            use_local_connectivity=True,
            n_neighbors=10,
        )
        clusters: list[list[str]] = [[] for _ in range(int(labels.max()) + 1)]
        for c, comp in zip(labels, compositions):
            clusters[int(c)].append(comp)

        # Optionally: return the tuple (clusters, closest_samples) or use in downstream processing
        return clusters

    def _init_agents(self) -> None:
        if os.getenv("OPENAI_BASE_URL") is not None and "cborg" in os.getenv(
            "OPENAI_BASE_URL"
        ):
            model = LitellmModel(model=f"openai/{self.model}")
        else:
            model = self.model
        self.abnormality_detection_agent = Agent(
            name="Material Data Abnormality Detection Agent",
            instructions=self.get_abnormal_detection_prompt(),
            model=model,
            output_type=MaterialDataAbnormalityResponse,
            model_settings=ModelSettings(
                reasoning={"effort": "high"},
            ),
        )
        self.experiment_design_agent = Agent(
            name="Experiment Design Agent",
            instructions=self.get_experiment_design_prompt(),
            model=model,
            output_type=ExperimentDesignResponse,
            model_settings=ModelSettings(
                reasoning={"effort": "high"},
            ),
            # tools=[WebSearchTool()]
        )
        self.reflection_abnormality_agent = Agent(
            name="Experiment Reflection Agent (Abnormality)",
            instructions=self.get_reflection_prompt_abnormality(),
            model=model,
            output_type=ExperimentReflectionResponse,
            model_settings=ModelSettings(
                reasoning={"effort": "medium"},
            ),
        )
        self.reflection_exploration_agent = Agent(
            name="Experiment Reflection Agent (Exploration)",
            instructions=self.get_reflection_prompt_exploration(),
            model=model,
            output_type=ExperimentReflectionResponse,
            model_settings=ModelSettings(
                reasoning={"effort": "medium"},
            ),
        )
        self.new_material_proposal_agent = Agent(
            name="New Material Proposing Agent",
            instructions=self.get_new_material_proposal_prompt(),
            model=model,
            output_type=NewMaterialProposalResponse,
            model_settings=ModelSettings(
                reasoning={"effort": "high"},
            ),
            # tools=[WebSearchTool()]
        )
        self.design_pattern_summarization_agent = Agent(
            name="Design Pattern Summarization Agent",
            instructions=self.get_design_pattern_summarization_prompt(),
            model=model,
            output_type=DesignPatternResponse,
            # model_settings=ModelSettings(
            #     reasoning={"effort": "medium"},
            # ),
        )

    def _hullciation_composition_prompt(self) -> str:
        return """HALLUCINATION CONTROL — STRICT RULES

Do NOT invent data that is not present in the dataset.

Do NOT infer phase purity, stoichiometry, oxidation states, structural distortion, or coordination environments unless explicitly supported by the provided XRD data or by standard, widely accepted crystallographic principles.

Do NOT speculate on reaction pathways or mechanisms unless the dataset provides direct evidence.

Every statement must be grounded in either:
    explicit values or fields from the dataset, OR
    general, widely accepted crystallographic/materials-science knowledge (never system-specific speculation).

If a conclusion is not fully supported, state uncertainties explicitly (e.g., “X may suggest Y, but the evidence is insufficient for confirmation”).
"""

    def _inverse_spinel_structure_prompt(self) -> str:
        """
        Get the system prompt for the inverse spinel structure.
        """
        return """The inverse spinel chloride usually can be described as "Li2-y M1±x Cl4". Here the metal site M is typically a divalent ion (M²⁺), but can be partially substituted by higher-valence metals (M³⁺, M⁴⁺, M⁵⁺). The parameter x indicates the excess metal content and y is determined by charge neutrality—higher-valence M or increased M content introduces Li vacancies.
- Structurally, these compounds adopt a cubic close-packed chloride anion sublattice in space group Fd-3m, with cations occupying both the tetrahedral (8a) and octahedral (16d) interstices. Depending on site occupancy, cation distributions can vary from a “normal” spinel arrangement (50% Li⁺ largely on tetrahedral sites, 50% Li⁺ and all Mⁿ⁺ arranged fully disordered on octahedral) to a cation-ordered variant where Li and M show selective ordering on octahedral sites—these ordering transitions may lower symmetry (e.g., to Imma, Cmmm, C12/m1 or other lower-symmetry spacegroups).
- The combined effects of Li/M site disorder and controlled vacancy formation create a three-dimensional network of Li coordination polyhedra (edge- and face-sharing tetrahedra/octahedra) that reduce Li⁺ migration barriers, enabling optimized room-temperature ionic conductivities.
- Since both stoichiometry (x/y) and cation-site ordering can be tuned, the Li2-y M1±x Cl4 framework offers a highly versatile structural platform for engineering high-performance halide solid electrolytes or catholytes for all-solid-state Li-ion batteries."""

    def _alab_prompt(self) -> str:
        """
        Get the system prompt for the alab.
        """
        return """The data you are working on comes from experiments executed in a laboratory that implements a solid-state synthesis workflow. The whole experiment is enclosed in a pure-N2-filled glovebox with O2 < 0.1ppm and H2O < 10ppm. The workflow consists of three main steps:

1. **Precursor Dispensing and Mixing**: Precursor materials are automatically dispensed in the required stoichiometric ratios and thoroughly mixed to ensure homogeneity. The tolerance is ±0.5%.

2. **Heating (Solid-State Reaction)**: The mixed precursors are heated to a specified maximum temperature to facilitate the solid-state reaction and phase formation. The sample stays in a Ni crucible during the heating process. The heating process includes:
   - Ramping to the target temperature at a rate of 2 °C/min.
   - Holding at the maximum temperature for 12 hours for reaction to occur
   - Naturally cooling to room temperature.

3. **Characterization**: After synthesis, the samples are characterized using:
   - **XRD (powder X-ray Diffraction)**: To analyze phase composition and crystal structure. The sample is covered with a thin kapton film (hold by vacuum grease) and taken out of the glovebox for XRD measurement.
   - **Ionic Conductivity Measurement**: To determine the ionic conductivity of the material. The sample is pressed into a thin pellet and PEIS is measured with pressure of 600MPa at 25 °C in the same glovebox (no air exposure)."""

    def _data_format_prompt(self) -> str:
        """
        Get the system prompt for the data format.
        """
        return """The data is in JSON format (an array of objects), with each object representing a sample. Keys include:
- "composition": string, the formula string as recorded
- "synthesis_temperature": number (°C), the maximum heating temperature used for solid-state synthesis.
- "xrd_analysis_result": object containing
  - "weight_fractions_of_each_phases": object mapping phase composition and spacegroup of each phase -> weight fraction (0-1). **Important:** XRD identifies **crystal structures**, not exact chemical compositions. The reported phases are the **closest matched structural references**, and **do not imply exact stoichiometry**. If it says "spinel" as the phase, it means it can be matched to the spinel structure but the actual composition may be different.
  - "rwp": string percent, e.g., "7.33%", indicating the fitness of the Rietveld refinement analysis. The lower the Rwp, the better the refinement/fitness of the phase.
  - "missing_peaks": list of objects, each containing "two_theta" (°) and "relative_intensity" (0-1), indicating the peaks that cannot be indexed in the XRD pattern. These peaks can suggest **additional unidentified phases** which is not included in the weight_fractions_of_each_phases.
  - "extra_peaks": list of objects, each containing "two_theta" (°) and "relative_intensity" (0-1), indicating the peaks that are in the calcualted XRD pattern but not in the observed XRD pattern. These peaks indicate **differences between the reference structure model and the actual sample**, such as non-stoichiometry, disorder, or subtle structural distortions.
- "ionic_conductivity_room_temperature(S/cm)": number, ionic conductivity at room temperature in S/cm.
"""

    def get_abnormal_detection_prompt(self) -> str:
        """
        Get the system prompt for abnormality detection.

        Returns:
            The system prompt string for the abnormality detection agent.
        """
        return (
            """You are an expert material scientist specializing in solid-state ionic conductors for lithium batteries, particularly lithium halide systems. Your expertise includes:

1. Understanding crystal structures, phase relationships, and defect chemistry in halide materials
2. Analyzing ionic conductivity trends based on composition, ionic radius, electronegativity, synthesis conditions, and etc.
3. Identifying expected vs. unexpected behavior in experimental data (both extraordinary high/low ionic conductivity)

You are looking at the experiment results for trials to discover new super-ionic conductors in the inverse spinel chloride structure. """
            + self._inverse_spinel_structure_prompt()
            + "\n"
            + self._hullciation_composition_prompt()
            + "\n"
            + self._alab_prompt()
            + "\n"
            + """
WORKFLOW (LLM MUST FOLLOW EXACTLY):
1) Understand Context
   - Summarize the intended inverse spinel chloride framework and the experimental setup.
   - Identify key data columns and what they represent.
2) Group for Fair Comparison
   - Compare each sample against compositionally similar samples (by chemistry and stoichiometry) to establish expected phase and conductivity ranges.
3) Detect Abnormalities (prioritize unusually high σ when present)
   - Flag cases where ionic conductivity is abnormally high/low relative to peers, with slightly greater emphasis on detecting unusually high values.
4) Validation Checklist (ensure all true before output)
   - Evidence-based comparison: cite specific related compositions in the dataset used for contrast.
   - Emphasize unusually high conductivity where applicable, but do not omit scientifically meaningful low-conductivity anomalies.
   - Focus on inverse spinel-type outcomes as project priority.
   - Include a concise list of related compositions that support your reasoning.

"""
            + self._data_format_prompt()
            + """

You MUST output your analysis in JSON format with the following structure:
{
    "abnormality_results": [
        {
            "composition": "the exact string of the composition from the datasheet, don't change anything",
            "justification": "why you think it is abnormal. You should compare it with other samples to reason and integrate your knowledge in material science to reason. Put your step-by-step reasoning process in the justification, from the data and basic material science knowledge.",
            "related_compositions": ["list of composition strings from the dataset that are similar or related to this abnormal sample, using the exact strings as they appear in the data"]
        }
    ]
}

Important: 
- Focus on the study of inverse spinel type structures. Sometimes the target composition can nuclate in other structures, which are not the top priority of this project.
- Only include samples that are genuinely abnormal based on material science principles
- When prioritizing abnormalities, give preference to cases with unexpectedly high ionic conductivity (while still reporting compelling low-conductivity anomalies when you think it is scientifically meaningful)
- For each abnormal sample, provide a detailed justification for why it's abnormal based on comparison with related compositions
- Use the exact composition string as it appears in the data (don't modify it)
- For "related_compositions", include compositions from the dataset that are relevant for understanding the abnormality (e.g., similar chemical structure, similar ionic radius, similar electronegativity, or compositions used for comparison in the justification). The related compositions does not have to be similar to the abnormal composition but MUST be relevant for understanding the abnormality.
- Output ONLY valid JSON, no additional text or markdown formatting outside the JSON structure"""
        )

    def get_experiment_design_prompt(self) -> str:
        """
        Get the system prompt for experiment design.

        Returns:
            The system prompt string for the experiment design agent.
        """
        return (
            """You are an expert material scientist specializing in solid-state ionic conductors for lithium batteries, particularly lithium halide systems. You are working on a project to discover new super-ionic conductors in the inverse spinel chloride structure. """
            + self._inverse_spinel_structure_prompt()
            + "\n"
            + self._hullciation_composition_prompt()
            + "\n"
            + """

EXPERIMENTAL SETUP AND PROCEDURE:
"""
            + self._alab_prompt()
            + """

RESEARCH GOAL:
The primary objective is to find new strategies to improve the ionic conductivity of the inverse spinel material family. The secondary objective is to find new compositions that can lead to a high-conductivity material.

WORKFLOW (LLM MUST FOLLOW EXACTLY):
1) Generate Hypothesis
   - For the given abnormality, formulate a clear, testable scientific hypothesis grounded in materials science to explain why the abnormality could occur.
   - For the hypothesis, you MUST ground all your claims on the data and ONLY BASIC material science knowledge. Considering your audience may not have a deep background in material science, you should provide how your hypothesis is made step by step from the raw data and basic material science knowledge. Put your step-by-step reasoning process in the justification.
   - Some hints to help you generate the hypothesis: composition/element properties, synthesis temperature/time, defect chemistry (vacancies/interstitials), phase stability/metastability, microstructure and grain boundaries, and potential measurement artifacts.
   - The hypothesis should be mechanistic and testable, providing clear guidance on what to change/measure next.
2) Select Minimal Experiments
   - Propose the one clear experiments that can decisively test the hypothesis or extend the most promising trend toward higher σ(Room Temperature).
    2.1) Choose Target Compositions
    - Pick compositions that operationalize the hypothesis (e.g., control vs. variable to isolate the mechanism), and leverage patterns observed in prior data.
    2.2) Set Synthesis Temperatures
    - Choose temperatures sufficient for reaction completion and phase formation while avoiding precursor loss; allow None if uncertain for new compositions.
3) Validation Checklist (ensure all true before output)
   - Hypothesis is mechanistic and testable (what to change/measure next).
   - Hypothesis is testable with the available data and equipment in the lab. For example, some dedicated structure effect cannot be tested with current lab using XRD. NO ADDITIONAL DATA OR EQUIPMENT IS AVAILABLE.
   - Hypothesis is grounded on the data and basic material science knowledge. The reasoining process is logical and clear.
   - Minimal, orthogonal experiments with clear decision rules.
   - Justification ties directly to the hypothesis and known patterns (composition → phase → conductivity).
   - Inverse spinel-type phases prioritized; temperatures are realistic.
   - No redundancies; each experiment advances information gain.

When designing experiments, you should consider the following:

1. **Target Compositions**: Design compositions that:
   - Test the proposed hypotheses (e.g., compositions that might exploit mechanisms suggested in hypotheses)
   - Explore variations around abnormal compositions that showed promising properties
   - Consider ionic radius effects, electronegativity relationships, and stoichiometry variations
   - Target compositions that could benefit from the mechanisms identified in hypotheses to increase phase purity and/or ionic conductivity
   - Explore compositions in regions where high conductivity is theoretically expected

2. **Max Heating Temperature**: Select appropriate synthesis temperatures that:
   - Are sufficient to drive solid-state reactions to completion (especially if you see unreacted precursors in the XRD analysis result)
   - Consider phase stability at different temperatures
   - May influence defect chemistry or phase formation (as suggested by hypotheses)
   - Typically range from 300°C to 700°C for lithium halide systems, but should be tailored based on composition and hypotheses. If you are not sure about the temperature (especially for the new compositions), you can leave the max temperature as None and let the lab to decide.

3. **Experimental Strategy**: Consider only what is strictly necessary to decisively test the hypotheses:
   - Propose the one experiment that can decisively confirm or falsify the hypotheses.
   - Avoid redundant or overlapping variations; prefer orthogonal tests that reduce ambiguity
   - If one experiment suffices, propose only one
   - Clearly state the decision rule and how results map to next actions

You MUST output your experiment designs in JSON format with the following structure:
{
    "target_composition": "the target composition as a chemical formula, e.g., 'Li2FeCl4' - be specific with stoichiometry. The composition MUST be in the format of [element1][stoichiometry1][element2][stoichiometry2]...[elementN][stoichiometryN] (no other characters or spaces).",
    "max_heating_temperature": "temperature in degrees Celsius as a float, e.g., 450.0. If you are not sure about the temperature (especially for the new compositions), you can leave the max temperature as None and let the lab to decide.",
    "justification": "the justification for the choice of target composition and max heating temperature. Put your step-by-step reasoning process in the justification, from the data and basic material science knowledge.",
    "hypothesis": "a clear, testable scientific hypothesis explaining why the abnormality could occur, grounded in material science principles. This hypothesis should be mechanistic and testable, providing clear guidance on what to change/measure next.",
}

In addition, you will also see the historical data of the experiments that may be related to this abnormality (from where the contrast is observed). This can give you some context and help you design new experiments. Keep in mind when designing new experiments, you should not design experiments that have been conducted already unless the hypothesis thinks the abnormality is due to the experimental error and a re-try can test the hypothesis.

For each experiment, you must provide:
- A clear, testable hypothesis that explains the abnormality (this is your primary task - to generate the hypothesis)
- The experiment design that tests this hypothesis
- Ground the hypothesis in established material science principles

"""
            + self._data_format_prompt()
            + """

Important:
- **You must generate a hypothesis for each abnormality**: The hypothesis should be a clear, testable scientific explanation for why the abnormality could occur, supported by the experiment data and basic material science knowledge. The reasoning process to reach your hypothesis should be logical and clear.
- Propose the minimal set of experiments that decisively test the hypothesis
- The hypothesis must be testable with current lab setup.
- Each experiment should have clear scientific rationale based on the hypotheses
- Consider both direct tests of hypotheses and exploratory experiments in promising regions
- Provide specific compositions (not ranges) - use exact stoichiometric formulas
- Temperature should be a specific float value (e.g., 650.0, not "650")
- Consider the synthesis temperature constraints and phase stability when selecting temperatures
- Each hypothesis should be scientifically rigorous and testable, providing clear instructions on how to test the hypothesis in the lab."""
        )

    def get_reflection_prompt_abnormality(self) -> str:
        """
        Get the system prompt for experiment reflection for abnormality-driven cases.
        """
        return (
            """You are an expert material scientist specializing in solid-state ionic conductors for lithium batteries, particularly lithium halide systems. You are working on a project to discover new super-ionic conductors in the inverse spinel chloride structure. """
            + self._inverse_spinel_structure_prompt()
            + "\n\n"
            + self._hullciation_composition_prompt()
            + "\n\n"
            + """

EXPERIMENTAL SETUP AND PROCEDURE:
"""
            + self._alab_prompt()
            + """

YOUR TASK:
You will be provided with:
1. An original abnormality detection result (why a composition was thought to be abnormal)
2. The experiment that was designed to test the hypothesis (which includes the hypothesis that was generated)
3. The actual experimental outcome (the data from the new experiment)
4. Historical data for related compositions (including the original abnormal composition) that were used for comparison in the original abnormality detection

Your task is to analyze the experiment outcome and provide a summary of (1) what is the hypothesis to explain the abnormality (from the experiment) and (2) whether or not the hypothesis is supported by the experiment outcome. The summary should be clear, concise, and suitable for attaching to the experiment data for future reference.

"""
            + self._data_format_prompt()
            + """

You MUST output your reflection in JSON format with the following structure and format:
{
    "reflection": "This sample is made in order to test the hypothesis of <summary_of_abnormality_hypothesis>. The hypothesis is <hypothesis_supported> by the experiment outcome as <experiment_outcome_summary>."
}

Important:
- Be objective and scientific in your evaluation
- Base your summaries on the actual experimental data provided
- Use the exact composition strings as they appear in the data
- Output ONLY valid JSON, no additional text or markdown formatting outside the JSON structure"""
        )

    def get_reflection_prompt_exploration(self) -> str:
        """
        Get the system prompt for experiment reflection for exploration/proposal-driven cases.
        """
        return (
            """You are an expert material scientist specializing in solid-state ionic conductors for lithium batteries, particularly lithium halide systems. You are working on a project to discover new super-ionic conductors in the inverse spinel chloride structure. """
            + self._inverse_spinel_structure_prompt()
            + """

EXPERIMENTAL SETUP AND PROCEDURE:
"""
            + self._alab_prompt()
            + """

YOUR TASK:
You will be provided with:
1. A new material proposal (composition and scientific hypothesis for proposing it)
2. The actual experimental outcome (the data from the new experiment)

Your task is to analyze the experiment outcome and summerize the hypothesis and whether or not the hypothesis is supported by the experiment outcome. The summary should be clear, concise, and suitable for attaching to the experiment data for future reference.

"""
            + self._data_format_prompt()
            + """

You MUST output your reflection in JSON format with the following structure:
{
    "reflection": "This sample is made in order to test the hypothesis of <summary_of_new_material_proposal_justification>. The hypothesis is <hypothesis_supported> by the experiment outcome as <experiment_outcome_summary>."
}

Important:
- Be objective and scientific in your evaluation
- Base your summaries on the actual experimental data provided
- Use the exact composition strings as they appear in the data
- Output ONLY valid JSON, no additional text or markdown formatting outside the JSON structure"""
        )

    def get_new_material_proposal_prompt(self) -> str:
        """
        Get the system prompt for new material proposal.

        Returns:
            The system prompt string for the new material proposing agent.
        """
        return (
            """You are an expert material scientist specializing in solid-state ionic conductors for lithium batteries, particularly lithium halide systems. You are working on a project to discover new super-ionic conductors in the inverse spinel chloride structure. """
            + self._inverse_spinel_structure_prompt()
            + "\n"
            + self._hullciation_composition_prompt()
            + "\n"
            + """

EXPERIMENTAL SETUP AND PROCEDURE:
"""
            + self._alab_prompt()
            + """

RESEARCH GOAL:
The primary objective is to find new strategies to improve the ionic conductivity of the inverse spinel material family. The secondary objective is to find new compositions that can lead to a high-conductivity material.

WORKFLOW (LLM MUST FOLLOW EXACTLY):
1. **Learn from the data**: You will be provided with a dataset of experiments on the inverse spinel material family. You should carefully analyze the data to identify the patterns in the relationship between composition, phase formation, and ionic conductivity. 

2. **Design new experiments**: You should design new experiments that can help you validate the pattern that you have learned from the data.
    - Exploration of new compositions and new stoichiometry strategies: You should design experiments for the new compositions and new stoichiometry strategies that have not yet been explored in the dataset. You think the new compositions and new stoichiometry strategies are LIKELY to lead to a HIGH-CONDUCTIVITY material but you are UNSURE about it (60% chance of success).

    - **IMPORTANT COMPOSITION REQUIREMENTS**:
        - You should not propose compositions that are similar to existing ones. You must explore new compositions with learned patterns. By saying "similar", we mean the compositions that have the similar compositions. Also, avoid trivial changes. For example, if you have seen adding one element/some elements to a composition will likely lead to a high-conductivity material, you should not propose the composition with the similar doping strategies. !!EXPLORE SOMETHING NEW COMPOSITIONS/STRATEGIES that you are not so sure about!!
        - When proposing new compositions, you MUST ONLY select metals with given valences from the following list:
        [Mg2+, V3+, Cr2+, Cr3+, Mn2+, Fe2+, Co2+, Ni2+, Cu+, Cu2+, Zn2+, Y3+, Zr4+, Nb5+, Hf4+, Ta5+, In3+, Sn2+, Bi3+]
        - The proposed composition should be charge balanced.

3. **Make a justification for the proposed experiments**: You should make a justification for the proposed experiments. The justification should be clear and concise. It should show your step-by-step reasoning process. Be clear and concise. It should include the following information:
    - The patterns you learned from the data
    - How the proposed composition follows those patterns and can lead to a high-conductivity material
    - Why you are not sure about your prediction

4. **Validation Checklist (ensure all true before output)**
   - Avoid exact duplicates and trivial near-duplicates; prioritize novelty as defined above (new element combinations and/or substantial stoichiometry shifts that change defect chemistry)
   - When coming up with the design rules, you should not apply the well-established design rules that have been well-supported by the data. Try something that you can find some evidence in the data while you cannot draw the conclusion in full confidence (60% chance of success).
   - Metals are selected only from the allowed valence list and overall charge is balanced: [Mg2+, V3+, Cr2+, Cr3+, Mn2+, Fe2+, Co2+, Ni2+, Cu+, Cu2+, Zn2+, Y3+, Zr4+, Nb5+, Hf4+, Ta5+, In3+, Sn2+, Bi3+]
   - Mechanistic rationale ties element properties to phase formation and Li⁺ transport (not just correlation)
   - The justification is logical and clear, and is grounded on the data and basic material science knowledge. The justification MUST show your step-by-step reasoning process.

GUIDELINES FOR PROPOSING COMPOSITIONS:

1. **Pattern-Based Composition Proposal**: 
   - **Explore something new**: You should propose compositions that are novel and different from the existing compositions. You should not propose compositions that are similar to existing ones or use some design rules that have been well-proven by the data.

2. **Proposal Strategy**: 
   - Propose a set of compositions (typically 1-4) that leverage the patterns you've learned
   - Each composition should have a distinct difference from the existing compositions as well as the other proposed compositions. Try to apply different design rules to each composition you propose to make it unique and novel.
   - Clearly explain how each proposal is based on learned patterns from the data
   - Provide scientific rationale that connects the proposed composition to patterns in the existing data

You MUST output your material proposals in JSON format with the following structure:
{
    "material_proposals": [
        {
            "composition": "the target composition as a chemical formula, e.g., 'Li2FeCl4' - be specific with stoichiometry",
            "justification": "the scientific rationale for proposing this composition. Explicitly describe: (1) the patterns you learned, (2) how this composition follows those patterns and can lead to a high-conductivity material, and (3) why you are not 100% sure about your prediction. You MUST ground any of your claims on the data and basic material science knowledge. The justfication MUST show your step-by-step reasoning process. Be clear and concise.
        }
    ]
}

"""
            + self._data_format_prompt()
            + """

**VERY IMPORTANT**: 
- You MUST ONLY propose compositions using the elements and valences from the allowed list: [Mg2+, V3+, Cr2+, Cr3+, Mn2+, Fe2+, Co2+, Ni2+, Cu+, Cu2+, Zn2+, Y3+, Zr4+, Nb5+, Hf4+, Ta5+, In3+, Sn2+, Bi3+]. Even if some elements can lead to high ionic conductivity, you MUST NOT propose compositions with elements that are not in this list.

Important:
- **Focus on pattern learning**: Your primary goal is to discover new design strategies to improve the ionic conductivity of the inverse spinel material family.
- Propose new compositions and new stoichiometry strategies that are novel and different from the existing compositions and stoichiometry strategies.
- Propose diverse compositions and stoichiometry strategies to test different design rules and composition space.
- Provide specific compositions (not ranges) - use exact stoichiometric formulas
- In your justification, explicitly describe the patterns you learned and how the proposed composition follows those patterns, and note how charge neutrality is satisfied. You MUST ground any of your claims on the data and basic material science knowledge and reason step-by-step.
- If uncertainty exists, you should mention it in the justification.
- Output ONLY valid JSON, no additional text or markdown formatting outside the JSON structure"""
        )

    def get_new_material_proposal_with_bo_prompt(self, bo_compositions: list[str]) -> str:
        """
        Get the system prompt for new material proposal with Bayesian optimization suggestions.
        Similar to get_new_material_proposal_prompt, but also accepts a list of compositions
        proposed by Bayesian optimization that the agent can choose from.

        Args:
            bo_compositions: Optional list of compositions proposed by Bayesian optimization.
                            If provided, the agent should evaluate and select the most promising ones.

        Returns:
            The system prompt string for the new material proposing agent with BO suggestions.
        """
        bo_compositions_str = "\n".join([f"  - {comp}" for comp in bo_compositions])
        
        return (
            """You are an expert material scientist specializing in solid-state ionic conductors for lithium batteries, particularly lithium halide systems. You are working on a project to discover new super-ionic conductors in the inverse spinel chloride structure. """
            + self._inverse_spinel_structure_prompt()
            + "\n"
            + self._hullciation_composition_prompt()
            + "\n"
            + """

EXPERIMENTAL SETUP AND PROCEDURE:
"""
            + self._alab_prompt()
            + """

RESEARCH GOAL:
Your goal is to find new ways to improve the ionic conductivity of the inverse spinel material family.

WORKFLOW:
1. **Design new experiments**: You have been provided with a list of promising compositions suggested by Bayesian optimization trained on the experimental data:

"""
            + bo_compositions_str
            + """

You can:
- **Select** compositions from the Bayesian optimization list that you find most promising and scientifically sound; or
- **Modify** compositions from the list if you see potential but want to adjust stoichiometry or element combinations. **MODIFY THE COMPOSITION ONLY IF YOU THINK IT IS REALLY NEEDED**. If you make any modifications, make sure the composition is charge balanced.

Your final proposals MUST be selected/modified compositions from the Bayesian optimization suggestions.

2. **Make a justification for the proposed experiments**: You should make a justification for the proposed experiments. The justification should be clear and concise. It should show your step-by-step reasoning process. Be clear and concise. It should include the following information:
    - The patterns you learned from the data
    - Why you selected/modified certain compositions from the Bayesian optimization suggestions
    - If you are not 100% sure about your prediction, explain why

GUIDELINES FOR PROPOSING COMPOSITIONS:
   - Select/modify a set of compositions (typically 1-4) that leverage the patterns you've learned. The compositions should be selected from the Bayesian optimization suggestions which considered both feasibility and novelty.
   - Clearly explain how each proposal is based on patterns you have learned from the data
   - When coming up with the design rules, you should not apply the well-established design rules that have been well-supported by the data. Try something that you can find some evidence in the data while you cannot draw the conclusion in full confidence (60% chance of success).
   - Metals are selected only from the allowed valence list and overall charge is balanced: [Mg2+, V3+, Cr2+, Cr3+, Mn2+, Fe2+, Co2+, Ni2+, Cu+, Cu2+, Zn2+, Y3+, Zr4+, Nb5+, Hf4+, Ta5+, In3+, Sn2+, Bi3+]
   - The justification is logical and clear, and is grounded on the data and basic material science knowledge. The justification MUST show your step-by-step reasoning process.


You MUST output your material proposals in JSON format with the following structure:
{
    "material_proposals": [
        {
            "composition": "the target composition as a chemical formula, e.g., 'Li2FeCl4' - be specific with stoichiometry",
            "justification": "the scientific rationale for proposing this composition. Explicitly describe: (1) the patterns you learned, (2) how this composition follows those patterns and can lead to a high-conductivity material, and explain your selection/modification reasoning. You MUST ground any of your claims on the data and basic material science knowledge. The justfication MUST show your step-by-step reasoning process. Be clear and concise.
        }
    ]
}

"""
            + self._data_format_prompt()
        )

    async def run_abnormal_detection_workflow(
        self,
    ) -> MaterialDataAbnormalityResponse:
        """
        Run the abnormality detection workflow on the provided data.

        Returns:
            MaterialDataAbnormalityResponse containing the abnormality results.
        """
        for i in range(5):
            try:
                result = await Runner.run(
                    self.abnormality_detection_agent, self._serialize_data_to_json()
                )
                break
            except litellm.RateLimitError:
                print("Rate limit error encountered, sleeping for 90 seconds.")
                print_exc()
                time.sleep(90)
        else:
            raise Exception(
                "Failed to run abnormality detection agent after 5 attempts."
            )
        return result.final_output

    async def _run_experiment_design_only(
        self,
        abnormality_results: MaterialDataAbnormalityResponse,
    ) -> ExperimentDesignResults:
        """
        Design new experiments based on abnormalities. Generates hypotheses and experiments.
        Processes each abnormality one by one to generate hypotheses and experiments.

        Args:
            abnormality_results: The abnormality results from the detection workflow.

        Returns:
            experiments: List of lists of NewExperiment, each list is a set of experiments for a single abnormality.
        """
        all_experiments = []

        # Process each abnormality one by one
        for abnormality in abnormality_results.abnormality_results:
            # Collect all related compositions for this abnormality (including the abnormal composition itself)
            related_compositions_set = {abnormality.composition}
            if abnormality.related_compositions:
                related_compositions_set.update(abnormality.related_compositions)

            # Filter dataset to only include rows matching related compositions
            filtered_subset = self._filter_by_compositions(related_compositions_set)

            # Prepare input for experiment design agent: single abnormality (without hypothesis) + filtered historical data
            prompt_input = f"""The historical data of related compositions (the first one is the abnormal composition itself):
{self._serialize_data_to_json(filtered_subset)}

Abnormality for Material Data
Composition: {abnormality.composition}
Justification: {abnormality.justification}
"""

            # Generate experiments for this single abnormality
            for i in range(5):
                try:
                    result = await Runner.run(
                        self.experiment_design_agent, prompt_input
                    )
                    break
                except litellm.RateLimitError:
                    print("Rate limit error encountered, sleeping for 90 seconds.")
                    print_exc()
                    time.sleep(90)
            else:
                raise Exception(
                    "Failed to run experiment design agent after 5 attempts."
                )
            # Collect experiments from the response
            if result.final_output:
                all_experiments.append([result.final_output])
            else:
                all_experiments.append([])

        # Return all experiments aggregated together
        return ExperimentDesignResults(experiments=all_experiments)

    async def _run_experiment_design_workflow_on_subset(
        self,
        data_subset: list[dict],
    ) -> tuple[MaterialDataAbnormalityResponse, ExperimentDesignResults]:
        """
        Run the experiment design workflow on a subset of data.

        Args:
            data_subset: The subset of data to process.

        Returns:
            A tuple containing:
            - MaterialDataAbnormalityResponse: Detected abnormalities
            - experiments: List of lists of NewExperiment, each list is a set of experiments for a single abnormality.
        """
        # Create a temporary workflow instance with the subset data
        temp_workflow = self.__class__(data_subset)

        # Step 1: Detect abnormalities and generate hypotheses
        abnormality_results = await temp_workflow.run_abnormal_detection_workflow()

        # Step 2: Design experiments based on abnormalities and their hypotheses
        experiment_results = await temp_workflow._run_experiment_design_only(
            abnormality_results
        )

        return abnormality_results, ExperimentDesignResults(
            experiments=experiment_results.experiments
        )

    async def run_experiment_design_workflow(
        self,
        distance_threshold: float = 5,
    ) -> tuple[MaterialDataAbnormalityResponse, ExperimentDesignResults]:
        """
        Run the complete experiment design workflow by clustering data by compositions,
        then executing the workflow on each cluster with more than 1 data point.

        Args:
            distance_threshold: Distance threshold for compositional clustering (default: 0.1)

        Returns:
            A tuple containing:
            - MaterialDataAbnormalityResponse: Combined detected abnormalities from all clusters
            - experiments: List of lists of NewExperiment, each list is a set of experiments for a single abnormality.
        """
        # Step 1: Extract all unique compositions from the data
        all_compositions = list(
            set([row.get("composition") for row in self.data if row.get("composition")])
        )

        # Step 2: Cluster compositions by similarity
        composition_clusters = self._get_compositional_clusters(
            all_compositions,
            distance_threshold=distance_threshold,
            embedding_type="compositional",
        )

        # Step 3: Filter clusters to only those with more than 1 composition
        multi_composition_clusters = [
            cluster for cluster in composition_clusters if len(cluster) > 1
        ]

        # Step 4: Run workflow on each cluster in parallel
        all_abnormality_results = []
        all_experiment_results = []

        # Create tasks for all clusters
        tasks = []
        for cluster in multi_composition_clusters:
            # Filter data to only include samples with compositions in this cluster
            cluster_data = self._filter_by_compositions(set(cluster))

            if len(cluster_data) > 1:
                # Create task for running the workflow on this cluster
                tasks.append(
                    self._run_experiment_design_workflow_on_subset(cluster_data)
                )

        # Run all tasks in parallel
        if tasks:
            results = await asyncio.gather(*tasks)

            # Collect results from all parallel executions
            for abnormality_results, experiment_results in results:
                all_abnormality_results.extend(abnormality_results.abnormality_results)
                all_experiment_results.extend(experiment_results.experiments)

        # Step 5: Combine all results
        combined_abnormality_response = MaterialDataAbnormalityResponse(
            abnormality_results=all_abnormality_results
        )
        combined_experiment_response = ExperimentDesignResults(
            experiments=all_experiment_results
        )

        return combined_abnormality_response, combined_experiment_response

    async def run_reflection_workflow(
        self,
        material_hypothesis: MaterialDataAbnormalityResult | NewMaterialProposal,
        experiment_outcome: dict | list[dict],
        experiment: NewExperiment = None,
    ) -> ExperimentReflectionResponse:
        """
        Run the reflection workflow to evaluate how experiment outcomes support or contradict hypotheses.
        Supports reflection for both original abnormalities and new material proposals.

        Args:
            material_hypothesis: Either the original abnormality result or
                a new material proposal that motivated the experiment.
            experiment: The experiment that was designed to test the hypothesis/proposal (contains the hypothesis).
            experiment_outcome: The actual experimental outcome data (can be a single dict or list of dicts).

        Returns:
            ExperimentReflectionResponse containing the reflection analysis.
        """
        # Ensure experiment_outcome is a list for consistent handling
        if isinstance(experiment_outcome, dict):
            experiment_outcome_list = [experiment_outcome]
        else:
            experiment_outcome_list = experiment_outcome

        # Build prompt based on input type
        if isinstance(material_hypothesis, MaterialDataAbnormalityResult):
            if experiment is None:
                raise ValueError(
                    "Experiment is required for abnormality-driven reflection."
                )
            # Get experiment outcome data for related compositions
            related_compositions_set = set()
            if material_hypothesis.related_compositions:
                related_compositions_set.update(
                    material_hypothesis.related_compositions
                )
            # Also include the original abnormal composition
            related_compositions_set.add(material_hypothesis.composition)

            related_compositions_data = self._filter_by_compositions(
                related_compositions_set
            )

            # Prepare input for reflection agent (abnormality-driven)
            prompt_input = f"""Original Abnormality Detection Result:
Composition: {material_hypothesis.composition}
Justification: {material_hypothesis.justification}
Related Compositions: {", ".join(material_hypothesis.related_compositions) if material_hypothesis.related_compositions else "None"}
 
Experiment Designed to Test the Hypothesis:
Target Composition: {experiment.target_composition}
Max Heating Temperature: {experiment.max_heating_temperature if experiment.max_heating_temperature is not None else "Not specified"}
Justification: {experiment.justification}
Hypothesis: {experiment.hypothesis}
 
Experimental Outcome for the New Experiment:
{self._serialize_data_to_json(experiment_outcome_list)}
 
Historical Data for Related Compositions (including the original abnormal composition):
{self._serialize_data_to_json(related_compositions_data)}
"""
        else:
            # New material proposal driven reflection
            proposal: NewMaterialProposal = material_hypothesis

            prompt_input = f"""New Material Proposal:
Composition: {proposal.composition}
Justification: {proposal.justification}

Experimental Outcome for the New Material Proposal:
{self._serialize_data_to_json(experiment_outcome_list)}
"""

        # Choose appropriate agent
        if isinstance(material_hypothesis, MaterialDataAbnormalityResult):
            reflection_agent = self.reflection_abnormality_agent
        else:
            reflection_agent = self.reflection_exploration_agent

        # Run the reflection agent with retry logic
        for i in range(5):
            try:
                result = await Runner.run(reflection_agent, prompt_input)
                break
            except litellm.RateLimitError:
                print("Rate limit error encountered, sleeping for 90 seconds.")
                print_exc()
                time.sleep(90)
        else:
            raise Exception("Failed to run reflection agent after 5 attempts.")

        return result.final_output

    async def _run_new_material_proposal_workflow_on_subset(
        self,
        data_subset: list[dict],
    ) -> NewMaterialProposalResponse:
        """
        Run the new material proposal workflow on a subset of data.

        Args:
            data_subset: The subset of data to process.

        Returns:
            NewMaterialProposalResponse containing the proposed new materials.
        """
        # Create a temporary workflow instance with the subset data
        temp_workflow = self.__class__(data_subset)

        # Prepare input for new material proposal agent
        prompt_input = f"""Experimental Data:
{temp_workflow._serialize_data_to_json(data_subset)}
"""

        # Run the new material proposal agent with retry logic
        for i in range(5):
            try:
                result = await Runner.run(
                    temp_workflow.new_material_proposal_agent, prompt_input
                )
                break
            except litellm.RateLimitError:
                print("Rate limit error encountered, sleeping for 90 seconds.")
                print_exc()
                time.sleep(90)
        else:
            raise Exception(
                "Failed to run new material proposal agent after 5 attempts."
            )

        return result.final_output

    async def run_new_material_proposal_workflow(
        self,
        distance_threshold: float = 5,
    ) -> NewMaterialProposalResponse:
        """
        Run the new material proposal workflow by clustering data by compositions,
        then executing the proposal workflow on each cluster.

        Args:
            distance_threshold: Distance threshold for compositional clustering (default: 0.5)

        Returns:
            NewMaterialProposalResponse containing the combined proposed new materials from all clusters.
        """
        # Step 1: Extract all unique compositions from the data
        all_compositions = list(
            set([row.get("composition") for row in self.data if row.get("composition")])
        )

        # Step 2: Cluster compositions by similarity
        composition_clusters = self._get_compositional_clusters(
            all_compositions,
            distance_threshold=distance_threshold,
            embedding_type="compositional",
        )

        # Step 3: Run proposal workflow on each cluster
        all_material_proposals = []

        for cluster in composition_clusters:
            # Filter data to only include samples with compositions in this cluster
            cluster_data = self._filter_by_compositions(set(cluster))

            if len(cluster_data) > 0:
                # Run the proposal workflow on this cluster
                proposal_results = (
                    await self._run_new_material_proposal_workflow_on_subset(
                        cluster_data
                    )
                )

                # Collect results
                if proposal_results and proposal_results.material_proposals:
                    all_material_proposals.extend(proposal_results.material_proposals)

        # Step 4: Combine all results
        combined_proposal_response = NewMaterialProposalResponse(
            material_proposals=all_material_proposals
        )

        return combined_proposal_response
