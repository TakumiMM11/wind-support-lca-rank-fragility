# LCA (Life Cycle Assessment) Calculation Layer

This module implements the core LCA calculation algorithms for wind turbine environmental impact assessment.

## Purpose

The LCA module provides:
- **Weight Cascade Algorithm:** Propagate mass changes through component dependencies
- **GWP Calculation:** Calculate Global Warming Potential using material coefficients
- **Result Normalization:** Convert absolute GWP to intensity (g-CO2/kWh)
- **Calculation Transparency:** Detailed logging and iteration tracking

## Module Structure

```
src/lca/
├── weight_cascade.py    # Weight cascade algorithm
├── gwp.py               # GWP calculation
├── calculator.py        # Main LCACalculator interface
└── __init__.py          # Public API exports
```

## Core Algorithms

### Weight Cascade

The weight cascade algorithm propagates mass changes through component dependencies using iterative linear scaling.

**Algorithm:**
```
for each iteration (max 10):
    for each dependency:
        primary_delta = current_mass - baseline_mass
        dependent_mass_change = scaling_factor × primary_delta
        dependent_mass += dependent_mass_change

    if max_relative_change < threshold (0.5%):
        converged = True
        break
```

**Formula:**
```
new_mass = base_mass + scaling_factor × (primary_mass - primary_base_mass)
```

**Convergence Criteria:**
- Threshold: 0.5% relative change (configurable)
- Maximum iterations: 10 (configurable)
- Converges when all components change < 0.5%

**Example:**
```python
from src.lca.weight_cascade import calculate_weight_cascade

result = calculate_weight_cascade(
    components=components_dict,
    dependencies=dependencies_list,
    structure_type='onshore',
    convergence_threshold=0.005,  # 0.5%
    max_iterations=10,
    log_iterations=True  # Enable detailed logging
)

print(f"Converged: {result.convergence_achieved}")
print(f"Iterations: {result.iterations}")
print(f"Mass changes: {result.mass_changes}")
```

### GWP Calculation

Global Warming Potential is calculated at the component level and aggregated by lifecycle phase.

**Formula:**
```
Component GWP = mass_kg × material.gwp_kgco2_per_kg
Total GWP = Σ(Component GWP)
```

**Intensity Calculation:**
```
Energy Generation (MWh) = rated_power_mw × lifetime_years × 365.25 × 24 × capacity_factor
Intensity (g-CO2/kWh) = (Total GWP kg × 1000) / (Energy MWh × 1000)
```

**Example:**
```python
from src.lca.gwp import calculate_gwp

result = calculate_gwp(
    components=updated_components,
    materials=materials_list,
    rated_power_mw=3.0,
    lifetime_years=20,
    capacity_factor=0.35
)

print(f"Total GWP: {result.total_gwp_kgco2:,.0f} kg-CO2")
print(f"Intensity: {result.intensity_gco2_per_kwh:.4f} g-CO2/kWh")
print(f"Energy: {result.energy_generation_mwh:,.0f} MWh")
```

### LCACalculator

High-level interface that orchestrates weight cascade and GWP calculation.

**Example:**
```python
from src.lca.calculator import LCACalculator
from src.lci.loaders import load_all_lci_data

# Load data
lci_data = load_all_lci_data(data_dir=Path("data/lci"))

# Create calculator
calculator = LCACalculator(
    lci_data=lci_data,
    structure_type='onshore',
    rated_power_mw=3.0,
    lifetime_years=20,
    capacity_factor=0.35,
    scenario_name='Onshore Baseline',
    enable_weight_cascade=True,
    log_iterations=True
)

# Execute calculation
result = calculator.calculate()

# Access results
print(f"Manufacturing GWP: {result.l1_manufacturing_kgco2:,.0f} kg-CO2")
print(f"Transport GWP: {result.l2_transport_kgco2:,.0f} kg-CO2")
print(f"Total GWP: {result.total_gwp_kgco2:,.0f} kg-CO2")
print(f"Intensity: {result.intensity_gco2_per_kwh:.4f} g-CO2/kWh")
```

## Data Structures

### WeightCascadeResult
```python
@dataclass
class WeightCascadeResult:
    updated_components: Dict[str, Component]  # After cascade
    iterations: int                           # Number performed
    convergence_achieved: bool                # True if threshold met
    mass_changes: Dict[str, float]            # kg change per component
    metadata: Dict[str, str]                  # Warnings, stats
```

### GWPResult
```python
@dataclass
class GWPResult:
    total_gwp_kgco2: float                    # Total lifecycle GWP
    intensity_gco2_per_kwh: float             # Normalized intensity
    phase_breakdown: Dict[str, PhaseGWP]      # By phase
    component_breakdown: List[ComponentGWP]   # By component
    energy_generation_mwh: float              # Lifetime energy
    metadata: Dict[str, str]                  # Additional info
```

### LCAResult
```python
@dataclass
class LCAResult:
    # Phase-level GWP
    l1_manufacturing_kgco2: float
    l2_transport_kgco2: float
    l3_o_and_m_kgco2: float
    l4_eol_kgco2: float
    total_gwp_kgco2: float

    # Normalized metrics
    intensity_gco2_per_kwh: float
    energy_generation_mwh: float

    # Weight cascade info
    weight_cascade_iterations: int
    weight_cascade_converged: bool

    # Component details
    component_gwp_breakdown: List[ComponentGWP]
```

## Calculation Workflow

1. **Load LCI Data**
   - Materials with GWP coefficients
   - Components with baseline masses
   - Dependencies with scaling factors

2. **Execute Weight Cascade** (optional)
   - Iterate until convergence or max iterations
   - Update component masses based on dependencies
   - Track convergence and mass changes

3. **Calculate GWP**
   - Compute GWP for each component
   - Aggregate by lifecycle phase
   - Calculate total GWP

4. **Normalize Results**
   - Calculate lifetime energy generation
   - Convert kg-CO2 to g-CO2/kWh
   - Compute intensity

5. **Return Results**
   - Structured result object
   - Phase and component breakdowns
   - Convergence metadata

## Error Handling

### ValueError
Raised for invalid inputs:
```python
# Negative power
ValueError: "rated_power_mw must be positive, got -5"

# Invalid capacity factor
ValueError: "capacity_factor must be 0-1, got 1.5"

# Missing material
ValueError: "Material 'unknown' not found for component 'blade'"

# Circular dependency
ValueError: "Circular dependency detected: A -> B -> C -> A"
```

## Performance Characteristics

### Weight Cascade
- **Time Complexity:** O(iterations × dependencies)
- **Typical Performance:** 1-5 iterations, <10ms
- **Worst Case:** 10 iterations, <50ms

### GWP Calculation
- **Time Complexity:** O(components × materials)
- **Typical Performance:** 100 components, <5ms
- **Worst Case:** 1000 components, <50ms

### Full LCA Calculation
- **Typical:** 100 components, 20 dependencies, <20ms
- **Large:** 1000 components, 200 dependencies, <200ms

## Design Principles

### Principle 1: Simple Module Separation
- Weight cascade isolated from GWP calculation
- Calculator orchestrates but doesn't contain logic
- Clear inputs and outputs for each function

### Principle 2: Data Transparency
- All calculations logged when `log_iterations=True`
- Iteration details tracked in result metadata
- Component-level breakdown always available

### Principle 6: Minimal Abstraction
- Direct implementation of algorithms, no frameworks
- Simple data structures (dataclasses)
- No inheritance hierarchies or abstract base classes
- Functions, not method chains

## Extending the Calculation Layer

### Adding New Calculation Methods

**Current:** Linear scaling weight cascade
```python
new_mass = base_mass + scaling_factor × primary_delta
```

**Future Extension Points:**
- Nonlinear scaling (quadratic, exponential)
- Multi-primary dependencies
- Dynamic scaling factors based on mass ranges
- Structural optimization feedback

### Adding New GWP Phases

Currently only manufacturing phase (L1) is fully implemented. To add transport (L2), O&M (L3), or EoL (L4):

1. Load LCA events from CSV
2. Calculate phase-specific GWP
3. Add to phase_breakdown dict
4. Aggregate into total_gwp

### Adding New Impact Categories

Beyond GWP (Global Warming Potential), support for:
- Acidification Potential (AP)
- Eutrophication Potential (EP)
- Ozone Depletion Potential (ODP)
- Primary Energy Demand (PED)

Follow the same pattern as GWP calculation with material-specific coefficients.

## Testing

### Unit Tests
```bash
pytest tests/unit/test_weight_cascade.py -v
pytest tests/unit/test_gwp_calculation.py -v
```

### Integration Tests
```bash
pytest tests/integration/test_end_to_end.py -v
```

### Example Test
```python
def test_weight_cascade_convergence():
    components = {...}  # Test fixtures
    dependencies = [...]

    result = calculate_weight_cascade(
        components, dependencies, 'onshore'
    )

    assert result.convergence_achieved is True
    assert result.iterations <= 10
```

## References

- IPCC AR5 100-year GWP coefficients
- ISO 14040:2006 - Environmental management - Life cycle assessment
- ISO 14044:2006 - Life cycle assessment - Requirements and guidelines
