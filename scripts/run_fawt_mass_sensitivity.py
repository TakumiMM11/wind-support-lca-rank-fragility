"""FAWT structural mass sensitivity analysis: ±30% scaling of FAWT L1+L2 GWP.

This script quantifies how FAWT GWP intensity responds to uncertainty in the
structural mass parameters obtained from demonstration-phase testing. A ±30%
range is applied to FAWT L1 (manufacturing) and L2 (transport/installation) GWP,
consistent with the scale-up uncertainty inherent in extrapolating prototype masses
to commercial configurations.

Method:
    For each FAWT configuration (all MW ratings × all materials):
        1. Read the baseline FAWT GWP breakdown from MCEngine internals.
        2. Apply mass scaling factors: 0.70, 0.85, 1.00, 1.15, 1.30
           (−30%, −15%, baseline, +15%, +30%).
        3. L3 O&M scales proportionally with mass; L4 EoL scales proportionally.
        4. L1+L2+L3+L4 are rescaled; intensity = rescaled_GWP / energy.
        5. Report the resulting GWP intensity range.

Output:
    results/latest/uncertainty/fawt_mass_sensitivity.csv
    results/latest/uncertainty/fawt_mass_sensitivity_summary.csv

Usage:
    python scripts/run_fawt_mass_sensitivity.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Mass scaling factors to evaluate (−30%, −15%, baseline, +15%, +30%)
MASS_SCALE_FACTORS = [0.70, 0.85, 1.00, 1.15, 1.30]
POWERS = [2.0, 5.0, 10.0, 15.0]
MATERIALS = ["gfrp", "cfrp", "rcfrp", "rrcfrp"]
LIFETIME_YEARS = 25
SEED = 42

OUTPUT_DIR = PROJECT_ROOT / "results" / "latest" / "uncertainty"


def get_fawt_gwp_components(
    power_mw: float,
    material_model: str,
    assumptions_path: Path,
    lci_dir: Path,
) -> dict:
    """Return the GWP component breakdown for one FAWT configuration.

    Returns a dict with keys: l1, l2, l3, l4, base_cf, total_mass_kg
    """
    from src.lca.uncertainty import MCEngine
    from src.cli.commands.matrix import (
        _apply_material_model,
        _estimate_l2_from_events,
        _estimate_l3_from_events,
        _estimate_l4_from_events,
        _estimate_l4_proxy,
        _estimate_transport_gwp_proxy,
        _scale_structure_mass_by_power,
    )
    from src.lca.calculator import LCACalculator
    from src.lci.loaders import load_all_lci_data

    assumptions = json.loads(assumptions_path.read_text())
    lci_data = load_all_lci_data(data_dir=lci_dir)
    structure = "fawt"

    scaled_lci = _scale_structure_mass_by_power(
        lci_data=lci_data,
        structure_type=structure,
        rated_power_mw=power_mw,
    )
    model_lci = _apply_material_model(
        lci_data=scaled_lci,
        structure_type=structure,
        material_model=material_model,
        assumptions=assumptions,
        assumption_point="base",
        fawt_arm_center_share=None,
    )

    structure_components = [
        c for c in model_lci.components.values() if c.structure_type == structure
    ]
    structure_events = [
        e for e in model_lci.events if e.structure_type == structure
    ]
    total_mass_kg = sum(c.mass_kg * c.quantity for c in structure_components)

    base_cf = assumptions["site_class_cf"]["baseline"][structure]["base"]
    calc = LCACalculator(
        lci_data=model_lci,
        structure_type=structure,
        rated_power_mw=power_mw,
        lifetime_years=LIFETIME_YEARS,
        capacity_factor=base_cf,
        scenario_name=f"fawt-mass-sens-{power_mw:g}mw-{material_model}",
        enable_weight_cascade=False,
        log_iterations=False,
        write_detailed_log=False,
    )
    result = calc.calculate()
    l1 = result.l1_manufacturing_kgco2

    l2_event = _estimate_l2_from_events(
        events=structure_events,
        structure_components=structure_components,
        vehicles=model_lci.vehicles,
        assumptions=assumptions,
    )
    l2_proxy = _estimate_transport_gwp_proxy(total_mass_kg, structure)
    l2 = l2_event if l2_event > 0 else l2_proxy

    l3_event = _estimate_l3_from_events(
        events=structure_events,
        structure_components=structure_components,
        vehicles=model_lci.vehicles,
        assumptions=assumptions,
        structure=structure,
        lifetime_years=LIFETIME_YEARS,
        site_class="baseline",
        assumption_point="base",
    )
    l3 = result.l3_o_and_m_kgco2 + l3_event

    l4_event = _estimate_l4_from_events(
        events=structure_events,
        structure_components=structure_components,
        vehicles=model_lci.vehicles,
        assumptions=assumptions,
        structure=structure,
        assumption_point="base",
        eol_credit_rate=None,
    )
    l4 = result.l4_eol_kgco2 + l4_event

    return {
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "l4": l4,
        "base_cf": base_cf,
        "total_mass_kg": total_mass_kg,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assumptions_path = PROJECT_ROOT / "data" / "model_assumptions.json"
    lci_dir = PROJECT_ROOT / "data" / "lci"

    records = []

    for power_mw in POWERS:
        for material_model in MATERIALS:
            logger.info("FAWT %.0f MW %s", power_mw, material_model)
            comps = get_fawt_gwp_components(power_mw, material_model, assumptions_path, lci_dir)
            l1 = comps["l1"]
            l2 = comps["l2"]
            l3 = comps["l3"]
            l4 = comps["l4"]
            base_cf = comps["base_cf"]

            # Energy at baseline CF (MWh = MW × 8760 h/yr × 25 yr)
            energy_mwh = power_mw * 8760.0 * LIFETIME_YEARS * base_cf

            # Baseline intensity (g-CO2/kWh = kg-CO2/MWh)
            baseline_intensity = (l1 + l2 + l3 + l4) / energy_mwh

            for scale in MASS_SCALE_FACTORS:
                # Scale L1, L2, L3, L4 proportionally with structural mass
                # L1 (manufacturing) and L2 (install) scale directly with mass
                # L3 (O&M) scales approximately proportionally (service intensity × mass)
                # L4 (EoL) scales with recyclable material volume
                l1_s = l1 * scale
                l2_s = l2 * scale
                l3_s = l3 * scale
                l4_s = l4 * scale

                total_s = l1_s + l2_s + l3_s + l4_s
                intensity_s = total_s / energy_mwh

                records.append({
                    "structure_type": "fawt",
                    "rated_power_mw": power_mw,
                    "material_model": material_model,
                    "mass_scale_factor": scale,
                    "l1_kgco2": l1_s,
                    "l2_kgco2": l2_s,
                    "l3_kgco2": l3_s,
                    "l4_kgco2": l4_s,
                    "total_kgco2": total_s,
                    "intensity_gco2_per_kwh": intensity_s,
                    "baseline_intensity": baseline_intensity,
                    "delta_vs_baseline": intensity_s - baseline_intensity,
                    "delta_pct": (intensity_s - baseline_intensity) / baseline_intensity * 100,
                    "lifetime_years": LIFETIME_YEARS,
                    "base_cf": base_cf,
                })

    df = pd.DataFrame(records)
    df_path = OUTPUT_DIR / "fawt_mass_sensitivity.csv"
    df.to_csv(df_path, index=False)
    logger.info("Saved: %s", df_path)

    # Summary: GFRP at 15MW for quick view
    print("\n=== FAWT Mass Sensitivity — 15 MW, GFRP ===")
    print("Mass scale | GWP intensity (g-CO2/kWh) | Delta vs baseline")
    print("-" * 60)
    key = df[(df["rated_power_mw"] == 15.0) & (df["material_model"] == "gfrp")]
    for _, row in key.iterrows():
        print(f"  ×{row['mass_scale_factor']:.2f}     |  {row['intensity_gco2_per_kwh']:>8.3f}               |  "
              f"{row['delta_vs_baseline']:+.3f} ({row['delta_pct']:+.1f}%)")

    # Summary by MW and material
    print("\n=== FAWT Mass Sensitivity — All MW, GFRP, scale −30% / base / +30% ===")
    summary_rows = []
    for power_mw in POWERS:
        subset = df[(df["rated_power_mw"] == power_mw) & (df["material_model"] == "gfrp")]
        row_70 = subset[subset["mass_scale_factor"] == 0.70].iloc[0]
        row_100 = subset[subset["mass_scale_factor"] == 1.00].iloc[0]
        row_130 = subset[subset["mass_scale_factor"] == 1.30].iloc[0]
        summary_rows.append({
            "rated_power_mw": power_mw,
            "intensity_-30%": row_70["intensity_gco2_per_kwh"],
            "intensity_base": row_100["intensity_gco2_per_kwh"],
            "intensity_+30%": row_130["intensity_gco2_per_kwh"],
            "range_width": row_130["intensity_gco2_per_kwh"] - row_70["intensity_gco2_per_kwh"],
        })
    summary_df = pd.DataFrame(summary_rows)
    print(summary_df.to_string(index=False, float_format="{:.3f}".format))

    summary_path = OUTPUT_DIR / "fawt_mass_sensitivity_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    logger.info("Saved: %s", summary_path)

    print(f"\nFull results saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
