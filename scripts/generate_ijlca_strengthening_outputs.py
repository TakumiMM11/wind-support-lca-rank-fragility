#!/usr/bin/env python3
"""Generate strengthening outputs for the IJLCA manuscript revision.

The outputs address four manuscript risks without overstating the available
evidence:
1. GWP-only weakness: material-burden screening by mass intensity.
2. Narrow MC scope: expanded stress envelope that combines MC intervals and
   deterministic stress tests.
3. FAWT evidence strength: disclosure-preserving evidence envelope.
4. Data quality: compact pedigree-style input quality register.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_v6_defense_outputs import (
    ASSUMPTIONS,
    LCI_DIR,
    STRUCTURE_ORDER,
    _compute_adjusted_case,
    _load_frozen_inputs,
)
from src.cli.commands.matrix import (
    _apply_material_model,
    _resolve_capacity_factor,
    _scale_structure_mass_by_power,
)
from src.lca.uncertainty import MCEngine


SRC = ROOT / "results" / "manuscript_v4_revision_20260319"
V6 = ROOT / "results" / "v6_extension_20260413"
OUT = ROOT / "results" / "ijlca_strengthening_20260702"


def _material_group(material_id: str) -> str:
    mid = str(material_id).lower()
    if "steel" in mid:
        return "steel"
    if "concrete" in mid:
        return "concrete"
    if "copper" in mid:
        return "copper"
    if any(k in mid for k in ["gfrp", "cfrt", "cfrtp", "rcfrtp", "rrcfrtp", "cpt"]):
        return "composite"
    if "aluminum" in mid:
        return "aluminum"
    return "other"


def build_material_burden_screen() -> pd.DataFrame:
    """Mass-intensity screen for non-GWP burden-shifting discussion."""
    assumptions, lci = _load_frozen_inputs()
    rows: list[dict] = []
    for structure in STRUCTURE_ORDER:
        cf = _resolve_capacity_factor(structure, None, assumptions, "baseline", "base")
        energy_mwh = 15.0 * 8760 * 25 * cf
        for material_model in ["gfrp", "cfrp"]:
            scaled = _scale_structure_mass_by_power(lci, structure, 15.0)
            model_lci = _apply_material_model(
                lci_data=scaled,
                structure_type=structure,
                material_model=material_model,
                assumptions=assumptions,
                assumption_point="base",
                fawt_arm_center_share=None,
            )
            group_masses: dict[str, float] = {}
            for comp in model_lci.components.values():
                if comp.structure_type != structure:
                    continue
                group = _material_group(comp.material_id)
                group_masses[group] = group_masses.get(group, 0.0) + comp.mass_kg * comp.quantity
            total = sum(group_masses.values())
            record = {
                "structure_type": structure,
                "material_model": material_model,
                "capacity_factor": cf,
                "total_mass_kg": total,
                "total_mass_kg_per_mwh": total / energy_mwh,
            }
            for group in ["steel", "concrete", "copper", "composite", "aluminum", "other"]:
                mass = group_masses.get(group, 0.0)
                record[f"{group}_mass_kg"] = mass
                record[f"{group}_kg_per_mwh"] = mass / energy_mwh
                record[f"{group}_mass_share"] = mass / total if total > 0 else 0.0
            rows.append(record)

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "material_burden_screen_15mw.csv", index=False)

    # Compact table for manuscript appendix: GFRP baseline plus composite shift.
    gfrp = out[out["material_model"] == "gfrp"].set_index("structure_type")
    cfrp = out[out["material_model"] == "cfrp"].set_index("structure_type")
    summary_rows = []
    for structure in STRUCTURE_ORDER:
        g = gfrp.loc[structure]
        c = cfrp.loc[structure]
        summary_rows.append(
            {
                "structure_type": structure,
                "gfrp_total_kg_per_mwh": g["total_mass_kg_per_mwh"],
                "gfrp_steel_kg_per_mwh": g["steel_kg_per_mwh"],
                "gfrp_concrete_kg_per_mwh": g["concrete_kg_per_mwh"],
                "gfrp_composite_kg_per_mwh": g["composite_kg_per_mwh"],
                "cfrp_total_kg_per_mwh": c["total_mass_kg_per_mwh"],
                "cfrp_composite_kg_per_mwh": c["composite_kg_per_mwh"],
                "composite_kg_per_mwh_delta_cfrp_minus_gfrp": c["composite_kg_per_mwh"]
                - g["composite_kg_per_mwh"],
                "dominant_mass_group_gfrp": max(
                    ["steel", "concrete", "copper", "composite", "aluminum", "other"],
                    key=lambda group: g[f"{group}_kg_per_mwh"],
                ),
            }
        )
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / "material_burden_screen_15mw_summary.csv", index=False)
    return summary


def build_expanded_uncertainty_envelope() -> pd.DataFrame:
    """Combine MC intervals with deterministic stress tests as a screening envelope."""
    baseline = pd.read_csv(SRC / "analysis" / "intensity_15mw_table.csv").set_index("structure_type")
    burden = build_material_burden_screen().set_index("structure_type")
    mc_engine = MCEngine(
        n_samples=10_000,
        seed=42,
        assumptions_path=ASSUMPTIONS,
        lci_dir=LCI_DIR,
    )
    mc_raw = mc_engine.run(
        structures=STRUCTURE_ORDER,
        rated_powers=[15.0],
        material_models=["gfrp"],
    )
    mc_raw.to_csv(OUT / "expanded_uncertainty_mc_raw_15mw_gfrp.csv", index=False)
    steel = pd.read_csv(V6 / "steel_coefficient_stress_15mw.csv")
    fawt_mass = pd.read_csv(SRC / "fawt_mass_sensitivity_stress_test.csv")
    onshore_scale = pd.read_csv(V6 / "onshore_scaling_exponent_sensitivity_15mw.csv")
    lifetime = pd.read_csv(SRC / "lifetime_sensitivity_15mw_gfrp.csv")
    concrete_coeff_base = 0.107
    concrete_coeff_high = 0.214

    rows: list[dict] = []
    for structure in STRUCTURE_ORDER:
        base = float(baseline.loc[structure, "gfrp"])
        mc = mc_raw[
            (mc_raw["structure_type"] == structure)
            & (mc_raw["rated_power_mw"] == 15.0)
            & (mc_raw["material_model"] == "gfrp")
        ]["intensity_gco2_per_kwh"]
        mc_low, mc_high = mc.quantile([0.025, 0.975]).to_list()

        steel_block = steel[(steel["structure_type"] == structure)]
        steel_low = float(steel_block["gfrp_intensity_gpkwh"].min())
        steel_high = float(steel_block["gfrp_intensity_gpkwh"].max())

        lifetime_block = lifetime[lifetime["structure_type"] == structure]
        life_low = float(lifetime_block["intensity_gco2_per_kwh"].min())
        life_high = float(lifetime_block["intensity_gco2_per_kwh"].max())

        concrete_high = base + float(burden.loc[structure, "gfrp_concrete_kg_per_mwh"]) * (
            concrete_coeff_high - concrete_coeff_base
        )

        scenario_values = [mc_low, mc_high, steel_low, steel_high, concrete_high]
        structural_stress_low = None
        structural_stress_high = None
        if structure == "fawt":
            f15 = fawt_mass[fawt_mass["rated_power_mw"] == 15].iloc[0]
            structural_stress_low = float(f15["intensity_-30pct_gco2_per_kwh"])
            structural_stress_high = float(f15["intensity_+30pct_gco2_per_kwh"])
            scenario_values += [structural_stress_low, structural_stress_high]
        elif structure == "onshore":
            structural_stress_low = float(onshore_scale["onshore_15mw_gfrp_gpkwh"].min())
            structural_stress_high = float(onshore_scale["onshore_15mw_gfrp_gpkwh"].max())
            scenario_values += [structural_stress_low, structural_stress_high]

        rows.append(
            {
                "structure_type": structure,
                "baseline_gpkwh": base,
                "mc95_low_cf_eol_gpkwh": mc_low,
                "mc95_high_cf_eol_gpkwh": mc_high,
                "steel_stress_low_gpkwh": steel_low,
                "steel_stress_high_gpkwh": steel_high,
                "lifetime_stress_low_gpkwh": life_low,
                "lifetime_stress_high_gpkwh": life_high,
                "concrete_stress_high_gpkwh": concrete_high,
                "structural_stress_low_gpkwh": structural_stress_low,
                "structural_stress_high_gpkwh": structural_stress_high,
                "screening_envelope_low_gpkwh": min(scenario_values),
                "screening_envelope_high_gpkwh": max(scenario_values),
                "note": "Screening envelope excludes common-horizon lifetime screen; not a joint confidence interval",
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "expanded_uncertainty_screening_envelope_15mw_gfrp.csv", index=False)
    return out


def build_concrete_coefficient_stress() -> pd.DataFrame:
    """One-factor high-strength concrete coefficient stress for concrete-heavy structures."""
    baseline = pd.read_csv(SRC / "analysis" / "intensity_15mw_table.csv").set_index("structure_type")
    burden = build_material_burden_screen().set_index("structure_type")
    rows: list[dict] = []
    base_coeff = 0.107
    stress_coeffs = [0.150, 0.200, 0.214]
    for structure in STRUCTURE_ORDER:
        base = float(baseline.loc[structure, "gfrp"])
        concrete_intensity = float(burden.loc[structure, "gfrp_concrete_kg_per_mwh"])
        record = {
            "structure_type": structure,
            "baseline_gpkwh": base,
            "concrete_kg_per_mwh": concrete_intensity,
        }
        for coeff in stress_coeffs:
            stressed = base + concrete_intensity * (coeff - base_coeff)
            record[f"concrete_coeff_{coeff:.3f}_gpkwh"] = stressed
            record[f"delta_vs_baseline_{coeff:.3f}_gpkwh"] = stressed - base
        rows.append(record)

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "concrete_coefficient_stress_15mw_gfrp.csv", index=False)
    return out


def build_baseline_phase_contribution() -> pd.DataFrame:
    """L1--L4 contribution table for the 15 MW GFRP baseline."""
    matrix = pd.read_csv(SRC / "matrix_latest.csv")
    df = matrix[
        (matrix["rated_power_mw"] == 15.0)
        & (matrix["material_model"] == "gfrp")
        & matrix["structure_type"].isin(STRUCTURE_ORDER)
    ].set_index("structure_type").loc[STRUCTURE_ORDER]
    rows: list[dict] = []
    for structure, row in df.iterrows():
        energy = float(row["energy_generation_mwh"])
        l1 = float(row["l1_manufacturing_kgco2"]) / energy
        l2 = float(row["l2_transport_kgco2"]) / energy
        l3 = float(row["l3_o_and_m_kgco2"]) / energy
        l4 = float(row["l4_eol_kgco2"]) / energy
        total = float(row["total_gwp_kgco2"]) / energy
        rows.append(
            {
                "structure_type": structure,
                "l1_manufacturing_gpkwh": l1,
                "l2_transport_installation_gpkwh": l2,
                "l3_o_and_m_gpkwh": l3,
                "l4_end_of_life_gpkwh": l4,
                "total_gpkwh": total,
                "l3_share_pct": 100.0 * l3 / total if total else 0.0,
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "baseline_phase_contribution_15mw_gfrp.csv", index=False)
    return out


def build_fawt_evidence_envelope() -> pd.DataFrame:
    threshold = pd.read_csv(V6 / "fawt_intensity_threshold_15mw.csv")
    fawt_mass = pd.read_csv(SRC / "fawt_mass_sensitivity_stress_test.csv")
    f15 = fawt_mass[fawt_mass["rated_power_mw"] == 15].iloc[0]
    rows = [
        {
            "evidence_item": "Structural mass basis",
            "disclosure_form": "Partner-provided category-level input; numerical detail not public",
            "quantitative_treatment": "Proportional lifecycle-intensity stress band: -30%, base, +30%",
            "15mw_value_or_range": f"{f15['intensity_-30pct_gco2_per_kwh']:.2f}-{f15['intensity_+30pct_gco2_per_kwh']:.2f} g-CO2eq/kWh",
            "interpretation": "Scenario evidence; not used as a public structural benchmark",
        },
        {
            "evidence_item": "Comparator-gap bound",
            "disclosure_form": "Derived from disclosed intensity outputs",
            "quantitative_treatment": "Allowable uplift before crossing semisubmersible/spar baseline",
            "15mw_value_or_range": "; ".join(
                f"{r.comparator_structure}: +{r.allowable_uplift_gpkwh:.2f} g-CO2eq/kWh ({r.allowable_uplift_pct_of_fawt_base:.1f}%)"
                for r in threshold.itertuples()
            ),
            "interpretation": "Baseline advantage is sensitive to structural-basis uplift",
        },
        {
            "evidence_item": "Capacity factor",
            "disclosure_form": "Floating-offshore proxy, not FAWT-specific measured performance",
            "quantitative_treatment": "Triangular Monte Carlo input",
            "15mw_value_or_range": "0.35 / 0.42 / 0.50",
            "interpretation": "Energy-yield uncertainty remains a major interpretation boundary",
        },
        {
            "evidence_item": "O&M intensity",
            "disclosure_form": "Floating-O&M proxy band",
            "quantitative_treatment": "min/base/max assumption register",
            "15mw_value_or_range": "0.12 / 0.17 / 0.23 kg-CO2eq per ton-year",
            "interpretation": "No measured commercial FAWT O&M claim",
        },
    ]
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "fawt_disclosure_evidence_envelope.csv", index=False)
    return out


def build_data_quality_register() -> pd.DataFrame:
    rows = [
        {
            "input_group": "Material GWP coefficients",
            "source_type": "Public/proxy",
            "technological_representativeness": 3,
            "geographical_representativeness": 3,
            "temporal_representativeness": 4,
            "completeness": 3,
            "uncertainty_treatment": "Deterministic coefficient stress/envelope",
            "main_limitation": "Some materials use process-matched proxies rather than project-specific LCIs",
        },
        {
            "input_group": "Public support-structure masses",
            "source_type": "Public reference designs/proxy",
            "technological_representativeness": 4,
            "geographical_representativeness": 3,
            "temporal_representativeness": 4,
            "completeness": 3,
            "uncertainty_treatment": "Scaling and coefficient stress tests",
            "main_limitation": "Not redesigned at each rated-power class",
        },
        {
            "input_group": "FAWT structural mass",
            "source_type": "Partner-bounded",
            "technological_representativeness": 2,
            "geographical_representativeness": 2,
            "temporal_representativeness": 3,
            "completeness": 2,
            "uncertainty_treatment": "Disclosure-preserving proportional stress band",
            "main_limitation": "Numerical structural breakdown cannot be fully disclosed",
        },
        {
            "input_group": "Capacity factor",
            "source_type": "Public/proxy",
            "technological_representativeness": 3,
            "geographical_representativeness": 2,
            "temporal_representativeness": 4,
            "completeness": 3,
            "uncertainty_treatment": "Structure-specific triangular Monte Carlo input",
            "main_limitation": "Representative rather than site-specific resource modelling",
        },
        {
            "input_group": "End-of-life credit",
            "source_type": "Scenario",
            "technological_representativeness": 2,
            "geographical_representativeness": 2,
            "temporal_representativeness": 3,
            "completeness": 2,
            "uncertainty_treatment": "Uniform credit-realisation Monte Carlo and deterministic EoL cases",
            "main_limitation": "Allocation and recycling-market realization are scenario-dependent",
        },
        {
            "input_group": "O&M intensity",
            "source_type": "Proxy",
            "technological_representativeness": 2,
            "geographical_representativeness": 2,
            "temporal_representativeness": 3,
            "completeness": 2,
            "uncertainty_treatment": "Proxy band and interpretation boundary",
            "main_limitation": "Floating and FAWT O&M strategies are not project-specific",
        },
    ]
    out = pd.DataFrame(rows)
    out["mean_quality_score"] = out[
        [
            "technological_representativeness",
            "geographical_representativeness",
            "temporal_representativeness",
            "completeness",
        ]
    ].mean(axis=1)
    out.to_csv(OUT / "data_quality_register.csv", index=False)
    return out


def build_markdown_summary(outputs: dict[str, pd.DataFrame]) -> Path:
    path = OUT / "ijlca_strengthening_summary_20260702.md"
    lines = [
        "# IJLCA Strengthening Outputs",
        "",
        "Generated outputs for four targeted manuscript improvements.",
        "",
        "## Output files",
        "",
    ]
    for name in [
        "material_burden_screen_15mw_summary.csv",
        "expanded_uncertainty_screening_envelope_15mw_gfrp.csv",
        "concrete_coefficient_stress_15mw_gfrp.csv",
        "baseline_phase_contribution_15mw_gfrp.csv",
        "fawt_disclosure_evidence_envelope.csv",
        "data_quality_register.csv",
    ]:
        lines.append(f"- `{name}`")
    lines += [
        "",
        "## Key interpretation",
        "",
        "- The material-burden screen is not a multi-impact LCIA result; it identifies resource/circularity burden-shifting candidates by material mass intensity.",
        "- The expanded uncertainty envelope is a scenario/stress envelope, not a joint confidence interval.",
        "- The concrete-coefficient stress tests the consequence of using a higher-strength concrete proxy for concrete-heavy floating structures.",
        "- The phase-contribution table exposes the small L3 O&M contribution implied by the compact structural-mass-linked O&M proxy.",
        "- FAWT findings remain disclosure-bounded scenario evidence.",
        "- The data-quality register makes proxy and partner-bounded inputs explicit.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    outputs = {
        "material": build_material_burden_screen(),
        "uncertainty": build_expanded_uncertainty_envelope(),
        "concrete": build_concrete_coefficient_stress(),
        "phase": build_baseline_phase_contribution(),
        "fawt": build_fawt_evidence_envelope(),
        "quality": build_data_quality_register(),
    }
    summary = build_markdown_summary(outputs)
    print(f"Wrote IJLCA strengthening outputs to {OUT}")
    print(f"Summary: {summary}")


if __name__ == "__main__":
    main()
