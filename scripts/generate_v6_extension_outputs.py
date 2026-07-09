#!/usr/bin/env python3
"""Generate v6 extension evidence outputs from the manuscript-linked dataset."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "manuscript_v4_revision_20260319"
OUT = ROOT / "results" / "v6_extension_20260413"

STRUCTURE_LABELS = {
    "onshore": "Onshore",
    "bottom_fixed": "Bottom-fixed",
    "fawt": "FAWT$^\\dagger$",
    "semisubmersible": "Semisub.",
    "spar": "Spar",
}


def build_cfrp_phase_delta() -> pd.DataFrame:
    df = pd.read_csv(SRC / "matrix_latest.csv")
    sub = df[(df["rated_power_mw"] == 15.0) & (df["material_model"].isin(["gfrp", "cfrp"]))].copy()
    wide = (
        sub.set_index(["structure_type", "material_model"])[
            [
                "l1_manufacturing_kgco2",
                "l2_transport_kgco2",
                "l3_o_and_m_kgco2",
                "l4_eol_kgco2",
                "total_gwp_kgco2",
                "intensity_gco2_per_kwh",
            ]
        ]
        .unstack("material_model")
        .sort_index()
    )
    out = pd.DataFrame(index=wide.index)
    out["delta_l1_kgco2"] = (
        wide[("l1_manufacturing_kgco2", "cfrp")] - wide[("l1_manufacturing_kgco2", "gfrp")]
    )
    out["delta_l2_kgco2"] = wide[("l2_transport_kgco2", "cfrp")] - wide[("l2_transport_kgco2", "gfrp")]
    out["delta_l3_kgco2"] = wide[("l3_o_and_m_kgco2", "cfrp")] - wide[("l3_o_and_m_kgco2", "gfrp")]
    out["delta_l4_kgco2"] = wide[("l4_eol_kgco2", "cfrp")] - wide[("l4_eol_kgco2", "gfrp")]
    out["delta_l234_kgco2"] = out["delta_l2_kgco2"] + out["delta_l3_kgco2"] + out["delta_l4_kgco2"]
    out["delta_total_kgco2"] = wide[("total_gwp_kgco2", "cfrp")] - wide[("total_gwp_kgco2", "gfrp")]
    out["delta_intensity_gpkwh"] = (
        wide[("intensity_gco2_per_kwh", "cfrp")] - wide[("intensity_gco2_per_kwh", "gfrp")]
    )
    out = out.reset_index()
    out.to_csv(OUT / "cfrp_phase_delta_15mw.csv", index=False)

    plot_df = out.copy()
    plot_df["delta_l1_kt"] = plot_df["delta_l1_kgco2"] / 1e3
    plot_df["delta_l234_kt"] = plot_df["delta_l234_kgco2"] / 1e3
    plot_df["delta_total_kt"] = plot_df["delta_total_kgco2"] / 1e3

    order = ["onshore", "bottom_fixed", "fawt", "semisubmersible", "spar"]
    plot_df["structure_type"] = pd.Categorical(plot_df["structure_type"], order, ordered=True)
    plot_df = plot_df.sort_values("structure_type")

    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    x = range(len(plot_df))
    ax.bar(x, plot_df["delta_l1_kt"], color="#c65146", label="L1 material/manufacturing increase")
    ax.bar(x, plot_df["delta_l234_kt"], color="#3b7ea1", label="L2-L4 offset")
    ax.scatter(x, plot_df["delta_total_kt"], color="black", zorder=3, label="Net total delta")
    ax.axhline(0.0, color="0.25", linewidth=1.0)
    ax.set_xticks(list(x), [STRUCTURE_LABELS[s] for s in plot_df["structure_type"]], rotation=20)
    ax.set_ylabel("Delta (kt-CO2eq)")
    ax.grid(axis="y", alpha=0.25)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.01),
        ncol=3,
        frameon=False,
        columnspacing=1.4,
        handletextpad=0.6,
    )
    fig.tight_layout(rect=[0, 0.12, 1, 1])
    fig.savefig(OUT / "cfrp_phase_delta_15mw.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out


def build_fawt_threshold() -> pd.DataFrame:
    intens = pd.read_csv(SRC / "analysis" / "intensity_15mw_table.csv").set_index("structure_type")
    stress = pd.read_csv(SRC / "fawt_mass_sensitivity_stress_test.csv")
    stress_15 = stress[stress["rated_power_mw"] == 15].iloc[0]

    fawt_base = float(intens.loc["fawt", "gfrp"])
    fawt_plus30 = float(stress_15["intensity_+30pct_gco2_per_kwh"])

    rows = []
    for comparator in ["semisubmersible", "spar"]:
        comp_val = float(intens.loc[comparator, "gfrp"])
        uplift = comp_val - fawt_base
        rows.append(
            {
                "reference_case": "15 MW GFRP baseline",
                "fawt_base_intensity_gpkwh": fawt_base,
                "comparator_structure": comparator,
                "comparator_intensity_gpkwh": comp_val,
                "allowable_uplift_gpkwh": uplift,
                "allowable_uplift_pct_of_fawt_base": uplift / fawt_base * 100.0,
                "fawt_plus30pct_stress_intensity_gpkwh": fawt_plus30,
                "plus30pct_case_crosses_comparator": fawt_plus30 > comp_val,
                "interpretation": "Intensity-based bound only; no structural-mass threshold claimed",
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "fawt_intensity_threshold_15mw.csv", index=False)
    return out


def build_rank_fragility() -> pd.DataFrame:
    df = pd.read_csv(SRC / "rank_reversal_probability.csv").copy()
    # In the manuscript-linked build, `rank_reversal_prob` stores point-estimate support.
    df["point_estimate_support_prob"] = df["rank_reversal_prob"]
    df["corrected_reversal_prob"] = 1.0 - df["point_estimate_support_prob"] - df["p_tie"]
    df["corrected_reversal_prob"] = df["corrected_reversal_prob"].clip(lower=0.0)
    df["pair_label"] = df["structure_a"].map(STRUCTURE_LABELS) + " vs " + df["structure_b"].map(STRUCTURE_LABELS)
    df = df.sort_values(["corrected_reversal_prob", "p_tie"], ascending=[False, False]).copy()

    plot_df = df.copy()
    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    y = range(len(plot_df))
    ax.barh(y, plot_df["point_estimate_support_prob"], color="#4c956c", label="Supports point estimate")
    ax.barh(
        y,
        plot_df["corrected_reversal_prob"],
        left=plot_df["point_estimate_support_prob"],
        color="#c65146",
        label="Reverses point estimate",
    )
    ax.barh(
        y,
        plot_df["p_tie"],
        left=plot_df["point_estimate_support_prob"] + plot_df["corrected_reversal_prob"],
        color="#9aa0a6",
        label="Tie (1% threshold)",
    )
    ax.set_yticks(list(y), plot_df["pair_label"].tolist())
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel("Probability")
    ax.grid(axis="x", alpha=0.25)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.01),
        ncol=3,
        frameon=False,
        columnspacing=1.4,
        handletextpad=0.6,
    )
    ax.invert_yaxis()
    fig.tight_layout(rect=[0, 0.12, 1, 1])
    fig.savefig(OUT / "rank_fragility_pairs_15mw.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    df = df.rename(
        columns={
            "structure_a": "pair_member_a",
            "structure_b": "pair_member_b",
            "p_tie": "tie_prob",
        }
    )
    df.to_csv(OUT / "rank_fragility_corrected_15mw.csv", index=False)
    return df


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    build_cfrp_phase_delta()
    build_fawt_threshold()
    build_rank_fragility()
    print(f"Wrote outputs to {OUT}")


if __name__ == "__main__":
    main()
