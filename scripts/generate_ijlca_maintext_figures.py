#!/usr/bin/env python3
"""Generate additional main-text figures for the IJLCA manuscript."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "manuscript_v4_revision_20260319"
STRENGTH = ROOT / "results" / "ijlca_strengthening_20260702"
OUT = ROOT / "submission" / "20260702_ijlca_v1"

STRUCTURE_ORDER = ["onshore", "bottom_fixed", "fawt", "semisubmersible", "spar"]
STRUCTURE_LABELS = ["Onshore", "Bottom-fixed", "FAWT*", "Semisub.", "Spar"]
MATERIAL_ORDER = ["gfrp", "cfrp", "rcfrp", "rrcfrp"]
MATERIAL_LABELS = ["GFRP", "CFRP", "rCFRP", "rrCFRP"]
POWER_ORDER = [2.0, 5.0, 10.0, 15.0]


def _clean_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def build_80case_landscape() -> None:
    df = pd.read_csv(SRC / "matrix_latest.csv")
    df = df[
        df["structure_type"].isin(STRUCTURE_ORDER)
        & df["material_model"].isin(MATERIAL_ORDER)
        & df["rated_power_mw"].isin(POWER_ORDER)
    ].copy()

    values = df["intensity_gco2_per_kwh"]
    vmin = np.floor(values.min())
    vmax = np.ceil(values.max())

    fig, axes = plt.subplots(2, 2, figsize=(9.8, 6.8), sharex=True, sharey=True)
    axes = axes.ravel()
    cmap = plt.get_cmap("YlGnBu_r")

    for ax, material, material_label in zip(axes, MATERIAL_ORDER, MATERIAL_LABELS):
        pivot = (
            df[df["material_model"] == material]
            .pivot(index="structure_type", columns="rated_power_mw", values="intensity_gco2_per_kwh")
            .reindex(index=STRUCTURE_ORDER, columns=POWER_ORDER)
        )
        im = ax.imshow(pivot.values, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
        ax.set_title(material_label, fontsize=11, weight="bold")
        ax.set_xticks(range(len(POWER_ORDER)), [f"{int(p)}" for p in POWER_ORDER])
        ax.set_yticks(range(len(STRUCTURE_ORDER)), STRUCTURE_LABELS)
        ax.tick_params(axis="both", labelsize=9)
        for i in range(pivot.shape[0]):
            for j in range(pivot.shape[1]):
                val = pivot.iloc[i, j]
                color = "white" if val > (vmin + vmax) / 2 else "black"
                ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=8, color=color)
        ax.axhline(2.5, color="#111827", linewidth=0.8, linestyle=":")
        ax.axhline(1.5, color="#111827", linewidth=0.8, linestyle=":")

    for ax in axes[2:]:
        ax.set_xlabel("Rated power (MW)", fontsize=10)
    for ax in axes[::2]:
        ax.set_ylabel("Support structure", fontsize=10)

    fig.subplots_adjust(left=0.12, right=0.86, bottom=0.10, top=0.88, wspace=0.16, hspace=0.20)
    cax = fig.add_axes([0.89, 0.20, 0.02, 0.60])
    cbar = fig.colorbar(im, cax=cax)
    cbar.set_label("GWP intensity (g-CO$_2$eq/kWh)", fontsize=10)
    cbar.ax.tick_params(labelsize=9)
    fig.suptitle("GWP landscape across 80 support-structure, scale, and blade-material cases", fontsize=12)
    fig.savefig(OUT / "fig8.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def build_uncertainty_envelope() -> None:
    df = pd.read_csv(STRENGTH / "expanded_uncertainty_screening_envelope_15mw_gfrp.csv")
    df = df.set_index("structure_type").reindex(STRUCTURE_ORDER).reset_index()

    y = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(8.8, 4.2))

    stress_low = df["screening_envelope_low_gpkwh"].to_numpy()
    stress_high = df["screening_envelope_high_gpkwh"].to_numpy()
    mc_low = df["mc95_low_cf_eol_gpkwh"].to_numpy()
    mc_high = df["mc95_high_cf_eol_gpkwh"].to_numpy()
    base = df["baseline_gpkwh"].to_numpy()

    ax.hlines(y, stress_low, stress_high, color="#9aa5b1", linewidth=9, alpha=0.55, label="Screening envelope")
    ax.hlines(y, mc_low, mc_high, color="#2563eb", linewidth=4, alpha=0.9, label="MC 95% interval")
    ax.scatter(base, y, color="#111827", s=36, zorder=3, label="Baseline")

    for yi, b, lo, hi in zip(y, base, stress_low, stress_high):
        ax.text(hi + 0.18, yi, f"{lo:.1f}-{hi:.1f}", va="center", fontsize=8)
        ax.text(b, yi - 0.22, f"{b:.1f}", ha="center", va="top", fontsize=8, color="#111827")

    ax.set_yticks(y, STRUCTURE_LABELS)
    ax.axhline(1.5, color="#111827", linewidth=0.8, linestyle=":")
    ax.axhline(2.5, color="#111827", linewidth=0.8, linestyle=":")
    ax.invert_yaxis()
    ax.set_xlabel("GWP intensity (g-CO$_2$eq/kWh)")
    ax.set_title("15 MW GFRP uncertainty intervals and screening envelopes", fontsize=12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, frameon=False, fontsize=9)
    _clean_axes(ax)
    fig.tight_layout()
    fig.savefig(OUT / "fig9.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def build_material_burden_bars() -> None:
    df = pd.read_csv(STRENGTH / "material_burden_screen_15mw.csv")
    df = df[(df["material_model"] == "gfrp") & df["structure_type"].isin(STRUCTURE_ORDER)]
    df = df.set_index("structure_type").reindex(STRUCTURE_ORDER)

    groups = [
        ("steel_kg_per_mwh", "Steel", "#4b5563"),
        ("concrete_kg_per_mwh", "Concrete", "#9ca3af"),
        ("composite_kg_per_mwh", "Composite", "#2563eb"),
        ("copper_kg_per_mwh", "Copper", "#b45309"),
        ("other_kg_per_mwh", "Other", "#6b7280"),
    ]

    fig, ax = plt.subplots(figsize=(8.8, 4.4))
    x = np.arange(len(df))
    bottom = np.zeros(len(df))
    for col, label, color in groups:
        values = df[col].fillna(0).to_numpy()
        ax.bar(x, values, bottom=bottom, label=label, color=color, edgecolor="white", linewidth=0.5)
        bottom += values

    for xi, total in zip(x, bottom):
        ax.text(xi, total + 0.45, f"{total:.1f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x, STRUCTURE_LABELS)
    ax.set_ylabel("Foreground material intensity (kg/MWh)")
    ax.set_title("Material-burden screen for the 15 MW GFRP cases", fontsize=12)
    ax.legend(ncol=5, frameon=False, fontsize=8, loc="upper left")
    _clean_axes(ax)
    fig.tight_layout()
    fig.savefig(OUT / "fig10.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    build_80case_landscape()
    build_uncertainty_envelope()
    build_material_burden_bars()


if __name__ == "__main__":
    main()
