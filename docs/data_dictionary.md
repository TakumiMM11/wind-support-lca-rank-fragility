# Data Dictionary

This file summarizes the main non-proprietary files included in the submission-version evidence package.

## data/

- `material_coefficients.csv`: foreground GWP coefficients used in the manuscript.
- `capacity_factor_inputs.csv`: triangular capacity-factor inputs used for the headline Monte Carlo analysis.
- `eol_credit_inputs.csv`: current-case and sampled end-of-life credit assumptions.
- `structural_inventory_public_proxy.csv`: disclosure category and inventory basis for each support-structure case.
- `model_assumptions.json`: model assumptions copied from the working repository for review transparency.
- `materials_model_input.csv`: material model input table copied from the working repository.

## results/

- `80_case_result_matrix.csv`: full 5 structure x 4 rating x 4 blade-material result matrix.
- `monte_carlo_summary.csv`: Monte Carlo summary output.
- `rank_fragility_pairwise.csv`: pairwise rank-fragility output.
- `prcc_summary.csv`: PRCC diagnostic summary for the sampled capacity-factor and end-of-life variables.
- `mc_convergence_summary.csv`: Monte Carlo convergence diagnostic table for the 15 MW GFRP bottom-fixed/onshore comparison. The convergence ordering column is `support_frequency_bottom_fixed_vs_onshore`, matching the support definition in `rank_fragility_pairwise.csv`.
- `bop_cf_break_even.csv`: offshore electrical BOP and capacity-factor break-even sensitivity.
- `cfrp_break_even_aep.csv`: AEP gain required for CFRP to break even against GFRP at 15 MW.
- `o_and_m_sensitivity.csv`: O&M multiplier sensitivity for 15 MW GFRP cases.
- `tie_threshold_sensitivity.csv`: 0.5%, 1%, 2%, and 5% tie-threshold sensitivity.
- `eol_sensitivity.csv`: end-of-life credit sensitivity.
- `capacity_factor_sensitivity.csv`: capacity-factor scenario sensitivity.
- `benchmark_range_check.csv`: literature benchmark transparency check.
- `fawt_mass_sensitivity_summary.csv`: FAWT derived mass-inventory sensitivity outputs.
- `lifetime_sensitivity_summary.csv`: common-horizon lifetime screen.
- `rr_rc_decomposition_summary_base.csv`: rCFRP versus rrCFRP decomposition for the base matrix.
- `rr_rc_decomposition_summary_fawt46.csv`: rCFRP versus rrCFRP decomposition for the FAWT scenario variant.

## figures/

- `figures/exported_figures/`: exported manuscript and supporting figures, including `mc_convergence.png`.
- `figures/figure_source_data/`: CSV source data used to build the manuscript figures and supporting figure checks.

## scripts/ and src/

The scripts and source modules document the analysis workflow used for the manuscript evidence package. Run scripts from the repository root unless the script header specifies otherwise.
