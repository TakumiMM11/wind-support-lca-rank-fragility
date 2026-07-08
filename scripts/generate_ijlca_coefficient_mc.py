#!/usr/bin/env python3
"""Supplementary coefficient-screening Monte Carlo for the IJLCA manuscript."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "ijlca_strengthening_20260702"

STRUCTURE_ORDER = ["onshore", "bottom_fixed", "fawt", "semisubmersible", "spar"]
BASE_CF = {
    "onshore": 0.30,
    "bottom_fixed": 0.40,
    "fawt": 0.42,
    "semisubmersible": 0.42,
    "spar": 0.42,
}
COEFFICIENTS = {
    "steel": 2.47,
    "concrete": 0.10714285714285714,
    "copper": 3.965,
    "composite": 3.43,
}


def pairwise_probs(a: np.ndarray, b: np.ndarray, base_a: float, base_b: float, threshold_pct: float = 1.0) -> dict:
    threshold = threshold_pct / 100.0
    diff = a - b
    tie = np.abs(diff) <= threshold * np.minimum(a, b)
    base_a_lower = base_a < base_b
    support = (diff < 0) if base_a_lower else (diff > 0)
    reversal = (diff > 0) if base_a_lower else (diff < 0)
    return {
        "support": float(np.mean(support & ~tie)),
        "reversal": float(np.mean(reversal & ~tie)),
        "tie": float(np.mean(tie)),
    }


def main() -> None:
    rng = np.random.default_rng(4242)
    mc = pd.read_csv(OUT / "expanded_uncertainty_mc_raw_15mw_gfrp.csv")
    burden = pd.read_csv(OUT / "material_burden_screen_15mw.csv")
    burden = burden[(burden["material_model"] == "gfrp")].set_index("structure_type")

    adjusted_blocks = []
    for structure in STRUCTURE_ORDER:
        block = mc[mc["structure_type"] == structure].copy()
        cf_scale = BASE_CF[structure] / block["capacity_factor"].to_numpy()
        delta = np.zeros(len(block))
        for group, coefficient in COEFFICIENTS.items():
            kg_per_mwh = float(burden.loc[structure, f"{group}_kg_per_mwh"])
            factor = rng.uniform(0.9, 1.1, size=len(block))
            delta += kg_per_mwh * cf_scale * coefficient * (factor - 1.0)
        block["intensity_with_coeff_mc_gpkwh"] = block["intensity_gco2_per_kwh"].to_numpy() + delta
        adjusted_blocks.append(block)

    out = pd.concat(adjusted_blocks, ignore_index=True)
    out.to_csv(OUT / "coefficient_screening_mc_15mw_gfrp.csv", index=False)

    baseline = (
        pd.read_csv(ROOT / "results" / "manuscript_v4_revision_20260319" / "analysis" / "intensity_15mw_table.csv")
        .set_index("structure_type")["gfrp"]
    )
    pivot = out.pivot(index="sample_id", columns="structure_type", values="intensity_with_coeff_mc_gpkwh")
    rows = []
    for a, b in [
        ("onshore", "bottom_fixed"),
        ("semisubmersible", "spar"),
        ("fawt", "semisubmersible"),
        ("fawt", "spar"),
    ]:
        probs = pairwise_probs(
            pivot[a].to_numpy(),
            pivot[b].to_numpy(),
            float(baseline[a]),
            float(baseline[b]),
        )
        rows.append(
            {
                "pair": f"{a} vs {b}",
                "baseline_a_gpkwh": float(baseline[a]),
                "baseline_b_gpkwh": float(baseline[b]),
                "support": probs["support"],
                "reversal": probs["reversal"],
                "tie": probs["tie"],
                "n_samples": len(pivot),
                "coefficient_distribution": "independent uniform 0.9-1.1 multipliers on steel, concrete, copper, and GFRP foreground manufacturing coefficients",
            }
        )

    summary = pd.DataFrame(rows)
    summary.to_csv(OUT / "coefficient_screening_mc_15mw_gfrp_summary.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
