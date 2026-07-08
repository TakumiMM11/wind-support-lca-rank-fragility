"""GWP (Global Warming Potential) Calculation Module.

This module implements GWP calculations for wind turbine LCA using IPCC AR5
100-year GWP coefficients embedded in material data.

Calculation Approach:
    Component GWP = mass_kg × material.gwp_kgco2_per_kg
    Total GWP = Σ(component GWP) across all phases
    Intensity = Total GWP / Lifetime Energy Generation (g-CO2eq/kWh)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List

from src.lci.models import Component, Material

logger = logging.getLogger(__name__)


@dataclass
class ComponentGWP:
    """GWP breakdown for a single component.

    Attributes:
        component_id: Component identifier
        component_name: Human-readable component name
        mass_kg: Component mass in kg
        material_id: Material identifier
        gwp_kgco2: Component GWP in kg-CO2
        gwp_per_kg: Material GWP coefficient (kg-CO2 per kg)
    """

    component_id: str
    component_name: str
    mass_kg: float
    material_id: str
    gwp_kgco2: float
    gwp_per_kg: float


@dataclass
class PhaseGWP:
    """GWP breakdown for a lifecycle phase.

    Attributes:
        phase_name: Phase identifier (manufacturing, transport, o_and_m, eol)
        total_gwp_kgco2: Total GWP for this phase in kg-CO2
        component_breakdown: List of component-level GWP values
        percentage: Percentage of total lifecycle GWP
    """

    phase_name: str
    total_gwp_kgco2: float
    component_breakdown: List[ComponentGWP] = field(default_factory=list)
    percentage: float = 0.0


@dataclass
class GWPResult:
    """Result of GWP calculation.

    Attributes:
        total_gwp_kgco2: Total lifecycle GWP in kg-CO2
        intensity_gco2_per_kwh: GWP intensity in g-CO2 per kWh
        phase_breakdown: Dict of phase-level GWP, keyed by phase name
        component_breakdown: List of component-level GWP for manufacturing phase
        energy_generation_mwh: Total lifetime energy generation in MWh
        metadata: Additional metadata (rated_power_mw, lifetime_years, capacity_factor, etc.)
    """

    total_gwp_kgco2: float
    intensity_gco2_per_kwh: float
    phase_breakdown: Dict[str, PhaseGWP]
    component_breakdown: List[ComponentGWP]
    energy_generation_mwh: float
    metadata: Dict[str, str] = field(default_factory=dict)


def calculate_gwp(
    components: Dict[str, Component],
    materials: List[Material],
    rated_power_mw: float,
    lifetime_years: int,
    capacity_factor: float,
) -> GWPResult:
    """Calculate GWP for manufacturing phase.

    This function computes component-level GWP using the formula:
        GWP = mass_kg × material.gwp_kgco2_per_kg

    Args:
        components: Dict of components after weight cascade
        materials: List of materials with GWP coefficients
        rated_power_mw: Turbine rated power in MW
        lifetime_years: Project lifetime in years
        capacity_factor: Capacity factor (0.0-1.0)

    Returns:
        GWPResult with component breakdown and total GWP

    Raises:
        ValueError: If material not found for component
        ValueError: If invalid energy generation parameters
    """
    # Validate inputs
    if rated_power_mw <= 0:
        raise ValueError(f"rated_power_mw must be positive, got {rated_power_mw}")
    if lifetime_years <= 0:
        raise ValueError(f"lifetime_years must be positive, got {lifetime_years}")
    if not 0 <= capacity_factor <= 1:
        raise ValueError(f"capacity_factor must be 0-1, got {capacity_factor}")

    # Build material lookup
    material_dict = {mat.id: mat for mat in materials}

    # Calculate component-level GWP
    component_gwps: List[ComponentGWP] = []
    phase_components: Dict[str, List[ComponentGWP]] = {
        "manufacturing": [],
        "transport": [],
        "o_and_m": [],
        "eol": [],
    }
    phase_totals: Dict[str, float] = {
        "manufacturing": 0.0,
        "transport": 0.0,
        "o_and_m": 0.0,
        "eol": 0.0,
    }

    phase_aliases = {
        "l1": "manufacturing",
        "manufacturing": "manufacturing",
        "a1-a3": "manufacturing",
        "l2": "transport",
        "transport": "transport",
        "a4": "transport",
        "l3": "o_and_m",
        "o_and_m": "o_and_m",
        "om": "o_and_m",
        "b": "o_and_m",
        "l4": "eol",
        "eol": "eol",
        "end_of_life": "eol",
        "c": "eol",
    }

    for comp_id, comp in components.items():
        # Look up material
        material = material_dict.get(comp.material_id)
        if not material:
            raise ValueError(
                f"Material '{comp.material_id}' not found for component '{comp_id}'. "
                f"Available materials: {list(material_dict.keys())}"
            )

        # Calculate GWP: mass × gwp_coefficient
        component_gwp = comp.mass_kg * material.gwp_kgco2_per_kg * comp.quantity

        component_gwps.append(
            ComponentGWP(
                component_id=comp_id,
                component_name=comp.name,
                mass_kg=comp.mass_kg * comp.quantity,
                material_id=comp.material_id,
                gwp_kgco2=component_gwp,
                gwp_per_kg=material.gwp_kgco2_per_kg,
            )
        )

        raw_phase = str(comp.metadata.get("phase", "L1")).strip().lower()
        normalized_phase = phase_aliases.get(raw_phase, "manufacturing")
        phase_totals[normalized_phase] += component_gwp
        phase_components[normalized_phase].append(component_gwps[-1])

    # Sort by GWP descending for better readability
    component_gwps.sort(key=lambda x: x.gwp_kgco2, reverse=True)
    for phase in phase_components:
        phase_components[phase].sort(key=lambda x: x.gwp_kgco2, reverse=True)

    total_gwp = sum(phase_totals.values())

    logger.info(f"Manufacturing GWP: {phase_totals['manufacturing']:.2f} kg-CO2eq")
    logger.info(f"Component breakdown: {len(component_gwps)} components")

    # Calculate energy generation
    # Energy = rated_power_mw × 8760 hours/year × lifetime_years × capacity_factor
    energy_generation_mwh = rated_power_mw * 8760 * lifetime_years * capacity_factor

    logger.info(f"Lifetime energy generation: {energy_generation_mwh:.2f} MWh")

    # Calculate intensity (g-CO2eq/kWh)
    # Convert MWh to kWh: 1 MWh = 1000 kWh
    # Convert kg-CO2eq to g-CO2eq: 1 kg = 1000 g
    intensity_gco2_per_kwh = (total_gwp * 1000) / (energy_generation_mwh * 1000)

    logger.info(f"GWP intensity (all phases): {intensity_gco2_per_kwh:.4f} g-CO2eq/kWh")

    phase_breakdown: Dict[str, PhaseGWP] = {}
    for phase_name, phase_total in phase_totals.items():
        if phase_total <= 0:
            continue
        phase_breakdown[phase_name] = PhaseGWP(
            phase_name=phase_name,
            total_gwp_kgco2=phase_total,
            component_breakdown=phase_components[phase_name],
            percentage=(phase_total / total_gwp * 100) if total_gwp > 0 else 0.0,
        )

    return GWPResult(
        total_gwp_kgco2=total_gwp,
        intensity_gco2_per_kwh=intensity_gco2_per_kwh,
        phase_breakdown=phase_breakdown,
        component_breakdown=phase_components["manufacturing"],
        energy_generation_mwh=energy_generation_mwh,
        metadata={
            "rated_power_mw": str(rated_power_mw),
            "lifetime_years": str(lifetime_years),
            "capacity_factor": str(capacity_factor),
        },
    )


def aggregate_gwp_by_phase(
    manufacturing_gwp: float,
    transport_gwp: float = 0.0,
    o_and_m_gwp: float = 0.0,
    eol_gwp: float = 0.0,
    component_breakdown: List[ComponentGWP] = None,
    energy_generation_mwh: float = 0.0,
) -> GWPResult:
    """Aggregate GWP across all lifecycle phases.

    Args:
        manufacturing_gwp: Manufacturing phase GWP in kg-CO2
        transport_gwp: Transport phase GWP in kg-CO2
        o_and_m_gwp: Operations & Maintenance phase GWP in kg-CO2
        eol_gwp: End-of-Life phase GWP in kg-CO2
        component_breakdown: Component-level breakdown (for manufacturing)
        energy_generation_mwh: Total lifetime energy in MWh

    Returns:
        GWPResult with phase aggregation
    """
    total_gwp = manufacturing_gwp + transport_gwp + o_and_m_gwp + eol_gwp

    # Calculate percentages
    phase_breakdown = {}

    if manufacturing_gwp > 0:
        phase_breakdown["manufacturing"] = PhaseGWP(
            phase_name="manufacturing",
            total_gwp_kgco2=manufacturing_gwp,
            component_breakdown=component_breakdown or [],
            percentage=(manufacturing_gwp / total_gwp * 100) if total_gwp > 0 else 0.0,
        )

    if transport_gwp > 0:
        phase_breakdown["transport"] = PhaseGWP(
            phase_name="transport",
            total_gwp_kgco2=transport_gwp,
            percentage=(transport_gwp / total_gwp * 100) if total_gwp > 0 else 0.0,
        )

    if o_and_m_gwp > 0:
        phase_breakdown["o_and_m"] = PhaseGWP(
            phase_name="o_and_m",
            total_gwp_kgco2=o_and_m_gwp,
            percentage=(o_and_m_gwp / total_gwp * 100) if total_gwp > 0 else 0.0,
        )

    if eol_gwp > 0:
        phase_breakdown["eol"] = PhaseGWP(
            phase_name="eol",
            total_gwp_kgco2=eol_gwp,
            percentage=(eol_gwp / total_gwp * 100) if total_gwp > 0 else 0.0,
        )

    # Calculate intensity
    intensity = 0.0
    if energy_generation_mwh > 0:
        intensity = (total_gwp * 1000) / (energy_generation_mwh * 1000)

    return GWPResult(
        total_gwp_kgco2=total_gwp,
        intensity_gco2_per_kwh=intensity,
        phase_breakdown=phase_breakdown,
        component_breakdown=component_breakdown or [],
        energy_generation_mwh=energy_generation_mwh,
    )


def normalize_gwp(
    total_gwp_kgco2: float,
    rated_power_mw: float,
    lifetime_years: int,
    capacity_factor: float,
) -> float:
    """Calculate GWP intensity normalized by energy generation.

    Args:
        total_gwp_kgco2: Total GWP in kg-CO2
        rated_power_mw: Turbine rated power in MW
        lifetime_years: Project lifetime in years
        capacity_factor: Capacity factor (0.0-1.0)

    Returns:
        GWP intensity in g-CO2 per kWh

    Raises:
        ValueError: If invalid parameters
    """
    if rated_power_mw <= 0:
        raise ValueError(f"rated_power_mw must be positive, got {rated_power_mw}")
    if lifetime_years <= 0:
        raise ValueError(f"lifetime_years must be positive, got {lifetime_years}")
    if not 0 <= capacity_factor <= 1:
        raise ValueError(f"capacity_factor must be 0-1, got {capacity_factor}")

    # Calculate energy generation in MWh
    energy_generation_mwh = rated_power_mw * 8760 * lifetime_years * capacity_factor

    # Convert to g-CO2 per kWh
    intensity_gco2_per_kwh = (total_gwp_kgco2 * 1000) / (energy_generation_mwh * 1000)

    return intensity_gco2_per_kwh


__all__ = [
    "ComponentGWP",
    "PhaseGWP",
    "GWPResult",
    "calculate_gwp",
    "aggregate_gwp_by_phase",
    "normalize_gwp",
]
