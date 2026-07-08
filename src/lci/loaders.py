"""CSV data loaders for LCI data.

This module provides functions to load and validate LCI data from CSV files,
converting them into typed dataclass instances.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd
from pydantic import ValidationError

from .models import Component, Dependency, LCAEvent, LCIData, Material, TransportVehicle
from .validators import (
    ComponentSchema,
    DependencySchema,
    LCAEventSchema,
    MaterialSchema,
    TransportVehicleSchema,
    validate_material_refs,
    validate_vehicle_refs,
)

logger = logging.getLogger(__name__)


class DataLoadError(Exception):
    """Exception raised when data loading fails."""

    pass


def load_materials(csv_path: Path) -> List[Material]:
    """Load materials from CSV file.

    Args:
        csv_path: Path to materials.csv

    Returns:
        List of Material instances

    Raises:
        DataLoadError: If file not found or validation fails
    """
    if not csv_path.exists():
        raise DataLoadError(f"Materials file not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} rows from {csv_path}")
    except Exception as e:
        raise DataLoadError(f"Failed to read {csv_path}: {e}")

    materials = []
    errors = []

    for idx, row in df.iterrows():
        try:
            # Convert NaN and invalid values to None for pydantic validation
            row_dict = {}
            for k, v in row.to_dict().items():
                if pd.isna(v):
                    row_dict[k] = None
                elif isinstance(v, str) and v.strip() in ['---', '', 'nan', 'NaN', 'NA']:
                    row_dict[k] = None
                else:
                    row_dict[k] = v

            # Validate with pydantic
            schema = MaterialSchema(**row_dict)

            # Extract mechanical properties
            mechanical_props = {}
            for col in df.columns:
                if col.endswith("_GPa") or col.endswith("_MPa"):
                    value = row[col]
                    # Skip NaN, invalid strings, and non-numeric values
                    if pd.notna(value):
                        if isinstance(value, str) and value.strip() in ['---', '', 'nan', 'NaN', 'NA']:
                            continue
                        try:
                            mechanical_props[col] = float(value)
                        except (ValueError, TypeError):
                            continue  # Skip invalid values

            # Create Material instance
            material = Material(
                id=schema.material.lower(),  # Normalize to lowercase
                name=schema.material,
                variant=schema.variant or "standard",
                density_kg_m3=schema.density_kg_m3 or 1.0,  # Default if not provided
                gwp_kgco2_per_kg=schema.gwp_kgco2_per_kg,
                mechanical_properties=mechanical_props,
                price_usd_per_kg=schema.price_usd_per_kg or 0.0,
                metadata={
                    "source": schema.source or "",
                    "notes": schema.notes or "",
                },
            )
            materials.append(material)

        except ValidationError as e:
            errors.append(f"Row {idx + 2}: {e}")  # +2 for header and 0-indexing

    if errors:
        error_msg = "\n".join(errors)
        raise DataLoadError(f"Validation errors in {csv_path}:\n{error_msg}")

    logger.info(f"Successfully loaded {len(materials)} materials")
    return materials


def load_components(csv_path: Path, structure_type: str | None = None) -> List[Component]:
    """Load components from CSV file.

    Args:
        csv_path: Path to components.csv
        structure_type: Optional filter by structure type

    Returns:
        List of Component instances

    Raises:
        DataLoadError: If file not found or validation fails
    """
    if not csv_path.exists():
        raise DataLoadError(f"Components file not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} rows from {csv_path}")
    except Exception as e:
        raise DataLoadError(f"Failed to read {csv_path}: {e}")

    # Filter by structure type if specified
    if structure_type:
        df = df[df["structure_id"] == structure_type]
        logger.info(f"Filtered to {len(df)} rows for structure_type={structure_type}")

    components: List[Component] = []
    errors = []

    for idx, row in df.iterrows():
        try:
            # Convert NaN and invalid values to None for pydantic validation
            row_dict = {}
            for k, v in row.to_dict().items():
                if pd.isna(v):
                    row_dict[k] = None
                elif isinstance(v, str) and v.strip() in ['---', '', 'nan', 'NaN', 'NA']:
                    row_dict[k] = None
                else:
                    row_dict[k] = v

            # Validate with pydantic
            schema = ComponentSchema(**row_dict)

            # Preserve CSV item_id as public component ID.
            component_id = schema.item_id
            component = Component(
                id=component_id,
                name=schema.name or schema.item_id,  # Default to item_id if name is missing
                structure_type=schema.structure_id,
                mass_kg=schema.total_mass_kg,
                base_mass_kg=schema.total_mass_kg,  # Initial base = current
                material_id=schema.material_ref.lower(),
                quantity=schema.quantity or 1,  # Default to 1 if not specified
                metadata={
                    "submodule": schema.submodule or "",
                    "module": schema.module or "",
                    "original_item_id": schema.item_id,  # Store original ID for reference
                },
            )
            components.append(component)

        except ValidationError as e:
            errors.append(f"Row {idx + 2}: {e}")

    if errors:
        error_msg = "\n".join(errors)
        raise DataLoadError(f"Validation errors in {csv_path}:\n{error_msg}")

    logger.info(f"Successfully loaded {len(components)} components")
    return components


def load_dependencies(csv_path: Path) -> List[Dependency]:
    """Load weight dependencies from CSV file.

    Args:
        csv_path: Path to weight_dependencies.csv

    Returns:
        List of Dependency instances

    Raises:
        DataLoadError: If file not found or validation fails
    """
    if not csv_path.exists():
        raise DataLoadError(f"Dependencies file not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} rows from {csv_path}")
    except Exception as e:
        raise DataLoadError(f"Failed to read {csv_path}: {e}")

    dependencies = []
    errors = []

    for idx, row in df.iterrows():
        try:
            # Validate with pydantic
            schema = DependencySchema(**row.to_dict())

            # Parse structure_types string to list
            if schema.structure_types == "all":
                structure_types = ["all"]
            else:
                structure_types = [t.strip() for t in schema.structure_types.split(",")]

            # Create Dependency instance
            dependency = Dependency(
                primary_component=schema.primary_component.lower(),
                dependent_component=schema.dependent_component.lower(),
                dependency_type=schema.dependency_type,
                scaling_factor=schema.scaling_factor,
                formula_reference=schema.formula_reference or "",
                structure_types=structure_types,
                notes=schema.notes or "",
            )
            dependencies.append(dependency)

        except ValidationError as e:
            errors.append(f"Row {idx + 2}: {e}")

    if errors:
        error_msg = "\n".join(errors)
        raise DataLoadError(f"Validation errors in {csv_path}:\n{error_msg}")

    logger.info(f"Successfully loaded {len(dependencies)} dependencies")
    return dependencies


def load_transport_vehicles(csv_path: Path) -> Dict[str, TransportVehicle]:
    """Load transport vehicles from CSV file.

    Args:
        csv_path: Path to transport_vehicles.csv

    Returns:
        Dict of TransportVehicle instances keyed by vehicle_type

    Raises:
        DataLoadError: If file not found or validation fails
    """
    if not csv_path.exists():
        raise DataLoadError(f"Transport vehicles file not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} rows from {csv_path}")
    except Exception as e:
        raise DataLoadError(f"Failed to read {csv_path}: {e}")

    vehicles = {}
    errors = []

    for idx, row in df.iterrows():
        try:
            # Validate with pydantic
            schema = TransportVehicleSchema(**row.to_dict())

            # Create TransportVehicle instance
            vehicle = TransportVehicle(
                vehicle_type=schema.vehicle_type.lower(),
                capacity_ton=schema.capacity_ton,
                base_fuel_L_per_km=schema.base_fuel_L_per_km,
                load_factor_sensitivity=schema.load_factor_sensitivity,
                gwp_kgco2_per_L=schema.gwp_kgco2_per_L,
                speed_km_per_hour=schema.speed_km_per_hour,
                metadata={
                    "fuel_type": schema.fuel_type or "",
                    "notes": schema.notes or "",
                },
            )
            vehicles[vehicle.vehicle_type] = vehicle

        except ValidationError as e:
            errors.append(f"Row {idx + 2}: {e}")

    if errors:
        error_msg = "\n".join(errors)
        raise DataLoadError(f"Validation errors in {csv_path}:\n{error_msg}")

    logger.info(f"Successfully loaded {len(vehicles)} transport vehicles")
    return vehicles


def load_lca_events(csv_path: Path, structure_type: str | None = None) -> List[LCAEvent]:
    """Load LCA events from CSV file.

    Args:
        csv_path: Path to lca_events.csv
        structure_type: Optional filter by structure type

    Returns:
        List of LCAEvent instances

    Raises:
        DataLoadError: If file not found or validation fails
    """
    if not csv_path.exists():
        raise DataLoadError(f"LCA events file not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} rows from {csv_path}")
    except Exception as e:
        raise DataLoadError(f"Failed to read {csv_path}: {e}")

    # Filter by structure type if specified
    if structure_type:
        df = df[df["structure_id"] == structure_type]
        logger.info(f"Filtered to {len(df)} rows for structure_type={structure_type}")

    events = []
    errors = []

    for idx, row in df.iterrows():
        try:
            # Convert NaN and invalid values to None for pydantic validation
            row_dict = {}
            for k, v in row.to_dict().items():
                if pd.isna(v):
                    row_dict[k] = None
                elif isinstance(v, str) and v.strip() in ['---', '', 'nan', 'NaN', 'NA']:
                    row_dict[k] = None
                else:
                    row_dict[k] = v

            # Validate with pydantic
            schema = LCAEventSchema(**row_dict)

            # Generate event_id if missing
            event_id = schema.event_id or f"event_{idx + 1}"

            # Determine distance_km from alternative fields
            distance_km = schema.distance_km
            if distance_km is None:
                # Try alternative distance fields in priority order
                if schema.one_way_km is not None:
                    distance_km = schema.one_way_km
                elif schema.route_km is not None:
                    distance_km = schema.route_km
                elif schema.roundtrip_km is not None:
                    distance_km = schema.roundtrip_km
                else:
                    distance_km = 0.0  # Default if no distance provided

            # Map visits_per_year to frequency_per_year
            frequency_per_year = schema.frequency_per_year or schema.visits_per_year

            # Collect metadata from extra columns to preserve event-level detail.
            metadata = {}
            if frequency_per_year is not None:
                metadata["frequency_per_year"] = frequency_per_year
            core_fields = {
                "event_id",
                "structure_id",
                "phase",
                "event_type",
                "component_ref",
                "vehicle_type",
                "distance_km",
                "trips",
                "gwp_kgco2",
                "frequency_per_year",
                "one_way_km",
                "route_km",
                "roundtrip_km",
                "visits_per_year",
            }
            for k, v in row_dict.items():
                if k in core_fields:
                    continue
                if v is None:
                    continue
                metadata[k] = v

            # Skip rows with missing critical fields (phase, event_type, vehicle_type)
            if not schema.phase or not schema.event_type or not schema.vehicle_type:
                logger.debug(f"Skipping row {idx + 2}: missing critical fields")
                continue

            # Create LCAEvent instance
            event = LCAEvent(
                event_id=event_id,
                structure_type=schema.structure_id,
                phase=schema.phase,
                event_type=schema.event_type,
                component_ref=schema.component_ref or "",
                vehicle_type=schema.vehicle_type.lower(),
                distance_km=distance_km,
                trips=schema.trips or 1,  # Default to 1 if not provided
                gwp_kgco2=schema.gwp_kgco2,
                metadata=metadata,
            )
            events.append(event)

        except ValidationError as e:
            errors.append(f"Row {idx + 2}: {e}")

    if errors:
        error_msg = "\n".join(errors)
        raise DataLoadError(f"Validation errors in {csv_path}:\n{error_msg}")

    logger.info(f"Successfully loaded {len(events)} LCA events")
    return events


def load_all_lci_data(
    data_dir: Path, structure_type: str | None = None, validate_refs: bool = True
) -> LCIData:
    """Load all LCI data from CSV files in specified directory.

    Args:
        data_dir: Directory containing CSV files (e.g., data/lci/)
        structure_type: Optional filter for components and events
        validate_refs: Whether to validate foreign key references

    Returns:
        LCIData instance with all loaded data

    Raises:
        DataLoadError: If any file fails to load or validation fails
    """
    logger.info(f"Loading LCI data from {data_dir}")

    # Load all data files
    materials = load_materials(data_dir / "materials.csv")
    loaded_components = load_components(data_dir / "components.csv", structure_type)
    components = {}
    for component in loaded_components:
        # Keep dict keys unique across structure types while preserving component.id.
        key = f"{component.structure_type}:{component.id.lower()}"
        components[key] = component
    dependencies = load_dependencies(data_dir / "weight_dependencies.csv")
    vehicles = load_transport_vehicles(data_dir / "transport_vehicles.csv")
    events = load_lca_events(data_dir / "lca_events.csv", structure_type)

    # Validate foreign key references
    if validate_refs:
        logger.info("Validating foreign key references...")

        # Convert to dicts for validation
        material_dicts = [{"material": m.name} for m in materials]
        component_dicts = [{"material_ref": c.material_id} for c in components.values()]
        vehicle_dicts = [{"vehicle_type": v.vehicle_type} for v in vehicles.values()]
        event_dicts = [{"vehicle_type": e.vehicle_type} for e in events]

        # Validate material references
        material_errors = validate_material_refs(component_dicts, material_dicts)
        if material_errors:
            raise DataLoadError(
                f"Foreign key validation errors in components.csv:\n" + "\n".join(material_errors)
            )

        # Validate vehicle references
        vehicle_errors = validate_vehicle_refs(event_dicts, vehicle_dicts)
        if vehicle_errors:
            raise DataLoadError(
                f"Foreign key validation errors in lca_events.csv:\n" + "\n".join(vehicle_errors)
            )

        logger.info("Foreign key validation passed")

    # Create LCIData container
    lci_data = LCIData(
        materials=materials,
        components=components,
        dependencies=dependencies,
        vehicles=vehicles,
        events=events,
        version="0.1.0",
    )

    logger.info(
        f"Successfully loaded LCI data: {len(materials)} materials, "
        f"{len(components)} components, {len(dependencies)} dependencies, "
        f"{len(vehicles)} vehicles, {len(events)} events"
    )

    return lci_data


__all__ = [
    "DataLoadError",
    "load_materials",
    "load_components",
    "load_dependencies",
    "load_transport_vehicles",
    "load_lca_events",
    "load_all_lci_data",
]
