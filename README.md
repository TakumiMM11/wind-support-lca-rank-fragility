# Climate-Focused Assessment of Wind-Turbine Support Structures: Source-Audited Inventories, Transfer-Validity Gates, and Rank Fragility

- Release: `1.1.1` (`v1.1.1-seta-submission`)
- Release date: 2026-07-18
- Repository: <https://github.com/TakumiMM11/wind-support-lca-rank-fragility>
- Zenodo concept DOI (all versions): <https://doi.org/10.5281/zenodo.21263857>

The version-specific Zenodo DOI will be minted from the GitHub release. No
unissued version DOI is asserted in this repository snapshot.

This package rebuilds the original manuscript's multi-support and rank-fragility
story with corrected material identities. It does **not** reproduce the earlier
80-cell point-estimate matrix.

The primary estimand is a cradle-to-gate material-production climate proxy for
four public 15 MW support-substructure designs: monopile, WindCrete, TLP, and
VolturnUS-S. ActiveFloat is retained only in a separate two-endpoint unit audit;
its baseline row preserves mass provenance but asserts no burden, intensity, or
rank. The common turbine, towers,
electrical BOP, fabrication, installation, O&M, end of life, anchors, and scour
protection are outside the central boundary. Station keeping is reported as a
separate additive layer.

Two uncertainty estimands are kept separate:

1. `equal_yield`: a common 0.42 capacity factor, isolating inventory and material
   effects;
2. `deployment`: correlated conditional capacity-factor ranges, showing how
   yield assumptions can alter an electricity-normalized ranking.

Sample frequencies are conditional stress-test diagnostics, not estimates of
the share of real projects for which one design is preferable.

## Reproduce

```bash
uv sync --frozen
uv run python scripts/run_analysis.py
uv run pytest -q
```

Every manuscript-facing output is regenerated under `analysis/` and `figures/`.
`analysis/run_metadata.json` records input and output SHA-256 hashes.
`figures/figure_manifest.json` records each figure's message, source tables,
unit, filters, evidence-tier key, and file hashes.

The metadata also records SHA-256 hashes for `src/analysis.py`,
`scripts/run_analysis.py`, `src/__init__.py`, `pyproject.toml`, `uv.lock`, and
the test module. Files containing `.bak_pre_` are immutable pre-change backups
and are deliberately excluded from the run manifests.

Key decision outputs are:

- `pairwise_rank_fragility.csv`: lower/tie sample fractions for core-only,
  core-plus-station-keeping, and deployment-conditioned estimands;
- `boundary_layer_rank_shifts.csv`: sampled ordering changes caused by adding
  station keeping;
- `data_resolution_thresholds.csv`: unmodelled steel or concrete mass needed
  to close each central burden gap;
- `analytic_rating_transfer.csv`: an explicitly non-engineered exponent screen,
  retained only to diagnose the former rating claim.

ActiveFloat is absent from primary conditional samples, summaries, pairwise
tables, rank distributions, boundary-shift tables, corner bounds, and rating
transfers. `baseline_15mw_support_results.csv` retains its source/mass row with
`point_estimate_status=audit_only_unit_endpoints` and blank burden, intensity,
and rank fields.

Additional audit-only outputs are:

- `activefloat_rebar_unit_endpoints.csv`: exclusive readings of the reported
  ActiveFloat rebar value 2550 as either 2550 kg or 2550 t. Neither endpoint is
  preferred or treated as central because the source unit remains unresolved.
  Both rows are non-headline endpoints and carry `no_central_claim=true`. The same
  rows derive physical-only residual endpoints from the published 34,387.2 t
  platform total: 13,984.65 t for the 2.55 t rebar reading and 11,437.2 t for
  the 2,550 t reading;
- `robustness_matrix_pairwise.csv`: pairwise sample fractions for triangular,
  uniform, and equal-weight discrete-endpoint marginals, WindCrete reinforcement
  caps of 5% and 12.5%, capacity-factor copula correlations of 0, 0.6, and 0.9,
  and tie bands of 0.5%, 1%, and 2%;
- `robustness_ab_reported_material_ordering.csv`: the conditional fraction of
  samples retaining the reported-material A/B order
  `monopile < TLP < VolturnUS`, versus another strict order or a tie;
- `missing_burden_parity_thresholds.csv`: links each unreported anchor or scour
  item to steel-equivalent and concrete-equivalent gap-closing thresholds. It
  does not assert an actual missing mass or material identity.

The robustness audit uses three fixed replicates of 20,000 samples per scenario
(`inputs/robustness_scenarios.json`). Replicate standard deviations and extrema
are reported alongside the pooled-mean sample fractions. These are conditional
design-space diagnostics, not real-project frequencies. The 5% WindCrete cap is
the pre-existing package mode used as a lower audit alternative; the 12.5% cap
is the pre-existing upper stress tied to the unresolved assumed-tonne
ActiveFloat ratio. Neither cap is an observed reinforcement rate.

`inputs/evidence_profile.csv` makes five evidence axes machine-readable:
source directness, material identity, boundary completeness, design-version
consistency, and coefficient specificity. Scores are ordinal audit aids only:
2 means direct/aligned, 1 means qualified or proxy-based, and 0 means a blocking
gap for that axis. Eligibility remains an explicit rule result, not a sum of
scores. In particular, ActiveFloat remains
`non_headline_unresolved_unit`; A/B/C is retained only as an auxiliary label.

Figure-specific source tables make the visual filters testable:

- `figure_1_plot_data.csv` contains four conditional bars and two hollow,
  unranked ActiveFloat unit endpoints;
- `figure_2_heatmap_values.csv` contains matched 4 × 4 core and
  core-plus-station-keeping matrices on a common 0--1 scale. ActiveFloat is
  absent from every row and column.

## Scientific safeguards

- Seawater, hydrostatic displacement, cross-check totals, and unresolved
  ActiveFloat residual mass cannot receive material coefficients.
- VolturnUS-S hull steel, fixed ballast, and operating seawater are kept in
  separate registers.
- WindCrete solid aggregate is not mapped to concrete.
- The omitted WindCrete reinforcement is an explicit sensitivity parameter.
- Evidence tiers are printed on comparison figures so proxy-only cases cannot
  be mistaken for equally supported alternatives.
- Pairwise outputs are named `sample_fraction_*`; they are not empirical
  project-win probabilities.
- Every audit-only table carries a `no_central_claim` flag.
- ActiveFloat's mutually exclusive kg and tonne readings are never mixed in one
  sample or treated as a distribution over real projects.
- `physical_mass_register.csv` keeps `af_unmapped_residual` only as a mass-free
  `audit_only_unit_dependent_placeholder`; neither residual endpoint is stored
  as a single physical central value or assigned a material identity.
- Missing anchor and scour thresholds are material-equivalent break-even values,
  not invented inventories.
- The former GFRP/CFRP cascade and arbitrary 2--15 MW power-law results are not
  treated as engineered design comparisons.
