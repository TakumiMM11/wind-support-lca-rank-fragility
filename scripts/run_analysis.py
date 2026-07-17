#!/usr/bin/env python3
"""Regenerate every table and figure used by the restored-story draft."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis import (
    CASE_ORDER,
    activefloat_rebar_unit_endpoints,
    analytic_corner_bounds,
    boundary_layer_rank_shifts,
    central_case_results,
    central_component_results,
    legacy_correction_results,
    load_inputs,
    monte_carlo_samples,
    pairwise_rank_results,
    qa_results,
    rank_distribution,
    rating_transfer_results,
    reversal_thresholds,
    robustness_audit_results,
    sample_summary,
    sha256,
    missing_burden_parity_thresholds,
)


RANKED_FIGURE_ORDER = (
    "monopile_15mw",
    "windcrete_15mw",
    "tlp_15mw",
    "volturnus_15mw",
)
FIGURE_LABELS = {
    "monopile_15mw": "Monopile\n[A]",
    "windcrete_15mw": "WindCrete\n[C: sensitivity]",
    "tlp_15mw": "TLP\n[B]",
    "volturnus_15mw": "VolturnUS-S\n[A]",
    "activefloat_15mw": "ActiveFloat\n[C: unit unresolved]",
}
EVIDENCE_TIERS = {
    "monopile_15mw": "A",
    "windcrete_15mw": "C_sensitivity",
    "tlp_15mw": "B",
    "volturnus_15mw": "A",
    "activefloat_15mw": "C_unresolved_unit",
}
COLORS = {
    "monopile_15mw": "#0072B2",
    "volturnus_15mw": "#D55E00",
    "windcrete_15mw": "#009E73",
    "activefloat_15mw": "#CC79A7",
    "tlp_15mw": "#E69F00",
}


def _save(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def figure_1_source_data(
    summary: pd.DataFrame,
    activefloat_units: pd.DataFrame,
) -> pd.DataFrame:
    """Freeze the four ranked bars and the two unranked ActiveFloat endpoints."""

    equal_summary = summary[
        summary["estimand"] == "equal_yield_gco2_per_kwh"
    ].set_index("case_id")
    core_summary = summary[
        summary["estimand"] == "core_equal_yield_gco2_per_kwh"
    ].set_index("case_id")
    rows = []
    for display_order, case_id in enumerate(RANKED_FIGURE_ORDER):
        total = float(equal_summary.loc[case_id, "median"])
        core = float(core_summary.loc[case_id, "median"])
        rows.append(
            {
                "display_order": display_order,
                "case_id": case_id,
                "display_label": FIGURE_LABELS[case_id].replace("\n", " | "),
                "evidence_profile": EVIDENCE_TIERS[case_id],
                "plot_role": "ranked_conditional_bar",
                "ranked_for_figure": True,
                "endpoint_label": "",
                "core_value_gco2_per_kwh": core,
                "stationkeeping_addition_gco2_per_kwh": total - core,
                "total_value_gco2_per_kwh": total,
                "sample_p05_gco2_per_kwh": float(equal_summary.loc[case_id, "p05"]),
                "sample_p95_gco2_per_kwh": float(equal_summary.loc[case_id, "p95"]),
                "source_semantics": "conditional median and 5--95% sampled range",
            }
        )
    endpoint_labels = {
        "reported_header_kg_literal": "2.55 t",
        "reported_value_interpreted_as_tonnes": "2550 t",
    }
    for endpoint in activefloat_units.sort_values("interpreted_rebar_mass_kg").itertuples(
        index=False
    ):
        core = float(endpoint.core_intensity_gco2_per_kwh_endpoint)
        total = float(endpoint.core_plus_stationkeeping_intensity_gco2_per_kwh_endpoint)
        rows.append(
            {
                "display_order": len(RANKED_FIGURE_ORDER),
                "case_id": "activefloat_15mw",
                "display_label": FIGURE_LABELS["activefloat_15mw"].replace("\n", " | "),
                "evidence_profile": EVIDENCE_TIERS["activefloat_15mw"],
                "plot_role": "unranked_unit_endpoint",
                "ranked_for_figure": False,
                "endpoint_label": endpoint_labels[endpoint.unit_scenario_id],
                "core_value_gco2_per_kwh": core,
                "stationkeeping_addition_gco2_per_kwh": total - core,
                "total_value_gco2_per_kwh": total,
                "sample_p05_gco2_per_kwh": np.nan,
                "sample_p95_gco2_per_kwh": np.nan,
                "source_semantics": "exclusive fixed unit endpoint; no sampled rank",
            }
        )
    return pd.DataFrame(rows)


def figure_2_source_data(pairwise: pd.DataFrame, tie_threshold: float) -> pd.DataFrame:
    """Build matched four-case heatmap cells with ActiveFloat excluded."""

    panels = (
        ("core_equal_yield_gco2_per_kwh", "Core substructure only"),
        ("equal_yield_gco2_per_kwh", "Core + station keeping"),
    )
    rows = []
    for panel_order, (estimand, panel_label) in enumerate(panels):
        subset = pairwise[pairwise["estimand"] == estimand]
        for row_order, row_case in enumerate(RANKED_FIGURE_ORDER):
            for column_order, column_case in enumerate(RANKED_FIGURE_ORDER):
                if row_case == column_case:
                    row_lower = 0.0
                    column_lower = 0.0
                    tie = 1.0
                    display_value = 0.5
                    comparison_scope = "diagonal"
                else:
                    match = subset[
                        ((subset["case_a"] == row_case) & (subset["case_b"] == column_case))
                        | ((subset["case_a"] == column_case) & (subset["case_b"] == row_case))
                    ]
                    if len(match) != 1:
                        raise RuntimeError(
                            "expected exactly one pairwise row for {} and {}".format(
                                row_case, column_case
                            )
                        )
                    result = match.iloc[0]
                    tie = float(result["sample_fraction_tie"])
                    if result["case_a"] == row_case:
                        row_lower = float(result["sample_fraction_a_lower"])
                        column_lower = float(result["sample_fraction_b_lower"])
                    else:
                        row_lower = float(result["sample_fraction_b_lower"])
                        column_lower = float(result["sample_fraction_a_lower"])
                    display_value = row_lower + 0.5 * tie
                    comparison_scope = str(result["comparison_scope"])
                rows.append(
                    {
                        "panel_order": panel_order,
                        "panel_label": panel_label,
                        "estimand": estimand,
                        "row_order": row_order,
                        "column_order": column_order,
                        "row_case_id": row_case,
                        "column_case_id": column_case,
                        "row_evidence_profile": EVIDENCE_TIERS[row_case],
                        "column_evidence_profile": EVIDENCE_TIERS[column_case],
                        "sample_fraction_row_lower": row_lower,
                        "sample_fraction_column_lower": column_lower,
                        "sample_fraction_tie": tie,
                        "reported_material_conditional_sample_fraction": display_value,
                        "tie_threshold": tie_threshold,
                        "comparison_scope": comparison_scope,
                    }
                )
    return pd.DataFrame(rows)


def make_figures(
    figure_1_data: pd.DataFrame,
    figure_2_data: pd.DataFrame,
    corrections: pd.DataFrame,
    figure_dir: Path,
) -> None:
    figure_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8})

    ranked = figure_1_data[figure_1_data["plot_role"] == "ranked_conditional_bar"].sort_values(
        "display_order"
    )
    endpoints = figure_1_data[
        figure_1_data["plot_role"] == "unranked_unit_endpoint"
    ].sort_values("total_value_gco2_per_kwh")
    x = ranked["display_order"].to_numpy(dtype=float)
    values = ranked["total_value_gco2_per_kwh"].to_numpy()
    core = ranked["core_value_gco2_per_kwh"].to_numpy()
    station = ranked["stationkeeping_addition_gco2_per_kwh"].to_numpy()
    lower = values - ranked["sample_p05_gco2_per_kwh"].to_numpy()
    upper = ranked["sample_p95_gco2_per_kwh"].to_numpy() - values

    fig, ax = plt.subplots(figsize=(6.9, 3.7))
    ax.bar(
        x,
        core,
        color=[COLORS[case_id] for case_id in ranked["case_id"]],
        label="Core substructure",
    )
    ax.bar(
        x,
        station,
        bottom=core,
        color="none",
        edgecolor=[COLORS[case_id] for case_id in ranked["case_id"]],
        hatch="///",
        label="Station keeping",
    )
    ax.errorbar(
        x,
        values,
        yerr=np.vstack([lower, upper]),
        fmt="none",
        ecolor="black",
        capsize=3,
        lw=0.8,
        label="5--95% sampled range",
    )
    endpoint_x = float(len(RANKED_FIGURE_ORDER))
    endpoint_values = endpoints["total_value_gco2_per_kwh"].to_numpy()
    ax.vlines(
        endpoint_x,
        endpoint_values.min(),
        endpoint_values.max(),
        color=COLORS["activefloat_15mw"],
        linestyles="--",
        linewidth=1.1,
        zorder=3,
    )
    ax.hlines(
        endpoint_values,
        endpoint_x - 0.08,
        endpoint_x + 0.08,
        color=COLORS["activefloat_15mw"],
        linewidth=1.1,
        zorder=3,
    )
    for marker, endpoint in zip(("o", "s"), endpoints.itertuples(index=False)):
        ax.scatter(
            endpoint_x,
            endpoint.total_value_gco2_per_kwh,
            s=38,
            marker=marker,
            facecolors="white",
            edgecolors=COLORS["activefloat_15mw"],
            linewidths=1.3,
            zorder=4,
            label=(
                "ActiveFloat unit endpoints (unranked)"
                if marker == "o"
                else "_nolegend_"
            ),
        )
        ax.annotate(
            "{}: {:.2f}".format(endpoint.endpoint_label, endpoint.total_value_gco2_per_kwh),
            (endpoint_x, endpoint.total_value_gco2_per_kwh),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=6.8,
            color="#6B2E63",
        )
    ax.annotate(
        "unit endpoints; unranked",
        (endpoint_x, endpoint_values.max()),
        xytext=(0, 19),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=7,
        fontweight="bold",
        color="#6B2E63",
    )
    tick_positions = list(x) + [endpoint_x]
    tick_labels = [FIGURE_LABELS[case_id] for case_id in ranked["case_id"]] + [
        FIGURE_LABELS["activefloat_15mw"]
    ]
    ax.set_xticks(tick_positions, tick_labels, rotation=18, ha="right")
    ax.set_ylabel("Material-production proxy\n(g CO$_2$e kWh$^{-1}$, equal yield)")
    ax.set_title(
        "Conditional four-case comparison with unranked ActiveFloat endpoints",
        loc="left",
    )
    ax.set_xlim(-0.55, endpoint_x + 0.75)
    ax.legend(frameon=False, fontsize=6.8, ncol=2, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(figure_dir / "Figure_1_multisupport_baseline.png", dpi=300)
    fig.savefig(figure_dir / "Figure_1_multisupport_baseline.pdf")
    plt.close(fig)

    estimands = (
        ("core_equal_yield_gco2_per_kwh", "Core substructure only"),
        ("equal_yield_gco2_per_kwh", "Core + station keeping"),
    )
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.5), layout="constrained")
    for panel, (estimand, panel_title) in zip(axes, estimands):
        subset = figure_2_data[figure_2_data["estimand"] == estimand]
        matrix = (
            subset.pivot(
                index="row_case_id",
                columns="column_case_id",
                values="reported_material_conditional_sample_fraction",
            )
            .loc[list(RANKED_FIGURE_ORDER), list(RANKED_FIGURE_ORDER)]
            .to_numpy()
        )
        image = panel.imshow(matrix, vmin=0, vmax=1, cmap="RdYlBu")
        for i in range(len(RANKED_FIGURE_ORDER)):
            for j in range(len(RANKED_FIGURE_ORDER)):
                text_color = "white" if matrix[i, j] < 0.18 or matrix[i, j] > 0.82 else "black"
                panel.text(
                    j,
                    i,
                    "{:.2f}".format(matrix[i, j]),
                    ha="center",
                    va="center",
                    fontsize=7,
                    color=text_color,
                )
        panel.set_xticks(
            range(len(RANKED_FIGURE_ORDER)),
            [FIGURE_LABELS[c] for c in RANKED_FIGURE_ORDER],
            rotation=38,
            ha="right",
        )
        panel.set_title(panel_title, fontsize=8)
    axes[0].set_yticks(
        range(len(RANKED_FIGURE_ORDER)),
        [FIGURE_LABELS[c] for c in RANKED_FIGURE_ORDER],
    )
    axes[1].set_yticks(range(len(RANKED_FIGURE_ORDER)), [])
    fig.suptitle("Reported-material rank stability by included boundary layer", fontsize=9)
    fig.colorbar(
        image,
        ax=axes,
        label="reported-material conditional sample fraction\n(row lower + 0.5 × tie)",
        shrink=0.82,
    )
    fig.savefig(figure_dir / "Figure_2_rank_stability.png", dpi=300)
    fig.savefig(figure_dir / "Figure_2_rank_stability.pdf")
    plt.close(fig)

    corr = corrections.pivot(index="design_id", columns="mapping_case", values="proxy_gwp_kgco2") / 1e6
    designs = ["volturnus_15mw", "windcrete_15mw"]
    fig, ax = plt.subplots(figsize=(5.3, 3.4))
    width = 0.36
    positions = np.arange(2)
    ax.bar(
        positions - width / 2,
        corr.loc[designs, "rejected_manuscript"],
        width,
        color="#999999",
        label="Legacy mapping",
    )
    ax.bar(positions + width / 2, corr.loc[designs, "source_corrected"], width, color="#009E73", label="Source-corrected mapping")
    ax.set_xticks(positions, ["VolturnUS-S", "WindCrete"])
    ax.set_ylabel("Material-production proxy (kt CO$_2$e)")
    ax.set_title("Material identity changes the inferred burden", loc="left")
    ax.legend(frameon=False, fontsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(figure_dir / "Figure_3_inventory_corrections.png", dpi=300)
    fig.savefig(figure_dir / "Figure_3_inventory_corrections.pdf")
    plt.close(fig)


def run(input_dir: Path, analysis_dir: Path, figure_dir: Path) -> None:
    inputs = load_inputs(input_dir)
    contributions = central_component_results(inputs)
    central = central_case_results(inputs)
    corrections = legacy_correction_results(inputs)
    samples = monte_carlo_samples(inputs)
    pairwise = pairwise_rank_results(inputs, samples)
    boundary_shifts = boundary_layer_rank_shifts(inputs, samples)
    ranks = pd.concat(
        [
            rank_distribution(samples, "core_equal_yield_gco2_per_kwh"),
            rank_distribution(samples, "equal_yield_gco2_per_kwh"),
            rank_distribution(samples, "deployment_gco2_per_kwh"),
        ],
        ignore_index=True,
    )
    summary = sample_summary(samples)
    corners = analytic_corner_bounds(inputs)
    thresholds = reversal_thresholds(inputs, central)
    rating = rating_transfer_results(inputs, central)
    activefloat_units = activefloat_rebar_unit_endpoints(inputs)
    robustness_pairwise, robustness_ordering = robustness_audit_results(inputs)
    missing_parity = missing_burden_parity_thresholds(inputs, central)
    figure_1_data = figure_1_source_data(summary, activefloat_units)
    figure_2_data = figure_2_source_data(
        pairwise, float(inputs.parameters["monte_carlo"]["tie_threshold"])
    )
    qa = qa_results(inputs, central, pairwise)
    if not bool(qa["passed"].all()):
        failures = qa.loc[~qa["passed"], "check"].tolist()
        raise RuntimeError("QA failed: {}".format(failures))
    if not np.allclose(
        robustness_pairwise[
            [
                "sample_fraction_a_lower",
                "sample_fraction_b_lower",
                "sample_fraction_tie",
            ]
        ].sum(axis=1),
        1.0,
    ):
        raise RuntimeError("robustness pairwise sample fractions do not close")
    if not np.allclose(
        robustness_ordering[
            [
                "sample_fraction_strict_reported_order",
                "sample_fraction_other_strict_order",
                "sample_fraction_with_any_tie",
            ]
        ].sum(axis=1),
        1.0,
    ):
        raise RuntimeError("robustness ordering sample fractions do not close")
    if not (
        activefloat_units["no_central_claim"].all()
        and robustness_pairwise["no_central_claim"].all()
        and robustness_ordering["no_central_claim"].all()
        and missing_parity["no_central_claim"].all()
    ):
        raise RuntimeError("an audit-only output is missing its no-central-claim flag")

    analysis_dir.mkdir(parents=True, exist_ok=True)
    _save(central, analysis_dir / "baseline_15mw_support_results.csv")
    _save(contributions, analysis_dir / "component_contributions.csv")
    _save(corrections, analysis_dir / "inventory_correction_effects.csv")
    _save(pairwise, analysis_dir / "pairwise_rank_fragility.csv")
    _save(boundary_shifts, analysis_dir / "boundary_layer_rank_shifts.csv")
    _save(ranks, analysis_dir / "rank_distribution.csv")
    _save(summary, analysis_dir / "conditional_sample_summary.csv")
    _save(corners, analysis_dir / "analytic_corner_bounds.csv")
    _save(thresholds, analysis_dir / "data_resolution_thresholds.csv")
    _save(rating, analysis_dir / "analytic_rating_transfer.csv")
    _save(activefloat_units, analysis_dir / "activefloat_rebar_unit_endpoints.csv")
    _save(robustness_pairwise, analysis_dir / "robustness_matrix_pairwise.csv")
    _save(
        robustness_ordering,
        analysis_dir / "robustness_ab_reported_material_ordering.csv",
    )
    _save(missing_parity, analysis_dir / "missing_burden_parity_thresholds.csv")
    _save(figure_1_data, analysis_dir / "figure_1_plot_data.csv")
    _save(figure_2_data, analysis_dir / "figure_2_heatmap_values.csv")
    _save(qa, analysis_dir / "input_and_result_qa.csv")
    samples.to_csv(analysis_dir / "conditional_samples.csv.gz", index=False, compression="gzip")

    make_figures(figure_1_data, figure_2_data, corrections, figure_dir)

    input_hashes = {
        path.name: sha256(path)
        for path in sorted(input_dir.glob("*"))
        if path.is_file() and ".bak_pre_" not in path.name
    }
    output_hashes = {
        path.name: sha256(path)
        for path in sorted(analysis_dir.glob("*"))
        if path.is_file()
        and path.name != "run_metadata.json"
        and ".bak_pre_" not in path.name
    }
    figure_hashes = {
        path.name: sha256(path)
        for path in sorted(figure_dir.glob("*"))
        if path.is_file()
        and path.name != "figure_manifest.json"
        and ".bak_pre_" not in path.name
    }
    execution_paths = (
        ROOT / "src" / "analysis.py",
        ROOT / "src" / "__init__.py",
        ROOT / "scripts" / "run_analysis.py",
    )
    environment_paths = (ROOT / "pyproject.toml", ROOT / "uv.lock")
    test_paths = tuple(sorted((ROOT / "tests").glob("test_*.py")))
    execution_hashes = {
        str(path.relative_to(ROOT)): sha256(path) for path in execution_paths
    }
    environment_hashes = {
        str(path.relative_to(ROOT)): sha256(path) for path in environment_paths
    }
    test_hashes = {str(path.relative_to(ROOT)): sha256(path) for path in test_paths}
    figure_source_files = {
        "Figure_1_multisupport_baseline": [
            "conditional_sample_summary.csv",
            "activefloat_rebar_unit_endpoints.csv",
            "figure_1_plot_data.csv",
        ],
        "Figure_2_rank_stability": [
            "pairwise_rank_fragility.csv",
            "figure_2_heatmap_values.csv",
        ],
        "Figure_3_inventory_corrections": ["inventory_correction_effects.csv"],
    }
    figure_source_hashes = {
        figure_id: {
            filename: sha256(analysis_dir / filename) for filename in filenames
        }
        for figure_id, filenames in figure_source_files.items()
    }
    figure_manifest = {
        "project": "wind-support-source-audit-rank-fragility",
        "generator": "scripts/run_analysis.py",
        "generator_version": "0.5.0",
        "prompt_version": "figure-alignment-v1",
        "data_version": inputs.parameters["analysis_id"],
        "version": "v2",
        "date": "2026-07-17",
        "author_or_agent": "Codex",
        "seed": inputs.parameters["monte_carlo"]["seed"],
        "canonical_output_dir": str(figure_dir.resolve()),
        "evidence_tier_key": {
            "A": "conditional reported-material comparison",
            "B": "conditional_product_proxy",
            "C": "sensitivity or evidence-limited proxy only",
        },
        "case_point_estimate_status": {
            str(row.case_id): str(row.point_estimate_status)
            for row in inputs.manifest.itertuples(index=False)
        },
        "activefloat_depth_semantics": {
            "material_proxy_depth_status": "not_specified",
            "associated_engineering_model_depth_m": 200,
            "interpretation": "the 200 m value belongs to an associated engineering model and is not assigned to the material proxy",
        },
        "execution_sha256": execution_hashes,
        "environment_sha256": environment_hashes,
        "figures": {
            "Figure_1_multisupport_baseline": {
                "title": "Conditional four-case comparison with unranked ActiveFloat endpoints",
                "caption_short": "Four conditional median bars retain 5--95% sampled ranges; ActiveFloat is shown only as two hollow unit endpoints and is unranked.",
                "source_data": figure_source_files["Figure_1_multisupport_baseline"],
                "source_sha256": figure_source_hashes["Figure_1_multisupport_baseline"],
                "unit": "g CO2e per kWh at common 0.42 capacity factor",
                "filters": "ranked bars: monopile, WindCrete sensitivity, TLP and VolturnUS-S; ActiveFloat exclusive 2.55 t and 2550 t rebar endpoints are unranked; turbine, tower, anchors and later stages excluded",
            },
            "Figure_2_rank_stability": {
                "title": "Reported-material rank stability by included boundary layer",
                "caption_short": "Matched four-case matrices use one common 0--1 scale and a one-percent tie band; ActiveFloat is excluded because its rebar unit is unresolved.",
                "source_data": figure_source_files["Figure_2_rank_stability"],
                "source_sha256": figure_source_hashes["Figure_2_rank_stability"],
                "unit": "reported-material conditional sample fraction (row lower + 0.5 times tie)",
                "filters": "monopile, WindCrete sensitivity, TLP and VolturnUS-S only; ActiveFloat excluded; equal-yield material-production proxy; matched core and core-plus-station-keeping panels",
                "color_scale": [0.0, 1.0],
                "tie_threshold": float(inputs.parameters["monte_carlo"]["tie_threshold"]),
            },
            "Figure_3_inventory_corrections": {
                "title": "Material identity changes the inferred burden",
                "caption_short": "Legacy and source-corrected material mappings for VolturnUS-S and WindCrete.",
                "source_data": figure_source_files["Figure_3_inventory_corrections"],
                "source_sha256": figure_source_hashes["Figure_3_inventory_corrections"],
                "unit": "kt CO2e material-production proxy",
                "filters": "core-substructure mapping audit only",
            },
        },
        "figure_sha256": figure_hashes,
    }
    (figure_dir / "figure_manifest.json").write_text(
        json.dumps(figure_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    metadata = {
        "analysis_id": inputs.parameters["analysis_id"],
        "seed": inputs.parameters["monte_carlo"]["seed"],
        "n_samples": inputs.parameters["monte_carlo"]["n_samples"],
        "interpretation": inputs.parameters["interpretation"],
        "audit_interpretation": inputs.robustness["interpretation"],
        "audit_outputs": {
            "activefloat_rebar_unit_endpoints.csv": "two exclusive unit readings; neither is headline eligible",
            "robustness_matrix_pairwise.csv": "conditional sample-fraction sensitivity matrix",
            "robustness_ab_reported_material_ordering.csv": "A/B reported-material ordering across audit choices",
            "missing_burden_parity_thresholds.csv": "steel- and concrete-equivalent thresholds only; no actual missing mass",
        },
        "primary_comparison_scope": "ActiveFloat excluded from primary samples, summaries, pairwise results, ranks and boundary shifts; baseline row retains mass provenance with no burden, intensity or rank",
        "figure_source_tables": {
            "figure_1_plot_data.csv": "four ranked conditional bars plus two unranked ActiveFloat unit endpoints",
            "figure_2_heatmap_values.csv": "matched four-case heatmap cells with ActiveFloat excluded",
        },
        "input_sha256": input_hashes,
        "output_sha256": output_hashes,
        "figure_sha256": figure_hashes,
        "execution_sha256": execution_hashes,
        "environment_sha256": environment_hashes,
        "test_sha256": test_hashes,
    }
    (analysis_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=ROOT / "inputs")
    parser.add_argument("--analysis-dir", type=Path, default=ROOT / "analysis")
    parser.add_argument("--figure-dir", type=Path, default=ROOT / "figures")
    args = parser.parse_args()
    run(args.input_dir, args.analysis_dir, args.figure_dir)


if __name__ == "__main__":
    main()
