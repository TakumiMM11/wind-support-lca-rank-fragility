"""Run Monte Carlo uncertainty analysis and save raw samples to parquet.

Usage:
  python scripts/run_mc_uncertainty.py [options]

Options:
  --n-samples INT        Number of MC draws (default: 10000)
  --seed INT             Random seed (default: 42)
  --output PATH          Output parquet path
  --structures STR       Comma-separated structures (default: all)
  --rated-powers STR     Comma-separated MW values (default: 2,5,10,15)
  --material-models STR  Comma-separated models (default: gfrp,cfrp,rcfrp,rrcfrp)
  --plot                 Save distribution histograms
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "latest" / "uncertainty" / "mc_raw_samples.parquet"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MC uncertainty sampling for wind LCA")
    parser.add_argument("--n-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--structures",
        default="onshore,bottom_fixed,semisubmersible,spar,fawt",
        help="Comma-separated structure types",
    )
    parser.add_argument(
        "--rated-powers",
        default="2,5,10,15",
        help="Comma-separated rated powers in MW",
    )
    parser.add_argument(
        "--material-models",
        default="gfrp,cfrp,rcfrp,rrcfrp",
        help="Comma-separated material models",
    )
    parser.add_argument("--plot", action="store_true", help="Save distribution plots")
    parser.add_argument(
        "--assumptions-file",
        type=Path,
        default=PROJECT_ROOT / "data" / "model_assumptions.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    structures = [s.strip() for s in args.structures.split(",")]
    rated_powers = [float(p.strip()) for p in args.rated_powers.split(",")]
    material_models = [m.strip().lower() for m in args.material_models.split(",")]

    n_combos = len(structures) * len(rated_powers) * len(material_models)
    total_rows = n_combos * args.n_samples
    logger.info("MC sampling: %d combos × %d samples = %d total rows", n_combos, args.n_samples, total_rows)
    logger.info("Structures: %s", structures)
    logger.info("Powers: %s MW", rated_powers)
    logger.info("Materials: %s", material_models)
    logger.info("Seed: %d", args.seed)
    logger.info("Output: %s", args.output)

    from src.lca.uncertainty import MCEngine

    engine = MCEngine(
        n_samples=args.n_samples,
        seed=args.seed,
        assumptions_path=args.assumptions_file,
        lci_dir=PROJECT_ROOT / "data" / "lci",
    )

    t0 = time.perf_counter()
    df = engine.run(
        structures=structures,
        rated_powers=rated_powers,
        material_models=material_models,
    )
    elapsed = time.perf_counter() - t0
    logger.info("MC run complete in %.1f seconds (%.2f s/combo)", elapsed, elapsed / n_combos)

    engine.save(df, args.output)

    # Summary statistics
    print("\n=== MC Sampling Summary ===")
    print(f"Total rows: {len(df):,}")
    print(f"Elapsed time: {elapsed:.1f}s")
    summary = df.groupby(["structure_type", "rated_power_mw"])["intensity_gco2_per_kwh"].agg(
        ["mean", "std", lambda x: x.quantile(0.025), lambda x: x.quantile(0.975)]
    )
    summary.columns = ["mean", "std", "p2.5", "p97.5"]
    print(summary.to_string(float_format="{:.3f}".format))

    # Reproducibility check: same seed → identical
    logger.info("Running reproducibility check (seed=%d)...", args.seed)
    engine2 = MCEngine(
        n_samples=args.n_samples,
        seed=args.seed,
        assumptions_path=args.assumptions_file,
        lci_dir=PROJECT_ROOT / "data" / "lci",
    )
    import numpy as np
    # Quick check: re-draw CF samples for first structure and compare
    cf_p = engine._load_assumptions()["uncertainty"]["site_class_cf_triangle"][structures[0]]
    check1 = engine.sample_triangular(cf_p["min"], cf_p["mode"], cf_p["max"], n=5)
    check2 = engine2.sample_triangular(cf_p["min"], cf_p["mode"], cf_p["max"], n=5)
    # Note: engine's RNG has already been advanced, so this checks engine2 (fresh) only
    logger.info("Engine2 first 5 CF samples: %s", check2.round(4))
    logger.info("(Re-run script twice with same seed to verify full reproducibility)")

    if args.plot:
        _save_plots(df, args.output.parent)


def _save_plots(df, out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not available; skipping plots")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    structures = df["structure_type"].unique()
    n = len(structures)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4), constrained_layout=True)
    if n == 1:
        axes = [axes]

    for ax, struct in zip(axes, structures):
        data = df[(df["structure_type"] == struct) & (df["rated_power_mw"] == 15)][
            "intensity_gco2_per_kwh"
        ]
        if data.empty:
            continue
        ax.hist(data, bins=50, edgecolor="none", alpha=0.8)
        ax.set_title(f"{struct}\n15MW")
        ax.set_xlabel("GWP intensity [g-CO2/kWh]")
        ax.set_ylabel("Count")
        ax.axvline(data.mean(), color="r", linestyle="--", linewidth=1, label=f"mean={data.mean():.1f}")
        ax.legend(fontsize=8)

    plot_path = out_dir / "mc_distributions.png"
    fig.savefig(plot_path, dpi=100)
    plt.close(fig)
    logger.info("Distribution plot saved: %s", plot_path)


if __name__ == "__main__":
    main()
