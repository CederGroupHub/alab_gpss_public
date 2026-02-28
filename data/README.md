# Data

This folder contains the raw experiment data produced by A-Lab GPSS.

## What is in this folder

- `dataset.json`: Consolidated dataset used by the agentic workflows.
- `NNN_<composition>/` directories: Per-sample experiment artifacts (for example, XRD patterns, EIS files, and refinement outputs).

## Directory naming

Sample directories follow a numbered prefix plus composition pattern, for example:
- `000_Li2MgCl4`
- `231_Li3YCl6`

The numeric prefix is the sample index used across scripts and analysis.

## Contents of each sample folder

Each sample folder (`NNN_<composition>/`) contains the same core artifact types:

- `pattern.xrdml`
  - Raw XRD measurement file for that sample
- `eis_data.csv`
  - EIS measurement data table
- `manual_refinement.lst`
  - Result file of manual XRD refinement
- `manual_refinement.png`
  - Plot/image generated from manual refinement
- `auto_refinement.png`
  - Plot/image generated from automated refinement
- `phases/`
  - CIF reference files used during phase analysis/refinement
  - Commonly includes `spinel.cif` and/or additional references (for example `LiCl_...cif`, `MnCl2_...cif`, `Li3YCl6_...cif`)
  - The spinel refers to a generated structure of spinel structure with the target composition.
- 