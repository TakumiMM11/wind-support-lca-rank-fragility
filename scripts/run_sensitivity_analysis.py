"""PRCC (Partial Rank Correlation Coefficient) sensitivity analysis.

Uses MC raw samples to compute PRCC between each input parameter
and the GWP intensity output.

Method: PRCC via residual Spearman rank correlation (Saltelli 2008 § 4.3).
Adopted per docs/sensitivity_method_decision.md (X-4 decision).

Outputs:
  results/latest/uncertainty_mc_summary.csv  (PRCC by structure/power/material)
  results/latest/sensitivity_prcc_summary.csv  (aggregated ranking)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scipy.stats import rankdata, spearmanr
except ImportError:
    print("ERROR: scipy is required. Install with: pip install scipy", file=sys.stderr)
    sys.exit(1)

try:
    from scipy.linalg import lstsq as scipy_lstsq
except ImportError:
    scipy_lstsq = None  # fallback to numpy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MC_PARQUET = PROJECT_ROOT / "results" / "latest" / "uncertainty" / "mc_raw_samples.parquet"
OUT_DIR = PROJECT_ROOT / "results" / "latest"

PARAM_NAMES = ["capacity_factor", "eol_credit_rate"]


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


def compute_prcc(X: np.ndarray, Y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Partial Rank Correlation Coefficient via residual Spearman method.

    For each parameter i:
      1. Rank-transform X and Y
      2. Regress X[:,i] on X[:,~i]; compute residual r_xi
      3. Regress Y on X[:,~i]; compute residual r_y
      4. PRCC_i = Spearman(r_xi, r_y)

    Args:
        X: (N, k) input parameter samples
        Y: (N,) output intensity values
    Returns:
        prcc: (k,) PRCC values in [-1, 1]
        pvalues: (k,) associated p-values
    """
    N, k = X.shape

    # Rank transform
    Xr = np.apply_along_axis(rankdata, 0, X).astype(float)
    Yr = rankdata(Y).astype(float)

    prcc = np.zeros(k)
    pvals = np.zeros(k)

    if k == 1:
        # Only one parameter: direct Spearman
        r, p = spearmanr(X[:, 0], Y)
        return np.array([r]), np.array([p])

    for i in range(k):
        # Covariates with intercept column (essential for unbiased regression)
        other_cols = np.delete(Xr, i, axis=1)  # shape (N, k-1)
        ones = np.ones((N, 1))
        covars_with_intercept = np.hstack([ones, other_cols])  # shape (N, k)

        # Residual of Xr[:,i] after regressing out covars
        if scipy_lstsq is not None:
            coefs_x, _, _, _ = scipy_lstsq(covars_with_intercept, Xr[:, i])
            coefs_y, _, _, _ = scipy_lstsq(covars_with_intercept, Yr)
        else:
            coefs_x, _, _, _ = np.linalg.lstsq(covars_with_intercept, Xr[:, i], rcond=None)
            coefs_y, _, _, _ = np.linalg.lstsq(covars_with_intercept, Yr, rcond=None)

        res_x = Xr[:, i] - covars_with_intercept @ coefs_x
        res_y = Yr - covars_with_intercept @ coefs_y

        r, p = spearmanr(res_x, res_y)
        prcc[i] = r
        pvals[i] = p

    return prcc, pvals


def main() -> None:
    parser = argparse.ArgumentParser(description="PRCC sensitivity analysis for LCA MC samples")
    parser.add_argument(
        "--mc-file", type=Path, default=MC_PARQUET,
        help="Input MC parquet file",
    )
    parser.add_argument(
        "--output", type=Path, default=OUT_DIR / "uncertainty_mc_summary.csv",
        help="Output CSV for detailed results",
    )
    parser.add_argument(
        "--summary-output", type=Path, default=OUT_DIR / "sensitivity_prcc_summary.csv",
        help="Output CSV for aggregated PRCC ranking",
    )
    args = parser.parse_args()

    try:
        df = _load_mc_samples(args.mc_file)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Loading MC samples from {args.mc_file}...")

    # Verify required columns
    required = PARAM_NAMES + ["intensity_gco2_per_kwh", "structure_type", "rated_power_mw", "material_model"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"ERROR: Missing columns: {missing}", file=sys.stderr)
        sys.exit(1)

    structures = sorted(df["structure_type"].unique())
    powers = sorted(df["rated_power_mw"].unique())
    materials = sorted(df["material_model"].unique())

    detail_records = []
    summary_records = []

    for struct in structures:
        for power in powers:
            for mat in materials:
                sub = df[
                    (df["structure_type"] == struct)
                    & (df["rated_power_mw"] == power)
                    & (df["material_model"] == mat)
                ]
                if sub.empty:
                    continue

                X = sub[PARAM_NAMES].values.astype(float)
                Y = sub["intensity_gco2_per_kwh"].values.astype(float)
                n_samples = len(sub)

                prcc, pvals = compute_prcc(X, Y)

                for param_idx, param in enumerate(PARAM_NAMES):
                    detail_records.append(
                        {
                            "structure_type": struct,
                            "rated_power_mw": power,
                            "material_model": mat,
                            "parameter": param,
                            "prcc": round(float(prcc[param_idx]), 5),
                            "abs_prcc": round(abs(float(prcc[param_idx])), 5),
                            "pvalue": round(float(pvals[param_idx]), 6),
                            "n_samples": n_samples,
                        }
                    )

    df_detail = pd.DataFrame(detail_records)

    # Aggregate: mean |PRCC| and rank by structure
    agg = (
        df_detail.groupby(["structure_type", "rated_power_mw", "parameter"])["abs_prcc"]
        .mean()
        .reset_index()
        .rename(columns={"abs_prcc": "mean_abs_prcc_across_materials"})
    )
    agg["rank"] = agg.groupby(["structure_type", "rated_power_mw"])["mean_abs_prcc_across_materials"].rank(
        ascending=False, method="dense"
    )
    agg = agg.sort_values(["structure_type", "rated_power_mw", "rank"])

    # Global summary (all structures combined)
    global_agg = (
        df_detail.groupby("parameter")["abs_prcc"]
        .agg(["mean", "std", "min", "max"])
        .reset_index()
        .rename(columns={"mean": "mean_abs_prcc", "std": "std_abs_prcc", "min": "min_abs_prcc", "max": "max_abs_prcc"})
        .sort_values("mean_abs_prcc", ascending=False)
    )
    global_agg["global_rank"] = range(1, len(global_agg) + 1)

    # Save outputs
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df_detail.to_csv(args.output, index=False)
    agg.to_csv(args.summary_output, index=False)

    print(f"\nDetailed PRCC saved: {args.output} ({len(df_detail)} rows)")
    print(f"Summary PRCC saved: {args.summary_output}")

    print("\n=== Global PRCC Ranking (all structures/powers/materials) ===")
    print(global_agg.to_string(index=False, float_format="{:.4f}".format))

    print("\n=== PRCC at 15MW (GFRP) ===")
    subset = df_detail[(df_detail["rated_power_mw"] == 15) & (df_detail["material_model"] == "gfrp")]
    pivot = subset.pivot_table(index="structure_type", columns="parameter", values="prcc")
    print(pivot.to_string(float_format="{:.4f}".format))

    print("\n=== Sensitivity decision ===")
    top_param = global_agg.iloc[0]["parameter"]
    print(f"Primary sensitivity driver: '{top_param}' (mean |PRCC| = {global_agg.iloc[0]['mean_abs_prcc']:.4f})")
    if len(global_agg) > 1:
        second_param = global_agg.iloc[1]["parameter"]
        ratio = global_agg.iloc[0]["mean_abs_prcc"] / global_agg.iloc[1]["mean_abs_prcc"]
        print(f"Ratio vs second driver ('{second_param}'): {ratio:.2f}x")


if __name__ == "__main__":
    main()
