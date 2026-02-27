# Post-Analysis Scripts
The scripts in this folder are used to perform post-analysis on the dataset to produce the plots in Figure. 4 of the manuscript.

## Strategy visualization (Figure 4a)
The strategy visualization is produced by the `extract_causal_effect.py` script. This script extracts the causal effects from the experiment reports. Then we use gemini text embedding model to embed the strategy text into text embedding space. Then we use PCA to visualize the embedding space.

## Shannon surprise (Figure 4b)
The Shannon surprise is produced by the `shannon_surprise.ipynb` script. This script calculates the Shannon surprise of the dataset. The Shannon surprise is a measure of the surprise of the dataset. It is calculated by the following formula.

## Fact check (Figure 4c&d)
The fact check is produced by the `fact_check_workflow.py` script. This script extracts the claims from the dataset and verifies them using the web search. Then we use the fact check results to produce the plots in Figure 4c&d.

## Verification results (Figure 4d)
The unverified claims are further classified into "no reference" and "contradicted" categories. This process is performed by the `classify_unverified_claims.py` script.
