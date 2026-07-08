"""T2: CF-equalized sensitivity analysis.

Tests what happens to structure rankings when all structures use the same CF.
Scenarios:
  - cf_equalized_035: all structures CF=0.35 (midpoint)
  - cf_equalized_030: all structures CF=0.30 (onshore value)
  - cf_equalized_040: all structures CF=0.40 (bottom-fixed value)

Outputs:
  results/latest/cf_equalized_sensitivity.csv
  results/latest/analysis/cf_equalized_ranking_plot.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MATRIX_CSV = PROJECT_ROOT / "results" / "latest" / "matrix_latest.csv"
OUT_CSV = PROJECT_ROOT / "results" / "latest" / "cf_equalized_sensitivity.csv"
OUT_PNG = PROJECT_ROOT / "results" / "latest" / "analysis" / "cf_equalized_ranking_plot.png"

STRUCTURE_ORDER = ["onshore", "bottom_fixed", "fawt", "semisubmersible", "spar"]
STRUCTURE_LABELS = ["Onshore", "Bottom-fixed", "FAWT", "Semisubmersible", "Spar"]

# Baseline CF values (frozen)
BASELINE_CF = {
    "onshore":         0.30,
    "bottom_fixed":    0.40,
    "fawt":            0.40,
    "semisubmersible": 0.42,
    "spar":            0.38,
}

EQUALIZED_CF_SCENARIOS = {
    "baseline":        None,    # use original CF (control)
    "cf_equalized_030": 0.30,
    "cf_equalized_035": 0.35,
    "cf_equalized_040": 0.40,
}

# Colors
SCENARIO_COLORS = {
    "baseline":         "#333333",
    "cf_equalized_030": "#E69F00",
    "cf_equalized_035": "#0072B2",
    "cf_equalized_040": "#009E73",
}
SCENARIO_DISPLAY = {
    "baseline":         "Baseline (original CF)",
    "cf_equalized_030": "All CF = 0.30 (onshore parity)",
    "cf_equalized_035": "All CF = 0.35 (midpoint)",
    "cf_equalized_040": "All CF = 0.40 (offshore parity)",
}


def _recalc_intensity(row: pd.Series, new_cf: float) -> float:
    """Recalculate GWP intensity with a new capacity factor.

    intensity = total_gwp_kgco2 / (rated_power_mw * 8760 * lifetime * CF)
    → scaled from baseline: intensity_new = intensity_base * CF_base / CF_new
    """
    original_cf = BASELINE_CF[row["structure_type"]]
    return row["intensity_gco2_per_kwh"] * original_cf / new_cf


def main() -> None:
    matrix = pd.read_csv(MATRIX_CSV)

    # Focus on GFRP, 15MW as representative case (also compute all MW)
    results = []
    for scenario, cf_val in EQUALIZED_CF_SCENARIOS.items():
        for _, row in matrix.iterrows():
            if cf_val is None:
                intensity = row["intensity_gco2_per_kwh"]
                effective_cf = BASELINE_CF[row["structure_type"]]
            else:
                intensity = _recalc_intensity(row, cf_val)
                effective_cf = cf_val
            results.append({
                "scenario": scenario,
                "effective_cf": effective_cf,
                "structure_type": row["structure_type"],
                "rated_power_mw": row["rated_power_mw"],
                "material_model": row["material_model"],
                "intensity_gco2_per_kwh": intensity,
            })

    df = pd.DataFrame(results)

    # Rank within each scenario × MW × material_model group
    df["rank"] = df.groupby(["scenario", "rated_power_mw", "material_model"])[
        "intensity_gco2_per_kwh"
    ].rank(method="min")

    df.to_csv(OUT_CSV, index=False)
    print(f"T2 output: {OUT_CSV} ({len(df)} rows)")

    # --- Summary print: 15MW, GFRP rankings ---
    sub = df[(df["rated_power_mw"] == 15.0) & (df["material_model"] == "gfrp")]
    print("\n=== 15MW GFRP: GWP intensity by CF scenario ===")
    pivot = sub.pivot_table(
        index="structure_type", columns="scenario", values="intensity_gco2_per_kwh"
    )[list(EQUALIZED_CF_SCENARIOS.keys())]
    print(pivot.reindex(STRUCTURE_ORDER).round(2).to_string())

    print("\n=== 15MW GFRP: Rank by CF scenario ===")
    pivot_rank = sub.pivot_table(
        index="structure_type", columns="scenario", values="rank"
    )[list(EQUALIZED_CF_SCENARIOS.keys())]
    print(pivot_rank.reindex(STRUCTURE_ORDER).astype(int).to_string())

    # --- Plot ---
    sub15 = sub.copy()
    fig, axes = plt.subplots(1, 4, figsize=(14, 5), sharey=True)
    fig.suptitle(
        "GWP intensity under equalized CF assumptions\n(15 MW, GFRP blade)",
        fontsize=12, y=1.01,
    )

    x = np.arange(len(STRUCTURE_ORDER))
    bar_width = 0.18
    offsets = np.linspace(
        -(len(EQUALIZED_CF_SCENARIOS) - 1) / 2,
        (len(EQUALIZED_CF_SCENARIOS) - 1) / 2,
        len(EQUALIZED_CF_SCENARIOS),
    ) * bar_width

    # Single grouped-bar plot
    fig2, ax2 = plt.subplots(figsize=(10, 5.5))

    for j, (scenario, _) in enumerate(EQUALIZED_CF_SCENARIOS.items()):
        vals = [
            sub15[sub15["structure_type"] == s]["intensity_gco2_per_kwh"].values[0]
            for s in STRUCTURE_ORDER
        ]
        ax2.bar(
            x + offsets[j], vals, bar_width,
            color=SCENARIO_COLORS[scenario], alpha=0.85,
            label=SCENARIO_DISPLAY[scenario], zorder=3,
        )

    ax2.set_xlabel("Structure type", fontsize=12)
    ax2.set_ylabel("GWP intensity (g-CO₂/kWh)", fontsize=12)
    ax2.set_title("Sensitivity of structure ranking to CF assumption\n(15 MW, GFRP)", fontsize=12)
    ax2.set_xticks(x)
    ax2.set_xticklabels(STRUCTURE_LABELS, fontsize=11)
    ax2.tick_params(axis="y", labelsize=11)
    ax2.legend(fontsize=9.5, loc="upper right", framealpha=0.9)
    ax2.grid(True, axis="y", linestyle=":", alpha=0.4)
    fig2.tight_layout()

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig2.savefig(OUT_PNG, dpi=600, bbox_inches="tight")
    plt.close(fig2)
    plt.close(fig)
    print(f"T2 plot: {OUT_PNG}")

    # --- Rank change summary ---
    baseline_ranks = pivot_rank["baseline"].reindex(STRUCTURE_ORDER)
    print("\n=== Rank changes from baseline ===")
    for scenario in list(EQUALIZED_CF_SCENARIOS.keys())[1:]:
        new_ranks = pivot_rank[scenario].reindex(STRUCTURE_ORDER)
        changes = new_ranks - baseline_ranks
        swaps = changes[changes != 0]
        if swaps.empty:
            print(f"  {scenario}: No rank changes")
        else:
            print(f"  {scenario}: Rank changes → {swaps.to_dict()}")


if __name__ == "__main__":
    main()
