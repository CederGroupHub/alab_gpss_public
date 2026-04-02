# Post-Analysis Scripts

This folder contains post-analysis code used to generate Figure 4 of the manuscript.

## Contents overview

- `extract_causal_effect.py`
  - Strategy-text processing and visualization pipeline (Figure 4a)
- `shannon_surprise.ipynb`
  - Shannon surprise analysis notebook (Figure 4c)
- `claim_extraction_workflow.py`
  - Claim extraction workflow (Figure 4d input)
- `results/`
  - Outputs we used for making the plots.

## Strategy visualization (Figure 4a)

Produced by `extract_causal_effect.py`:
- Extracts causal-effect/strategy text from experiment reports
- Embeds text with a Gemini embedding model
- Uses PCA to visualize strategy embeddings

## Shannon surprise (Figure 4c)

Produced by `shannon_surprise.ipynb`:
- Computes Shannon surprise values for the dataset
- Generates the corresponding distribution/summary plot

## Claim extraction (Figure 4d input)

Produced by `claim_extraction_workflow.py`:
- Extracts scientific claims from the dataset using openai gpt-5-mini
