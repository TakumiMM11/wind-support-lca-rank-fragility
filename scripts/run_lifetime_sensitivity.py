"""Lifetime sensitivity analysis: 20 / 25 / 30 year operational lifetime.

Runs MC (n=1000 per combo, seed=42) for each lifetime and reports the
change in GWP intensity relative to the baseline 25-year case.

Output:
    results/latest/uncertainty/lifetime_sensitivity.csv
    results/latest/uncertainty/lifetime_sensitivity_summary.csv

Usage:
    python scripts/run_lifetime_sensitivity.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

LIFETIMES = [20, 25, 30]
STRUCTURES = ["onshore", "bottom_fixed", "semisubmersible", "spar", "fawt"]
POWERS = [2.0, 5.0, 10.0, 15.0]
MATERIALS = ["gfrp", "cfrp", "rcfrp", "rrcfrp"]
N_SAMPLES = 1_000   # sufficient for median/percentile comparison
SEED = 42

OUTPUT_DIR = PROJECT_ROOT / "results" / "latest" / "uncertainty"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from src.lca.uncertainty import MCEngine

    all_summaries = []

    for lifetime in LIFETIMES:
        logger.info("=== Lifetime = %d years ===", lifetime)
        engine = MCEngine(
            n_samples=N_SAMPLES,
            seed=SEED,
            assumptions_path=PROJECT_ROOT / "data" / "model_assumptions.json",
            lci_dir=PROJECT_ROOT / "data" / "lci",
            lifetime_years=lifetime,
        )
        df = engine.run(
            structures=STRUCTURES,
            rated_powers=POWERS,
            material_models=MATERIALS,
        )
        df["lifetime_years"] = lifetime

        # Compute summary statistics
        grp = df.groupby(["structure_type", "rated_power_mw", "material_model", "lifetime_years"])
        summary = grp["intensity_gco2_per_kwh"].agg(
            median="median",
            p2_5=lambda x: x.quantile(0.025),
            p97_5=lambda x: x.quantile(0.975),
        ).reset_index()
        all_summaries.append(summary)
        logger.info("Lifetime %d: median range %.2f – %.2f g-CO2/kWh",
                    lifetime,
                    summary["median"].min(),
                    summary["median"].max())

    combined = pd.concat(all_summaries, ignore_index=True)

    # Pivot to show change relative to 25yr
    pivot = combined.pivot_table(
        index=["structure_type", "rated_power_mw", "material_model"],
        columns="lifetime_years",
        values="median",
    ).reset_index()
    pivot.columns.name = None
    col_25 = 25
    pivot["delta_20yr_pct"] = (pivot[20] - pivot[col_25]) / pivot[col_25] * 100
    pivot["delta_30yr_pct"] = (pivot[30] - pivot[col_25]) / pivot[col_25] * 100
    pivot = pivot.rename(columns={20: "median_20yr", 25: "median_25yr", 30: "median_30yr"})

    # Save outputs
    combined_path = OUTPUT_DIR / "lifetime_sensitivity.csv"
    summary_path = OUTPUT_DIR / "lifetime_sensitivity_summary.csv"
    combined.to_csv(combined_path, index=False)
    pivot.to_csv(summary_path, index=False)
    logger.info("Saved: %s", combined_path)
    logger.info("Saved: %s", summary_path)

    # Print summary for key configurations
    print("\n=== Lifetime Sensitivity — Key Configurations (15 MW, GFRP) ===")
    key = pivot[
        (pivot["rated_power_mw"] == 15.0) & (pivot["material_model"] == "gfrp")
    ][["structure_type", "median_20yr", "median_25yr", "median_30yr",
       "delta_20yr_pct", "delta_30yr_pct"]].copy()
    key = key.sort_values("median_25yr")
    print(key.to_string(index=False, float_format="{:.2f}".format))

    print("\n=== Lifetime Sensitivity — All Structures, All MW, GFRP ===")
    gfrp_all = pivot[pivot["material_model"] == "gfrp"][
        ["structure_type", "rated_power_mw", "median_20yr", "median_25yr",
         "median_30yr", "delta_20yr_pct", "delta_30yr_pct"]
    ].sort_values(["structure_type", "rated_power_mw"])
    print(gfrp_all.to_string(index=False, float_format="{:.2f}".format))

    print(f"\nFull results saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
