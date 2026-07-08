# LCI (Life Cycle Inventory) Data Layer

This module provides the data layer for the LCA Toolkit, handling CSV loading, data validation, and data models for lifecycle inventory information.

## Purpose

The LCI module separates data concerns from calculation logic, providing:
- **CSV Loading:** Parse materials, components, dependencies, and events from CSV files
- **Data Validation:** Pydantic schemas ensure data quality at load time
- **Type Safety:** Dataclasses provide compile-time type checking
- **Foreign Key Validation:** Ensure referential integrity across CSV files

## Module Structure

```
src/lci/
├── models.py         # Data models (Material, Component, Dependency, etc.)
├── loaders.py        # CSV loading functions
├── validators.py     # Pydantic schemas for validation
└── __init__.py       # Public API exports
```

## Core Data Models

### Material
Represents material properties and environmental coefficients:
```python
@dataclass
class Material:
    id: str                          # e.g., "steel", "gfrp"
    name: str                        # Human-readable name
    variant: str                     # Material variant
    density_kg_m3: float             # Density
    gwp_kgco2_per_kg: float          # GWP coefficient
    mechanical_properties: Dict      # E1_GPa, G12_GPa, etc.
    price_usd_per_kg: float
    metadata: Dict[str, str]
```

### Component
Represents wind turbine components:
```python
@dataclass
class Component:
    id: str                          # e.g., "blade", "tower"
    name: str
    structure_type: str              # onshore, bottom_fixed, etc.
    mass_kg: float                   # Current mass (may change in cascade)
    base_mass_kg: float              # Baseline mass
    material_id: str                 # Foreign key to Material
    quantity: int
    metadata: Dict[str, str]
```

### Dependency
Represents component weight dependencies:
```python
@dataclass
class Dependency:
    primary_component: str           # Component whose mass change triggers cascade
    dependent_component: str         # Component affected by cascade
    dependency_type: str             # direct_load, top_mass, etc.
    scaling_factor: float            # Mass propagation multiplier (0-2)
    formula_reference: str
    structure_types: List[str]       # Applicable structure types
    notes: str
```

## CSV File Schemas

### materials.csv
Required columns:
- `material` (str): Material identifier
- `variant` (str, optional): Material variant
- `density_kg_m3` (float): Material density
- `gwp_kgco2_per_kg` (float): GWP coefficient (≥ 0)
- `price_usd_per_kg` (float, optional): Material price
- `source` (str, optional): Data source reference
- `notes` (str, optional): Additional notes
- Mechanical properties (optional): `E1_GPa`, `G12_GPa`, etc.

### components.csv
Required columns:
- `item_id` (str): Component identifier
- `name` (str, optional): Component name
- `structure_id` (str): Structure type (onshore, bottom_fixed, etc.)
- `total_mass_kg` (float): Component mass (> 0)
- `material_ref` (str): Material identifier (foreign key)
- `quantity` (int, optional): Number of components (≥ 1)
- `submodule` (str, optional): Submodule classification
- `module` (str, optional): Module classification

### weight_dependencies.csv
Required columns:
- `primary_component` (str): Primary component ID
- `dependent_component` (str): Dependent component ID
- `dependency_type` (str): direct_load, top_mass, overturning_moment, etc.
- `scaling_factor` (float): Scaling factor (0-2)
- `formula_reference` (str, optional): Calculation formula reference
- `structure_types` (str): Comma-separated types or "all"
- `notes` (str, optional): Additional notes

## Usage Examples

### Load Materials
```python
from pathlib import Path
from src.lci.loaders import load_materials

materials = load_materials(Path("data/lci/materials.csv"))
for material in materials:
    print(f"{material.name}: {material.gwp_kgco2_per_kg} kg-CO2/kg")
```

### Load Components with Filtering
```python
from src.lci.loaders import load_components

# Load only onshore components
components = load_components(
    Path("data/lci/components.csv"),
    structure_type="onshore"
)
```

### Load All LCI Data
```python
from src.lci.loaders import load_all_lci_data

lci_data = load_all_lci_data(data_dir=Path("data/lci"))
print(f"Loaded {len(lci_data.materials)} materials")
print(f"Loaded {len(lci_data.components)} components")
print(f"Loaded {len(lci_data.dependencies)} dependencies")
```

### Validate Scenario YAML
```python
from src.lci.validators import ScenarioSchema
import yaml

with open("scenarios/001-onshore-3mw-baseline/scenario.yaml") as f:
    data = yaml.safe_load(f)

# This will raise ValidationError if invalid
scenario = ScenarioSchema(**data)
print(f"Valid scenario: {scenario.name}")
```

## Error Handling

### DataLoadError
Raised when CSV loading fails:
```python
try:
    materials = load_materials(csv_path)
except DataLoadError as e:
    print(f"Failed to load: {e}")
```

### ValidationError (Pydantic)
Raised when data doesn't match schema:
```python
from pydantic import ValidationError

try:
    schema = MaterialSchema(**row_dict)
except ValidationError as e:
    print(f"Validation failed: {e}")
```

## Data Validation Rules

### Material Validation
- `gwp_kgco2_per_kg` must be ≥ 0
- `density_kg_m3` must be > 0 if provided
- `price_usd_per_kg` must be ≥ 0 if provided

### Component Validation
- `total_mass_kg` must be > 0
- `structure_id` must be valid type (onshore, bottom_fixed, semisubmersible, spar, fawt)
- `material_ref` must exist in materials.csv (foreign key validation)
- `quantity` must be ≥ 1 if provided

### Dependency Validation
- `scaling_factor` must be 0-2
- `structure_types` must be valid types or "all"
- `primary_component` and `dependent_component` must exist in components.csv

### Scenario Validation
- `rated_power_mw` must be 0-20 MW
- `lifetime_years` must be 15-50 years
- `capacity_factor` must be 0-1
- `materials` dict cannot be empty

## Performance Notes

- CSV loading is cached in memory after first load
- Material and component dictionaries use `id` as key for O(1) lookup
- Foreign key validation runs after all data is loaded
- Large CSV files (10,000+ rows) load in <1 second

## Design Principles

This module follows Principle 1 (Simple Module Separation):
- Clean separation between models, loaders, and validators
- Direct imports (no circular dependencies)
- Each file has single, clear responsibility

And Principle 6 (Minimal Abstraction):
- Uses dataclasses, not custom base classes
- Direct CSV parsing with pandas, no ORM
- Simple validation with pydantic, no complex framework
