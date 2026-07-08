"""Rank reversal probability analysis from MC samples.

Computes P(A > B), P(tie), P(B > A) for every pair of structures
at specified rated power and material model using MC raw samples.

Tie threshold selection rationale:
  Method A (5th percentile of |onshore - bottom_fixed| at 15MW GFRP): 0.0798 g-CO2/kWh
  Method B (constant absolute): 0.5 g-CO2/kWh
  Method C (relative, 1%):      ~0.12 g-CO2/kWh at 15MW (≈ LCA model uncertainty floor)
  ADOPTED: Method C (1% relative threshold)
  Reason: 1% relative difference represents a practically insignificant difference
  at the scale of LCA uncertainty; consistent with LCA reporting conventions.

Outputs:
  results/latest/rank_reversal_probability.csv
  results/latest/rank_reversal_all_mw.csv  (all MW values)
"""
from __future__ import annotations

import argparse
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MC_PARQUET = PROJECT_ROOT / "results" / "latest" / "uncertainty" / "mc_raw_samples.parquet"
OUT_DIR = PROJECT_ROOT / "results" / "latest"

# 引き分け判定閾値（相対差 1%）
TIE_THRESHOLD_PCT = 1.0


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


def compute_rank_reversal(
    pivoted: pd.DataFrame,
    structures: list[str],
    n_samples: int,
    rated_power_mw: float,
    material_model: str,
) -> list[dict]:
    """Compute rank reversal probabilities for all structure pairs.

    For each pair (A, B):
        P(A > B)  = fraction of samples where intensity_A > intensity_B and not tie
        P(tie)    = fraction of samples where |intensity_A - intensity_B| / mean < threshold
        P(B > A)  = 1 - P(A > B) - P(tie)   [complement; verified to sum to 1.0]
    """
    results = []
    for struct_a, struct_b in combinations(structures, 2):
        col_a = pivoted[struct_a].values
        col_b = pivoted[struct_b].values
        diff = col_a - col_b  # positive → A > B
        mean_gwp = (col_a + col_b) / 2.0

        # Tie: relative difference < threshold
        relative_diff_pct = np.abs(diff) / mean_gwp * 100.0
        is_tie = relative_diff_pct <= TIE_THRESHOLD_PCT

        p_a_gt_b = float((diff > 0).mean())
        p_b_gt_a = float((diff < 0).mean())
        p_tie = float(is_tie.mean())

        # Re-normalize to ensure sum = 1.0 (tie overrides ordering)
        p_a_gt_b_no_tie = float(((diff > 0) & ~is_tie).mean())
        p_b_gt_a_no_tie = float(((diff < 0) & ~is_tie).mean())
        total = p_a_gt_b_no_tie + p_b_gt_a_no_tie + p_tie

        # Symmetry assertion
        assert abs(total - 1.0) < 1e-6, (
            f"Probability sum != 1.0 for ({struct_a}, {struct_b}): "
            f"P(A>B)={p_a_gt_b_no_tie:.6f}, P(B>A)={p_b_gt_a_no_tie:.6f}, P(tie)={p_tie:.6f}, sum={total:.6f}"
        )

        mean_a = float(col_a.mean())
        mean_b = float(col_b.mean())
        base_rank_a_lower = mean_a < mean_b  # True if A has lower GWP (better)

        results.append(
            {
                "rated_power_mw": rated_power_mw,
                "material_model": material_model,
                "structure_a": struct_a,
                "structure_b": struct_b,
                "mean_intensity_a": round(mean_a, 4),
                "mean_intensity_b": round(mean_b, 4),
                "p_a_lower_gwp": round(p_a_gt_b_no_tie if not base_rank_a_lower else p_b_gt_a_no_tie, 4),
                "p_b_lower_gwp": round(p_b_gt_a_no_tie if not base_rank_a_lower else p_a_gt_b_no_tie, 4),
                "p_tie": round(p_tie, 4),
                "p_a_gt_b": round(p_a_gt_b_no_tie, 4),
                "p_b_gt_a": round(p_b_gt_a_no_tie, 4),
                "base_rank_a_lower": base_rank_a_lower,
                "rank_reversal_prob": round(
                    p_b_gt_a_no_tie if base_rank_a_lower else p_a_gt_b_no_tie, 4
                ),
                "n_samples": n_samples,
                "tie_threshold_pct": TIE_THRESHOLD_PCT,
            }
        )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank reversal probability from MC samples")
    parser.add_argument(
        "--rated-power", type=float, default=15.0,
        help="Primary rated power for summary output (default: 15 MW)",
    )
    parser.add_argument(
        "--material-model", default="gfrp",
        help="Material model to analyze (default: gfrp)",
    )
    parser.add_argument(
        "--all-mw", action="store_true",
        help="Also compute for all available MW values",
    )
    parser.add_argument(
        "--mc-file", type=Path, default=MC_PARQUET,
        help="Input MC parquet file",
    )
    args = parser.parse_args()

    try:
        df = _load_mc_samples(args.mc_file)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Loading MC samples from {args.mc_file}...")
    n_samples = int(df["sample_id"].max()) + 1
    structures = sorted(df["structure_type"].unique().tolist())

    print(f"Samples: {n_samples:,}, Structures: {structures}")
    print(f"Tie threshold: {TIE_THRESHOLD_PCT}% relative difference")

    # Primary analysis at specified power + material
    mask = (df["rated_power_mw"] == args.rated_power) & (df["material_model"] == args.material_model)
    sub = df[mask]
    if sub.empty:
        print(f"ERROR: No data for {args.rated_power}MW / {args.material_model}", file=sys.stderr)
        sys.exit(1)

    pivoted = sub.pivot_table(
        index="sample_id", columns="structure_type", values="intensity_gco2_per_kwh", aggfunc="mean"
    )
    # Ensure all structures present
    available_structures = [s for s in structures if s in pivoted.columns]

    records = compute_rank_reversal(pivoted, available_structures, n_samples, args.rated_power, args.material_model)
    df_out = pd.DataFrame(records)

    print("\n=== Rank Reversal Probability Summary ===")
    print(f"(rated_power={args.rated_power}MW, material={args.material_model})")
    display_cols = ["structure_a", "structure_b", "mean_intensity_a", "mean_intensity_b",
                    "rank_reversal_prob", "p_tie", "base_rank_a_lower"]
    print(df_out[display_cols].to_string(index=False))

    summary_path = OUT_DIR / "rank_reversal_probability.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(summary_path, index=False)
    print(f"\nSummary saved: {summary_path}")

    # Phase β checks
    print("\n=== Phase β Checks ===")

    # 1. Symmetry (already asserted in compute_rank_reversal, print for verification)
    print("✓ Symmetry: P(A>B) + P(B>A) + P(tie) = 1.0 for all pairs")

    # 2. Extreme values
    extreme = df_out[df_out["rank_reversal_prob"] >= 0.999]
    if extreme.empty:
        print("✓ No extreme rank reversal probabilities (>= 99.9%)")
    else:
        print(f"⚠ Extreme rank reversal (>= 99.9%):")
        print(extreme[["structure_a", "structure_b", "rank_reversal_prob"]].to_string(index=False))

    # 3. Convergence check (compare with n//2 samples)
    n_half = n_samples // 2
    sub_half = df[mask & (df["sample_id"] < n_half)]
    pivoted_half = sub_half.pivot_table(
        index="sample_id", columns="structure_type", values="intensity_gco2_per_kwh", aggfunc="mean"
    )
    records_half = compute_rank_reversal(pivoted_half, available_structures, n_half, args.rated_power, args.material_model)
    df_half = pd.DataFrame(records_half)
    max_diff = (df_out["rank_reversal_prob"] - df_half["rank_reversal_prob"]).abs().max()
    print(f"{'✓' if max_diff < 0.005 else '⚠'} Convergence: max |Δrr_prob| N/2 vs N = {max_diff:.5f} {'(< 0.005 OK)' if max_diff < 0.005 else '(>= 0.005 WARNING)'}")

    # All-MW analysis
    if args.all_mw:
        all_records = []
        for mw in sorted(df["rated_power_mw"].unique()):
            for mat in sorted(df["material_model"].unique()):
                sub_mw = df[(df["rated_power_mw"] == mw) & (df["material_model"] == mat)]
                if sub_mw.empty:
                    continue
                pivoted_mw = sub_mw.pivot_table(
                    index="sample_id", columns="structure_type", values="intensity_gco2_per_kwh", aggfunc="mean"
                )
                av_structs = [s for s in structures if s in pivoted_mw.columns]
                recs = compute_rank_reversal(pivoted_mw, av_structs, n_samples, mw, mat)
                all_records.extend(recs)

        df_all = pd.DataFrame(all_records)
        all_path = OUT_DIR / "rank_reversal_all_mw.csv"
        df_all.to_csv(all_path, index=False)
        print(f"\nAll-MW results saved: {all_path} ({len(df_all)} rows)")


if __name__ == "__main__":
    main()
