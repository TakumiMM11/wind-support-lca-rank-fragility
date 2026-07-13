# Reproduction Instructions

This package preserves the non-proprietary submission-version evidence. Run scripts from the repository root so that relative paths resolve against the included `data/`, `results/`, and `figures/` directories.

Recommended release workflow:

1. Create or update the public GitHub repository.
2. Confirm that `README.md`, `CITATION.cff`, `LICENSE`, `data/`, `results/`, `figures/`, `scripts/`, `src/`, and `docs/` are present.
3. Run the analysis scripts needed for the final tables and figures, or verify that the included outputs match the manuscript.
4. Create the GitHub release.
5. Archive the release through Zenodo.
6. Insert the GitHub URL and Zenodo DOI into the manuscript Data availability section.

For this submission package, the archived `v1.0.4-submission` GitHub release DOI is https://doi.org/10.5281/zenodo.21334186.

Verification outputs referenced in the manuscript are included at:

- `results/prcc_summary.csv`
- `results/mc_convergence_summary.csv`, where `support_frequency_bottom_fixed_vs_onshore` is the conditional sampling frequency supporting the bottom-fixed/onshore point-estimate ordering.
- `figures/exported_figures/mc_convergence.png`

The Monte Carlo convergence figure can be regenerated with:

```bash
python3 scripts/plot_mc_convergence.py
```

Run the consistency check before using the archived outputs:

```bash
python3 scripts/check_submission_consistency.py
```

The expected output is also archived in `docs/consistency_check_log.txt`.

The FAWT absolute structural mass inputs are intentionally not reproduced in this repository. Derived FAWT scenario outputs are included for interpretation.
