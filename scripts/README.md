# Scripts for Operating the Lab

This folder contains operational scripts for:
- Data/measurement analysis
- Agentic experiment-design workflows
- Experiment submission

## Analysis workflows

- `analysis_workflow.py`: Main analysis pipeline to fit impedance data and extract phase information from XRD data

## Agentic workflows
These scripts define and run agent workflows for experiment planning and reporting:

- `agent_abnormality_detection.py`
  - Detects abnormal materials/experiments in the dataset
- `agent_pattern_finding.py`
  - Pattern-finding workflow to propose new experiments
- `agent_bo_assisted_pattern_finding.py`
  - Bayesian-optimization-assisted pattern finding for new experiment proposals
- `agent_summarize.py`
  - Summarizes experiment results into short notes for future agent runs
- `agent_prompts.py`
  - Prompt and workflow definitions used by agent scripts

**Note:** You will need to supply API keys for the agents to work. Create a `.env` file in the root directory and add the following keys:

```
OPENAI_API_KEY=xxxxxxxxxxxxxxxxx
OPENAI_AGENTS_DISABLE_TRACING=1
```


## Experiment submission

- `submit_experiment.ipynb`
  - Notebook for submitting experiments to the lab when A-Lab GPSS is running
  - For a simulated/local stack setup, follow:
    - [`src/alab_gpss/README.md`](../src/alab_gpss/README.md)
