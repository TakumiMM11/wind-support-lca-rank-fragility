"""EoL credit sensitivity analysis: run 3 scenarios and summarise.

Scenarios:
  cutoff   -- eol_credit_rate = 0.0  (no virgin-material credit at all)
  credit50 -- eol_credit_rate = 0.5  (50% credit realization)
  current  -- eol_credit_rate = None (use model default per structure)

Writes:
  results/latest/eol_sensitivity_summary.csv
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = PROJECT_ROOT / "venv" / "bin" / "python"
MATRIX_CMD = [str(PYTHON), "-m", "src.cli.main", "matrix",
               "--site-class", "baseline",
               "--assumption-point", "base",
               "--no-archive-old"]
OUT_DIR = PROJECT_ROOT / "results" / "latest"
SUMMARY_FILE = OUT_DIR / "eol_sensitivity_summary.csv"

SCENARIOS = [
    {"label": "cutoff",   "extra_args": ["--eol-credit-rate", "0.0"]},
    {"label": "credit50", "extra_args": ["--eol-credit-rate", "0.5"]},
    {"label": "current",  "extra_args": []},
]


def run_scenario(label: str, extra_args: list[str]) -> pd.DataFrame:
    with tempfile.TemporaryDirectory() as tmp:
        out_csv = Path(tmp) / "matrix.csv"
        cmd = MATRIX_CMD + extra_args + ["--output-file", str(out_csv)]
        print(f"\n[EoL sensitivity] Running scenario: {label}")
        print("  CMD:", " ".join(cmd))
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout[-2000:] if result.stdout else "")
            print(result.stderr[-2000:] if result.stderr else "", file=sys.stderr)
            raise RuntimeError(f"matrix command failed for scenario '{label}' (exit={result.returncode})")
        df = pd.read_csv(out_csv)
        df["eol_scenario"] = label
        return df


def main() -> None:
    dfs = []
    for sc in SCENARIOS:
        df = run_scenario(sc["label"], sc["extra_args"])
        dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True)

    # Build pivot summary: intensity_gco2_per_kwh for each (structure, power, model, scenario)
    key_cols = ["structure_type", "rated_power_mw", "material_model", "eol_scenario"]
    summary_cols = key_cols + ["intensity_gco2_per_kwh", "l4_eol_kgco2", "total_gwp_kgco2",
                               "capacity_factor", "assumption_point"]
    summary = combined[summary_cols].copy()

    # Pivot to wide format for easy comparison
    pivot = summary.pivot_table(
        index=["structure_type", "rated_power_mw", "material_model"],
        columns="eol_scenario",
        values="intensity_gco2_per_kwh",
    ).reset_index()
    pivot.columns.name = None

    # Ensure column order
    scenario_labels = [sc["label"] for sc in SCENARIOS]
    for col in scenario_labels:
        if col not in pivot.columns:
            pivot[col] = float("nan")

    # Delta columns (cutoff - current, credit50 - current)
    pivot["delta_cutoff_vs_current_gpkwh"] = pivot["cutoff"] - pivot["current"]
    pivot["delta_credit50_vs_current_gpkwh"] = pivot["credit50"] - pivot["current"]

    # Physical check: cutoff >= current >= credit50 (more credit → lower GWP)
    pivot["check_cutoff_ge_current"] = pivot["cutoff"] >= pivot["current"] - 1e-6
    pivot["check_current_ge_credit50"] = pivot["current"] >= pivot["credit50"] - 1e-6

    all_pass = pivot["check_cutoff_ge_current"].all() and pivot["check_current_ge_credit50"].all()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Save full long-form CSV
    summary.sort_values(["structure_type", "rated_power_mw", "material_model", "eol_scenario"]).to_csv(
        OUT_DIR / "eol_sensitivity_long.csv", index=False
    )

    # Save pivot summary
    pivot.sort_values(["structure_type", "rated_power_mw", "material_model"]).to_csv(
        SUMMARY_FILE, index=False
    )

    print(f"\n[EoL sensitivity] Summary written to: {SUMMARY_FILE}")
    print(f"[EoL sensitivity] Long form written to: {OUT_DIR / 'eol_sensitivity_long.csv'}")
    print(f"\n[EoL sensitivity] Physical ordering check: {'PASS' if all_pass else 'FAIL'}")

    # Print compact table
    print("\n--- intensity (g-CO2/kWh) by scenario ---")
    display_cols = ["structure_type", "rated_power_mw", "material_model",
                    "cutoff", "current", "credit50",
                    "delta_cutoff_vs_current_gpkwh", "delta_credit50_vs_current_gpkwh"]
    available = [c for c in display_cols if c in pivot.columns]
    print(pivot[available].to_string(index=False, float_format="{:.3f}".format))

    if not all_pass:
        failures = pivot[~(pivot["check_cutoff_ge_current"] & pivot["check_current_ge_credit50"])]
        print("\n[WARNING] Physical ordering violated for:")
        print(failures[["structure_type", "rated_power_mw", "material_model",
                         "cutoff", "current", "credit50"]].to_string(index=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
