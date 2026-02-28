# A-Lab GPSS

This repository contains the code used to operate the A-Lab GPSS platform.
It includes both:
- Lab hardware control/orchestration code
- AI-assisted and analysis workflows used around experiment execution

## Repository map

- `src/alab_gpss/`: Core GPSS application code
- `src/daemon/`: Raspberry Pi daemons for operational monitoring and trigger devices
- `scripts/`: Analysis and agentic workflow scripts
- `post_analysis/`: Post-analysis scripts/notebooks used for manuscript figures
- `data/`: Raw experiment data and dataset index files

## Where to start

- If you want to run the GPSS stack (backend/UI + task system), start with:
  - [`src/alab_gpss/README.md`](src/alab_gpss/README.md)
- If you want to understand/operate lab-side daemons, see:
  - [`src/daemon/README.md`](src/daemon/README.md)
- If you want to run analysis or agent workflows, see:
  - [`scripts/README.md`](scripts/README.md)
- If you want to reproduce post-analysis figures, see:
  - [`post_analysis/README.md`](post_analysis/README.md)
- If you are exploring raw experiment artifacts, see:
  - [`data/README.md`](data/README.md)

## Typical workflow in this repository

1. Run the core GPSS services (`src/alab_gpss`).
2. Submit or execute experiments.
3. Run analysis/agent workflows (`scripts/`).
4. Run manuscript post-analysis (`post_analysis/`).
