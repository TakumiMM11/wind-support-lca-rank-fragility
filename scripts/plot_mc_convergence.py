#!/usr/bin/env python3
"""Regenerate the Monte Carlo convergence diagnostic figure."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "results" / "mc_convergence_summary.csv"
OUT = ROOT / "figures" / "exported_figures" / "mc_convergence.png"


def main() -> None:
    df = pd.read_csv(CSV)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    axes[0].plot(df["n_samples"], df["mean_onshore"], label="Onshore", color="#E69F00", linewidth=2)
    axes[0].plot(df["n_samples"], df["mean_bottom_fixed"], label="Bottom-fixed", color="#56B4E9", linewidth=2)
    axes[0].set_xlabel("Monte Carlo samples")
    axes[0].set_ylabel("Cumulative mean intensity (g-CO2eq/kWh)")
    axes[0].set_title("Cumulative mean convergence")
    axes[0].grid(True, linestyle=":", alpha=0.35)
    axes[0].legend(frameon=False, fontsize=9)

    support_col = "support_frequency_bottom_fixed_vs_onshore"
    axes[1].plot(df["n_samples"], df[support_col], color="#0072B2", linewidth=2)
    axes[1].axhline(df[support_col].iloc[-1], color="#444444", linestyle="--", linewidth=1.0)
    axes[1].set_xlabel("Monte Carlo samples")
    axes[1].set_ylabel("Support frequency")
    axes[1].set_title("Bottom-fixed vs. onshore support convergence")
    axes[1].grid(True, linestyle=":", alpha=0.35)

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=300, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
