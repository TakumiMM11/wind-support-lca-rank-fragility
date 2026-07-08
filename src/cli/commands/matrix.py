"""Matrix command - Execute LCA across structure/power/material combinations."""

from __future__ import annotations

import copy
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import click
import pandas as pd

from src.lca.calculator import LCACalculator
from src.lci.loaders import load_all_lci_data
from src.lci.models import Component, LCAEvent, LCIData, Material, TransportVehicle
from src.utils.manifest import ManifestWriter

logger = logging.getLogger(__name__)

DEFAULT_STRUCTURES = ["onshore", "bottom_fixed", "semisubmersible", "spar", "fawt"]
DEFAULT_POWERS_MW = [2.0, 5.0, 10.0, 15.0]
DEFAULT_MATERIAL_MODELS = ["gfrp", "cfrp", "rcfrp", "rrcfrp"]

# Material IDs are normalized to lowercase by loader.
MATERIAL_MODELS: Dict[str, Dict[str, str]] = {
    "gfrp": {"steel": "steel()"},
    "cfrp": {"steel": "steel()"},
    "rcfrp": {"steel": "steel()"},
    "rrcfrp": {"steel": "steel()"},
}

DEFAULT_CAPACITY_FACTORS = {
    "onshore": 0.35,
    "bottom_fixed": 0.45,
    "semisubmersible": 0.50,
    "spar": 0.50,
    "fawt": 0.50,
}

REFERENCE_POWER_MW = {
    "onshore": 3.0,
    "bottom_fixed": 15.0,
    "semisubmersible": 15.0,
    "spar": 15.0,
    "fawt": 15.0,
}

# Fraction of aggregate component mass treated as blade/composite-sensitive.
# This avoids applying CFRP substitution to full RNA aggregates.
BLADE_FRACTION_BY_ITEM_ID = {
    "on_rotor": 0.67,   # blade+hub aggregate
    "bf_rotor": 0.30,   # RNA proxy (blade share only)
    "fl_rotor": 0.30,   # floating RNA proxy
    "fawt_rotor_support": 1.0,
}

BLADE_DESIGN_BY_MODEL = {
    # Baseline
    "gfrp": {
        "mass_factor": 1.00,
        "layers": [("ud-gfrp", 1.00)],
    },
    # CFRP case: CFRTS only
    "cfrp": {
        "mass_factor": 0.72,
        "layers": [("vud-cfrts(general)", 1.00)],
    },
    # rCFRP case: CFRTS skin + 1x recycled CFRTP core
    "rcfrp": {
        "mass_factor": 0.75,
        "layers": [("vud-cfrts(general)", 0.40), ("rcfrtp", 0.60)],
    },
    # rrCFRP case: 2x recycled CFRTP core has better GWP/kg, but needs more core mass
    "rrcfrp": {
        "mass_factor": 0.82,
        "layers": [("vud-cfrts(general)", 0.35), ("rrcfrtp_proxy", 0.65)],
    },
}

# Conservative compression to avoid FAWT overestimation from direct Excel transfer.
FAWT_COMPRESSION = {
    "fawt_spar": 0.30,
}

# FAWT ballast proxy: low-CG stabilization with hydrostatic reserve.
FAWT_BALLAST_PROXY = {
    "top_mass_coeff": 1.25,
    "spar_mass_coeff": 0.20,
    "min_top_mass_coeff": 0.90,
}
# Guardrails for FAWT 46% scenario:
# apply only partial compression to heavy supports so results stay in
# the same order-of-magnitude as the base analysis run.
FAWT_SHARE_COMPRESSION_MIN_SCALE = 0.92
FAWT_SHARE_COMPRESSION_BLEND = 0.35
FAWT_SHARE_COMPRESSION_TARGET_ITEMS = {"fawt_spar", "fawt_ballast", "fawt_pto"}

# Mass cascade proxy coefficients for "lighter blade -> lighter support structure".
STRUCTURAL_FEEDBACK_COEFFS = {
    "onshore": {"on_tower": 0.30, "on_foundation": 0.40},
    "bottom_fixed": {"bf_tower": 0.25, "bf_foundation": 0.30},
    "semisubmersible": {"fl_tower": 0.20, "fl_platform": 0.35, "fl_ballast": 0.45, "fl_mooring": 0.25},
    "spar": {"fl_tower": 0.20, "fl_platform": 0.35, "fl_mooring": 0.25},
    "fawt": {"fawt_shaft": 0.15, "fawt_pto": 0.20, "fawt_spar": 0.35, "fawt_ballast": 0.50},
}

TRANSPORT_DISTANCE_KM = {
    "onshore": 200.0,
    "bottom_fixed": 350.0,
    "semisubmersible": 800.0,
    "spar": 900.0,
    "fawt": 900.0,
}

# Mixed logistics proxy (road+marine blended), kg-CO2 per ton-km.
TRANSPORT_EMISSION_FACTOR_KGCO2_PER_TON_KM = 0.015
DEFAULT_MATRIX_OUTPUT = Path("results/latest/matrix_latest.csv")
MATRIX_ARCHIVE_DIR = Path("results/archive/matrix")
DEFAULT_ASSUMPTIONS_FILE = Path("data/model_assumptions.json")
ASSUMPTION_POINTS = ["min", "base", "max"]
COMPONENT_REF_KEYWORDS = {
    "blade": ["blade", "rotor", "rotor_support"],
    "tower": ["tower"],
    "nacelle": ["nacelle", "pto", "generator", "gearbox"],
    "foundation_concrete": ["foundation", "platform", "ballast", "concrete"],
    "concrete": ["foundation", "platform", "ballast", "concrete"],
    "rebar": ["foundation", "tower", "spar"],
    "electrical_bop": ["elec", "cable", "electrical", "copper"],
}


def _parse_csv_list(raw: str) -> List[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_power_list(raw: str) -> List[float]:
    values = []
    for item in _parse_csv_list(raw):
        try:
            value = float(item)
        except ValueError as e:
            raise click.BadParameter(f"Invalid power value '{item}'") from e
        if value <= 0:
            raise click.BadParameter(f"Power must be positive, got {value}")
        values.append(value)
    return values


def _is_composite_component(component: Component) -> bool:
    original_id = component.metadata.get("original_item_id", "").lower()
    name = component.name.lower()
    return any(key in original_id for key in ("rotor", "rotor_support", "blade")) or any(
        key in name for key in ("ブレード", "rotor-support", "rotor")
    )


def _get_blade_fraction(component: Component) -> float:
    original_id = component.metadata.get("original_item_id", "").lower()
    return BLADE_FRACTION_BY_ITEM_ID.get(original_id, 1.0)


def _item_id(component: Component) -> str:
    return component.metadata.get("original_item_id", "").lower()


def _mass_scaling_exponent(component: Component) -> float:
    item = _item_id(component)
    # Calibrated to avoid non-physical worsening at higher MW while keeping
    # structurally heavier subsystems near-linear.
    if any(k in item for k in ("rotor", "rotor_support")):
        return 0.92
    if "tower" in item:
        return 0.97
    if any(k in item for k in ("foundation", "platform", "ballast", "mooring")):
        return 1.00
    if any(k in item for k in ("nacelle", "pto", "shaft", "elec")):
        return 0.95
    return 0.97


def _scale_structure_mass_by_power(
    lci_data: LCIData,
    structure_type: str,
    rated_power_mw: float,
) -> LCIData:
    """Scale structure component masses from reference power to target power."""
    ref = REFERENCE_POWER_MW[structure_type]
    if rated_power_mw <= 0:
        return lci_data

    ratio = rated_power_mw / ref
    if abs(ratio - 1.0) < 1e-9:
        return lci_data

    scaled = copy.deepcopy(lci_data)
    for comp in scaled.components.values():
        if comp.structure_type != structure_type:
            continue
        exp = _mass_scaling_exponent(comp)
        mass_scale = ratio ** exp
        comp.mass_kg = comp.mass_kg * mass_scale
        comp.base_mass_kg = comp.base_mass_kg * mass_scale
    return scaled


def _apply_structural_feedback(
    lci_data: LCIData,
    structure_type: str,
    blade_reduction_fraction: float,
) -> None:
    """Apply proxy cascade from blade mass reduction to support components."""
    if blade_reduction_fraction <= 0:
        return

    coeffs = STRUCTURAL_FEEDBACK_COEFFS.get(structure_type, {})
    if not coeffs:
        return

    for comp in lci_data.components.values():
        if comp.structure_type != structure_type:
            continue
        item = _item_id(comp)
        if item not in coeffs:
            continue
        k = coeffs[item]
        multiplier = max(0.50, 1.0 - k * blade_reduction_fraction)
        comp.mass_kg *= multiplier
        comp.base_mass_kg *= multiplier


def _apply_material_model(
    lci_data: LCIData,
    structure_type: str,
    material_model: str,
    assumptions: dict,
    assumption_point: str,
    fawt_arm_center_share: float | None = None,
) -> LCIData:
    """Return LCIData copy with material substitutions for one structure."""
    model = MATERIAL_MODELS[material_model]
    steel_material = model["steel"]
    blade_design = copy.deepcopy(BLADE_DESIGN_BY_MODEL[material_model])
    # Structure-specific blade design overrides from assumption register.
    override = (
        assumptions.get("blade_design_by_structure", {})
        .get(structure_type, {})
        .get(material_model, {})
    )
    if override:
        if "mass_factor" in override:
            blade_design["mass_factor"] = _value_at_point(override["mass_factor"], assumption_point)
        if "layer_shares" in override:
            layer_map = {}
            for mat_id, block in override["layer_shares"].items():
                layer_map[mat_id] = _value_at_point(block, assumption_point)
            total = sum(v for v in layer_map.values() if v > 0)
            if total > 0:
                blade_design["layers"] = [(k, v / total) for k, v in layer_map.items() if v > 0]
    blade_mass_factor = blade_design["mass_factor"]
    blade_layers = blade_design["layers"]

    material_ids = {m.id for m in lci_data.materials}
    if steel_material not in material_ids:
        raise ValueError(f"Steel material '{steel_material}' not found in materials.csv")

    # Ensure rrCFRTP proxy exists (2nd recycle scenario)
    if "rrcfrtp_proxy" not in material_ids:
        rcfrtp = next((m for m in lci_data.materials if m.id == "rcfrtp"), None)
        if rcfrtp is None:
            raise ValueError("Material 'rcfrtp' not found in materials.csv")
        rrcfrtp = Material(
            id="rrcfrtp_proxy",
            name="rrCFRTP(proxy)",
            variant="2x_recycled",
            density_kg_m3=rcfrtp.density_kg_m3,
            # Better environmental coefficient than 1x recycled core
            gwp_kgco2_per_kg=rcfrtp.gwp_kgco2_per_kg * 0.82,
            mechanical_properties=rcfrtp.mechanical_properties.copy(),
            price_usd_per_kg=rcfrtp.price_usd_per_kg,
            metadata={"source": "model_proxy", "notes": "2x recycled CFRTP proxy"},
        )
        lci_data = copy.deepcopy(lci_data)
        lci_data.materials.append(rrcfrtp)
        material_ids.add("rrcfrtp_proxy")

    for mat_id, _ in blade_layers:
        if mat_id not in material_ids:
            raise ValueError(f"Blade layer material '{mat_id}' not found in materials.csv")

    updated = copy.deepcopy(lci_data)
    baseline_blade_mass = 0.0
    updated_blade_mass = 0.0

    new_components: Dict[str, Component] = {}

    for comp_id, comp in list(updated.components.items()):
        if comp.structure_type != structure_type:
            continue

        if _is_composite_component(comp):
            blade_fraction = _get_blade_fraction(comp)
            blade_fraction = max(0.0, min(1.0, blade_fraction))

            if blade_fraction >= 1.0:
                baseline_blade_mass += comp.mass_kg
                total_blade_mass = comp.mass_kg * blade_mass_factor
                # Reuse original component for first layer and create extra layers if needed
                first_mat, first_frac = blade_layers[0]
                comp.mass_kg = total_blade_mass * first_frac
                comp.base_mass_kg = total_blade_mass * first_frac
                comp.material_id = first_mat
                updated_blade_mass += total_blade_mass
                for idx, (mat_id, frac) in enumerate(blade_layers[1:], start=1):
                    layer_mass = total_blade_mass * frac
                    layer_comp = Component(
                        id=f"{comp.id}__layer_{idx}",
                        name=f"{comp.name} (layer {idx})",
                        structure_type=comp.structure_type,
                        mass_kg=layer_mass,
                        base_mass_kg=layer_mass,
                        material_id=mat_id,
                        quantity=comp.quantity,
                        metadata=comp.metadata.copy(),
                    )
                    new_components[layer_comp.id] = layer_comp
                continue

            if blade_fraction <= 0.0:
                continue

            # Split aggregate component: blade-sensitive share + non-blade share.
            blade_mass = comp.mass_kg * blade_fraction
            non_blade_mass = comp.mass_kg - blade_mass
            baseline_blade_mass += blade_mass

            comp.mass_kg = non_blade_mass
            comp.base_mass_kg = non_blade_mass

            blade_mass_scaled = blade_mass * blade_mass_factor
            updated_blade_mass += blade_mass_scaled
            for idx, (mat_id, frac) in enumerate(blade_layers):
                layer_mass = blade_mass_scaled * frac
                layer_suffix = "blade_share" if idx == 0 else f"blade_share_layer_{idx}"
                blade_comp = Component(
                    id=f"{comp.id}__{layer_suffix}",
                    name=f"{comp.name} (blade share)" if idx == 0 else f"{comp.name} (blade layer {idx})",
                    structure_type=comp.structure_type,
                    mass_kg=layer_mass,
                    base_mass_kg=layer_mass,
                    material_id=mat_id,
                    quantity=comp.quantity,
                    metadata=comp.metadata.copy(),
                )
                new_components[blade_comp.id] = blade_comp
            continue

        if comp.material_id == "steel()" and steel_material != "steel()":
            comp.material_id = steel_material

    updated.components.update(new_components)

    # Apply structural feedback from lighter blade components.
    if baseline_blade_mass > 0 and updated_blade_mass < baseline_blade_mass:
        reduction = 1.0 - (updated_blade_mass / baseline_blade_mass)
        _apply_structural_feedback(updated, structure_type, reduction)

    # Compress FAWT heavy structural masses to avoid direct-overestimate carry-over.
    if structure_type == "fawt":
        fawt_components = []
        for comp in updated.components.values():
            if comp.structure_type != "fawt":
                continue
            fawt_components.append(comp)
            item = _item_id(comp)
            if item in FAWT_COMPRESSION:
                comp.mass_kg *= FAWT_COMPRESSION[item]
                comp.base_mass_kg *= FAWT_COMPRESSION[item]

        # Recalculate ballast from low-CG stability proxy instead of fixed factor.
        top_items = {"fawt_rotor_support", "fawt_shaft", "fawt_pto"}
        top_mass = sum(c.mass_kg for c in fawt_components if _item_id(c) in top_items)
        spar_mass = sum(c.mass_kg for c in fawt_components if _item_id(c) == "fawt_spar")
        ballast_comp = next((c for c in fawt_components if _item_id(c) == "fawt_ballast"), None)
        if ballast_comp is not None:
            target_ballast = (
                FAWT_BALLAST_PROXY["top_mass_coeff"] * top_mass
                + FAWT_BALLAST_PROXY["spar_mass_coeff"] * spar_mass
            )
            min_ballast = FAWT_BALLAST_PROXY["min_top_mass_coeff"] * top_mass
            target_ballast = max(target_ballast, min_ballast)
            # Keep this step as compression-only to stay conservative.
            ballast_comp.mass_kg = min(ballast_comp.mass_kg, target_ballast)
            ballast_comp.base_mass_kg = min(ballast_comp.base_mass_kg, target_ballast)

        # Optional scenario: move toward target (rotor-support + shaft) share
        # using bounded compression on heavy support items only.
        if fawt_arm_center_share is not None:
            rotor_support = next((c for c in fawt_components if _item_id(c) == "fawt_rotor_support"), None)
            shaft = next((c for c in fawt_components if _item_id(c) == "fawt_shaft"), None)
            if rotor_support is not None and shaft is not None:
                target_share = max(0.01, min(0.95, float(fawt_arm_center_share)))
                pair_current = rotor_support.mass_kg + shaft.mass_kg
                total_current = sum(c.mass_kg for c in fawt_components)
                others = max(0.0, total_current - pair_current)
                if others > 0 and pair_current > 0:
                    current_share = pair_current / total_current if total_current > 0 else 0.0
                    if target_share <= current_share:
                        return updated

                    # Compression-only interpretation with guardrails:
                    # keep rotor-support/shaft as-is; partially compress selected
                    # heavy supports so pair share moves toward target.
                    others_target = (pair_current * (1.0 - target_share)) / target_share
                    if others_target < others:
                        raw_scale = others_target / others
                        bounded_scale = max(FAWT_SHARE_COMPRESSION_MIN_SCALE, raw_scale)
                        scale = 1.0 - FAWT_SHARE_COMPRESSION_BLEND * (1.0 - bounded_scale)
                        for comp in fawt_components:
                            if comp is rotor_support or comp is shaft:
                                continue
                            if _item_id(comp) not in FAWT_SHARE_COMPRESSION_TARGET_ITEMS:
                                continue
                            comp.mass_kg *= scale
                            comp.base_mass_kg *= scale

    return updated


def _estimate_transport_gwp_proxy(total_mass_kg: float, structure_type: str) -> float:
    """Estimate transport GWP from total transported mass (proxy model)."""
    distance = TRANSPORT_DISTANCE_KM.get(structure_type, 300.0)
    mass_ton = total_mass_kg / 1000.0
    return mass_ton * distance * TRANSPORT_EMISSION_FACTOR_KGCO2_PER_TON_KM


def _load_assumptions(path: Path) -> dict:
    if not path.exists():
        raise ValueError(f"Assumptions file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _value_at_point(block: dict, point: str) -> float:
    if point not in block:
        raise ValueError(f"Assumption point '{point}' not found in {block}")
    return float(block[point])


def _resolve_capacity_factor(
    structure: str,
    capacity_factor_override: float | None,
    assumptions: dict,
    site_class: str,
    assumption_point: str,
) -> float:
    if capacity_factor_override is not None:
        return capacity_factor_override
    try:
        return _value_at_point(assumptions["site_class_cf"][site_class][structure], assumption_point)
    except KeyError as e:
        raise ValueError(f"Missing site_class_cf definition for site_class='{site_class}', structure='{structure}'") from e


def _estimate_l3_proxy(
    total_mass_kg: float,
    structure: str,
    lifetime_years: int,
    assumptions: dict,
    site_class: str,
    assumption_point: str,
) -> float:
    service_rate = _value_at_point(
        assumptions["l3_service_kgco2_per_ton_year"][structure],
        assumption_point,
    )
    site_mult = _value_at_point(
        assumptions["l3_site_multiplier"][site_class],
        assumption_point,
    )
    return (total_mass_kg / 1000.0) * service_rate * site_mult * lifetime_years


def _material_group(material_id: str, assumptions: dict) -> str | None:
    mat = material_id.lower()
    for rule in assumptions["material_group_rules"]:
        if any(token in mat for token in rule["match_any"]):
            return rule["group"]
    return None


def _as_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _component_mass_by_ref(structure_components: list[Component], component_ref: str, assumptions: dict) -> float:
    ref = (component_ref or "").lower().strip()
    if not ref:
        return 0.0

    # Direct keyword mapping first.
    keys = COMPONENT_REF_KEYWORDS.get(ref, [ref])
    mass = 0.0
    for comp in structure_components:
        item = _item_id(comp)
        if any(k in item for k in keys):
            mass += comp.mass_kg * comp.quantity
    if mass > 0:
        return mass

    # Fallback to material-group-level aggregate if component_ref is material-like.
    for group in ("steel", "concrete", "copper", "aluminum", "composite"):
        if group in ref:
            return sum(
                c.mass_kg * c.quantity
                for c in structure_components
                if _material_group(c.material_id, assumptions) == group
            )
    return 0.0


def _distance_km_from_event(event: LCAEvent) -> float:
    d = _as_float(event.distance_km, 0.0)
    if d > 0:
        return d
    return max(
        _as_float(event.metadata.get("one_way_km"), 0.0),
        _as_float(event.metadata.get("route_km"), 0.0),
        _as_float(event.metadata.get("roundtrip_km"), 0.0),
    )


def _transport_event_gwp(
    event: LCAEvent,
    vehicles: dict[str, TransportVehicle],
    load_mass_kg: float,
    distance_km: float,
    trips: float,
) -> float:
    if trips <= 0:
        return 0.0
    fixed_per_trip = _as_float(event.metadata.get("fixed_gwp_kgco2_per_trip"), 0.0)
    fixed_total = fixed_per_trip * trips
    if distance_km <= 0:
        return fixed_total
    vehicle = vehicles.get((event.vehicle_type or "").lower())
    if vehicle is None:
        # Fallback coefficient if vehicle is missing.
        variable = (load_mass_kg / 1000.0) * distance_km * trips * TRANSPORT_EMISSION_FACTOR_KGCO2_PER_TON_KM
        return variable + fixed_total

    load_ton = max(0.0, load_mass_kg / 1000.0)
    # Use one-trip payload as effective loading.
    payload_ton = load_ton / max(trips, 1.0)
    load_ratio = min(1.0, payload_ton / max(vehicle.capacity_ton, 1e-6))
    fuel_per_km = vehicle.base_fuel_L_per_km * (1.0 + vehicle.load_factor_sensitivity * load_ratio)
    variable = distance_km * trips * fuel_per_km * vehicle.gwp_kgco2_per_L
    return variable + fixed_total


def _estimate_l2_from_events(
    events: list[LCAEvent],
    structure_components: list[Component],
    vehicles: dict[str, TransportVehicle],
    assumptions: dict,
) -> float:
    total = 0.0
    for event in events:
        if event.phase != "A4":
            continue
        trips = _as_float(event.trips, 1.0)
        distance_km = _distance_km_from_event(event)
        mass_kg = _as_float(event.metadata.get("mass_t"), 0.0) * 1000.0
        if mass_kg <= 0:
            mass_kg = _component_mass_by_ref(structure_components, event.component_ref, assumptions)
        total += _transport_event_gwp(
            event=event,
            vehicles=vehicles,
            load_mass_kg=mass_kg,
            distance_km=distance_km,
            trips=trips,
        )
    return total


def _estimate_l3_from_events(
    events: list[LCAEvent],
    structure_components: list[Component],
    vehicles: dict[str, TransportVehicle],
    assumptions: dict,
    lifetime_years: int,
    structure: str,
    site_class: str,
    assumption_point: str,
) -> float:
    total = 0.0
    site_mult = _value_at_point(assumptions["l3_site_multiplier"][site_class], assumption_point)
    consumables = assumptions.get("l3_consumable_gwp_kgco2_per_kg", {})
    diesel_factor = _value_at_point(consumables.get("diesel", {"base": 2.68}), assumption_point)
    visit_km_factor = _value_at_point(assumptions.get("l3_visit_transport_kgco2_per_km", {"base": 0.28}), assumption_point)

    for event in events:
        if event.phase != "B":
            continue

        if event.event_type == "annual_visit":
            freq = _as_float(event.metadata.get("frequency_per_year"), 0.0)
            if freq <= 0:
                freq = _as_float(event.metadata.get("visits_per_year"), 0.0)
            if freq <= 0:
                freq = 1.0
            distance_km = _distance_km_from_event(event)
            if distance_km <= 0:
                distance_km = _as_float(event.metadata.get("roundtrip_km"), 0.0)
            total += lifetime_years * freq * distance_km * visit_km_factor * site_mult
            continue

        # Frequency over lifetime
        freq = _as_float(event.metadata.get("frequency_per_year"), 0.0)
        expected_life = _as_float(event.metadata.get("expected_events_per_life"), 0.0)
        if freq > 0:
            life_factor = freq * lifetime_years
        elif expected_life > 0:
            life_factor = expected_life
        else:
            # Fallback: one event per lifetime for replacement-like events
            life_factor = 1.0

        distance_km = _distance_km_from_event(event)
        if distance_km <= 0:
            distance_km = max(
                _as_float(event.metadata.get("roundtrip_km"), 0.0),
                _as_float(event.metadata.get("inbound_truck_km"), 0.0) + _as_float(event.metadata.get("outbound_truck_km"), 0.0),
            )

        trips = _as_float(event.trips, 1.0)
        mass_kg = _as_float(event.metadata.get("mass_t"), 0.0) * 1000.0
        if mass_kg <= 0:
            mass_kg = _component_mass_by_ref(structure_components, event.component_ref, assumptions) * 0.05
        transport = _transport_event_gwp(
            event=event,
            vehicles=vehicles,
            load_mass_kg=mass_kg,
            distance_km=distance_km,
            trips=trips,
        )

        crane_days = _as_float(event.metadata.get("crane_days"), 0.0)
        crane_fuel = _as_float(event.metadata.get("crane_fuel_L_per_day"), 0.0)
        crane_gwp = crane_days * crane_fuel * diesel_factor

        lube = _as_float(event.metadata.get("lube_oil_kg"), 0.0) * _value_at_point(consumables.get("lube_oil", {"base": 3.0}), assumption_point)
        grease = _as_float(event.metadata.get("grease_kg"), 0.0) * _value_at_point(consumables.get("grease", {"base": 3.2}), assumption_point)
        filters = _as_float(event.metadata.get("filters_kg"), 0.0) * _value_at_point(consumables.get("filters", {"base": 4.0}), assumption_point)
        spares = _as_float(event.metadata.get("minor_spares_kg"), 0.0) * _value_at_point(consumables.get("minor_spares", {"base": 2.8}), assumption_point)

        total += life_factor * site_mult * (transport + crane_gwp + lube + grease + filters + spares)

    # Safety floor: keep structure-level service burden proxy as minimum coverage.
    proxy_floor = _estimate_l3_proxy(
        total_mass_kg=sum(c.mass_kg * c.quantity for c in structure_components),
        structure=structure,
        lifetime_years=lifetime_years,
        assumptions=assumptions,
        site_class=site_class,
        assumption_point=assumption_point,
    )
    return max(total, proxy_floor)


def _estimate_l4_from_events(
    events: list[LCAEvent],
    structure_components: list[Component],
    vehicles: dict[str, TransportVehicle],
    assumptions: dict,
    structure: str,
    assumption_point: str,
    eol_credit_rate: float | None = None,
) -> float:
    # Start from material-level recovery model.
    l4_material_model = _estimate_l4_proxy(
        structure_components=structure_components,
        structure=structure,
        assumptions=assumptions,
        assumption_point=assumption_point,
        eol_credit_rate=eol_credit_rate,
    )

    # Add explicit dismantling/transport overhead from events.
    consumables = assumptions.get("l3_consumable_gwp_kgco2_per_kg", {})
    diesel_factor = _value_at_point(consumables.get("diesel", {"base": 2.68}), assumption_point)
    overhead = 0.0
    for event in events:
        if event.phase != "C":
            continue
        distance_km = _distance_km_from_event(event)
        trips = _as_float(event.trips, 1.0)
        mass_kg = _as_float(event.metadata.get("mass_t"), 0.0) * 1000.0
        if mass_kg <= 0:
            mass_kg = _component_mass_by_ref(structure_components, event.component_ref, assumptions) * 0.5
        overhead += _transport_event_gwp(
            event=event,
            vehicles=vehicles,
            load_mass_kg=mass_kg,
            distance_km=distance_km,
            trips=trips,
        )
        overhead += _as_float(event.metadata.get("crane_days"), 0.0) * _as_float(event.metadata.get("crane_fuel_L_per_day"), 0.0) * diesel_factor
    return l4_material_model + overhead


def _estimate_l4_proxy(
    structure_components: list[Component],
    structure: str,
    assumptions: dict,
    assumption_point: str,
    eol_credit_rate: float | None = None,
) -> float:
    if eol_credit_rate is not None:
        credit_realization = eol_credit_rate
    else:
        credit_realization = _value_at_point(
            assumptions["l4_credit_realization"][structure],
            assumption_point,
        )
    structure_mult = _value_at_point(
        assumptions["l4_structure_multiplier"][structure],
        assumption_point,
    )

    material_params = assumptions["l4_material_parameters"]
    l4_total = 0.0
    for comp in structure_components:
        mass_kg = comp.mass_kg * comp.quantity
        if mass_kg <= 0:
            continue
        group = _material_group(comp.material_id, assumptions)
        if group is None:
            continue
        p = material_params[group]
        recovery = _value_at_point(p["recovery_rate"], assumption_point)
        reprocess = _value_at_point(p["reprocess_burden_kgco2_per_kg"], assumption_point)
        landfill = _value_at_point(p["landfill_burden_kgco2_per_kg"], assumption_point)
        virgin_credit = _value_at_point(p["virgin_avoid_credit_kgco2_per_kg"], assumption_point)
        eol_per_kg = (recovery * reprocess) + ((1.0 - recovery) * landfill) - (recovery * credit_realization * virgin_credit)
        l4_total += mass_kg * eol_per_kg

    return l4_total * structure_mult


def _archive_existing_output(output_path: Path) -> Path | None:
    """Archive existing output file and return archive path if moved."""
    if not output_path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    MATRIX_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archived = MATRIX_ARCHIVE_DIR / f"{output_path.stem}_{timestamp}{output_path.suffix}"
    shutil.move(str(output_path), str(archived))
    return archived


def _add_rr_rc_decomposition_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add rr-vs-rc decomposition columns for interpretability (FB4 support).

    Columns are attached to both `rcfrp` and `rrcfrp` rows of the same
    structure/power/site settings:
    - rr_rc_net_delta_gpkwh
    - rr_rc_core_mass_penalty_effect_gpkwh
    - rr_rc_material_factor_benefit_gpkwh
    """
    out = df.copy()
    out["rr_rc_net_delta_gpkwh"] = pd.NA
    out["rr_rc_core_mass_penalty_effect_gpkwh"] = pd.NA
    out["rr_rc_material_factor_benefit_gpkwh"] = pd.NA

    subset = out[out["material_model"].isin(["rcfrp", "rrcfrp"])].copy()
    if subset.empty:
        return out

    key_cols = [
        "structure_type",
        "rated_power_mw",
        "site_class",
        "assumption_point",
        "lifetime_years",
        "capacity_factor",
    ]

    val_cols = [
        "component_total_mass_kg",
        "energy_generation_mwh",
        "total_gwp_kgco2",
        "intensity_gco2_per_kwh",
        "l1_manufacturing_kgco2",
        "l2_transport_kgco2",
        "l3_o_and_m_kgco2",
        "l4_eol_kgco2",
    ]

    rc = subset[subset["material_model"] == "rcfrp"][key_cols + val_cols].rename(
        columns={c: f"{c}_rc" for c in val_cols}
    )
    rr = subset[subset["material_model"] == "rrcfrp"][key_cols + val_cols].rename(
        columns={c: f"{c}_rr" for c in val_cols}
    )
    # Normalize potential null keys before merge.
    for k in key_cols:
        if pd.api.types.is_numeric_dtype(rc[k]):
            rc[k] = rc[k].fillna(-9999.0)
            rr[k] = rr[k].fillna(-9999.0)
        else:
            rc[k] = rc[k].fillna("__NA__")
            rr[k] = rr[k].fillna("__NA__")
    pair = rc.merge(rr, on=key_cols, how="inner")
    if pair.empty:
        return out

    mass_rc = pair["component_total_mass_kg_rc"].astype(float)
    mass_rr = pair["component_total_mass_kg_rr"].astype(float)
    mass_diff = mass_rr - mass_rc
    total_delta_kgco2 = pair["total_gwp_kgco2_rr"].astype(float) - pair["total_gwp_kgco2_rc"].astype(float)
    energy_mwh = pair["energy_generation_mwh_rc"].astype(float).clip(lower=1e-9)

    phase_cols = [
        "l1_manufacturing_kgco2",
        "l2_transport_kgco2",
        "l3_o_and_m_kgco2",
        "l4_eol_kgco2",
    ]
    mass_penalty_kgco2 = pd.Series(0.0, index=pair.index)
    safe_mass_rc = mass_rc.where(mass_rc > 0, 1e-9)
    for ph in phase_cols:
        rc_intensity_per_kg = pair[f"{ph}_rc"].astype(float) / safe_mass_rc
        mass_penalty_kgco2 = mass_penalty_kgco2 + (rc_intensity_per_kg * mass_diff)

    material_benefit_kgco2 = total_delta_kgco2 - mass_penalty_kgco2

    # Numeric identity: kg/MWh == g/kWh
    pair["rr_rc_net_delta_gpkwh"] = total_delta_kgco2 / energy_mwh
    pair["rr_rc_core_mass_penalty_effect_gpkwh"] = mass_penalty_kgco2 / energy_mwh
    pair["rr_rc_material_factor_benefit_gpkwh"] = material_benefit_kgco2 / energy_mwh

    decomp_cols = key_cols + [
        "rr_rc_net_delta_gpkwh",
        "rr_rc_core_mass_penalty_effect_gpkwh",
        "rr_rc_material_factor_benefit_gpkwh",
    ]
    pair = pair[decomp_cols]

    out = out.merge(pair, on=key_cols, how="left", suffixes=("", "_new"))
    for col in [
        "rr_rc_net_delta_gpkwh",
        "rr_rc_core_mass_penalty_effect_gpkwh",
        "rr_rc_material_factor_benefit_gpkwh",
    ]:
        new_col = f"{col}_new"
        if new_col in out.columns:
            out[col] = out[new_col].where(out[new_col].notna(), out[col])
            out.drop(columns=[new_col], inplace=True)

    mask = out["material_model"].isin(["rcfrp", "rrcfrp"])
    for col in [
        "rr_rc_net_delta_gpkwh",
        "rr_rc_core_mass_penalty_effect_gpkwh",
        "rr_rc_material_factor_benefit_gpkwh",
    ]:
        out.loc[~mask, col] = pd.NA

    return out


@click.command()
@click.option(
    "--structures",
    default=",".join(DEFAULT_STRUCTURES),
    show_default=True,
    help="Comma-separated structure types",
)
@click.option(
    "--rated-powers",
    default=",".join(str(v).rstrip("0").rstrip(".") for v in DEFAULT_POWERS_MW),
    show_default=True,
    help="Comma-separated rated powers in MW",
)
@click.option(
    "--material-models",
    default=",".join(DEFAULT_MATERIAL_MODELS),
    show_default=True,
    help="Comma-separated material models: gfrp,cfrp,rcfrp,rrcfrp",
)
@click.option(
    "--lifetime-years",
    type=int,
    default=25,
    show_default=True,
    help="Project lifetime in years",
)
@click.option(
    "--capacity-factor",
    type=float,
    default=None,
    help="Fixed capacity factor for all structures (if omitted, structure defaults are used)",
)
@click.option(
    "--weight-cascade/--no-weight-cascade",
    default=False,
    show_default=True,
    help="Enable or disable weight cascade",
)
@click.option(
    "--site-class",
    default="baseline",
    show_default=True,
    help="Site condition class defined in assumptions file",
)
@click.option(
    "--fawt-arm-center-share",
    type=float,
    default=None,
    help="Optional FAWT assumption: enforce (rotor-support+shaft) share of total FAWT mass (0-1)",
)
@click.option(
    "--assumption-point",
    type=click.Choice(ASSUMPTION_POINTS),
    default="base",
    show_default=True,
    help="Use min/base/max values from assumptions",
)
@click.option(
    "--assumptions-file",
    type=click.Path(path_type=Path),
    default=DEFAULT_ASSUMPTIONS_FILE,
    show_default=True,
    help="Model assumptions JSON file",
)
@click.option(
    "--output-file",
    "-o",
    type=click.Path(path_type=Path),
    help="Output CSV path (default: results/latest/matrix_latest.csv)",
)
@click.option(
    "--archive-old/--no-archive-old",
    default=True,
    show_default=True,
    help="Archive existing output file before overwriting",
)
@click.option(
    "--eol-credit-rate",
    type=float,
    default=None,
    help="Override EoL credit realization rate [0-1] for all structures (None = use model default)",
)
@click.pass_context
def matrix(
    ctx,
    structures: str,
    rated_powers: str,
    material_models: str,
    lifetime_years: int,
    capacity_factor: float | None,
    weight_cascade: bool,
    site_class: str,
    fawt_arm_center_share: float | None,
    assumption_point: str,
    assumptions_file: Path,
    output_file: Path | None,
    archive_old: bool,
    eol_credit_rate: float | None,
):
    """Run matrix calculations over structure × rated_power × material_model."""
    verbose = ctx.obj.get("verbose", False)

    selected_structures = _parse_csv_list(structures)
    selected_material_models = [m.lower() for m in _parse_csv_list(material_models)]
    selected_powers = _parse_power_list(rated_powers)

    invalid_structures = [s for s in selected_structures if s not in DEFAULT_STRUCTURES]
    if invalid_structures:
        raise click.BadParameter(f"Invalid structures: {invalid_structures}")

    invalid_models = [m for m in selected_material_models if m not in MATERIAL_MODELS]
    if invalid_models:
        raise click.BadParameter(f"Invalid material models: {invalid_models}")

    if capacity_factor is not None and not 0 < capacity_factor < 1:
        raise click.BadParameter("capacity-factor must be in range (0, 1)")
    if fawt_arm_center_share is not None and not 0 < fawt_arm_center_share < 1:
        raise click.BadParameter("fawt-arm-center-share must be in range (0, 1)")
    if eol_credit_rate is not None and not 0.0 <= eol_credit_rate <= 1.0:
        raise click.BadParameter("eol-credit-rate must be in range [0, 1]")

    assumptions = _load_assumptions(assumptions_file)
    site_classes = assumptions.get("site_class_cf", {})
    if site_class not in site_classes:
        raise click.BadParameter(f"Invalid site-class '{site_class}'. Available: {sorted(site_classes.keys())}")

    click.echo("Loading shared LCI data...")
    try:
        lci_data = load_all_lci_data(data_dir=Path("data/lci"))
    except Exception as e:
        click.echo(f"Error: Failed to load LCI data: {e}", err=True)
        sys.exit(2)

    combos = [
        (structure, power, model)
        for structure in selected_structures
        for power in selected_powers
        for model in selected_material_models
    ]

    click.echo(f"Running {len(combos)} combination(s)...")

    results = []
    failures = 0

    for idx, (structure, power, model) in enumerate(combos, 1):
        cf = _resolve_capacity_factor(
            structure=structure,
            capacity_factor_override=capacity_factor,
            assumptions=assumptions,
            site_class=site_class,
            assumption_point=assumption_point,
        )
        scenario_name = f"matrix-{structure}-{power:g}mw-{model}"

        click.echo(f"[{idx}/{len(combos)}] {scenario_name}")

        try:
            model_lci_data = _apply_material_model(
                lci_data=_scale_structure_mass_by_power(
                    lci_data=lci_data,
                    structure_type=structure,
                    rated_power_mw=power,
                ),
                structure_type=structure,
                material_model=model,
                assumptions=assumptions,
                assumption_point=assumption_point,
                fawt_arm_center_share=fawt_arm_center_share if structure == "fawt" else None,
            )

            calculator = LCACalculator(
                lci_data=model_lci_data,
                structure_type=structure,
                rated_power_mw=power,
                lifetime_years=lifetime_years,
                capacity_factor=cf,
                scenario_name=scenario_name,
                enable_weight_cascade=weight_cascade,
                log_iterations=verbose,
                write_detailed_log=False,
            )
            calc_result = calculator.calculate()

            structure_components = [
                c for c in model_lci_data.components.values() if c.structure_type == structure
            ]
            structure_events = [
                e for e in model_lci_data.events if e.structure_type == structure
            ]
            total_component_mass_kg = sum(c.mass_kg * c.quantity for c in structure_components)
            l2_event = _estimate_l2_from_events(
                events=structure_events,
                structure_components=structure_components,
                vehicles=model_lci_data.vehicles,
                assumptions=assumptions,
            )
            l2_proxy = _estimate_transport_gwp_proxy(total_component_mass_kg, structure)
            l2_adjusted = l2_event if l2_event > 0 else l2_proxy

            l3_event = _estimate_l3_from_events(
                events=structure_events,
                structure_components=structure_components,
                vehicles=model_lci_data.vehicles,
                assumptions=assumptions,
                structure=structure,
                lifetime_years=lifetime_years,
                site_class=site_class,
                assumption_point=assumption_point,
            )
            l4_event = _estimate_l4_from_events(
                events=structure_events,
                structure_components=structure_components,
                vehicles=model_lci_data.vehicles,
                assumptions=assumptions,
                structure=structure,
                assumption_point=assumption_point,
                eol_credit_rate=eol_credit_rate,
            )
            l3_adjusted = calc_result.l3_o_and_m_kgco2 + l3_event
            l4_adjusted = calc_result.l4_eol_kgco2 + l4_event
            total_gwp_adjusted = (
                calc_result.l1_manufacturing_kgco2
                + l2_adjusted
                + l3_adjusted
                + l4_adjusted
            )
            intensity_adjusted = (
                (total_gwp_adjusted * 1000.0) / (calc_result.energy_generation_mwh * 1000.0)
                if calc_result.energy_generation_mwh > 0
                else 0.0
            )

            results.append(
                {
                    "scenario_name": scenario_name,
                    "structure_type": structure,
                    "rated_power_mw": power,
                    "material_model": model,
                    "site_class": site_class,
                    "assumption_point": assumption_point,
                    "fawt_arm_center_share": fawt_arm_center_share if structure == "fawt" else None,
                    "lifetime_years": lifetime_years,
                    "capacity_factor": cf,
                    "component_total_mass_kg": total_component_mass_kg,
                    "l1_manufacturing_kgco2": calc_result.l1_manufacturing_kgco2,
                    "l2_transport_kgco2": l2_adjusted,
                    "l3_o_and_m_kgco2": l3_adjusted,
                    "l4_eol_kgco2": l4_adjusted,
                    "l2_proxy_kgco2": l2_proxy,
                    "l2_event_kgco2": l2_event,
                    "l3_event_kgco2": l3_event,
                    "l4_event_kgco2": l4_event,
                    "total_gwp_kgco2": total_gwp_adjusted,
                    "intensity_gco2_per_kwh": intensity_adjusted,
                    "energy_generation_mwh": calc_result.energy_generation_mwh,
                    "weight_cascade_iterations": calc_result.weight_cascade_iterations,
                    "weight_cascade_converged": calc_result.weight_cascade_converged,
                }
            )
        except Exception as e:
            failures += 1
            click.echo(f"  ✗ Failed: {e}", err=True)
            logger.exception(
                "Matrix run failed for structure=%s power=%s model=%s",
                structure,
                power,
                model,
            )

    if not results:
        click.echo("Error: all matrix calculations failed", err=True)
        sys.exit(2)

    df = pd.DataFrame(results)
    df = _add_rr_rc_decomposition_columns(df)
    output_path = output_file if output_file else DEFAULT_MATRIX_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)
    archived_path = _archive_existing_output(output_path) if archive_old else None
    df.to_csv(output_path, index=False)

    # Write reproducibility manifest
    lci_dir = Path("data/lci")
    lci_input_files = [str(p) for p in lci_dir.glob("*.csv") if p.is_file()]
    lci_input_files.append(str(assumptions_file))
    manifest_path = ManifestWriter().write(
        command=" ".join(["python -m src.cli.main", "matrix", "--site-class", site_class,
                          "--assumption-point", assumption_point]),
        input_files=lci_input_files,
        output_files=[str(output_path)],
        output_dir=str(output_path.parent),
    )
    click.echo(f"  Manifest: {manifest_path}")

    click.echo("")
    click.echo("MATRIX SUMMARY")
    click.echo(f"  Successful: {len(results)}")
    click.echo(f"  Failed: {failures}")
    if archived_path is not None:
        click.echo(f"  Archived previous output: {archived_path}")
    click.echo(f"  Output: {output_path}")

    preview_cols = [
        "structure_type",
        "rated_power_mw",
        "material_model",
        "total_gwp_kgco2",
        "intensity_gco2_per_kwh",
    ]
    click.echo("")
    click.echo(df[preview_cols].head(20).to_string(index=False))

    if failures > 0:
        sys.exit(1)


__all__ = ["matrix"]
