"""Back-casting literature benchmark validation script.

Usage:
  Point estimate only (D-2a):
    python scripts/run_backcasting_validation.py

  With MC-derived 95% CI (D-2b, requires mc_raw_samples.parquet):
    python scripts/run_backcasting_validation.py --with-ci

Outputs:
  Point estimate: results/latest/benchmark_range_check_point.csv
  With CI:        results/latest/benchmark_range_check.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_FILE = PROJECT_ROOT / "data" / "backcasting_benchmark.json"
MATRIX_CSV = PROJECT_ROOT / "results" / "latest" / "matrix_latest.csv"
MC_PARQUET = PROJECT_ROOT / "results" / "latest" / "uncertainty" / "mc_raw_samples.parquet"
OUT_DIR = PROJECT_ROOT / "results" / "latest"


def _load_mc_samples(path: Path) -> pd.DataFrame:
    """Load MC samples from parquet or CSV fallback."""
    if path.exists():
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        try:
            return pd.read_parquet(path)
        except ImportError:
            csv_fallback = path.with_suffix(".csv")
            if csv_fallback.exists():
                return pd.read_csv(csv_fallback)
            raise

    csv_fallback = path.with_suffix(".csv")
    if csv_fallback.exists():
        return pd.read_csv(csv_fallback)

    raise FileNotFoundError(f"MC file not found: {path} (or {csv_fallback})")


def _nearest_mw(matrix: pd.DataFrame, structure: str, target_mw: float) -> tuple[float, pd.Series]:
    """Return (actual_mw, row) where actual_mw is closest to target_mw."""
    sub = matrix[matrix["structure_type"] == structure].copy()
    if sub.empty:
        raise ValueError(f"No data for structure='{structure}'")
    available_mws = sub["rated_power_mw"].unique()
    closest_mw = float(min(available_mws, key=lambda m: abs(m - target_mw)))
    row = sub[sub["rated_power_mw"] == closest_mw].iloc[0]
    return closest_mw, row


def main() -> None:
    parser = argparse.ArgumentParser(description="Back-casting benchmark validation")
    parser.add_argument(
        "--with-ci",
        action="store_true",
        help="Add MC-derived 95%% CI columns (requires mc_raw_samples.parquet)",
    )
    parser.add_argument(
        "--material-model",
        default="gfrp",
        help="Material model to use for model GWP lookup (default: gfrp)",
    )
    args = parser.parse_args()

    if not BENCHMARK_FILE.exists():
        print(f"ERROR: Benchmark file not found: {BENCHMARK_FILE}", file=sys.stderr)
        sys.exit(1)
    if not MATRIX_CSV.exists():
        print(f"ERROR: Matrix CSV not found: {MATRIX_CSV}", file=sys.stderr)
        sys.exit(1)

    benchmarks = json.loads(BENCHMARK_FILE.read_text())
    matrix = pd.read_csv(MATRIX_CSV)

    # Filter to selected material model
    mat = args.material_model.lower()
    if mat not in matrix["material_model"].unique():
        available = matrix["material_model"].unique().tolist()
        print(f"ERROR: material_model '{mat}' not found. Available: {available}", file=sys.stderr)
        sys.exit(1)
    matrix_filtered = matrix[matrix["material_model"] == mat]

    # Load MC data if needed
    mc_df: pd.DataFrame | None = None
    if args.with_ci:
        try:
            mc_df = _load_mc_samples(MC_PARQUET)
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    results = []
    for case in benchmarks["cases"]:
        structure = case["structure"]
        target_mw = float(case["capacity_mw"])
        bm_low = float(case["benchmark_low_gco2_per_kwh"])
        bm_high = float(case["benchmark_high_gco2_per_kwh"])

        # Find nearest available MW
        try:
            actual_mw, row = _nearest_mw(matrix_filtered, structure, target_mw)
        except ValueError as e:
            print(f"  SKIP {case['id']} {structure} {target_mw}MW: {e}", file=sys.stderr)
            continue

        model_gwp = float(row["intensity_gco2_per_kwh"])
        mw_note = f"nearest={actual_mw}MW" if actual_mw != target_mw else ""

        # CI calculation
        ci_low: float | None = None
        ci_high: float | None = None
        if args.with_ci and mc_df is not None:
            mc_sub = mc_df[
                (mc_df["structure_type"] == structure)
                & (mc_df["rated_power_mw"] == actual_mw)
                & (mc_df["material_model"] == mat)
            ]["intensity_gco2_per_kwh"]
            if not mc_sub.empty:
                ci_low = float(np.quantile(mc_sub, 0.025))
                ci_high = float(np.quantile(mc_sub, 0.975))

        in_range = bm_low <= model_gwp <= bm_high
        bm_mid = (bm_low + bm_high) / 2.0
        deviation_pct = (model_gwp - bm_mid) / bm_mid * 100.0
        reason_code = "" if in_range else ("OVER" if model_gwp > bm_high else "UNDER")

        # CI range check: does the CI overlap with the benchmark range?
        # (partial overlap is sufficient; full containment would be too strict
        #  given that MC uncertainty spans the full CF/EoL parameter space)
        if ci_low is not None and ci_high is not None:
            in_range_with_ci = (ci_low <= bm_high) and (ci_high >= bm_low)
        else:
            in_range_with_ci = None

        results.append({
            "case_id": case["id"],
            "structure": structure,
            "benchmark_mw": target_mw,
            "model_mw_used": actual_mw,
            "mw_note": mw_note,
            "material_model": mat,
            "model_gwp_gpkwh": round(model_gwp, 3),
            "model_gwp_ci_low_gpkwh": round(ci_low, 3) if ci_low is not None else np.nan,
            "model_gwp_ci_high_gpkwh": round(ci_high, 3) if ci_high is not None else np.nan,
            "benchmark_low_gpkwh": bm_low,
            "benchmark_high_gpkwh": bm_high,
            "in_range": in_range,
            "in_range_with_ci": in_range_with_ci if in_range_with_ci is not None else np.nan,
            "deviation_from_midpoint_pct": round(deviation_pct, 1),
            "reason_code": reason_code,
        })

    if not results:
        print("ERROR: No cases matched. Check benchmark and matrix files.", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(results)
    n_in_range = int(df["in_range"].sum())
    n_total = len(df)
    in_range_pct = n_in_range / n_total * 100.0

    print("\n=== Back-casting Validation Results ===")
    display_cols = [
        "case_id", "structure", "benchmark_mw", "model_mw_used",
        "model_gwp_gpkwh", "benchmark_low_gpkwh", "benchmark_high_gpkwh",
        "in_range", "deviation_from_midpoint_pct", "reason_code"
    ]
    print(df[display_cols].to_string(index=False))
    print(f"\nin_range: {n_in_range}/{n_total} ({in_range_pct:.1f}%)")

    if args.with_ci:
        output_path = OUT_DIR / "benchmark_range_check.csv"
    else:
        output_path = OUT_DIR / "benchmark_range_check_point.csv"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Output: {output_path}")

    if in_range_pct < 80.0:
        print(f"\nWARNING: in_range rate {in_range_pct:.1f}% < 80% threshold. Review model or benchmarks.")
        sys.exit(1)


if __name__ == "__main__":
    main()
