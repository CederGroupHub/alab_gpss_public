# Post-Analysis Scripts

This folder contains post-analysis code used to generate Figure 4 of the manuscript.

## Contents overview

- `extract_causal_effect.py`
  - Strategy-text processing and visualization pipeline (Figure 4a)
- `shannon_surprise.ipynb`
  - Shannon surprise analysis notebook (Figure 4b)
- `fact_check_workflow.py`
  - Claim extraction + external-reference verification workflow (Figure 4c/4d input)
- `classify_unverified_claims.py`
  - Categorizes unverified claims into `no reference` and `contradicted` (Figure 4d)
- `results/`
  - Outputs we used for making the plots.

## Strategy visualization (Figure 4a)

Produced by `extract_causal_effect.py`:
- Extracts causal-effect/strategy text from experiment reports
- Embeds text with a Gemini embedding model
- Uses PCA to visualize strategy embeddings

## Shannon surprise (Figure 4b)

Produced by `shannon_surprise.ipynb`:
- Computes Shannon surprise values for the dataset
- Generates the corresponding distribution/summary plot

## Fact check (Figure 4c and Figure 4d input)

Produced by `fact_check_workflow.py`:
- Extracts scientific claims from the dataset
- Verifies external-referenced claims using web search
- Produces structured fact-check outputs used for downstream plotting

## Verification result classification (Figure 4d)

Produced by `classify_unverified_claims.py`:
- Takes unverified claims from fact-check outputs
- Assigns categories (`no reference`, `contradicted`)
