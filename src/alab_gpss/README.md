# ALAB GPSS

Control and analysis code for the GPSS platform, including:
- hardware device/task orchestration (`alab_gpss.system`)
- FastAPI backend + React UI (`alab_gpss.backend`, `alab_gpss/ui`)
- experimental data analysis workflows (`scripts/`)
- support daemons for scanner/light/caliper integrations (`src/daemon/`)

## Repository Layout

```text
src/
  alab_gpss/
    backend/                # FastAPI app + routers
    system/                 # device wrappers and task definitions
    experiment_design/      # chemistry/reaction helpers
    ui/                     # React frontend
  daemon/
    gpss_qrcode_scanner/
    gpss_height_caliper/
    gpss_light_monitor/
scripts/                    # analysis and AI workflow scripts
data/                       # local dataset location (expected: data/dataset.json)
```

## Prerequisites

- Python 3.10+
- Node.js 18+ and npm (for UI development)
- MongoDB reachable by the configured hosts
- Optional: hardware/network access for GPSS devices and Aeris/BioLogic integrations

## Python Setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

If you use `uv`:

```bash
uv sync
```

## Configuration

### AlabOS / infrastructure config

An example config is provided at:
- `src/alab_gpss/system/alabos_config_example.toml`

You will need to set host/port/credentials for MongoDB, RabbitMQ, alarm channels, etc.

### Device/network assumptions

Current code includes hardcoded/internal addresses for many devices (robot arms, furnaces, BioLogic, Aeris, etc.).
Review before deployment:
- `src/alab_gpss/system/__init__.py`
- `src/alab_gpss/backend/routers/ionic_conductivity.py`
- `src/alab_gpss/backend/routers/xrd_sample_holder.py`

### TLS certificates (optional)

`backend/server.py` attempts to use:
- `ssl_keys/aragorn-key.pem`
- `ssl_keys/aragorn-cert.pem`

If files are missing, the wrapper uses a fallback to run without SSL files.

## Run Backend API

```bash
python -m alab_gpss.backend.server
```

Default bind:
- host: `0.0.0.0`
- port: `8000`

Main routers are mounted under:
- `/api/dosing-head/`
- `/api/consumable-rack/`
- `/api/xrd-sample-holder/`
- `/api/ionic-conductivity/`

## Run Frontend (dev)

```bash
cd src/alab_gpss/ui
npm install
npm start
```

The UI proxies API requests to `http://localhost:8000` (see `ui/package.json`).

To build frontend assets:

```bash
npm run build
```

The backend serves built assets from `src/alab_gpss/ui/build/` when present.

## Analysis / Workflow Scripts

Main scripts in `scripts/`:
- `analysis_workflow.py`: conductivity fitting + XRD phase extraction + DB update pipeline
- `experiment_design.py`: agent-driven experiment design workflow utilities
- `explore.py`: new material proposal workflow
- `explore_bo.py`: Bayesian optimization + proposal generation
- `find_abnormality.py`: abnormality detection workflow
- `reflection.py`: reflection workflow for completed experiments

Most of these scripts expect a dataset at:
- `data/dataset.json`

And/or access to MongoDB instances used in the lab environment.

## Daemons

- `src/daemon/gpss_qrcode_scanner/main.py`
  - reads scanner input and posts measurement jobs to ionic conductivity API
- `src/daemon/gpss_height_caliper/main.py`
  - reads caliper values and updates sample height via API
- `src/daemon/gpss_light_monitor/main.py`
  - monitors/controls Govee lighting devices

These daemons are environment-driven (API URLs, device hints, credentials), but include sensible defaults in code.

## Notes

- `pyproject.toml` currently defines a console script entry `alab_gpss = alab_gpss.cli:cli`, but `src/alab_gpss/cli.py` is not present in this repository.
- Some modules are tightly coupled to lab-specific infrastructure; local development may require stubbing or simulation mode.
