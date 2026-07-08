"""Pydantic validation schemas for LCI data and scenarios.

This module defines pydantic models for validating CSV data and YAML scenario files.
All schemas enforce data quality constraints and provide clear error messages.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class MaterialSchema(BaseModel):
    """Validation schema for materials.csv rows."""

    material: str = Field(..., min_length=1, description="Material identifier")
    variant: Optional[str] = Field(None, description="Material variant (optional)")
    density_kg_m3: Optional[float] = Field(None, gt=0, description="Density must be positive if provided")
    gwp_kgco2_per_kg: float = Field(..., ge=0, description="GWP must be non-negative")
    E1_GPa: Optional[float] = Field(None, ge=0, description="Young's modulus")
    G12_GPa: Optional[float] = Field(None, ge=0, description="Shear modulus")
    price_usd_per_kg: Optional[float] = Field(None, ge=0, description="Price must be non-negative if provided")
    source: Optional[str] = Field(None, description="Data source reference")
    notes: Optional[str] = Field(None, description="Additional notes")

    model_config = {"extra": "allow"}  # Allow additional mechanical properties


class ComponentSchema(BaseModel):
    """Validation schema for components.csv rows."""

    item_id: str = Field(..., min_length=1, description="Component identifier")
    name: Optional[str] = Field(None, description="Component name (optional, defaults to item_id)")
    structure_id: Literal[
        "onshore", "bottom_fixed", "semisubmersible", "spar", "fawt"
    ] = Field(..., description="Structure type")
    total_mass_kg: float = Field(..., gt=0, description="Mass must be positive")
    material_ref: str = Field(..., min_length=1, description="Material reference")
    quantity: Optional[int] = Field(None, ge=1, description="Quantity must be at least 1")
    submodule: Optional[str] = None
    module: Optional[str] = None

    model_config = {"extra": "allow"}


class DependencySchema(BaseModel):
    """Validation schema for weight_dependencies.csv rows."""

    primary_component: str = Field(..., min_length=1, description="Primary component ID")
    dependent_component: str = Field(..., min_length=1, description="Dependent component ID")
    dependency_type: Literal[
        "direct_load", "top_mass", "overturning_moment", "buoyancy_requirement", "load_capacity", "crane_load"
    ] = Field(..., description="Dependency type")
    scaling_factor: float = Field(..., ge=0, le=2.0, description="Scaling factor (0-2)")
    formula_reference: Optional[str] = None
    structure_types: str = Field("all", description="Applicable structure types")
    notes: Optional[str] = None

    @field_validator("structure_types")
    @classmethod
    def validate_structure_types(cls, v: str) -> str:
        """Validate structure_types field format."""
        if v == "all":
            return v
        # Allow comma-separated list of structure types
        valid_types = {"onshore", "bottom_fixed", "floating_semi_sub", "floating_spar", "fawt"}
        types = [t.strip() for t in v.split(",")]
        for t in types:
            if t not in valid_types:
                raise ValueError(
                    f"Invalid structure type '{t}'. Must be one of: {', '.join(valid_types)}"
                )
        return v


class TransportVehicleSchema(BaseModel):
    """Validation schema for transport_vehicles.csv rows."""

    vehicle_type: str = Field(..., min_length=1, description="Vehicle identifier")
    capacity_ton: float = Field(..., gt=0, description="Capacity must be positive")
    base_fuel_L_per_km: float = Field(..., gt=0, description="Fuel consumption must be positive")
    load_factor_sensitivity: float = Field(
        ..., ge=0, le=1.0, description="Load sensitivity (0-1)"
    )
    gwp_kgco2_per_L: float = Field(..., ge=0, description="Fuel GWP must be non-negative")
    speed_km_per_hour: float = Field(50.0, gt=0, description="Speed must be positive")
    fuel_type: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "allow"}


class LCAEventSchema(BaseModel):
    """Validation schema for lca_events.csv rows."""

    event_id: Optional[str] = Field(None, description="Event identifier (auto-generated if missing)")
    structure_id: Literal[
        "onshore", "bottom_fixed", "semisubmersible", "spar", "fawt"
    ] = Field(..., description="Structure type")
    phase: Optional[Literal["A4", "B", "C"]] = Field(None, description="Lifecycle phase")
    event_type: Optional[str] = Field(None, description="Event type")
    component_ref: Optional[str] = None
    vehicle_type: Optional[str] = Field(None, description="Vehicle type")
    distance_km: Optional[float] = Field(None, ge=0, description="Distance (optional, can be calculated)")
    trips: Optional[int] = Field(None, ge=1, description="Trips must be at least 1 if provided")
    gwp_kgco2: float = Field(0.0, ge=0, description="GWP must be non-negative")
    frequency_per_year: Optional[float] = Field(None, ge=0, description="Annual frequency")

    # Alternative distance fields (handled in loader)
    one_way_km: Optional[float] = Field(None, ge=0, description="One-way distance")
    route_km: Optional[float] = Field(None, ge=0, description="Route distance")
    roundtrip_km: Optional[float] = Field(None, ge=0, description="Roundtrip distance")
    visits_per_year: Optional[float] = Field(None, ge=0, description="Annual visits")

    model_config = {"extra": "allow"}


# Scenario YAML validation schemas


class TransportConfig(BaseModel):
    """Transport configuration within scenario."""

    distance_km: float = Field(..., gt=0, description="Transport distance")
    vessel_type: Optional[str] = Field(None, description="Vessel type for offshore")
    vehicle_type: Optional[str] = Field(None, description="Vehicle type for onshore")


class CalculationMethodsConfig(BaseModel):
    """Calculation methods configuration."""

    weight_cascade: Literal["linear_scaling"] = Field(
        "linear_scaling", description="Weight cascade method"
    )
    gwp: Literal["ipcc_ar5_100yr"] = Field("ipcc_ar5_100yr", description="GWP method")
    allocation: Literal["mass_based", "economic"] = Field(
        "mass_based", description="Allocation method"
    )


class OptionsConfig(BaseModel):
    """Calculation options configuration."""

    enable_weight_cascade: bool = Field(True, description="Enable weight cascade")
    max_cascade_iterations: int = Field(10, ge=1, le=50, description="Max iterations")
    convergence_threshold: float = Field(0.005, gt=0, lt=0.1, description="Convergence threshold")
    log_iterations: bool = Field(False, description="Log cascade iterations")
    recycling_method: Optional[Literal["avoided_burden", "cut_off"]] = Field(
        None, description="Recycling allocation method"
    )


class ScenarioSchema(BaseModel):
    """Validation schema for YAML scenario files."""

    name: str = Field(..., min_length=1, description="Scenario name")
    structure_type: Literal[
        "onshore", "bottom_fixed", "floating_semi_sub", "floating_spar", "fawt"
    ] = Field(..., description="Structure type")
    rated_power_mw: float = Field(..., gt=0, le=20, description="Rated power (0-20 MW)")
    lifetime_years: int = Field(..., ge=15, le=50, description="Lifetime (15-50 years)")
    capacity_factor: float = Field(..., gt=0, lt=1, description="Capacity factor (0-1)")
    materials: Dict[str, str] = Field(..., description="Component material assignments")
    transport: TransportConfig
    calculation_methods: CalculationMethodsConfig = Field(
        default_factory=CalculationMethodsConfig, description="Calculation method selection"
    )
    options: OptionsConfig = Field(
        default_factory=OptionsConfig, description="Calculation options"
    )

    @field_validator("materials")
    @classmethod
    def validate_materials_not_empty(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Ensure materials dict is not empty."""
        if not v:
            raise ValueError("Materials dict cannot be empty")
        return v


# Foreign key validation helpers


def _validate_reference_values(
    rows: List[Dict[str, Any]],
    references: List[Dict[str, Any]],
    row_key: str,
    reference_key: str,
    reference_file: str,
) -> List[str]:
    """Validate that row values for row_key exist in reference records."""
    reference_values = {ref.get(reference_key, "").lower() for ref in references}
    errors = []

    for i, row in enumerate(rows):
        row_value = row.get(row_key, "")
        if row_value.lower() not in reference_values:
            errors.append(
                f"Row {i+1}: {row_key} '{row_value}' not found in {reference_file}"
            )

    return errors


def validate_material_refs(
    components: List[Dict[str, Any]], materials: List[Dict[str, Any]]
) -> List[str]:
    """Validate that all component material_ref values exist in materials.

    Args:
        components: List of component dicts
        materials: List of material dicts

    Returns:
        List of error messages (empty if valid)
    """
    return _validate_reference_values(
        rows=components,
        references=materials,
        row_key="material_ref",
        reference_key="material",
        reference_file="materials.csv",
    )


def validate_vehicle_refs(
    events: List[Dict[str, Any]], vehicles: List[Dict[str, Any]]
) -> List[str]:
    """Validate that all event vehicle_type values exist in transport_vehicles.

    Args:
        events: List of event dicts
        vehicles: List of vehicle dicts

    Returns:
        List of error messages (empty if valid)
    """
    return _validate_reference_values(
        rows=events,
        references=vehicles,
        row_key="vehicle_type",
        reference_key="vehicle_type",
        reference_file="transport_vehicles.csv",
    )


__all__ = [
    "MaterialSchema",
    "ComponentSchema",
    "DependencySchema",
    "TransportVehicleSchema",
    "LCAEventSchema",
    "TransportConfig",
    "CalculationMethodsConfig",
    "OptionsConfig",
    "ScenarioSchema",
    "validate_material_refs",
    "validate_vehicle_refs",
]
