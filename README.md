# Climate-Focused LCA of Wind Turbine Support Structures

This repository contains the non-proprietary data tables, analysis scripts, Monte Carlo summaries, deterministic stress-test outputs, and figure source data for the manuscript:

"Climate-Focused LCA of Wind Turbine Support Structures: Source-Explicit Inventories and Rank Fragility"

The repository does not disclose partner-provided FAWT structural mass inputs. Derived scenario results, disclosure status, and deterministic-envelope outputs are documented in the manuscript and in `docs/proprietary_data_note.md`.

## Repository Role

The active repository is maintained on GitHub at https://github.com/TakumiMM11/wind-support-lca-rank-fragility. The submission-version release will be archived through Zenodo and cited in the manuscript once the Zenodo DOI is issued.

Placeholders to replace before submission:

- Zenodo DOI: `[Zenodo DOI]`
- Release: `v1.0-submission`

## Contents

- `data/`: shareable material coefficients and modeling assumptions.
- `results/`: 80-case matrix, Monte Carlo outputs, rank-fragility tables, and deterministic stress-test tables.
- `figures/figure_source_data/`: source data used for manuscript figures and tables.
- `figures/exported_figures/`: exported figure files.
- `scripts/`: analysis and figure-generation scripts used in the project workflow.
- `src/`: supporting Python source modules required by the scripts.
- `docs/`: data dictionary, reproduction notes, and proprietary-data boundary.

## Reproduction

The repository is intended to preserve the non-proprietary submission-version evidence package. Some paths in the copied scripts may need adjustment after the GitHub repository is finalized. See `docs/reproduction_instructions.md`.

## Proprietary Boundary

FAWT is treated as a private scenario case, not as a public reference-design benchmark. Absolute FAWT structural mass inputs are not included. The repository includes central GWP results, sensitivity outputs, disclosure labels, and figure source data needed to interpret the manuscript.

## Citation

After Zenodo archives `v1.0-submission`, cite the archived release DOI listed in `CITATION.cff`.
