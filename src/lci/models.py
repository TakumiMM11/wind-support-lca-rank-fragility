"""LCI Data Models.

This module defines dataclasses for Life Cycle Inventory data entities:
materials, components, dependencies, transport vehicles, and LCA events.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Material:
    """Material properties and environmental impact coefficients.

    Attributes:
        id: Unique material identifier (e.g., "steel", "gfrp")
        name: Human-readable material name
        variant: Material variant (e.g., "structural", "high_strength")
        density_kg_m3: Material density in kg/m³
        gwp_kgco2_per_kg: Global Warming Potential in kg-CO2 per kg material
        mechanical_properties: Dict of mechanical properties (E1_GPa, G12_GPa, etc.)
        price_usd_per_kg: Material price in USD per kg
        metadata: Additional metadata (source, notes, etc.)
    """

    id: str
    name: str
    variant: str
    density_kg_m3: float
    gwp_kgco2_per_kg: float
    mechanical_properties: Dict[str, float] = field(default_factory=dict)
    price_usd_per_kg: float = 0.0
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Component:
    """Wind turbine component specifications.

    Attributes:
        id: Canonical component ID (e.g., "blade", "tower", "nacelle")
        name: Human-readable component name
        structure_type: Structure type (onshore, bottom_fixed, floating_semi_sub, floating_spar, fawt)
        mass_kg: Current mass in kg (may be modified by weight cascade)
        base_mass_kg: Original baseline mass in kg
        material_id: Foreign key to Material.id
        quantity: Number of this component in the turbine
        metadata: Additional metadata (submodule, module, notes, etc.)
    """

    id: str
    name: str
    structure_type: str
    mass_kg: float
    base_mass_kg: float
    material_id: str
    quantity: int = 1
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Dependency:
    """Component weight dependency relationship.

    Defines how mass changes in one component affect dependent components
    through the weight cascade algorithm.

    Attributes:
        primary_component: Component whose mass change triggers cascade
        dependent_component: Component whose mass is affected
        dependency_type: Type of dependency (direct_load, top_mass, overturning_moment, buoyancy_requirement)
        scaling_factor: Multiplier for mass propagation (0.0-1.0)
        formula_reference: Reference to calculation formula
        structure_types: List of structure types this dependency applies to (["all"] for universal)
        notes: Additional notes about the dependency
    """

    primary_component: str
    dependent_component: str
    dependency_type: str
    scaling_factor: float
    formula_reference: str = ""
    structure_types: List[str] = field(default_factory=lambda: ["all"])
    notes: str = ""


@dataclass
class TransportVehicle:
    """Transport vehicle specifications for lifecycle phase calculations.

    Attributes:
        vehicle_type: Vehicle identifier (e.g., "truck_heavy", "heavy_lift_vessel")
        capacity_ton: Load capacity in metric tons
        base_fuel_L_per_km: Base fuel consumption in liters per km
        load_factor_sensitivity: How fuel consumption scales with load (0.0-1.0)
        gwp_kgco2_per_L: GWP of fuel in kg-CO2 per liter
        speed_km_per_hour: Average travel speed in km/h
        metadata: Additional metadata (fuel_type, notes, etc.)
    """

    vehicle_type: str
    capacity_ton: float
    base_fuel_L_per_km: float
    load_factor_sensitivity: float
    gwp_kgco2_per_L: float
    speed_km_per_hour: float = 50.0
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class LCAEvent:
    """Lifecycle event definition (transport, O&M, end-of-life).

    Attributes:
        event_id: Unique event identifier
        structure_type: Structure type this event applies to
        phase: Lifecycle phase (A4=transport, B=O&M, C=end-of-life)
        event_type: Type of event (delivery, annual_visit, replacement, dismantle)
        component_ref: Component this event relates to
        vehicle_type: Vehicle used for this event
        distance_km: Distance traveled in km
        trips: Number of trips
        gwp_kgco2: Calculated GWP for this event in kg-CO2
        metadata: Flexible additional data (frequency, notes, etc.)
    """

    event_id: str
    structure_type: str
    phase: str
    event_type: str
    component_ref: str
    vehicle_type: str
    distance_km: float
    trips: int
    gwp_kgco2: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LCIData:
    """Container for all LCI data loaded from CSV files.

    Aggregates all data entities needed for LCA calculations.

    Attributes:
        materials: List of all materials
        components: Dict of components keyed by component ID
        dependencies: List of weight dependencies
        vehicles: Dict of vehicles keyed by vehicle_type
        events: List of lifecycle events
        version: Data version identifier
    """

    materials: List[Material] = field(default_factory=list)
    components: Dict[str, Component] = field(default_factory=dict)
    dependencies: List[Dependency] = field(default_factory=list)
    vehicles: Dict[str, TransportVehicle] = field(default_factory=dict)
    events: List[LCAEvent] = field(default_factory=list)
    version: str = "0.1.0"

    def get_material_by_id(self, material_id: str) -> Optional[Material]:
        """Find material by ID.

        Args:
            material_id: Material identifier

        Returns:
            Material instance or None if not found
        """
        for material in self.materials:
            if material.id == material_id:
                return material
        return None

    def get_component_by_id(self, component_id: str) -> Optional[Component]:
        """Find component by ID.

        Args:
            component_id: Component identifier

        Returns:
            Component instance or None if not found
        """
        return self.components.get(component_id)


__all__ = [
    "Material",
    "Component",
    "Dependency",
    "TransportVehicle",
    "LCAEvent",
    "LCIData",
]
