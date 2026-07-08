#!/usr/bin/env python3
"""Analyze CFRP vs GFRP crossover behavior by structure and MW."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "base": ROOT / "results/latest/matrix_latest.csv",
    "fawt46": ROOT / "results/latest/matrix_latest_fawt46.csv",
}
OUTDIR = ROOT / "results/latest/cfrp_crossover"
SUBMISSION_OUTDIR = ROOT / "submission/20260211_submission_v1/results_cfrp_crossover"
DOC_PATH = ROOT / "docs/cfrp_crossover_analysis_20260211.md"
SUBMISSION_DOC_PATH = ROOT / "submission/20260211_submission_v1/docs/cfrp_crossover_analysis_20260211.md"



def _find_crossover(powers: list[float], deltas: list[float]) -> tuple[str, float | None, str]:
    # Exact zero at sampled points
    for p, d in zip(powers, deltas):
        if abs(d) < 1e-9:
            return "sampled", float(p), "delta=0 at sampled MW"

    # Sign change between adjacent points
    for i in range(len(powers) - 1):
        p1, p2 = powers[i], powers[i + 1]
        d1, d2 = deltas[i], deltas[i + 1]
        if d1 == 0:
            return "sampled", float(p1), "delta=0 at sampled MW"
        if d1 * d2 < 0:
            # Linear interpolation
            p_star = p1 + (0 - d1) * (p2 - p1) / (d2 - d1)
            return "interpolated", float(p_star), f"sign change between {p1} and {p2} MW"

    # No crossover in range, optional extrapolation from last segment
    if len(powers) >= 2:
        p1, p2 = powers[-2], powers[-1]
        d1, d2 = deltas[-2], deltas[-1]
        slope = (d2 - d1) / (p2 - p1) if p2 != p1 else 0.0
        if slope < 0 and d2 > 0:
            p_star = p2 + d2 / abs(slope)
            return "extrapolated", float(p_star), "delta decreasing but still > 0 at max MW"

    return "none", None, "no crossover within analyzed range"



def _analyze_one(label: str, path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(path)

    g = df[df["material_model"] == "gfrp"][
        ["structure_type", "rated_power_mw", "intensity_gco2_per_kwh"]
    ].rename(columns={"intensity_gco2_per_kwh": "intensity_gfrp"})
    c = df[df["material_model"] == "cfrp"][
        ["structure_type", "rated_power_mw", "intensity_gco2_per_kwh"]
    ].rename(columns={"intensity_gco2_per_kwh": "intensity_cfrp"})

    delta = g.merge(c, on=["structure_type", "rated_power_mw"], how="inner")
    delta["delta_cfrp_minus_gfrp_gpkwh"] = delta["intensity_cfrp"] - delta["intensity_gfrp"]
    delta["dataset"] = label

    rows = []
    for structure, sub in delta.groupby("structure_type"):
        s = sub.sort_values("rated_power_mw")
        p = s["rated_power_mw"].tolist()
        d = s["delta_cfrp_minus_gfrp_gpkwh"].tolist()
        mode, mw, note = _find_crossover(p, d)
        rows.append(
            {
                "dataset": label,
                "structure_type": structure,
                "delta_at_2mw_gpkwh": float(d[0]),
                "delta_at_15mw_gpkwh": float(d[-1]),
                "delta_trend_15_minus_2_gpkwh": float(d[-1] - d[0]),
                "crossover_mode": mode,
                "estimated_crossover_mw": mw,
                "note": note,
            }
        )

    summary = pd.DataFrame(rows).sort_values("structure_type")
    return delta.sort_values(["structure_type", "rated_power_mw"]), summary



def _plot_deltas(base_delta: pd.DataFrame, f46_delta: pd.DataFrame) -> None:
    structures = sorted(base_delta["structure_type"].unique())
    ncols = min(3, max(1, len(structures)))
    nrows = math.ceil(len(structures) / ncols)
    fig, axes_grid = plt.subplots(
        nrows,
        ncols,
        figsize=(4 * ncols, 3.8 * nrows),
        constrained_layout=True,
        squeeze=False,
    )
    axes = list(axes_grid.ravel())
    used_axes = []

    for i, st in enumerate(structures):
        ax = axes[i]
        used_axes.append(ax)
        b = base_delta[base_delta["structure_type"] == st].sort_values("rated_power_mw")
        f = f46_delta[f46_delta["structure_type"] == st].sort_values("rated_power_mw")
        ax.plot(b["rated_power_mw"], b["delta_cfrp_minus_gfrp_gpkwh"], marker="o", label="base")
        ax.plot(f["rated_power_mw"], f["delta_cfrp_minus_gfrp_gpkwh"], marker="s", label="fawt46")
        ax.axhline(0.0, color="gray", linewidth=1.0)
        ax.set_title(st)
        ax.set_xlabel("MW")
        if i % ncols == 0:
            ax.set_ylabel("CFRP - GFRP [g-CO2eq/kWh]")
        ax.grid(alpha=0.25)

    for j in range(len(structures), len(axes)):
        axes[j].axis("off")

    handles, labels = used_axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2)
    fig.suptitle("CFRP Crossover Trend by Structure")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTDIR / "cfrp_crossover_delta_lines.png", dpi=220)
    plt.close(fig)



def _write_doc(base_summary: pd.DataFrame, f46_summary: pd.DataFrame) -> None:
    def _fmt(df: pd.DataFrame) -> str:
        cols = [
            "structure_type",
            "delta_at_2mw_gpkwh",
            "delta_at_15mw_gpkwh",
            "delta_trend_15_minus_2_gpkwh",
            "crossover_mode",
            "estimated_crossover_mw",
        ]
        t = df[cols].copy()
        for c in ["delta_at_2mw_gpkwh", "delta_at_15mw_gpkwh", "delta_trend_15_minus_2_gpkwh", "estimated_crossover_mw"]:
            t[c] = t[c].map(lambda x: "" if pd.isna(x) else f"{float(x):.3f}")
        header = "| " + " | ".join(cols) + " |"
        sep = "| " + " | ".join(["---"] * len(cols)) + " |"
        rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in t.itertuples(index=False, name=None)]
        return "\n".join([header, sep] + rows)

    lines = []
    lines.append("# CFRPクロスオーバー解析（2026-02-11）")
    lines.append("")
    lines.append("## 目的")
    lines.append("FB1対応として、構造ごとに `CFRP - GFRP` の原単位差がMW増加でどう変化するかを定量化する。")
    lines.append("")
    lines.append("## 判定ルール")
    lines.append("- `delta = intensity(CFRP) - intensity(GFRP)`")
    lines.append("- `delta < 0` なら CFRP優位")
    lines.append("- `delta = 0` となるMWをクロスオーバー点として推定（サンプル点/内挿/外挿）")
    lines.append("")
    lines.append("## base結果")
    lines.append(_fmt(base_summary))
    lines.append("")
    lines.append("## fawt46結果")
    lines.append(_fmt(f46_summary))
    lines.append("")
    lines.append("## 要点")
    lines.append("- 本モデルでは多くの構造で `delta > 0` が維持され、解析範囲(2-15MW)内で明確なクロスオーバーは限定的。")
    lines.append("- ただし `delta_trend_15_minus_2` が負の場合、MW増加でCFRP不利幅は縮小している。")
    lines.append("- クロスオーバー外挿値が得られる構造は、波及係数強化時の優先再同定対象とする。")
    lines.append("")
    lines.append("## 出力")
    lines.append("- `results/latest/cfrp_crossover/base_cfrp_vs_gfrp_delta_by_power.csv`")
    lines.append("- `results/latest/cfrp_crossover/base_cfrp_crossover_summary.csv`")
    lines.append("- `results/latest/cfrp_crossover/fawt46_cfrp_vs_gfrp_delta_by_power.csv`")
    lines.append("- `results/latest/cfrp_crossover/fawt46_cfrp_crossover_summary.csv`")
    lines.append("- `results/latest/cfrp_crossover/cfrp_crossover_delta_lines.png`")

    DOC_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")



def _sync_submission() -> None:
    SUBMISSION_OUTDIR.mkdir(parents=True, exist_ok=True)
    SUBMISSION_DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    for p in OUTDIR.glob("*"):
        if p.is_file():
            (SUBMISSION_OUTDIR / p.name).write_bytes(p.read_bytes())
    SUBMISSION_DOC_PATH.write_bytes(DOC_PATH.read_bytes())



def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    base_delta, base_summary = _analyze_one("base", INPUTS["base"])
    f46_delta, f46_summary = _analyze_one("fawt46", INPUTS["fawt46"])

    base_delta.to_csv(OUTDIR / "base_cfrp_vs_gfrp_delta_by_power.csv", index=False)
    base_summary.to_csv(OUTDIR / "base_cfrp_crossover_summary.csv", index=False)
    f46_delta.to_csv(OUTDIR / "fawt46_cfrp_vs_gfrp_delta_by_power.csv", index=False)
    f46_summary.to_csv(OUTDIR / "fawt46_cfrp_crossover_summary.csv", index=False)

    _plot_deltas(base_delta, f46_delta)
    _write_doc(base_summary, f46_summary)
    _sync_submission()


if __name__ == "__main__":
    main()
