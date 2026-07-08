# Visualization Layer

This module provides publication-quality visualization for LCA results using matplotlib with configurable styling.

## Purpose

The visualization module enables:
- **Publication-Ready Plots:** 300 DPI PNG output with proper fonts
- **Colorblind-Safe Palettes:** Paul Tol's scientifically-proven color schemes
- **Configurable Styling:** YAML-based matplotlib configuration
- **Three Plot Types:** Breakdown, comparison, and component contribution
- **Embedded Metadata:** PNG files include generation timestamp and description

## Module Structure

```
src/viz/
├── styles.yaml       # Matplotlib configuration and color palettes
├── styles.py         # Style loading and application
├── plots.py          # Plot generation functions
├── export.py         # Figure saving with metadata
└── __init__.py       # Public API exports
```

## Style Configuration

### styles.yaml Structure

```yaml
matplotlib:
  figure:
    dpi: 300
    figsize: [6.5, 4.5]  # Journal column width
    facecolor: white

  font:
    family: serif
    size: 10
    serif: [Times New Roman, DejaVu Serif, ...]

  axes:
    labelsize: 10
    titlesize: 11
    grid: true

  legend:
    fontsize: 9
    frameon: true

colors:
  lifecycle_phases:
    l1_manufacturing: "#4477AA"  # Blue
    l2_transport: "#66CCEE"       # Cyan
    l3_o_and_m: "#228833"         # Green
    l4_eol: "#CCBB44"             # Yellow

  structure_types:
    onshore: "#4477AA"
    bottom_fixed: "#66CCEE"
    semisubmersible: "#228833"
    spar: "#CCBB44"
    fawt: "#EE6677"

plots:
  gwp_breakdown:
    figsize: [6.5, 4.5]
    ylabel: "GWP (kg CO₂ eq)"
    title: "Lifecycle GWP Breakdown by Phase"
```

### Loading and Applying Styles

```python
from src.viz.styles import apply_style, get_color_palette

# Apply default style (loads from src/viz/styles.yaml)
apply_style()

# Get color palette
phase_colors = get_color_palette("lifecycle_phases")
print(phase_colors["l1_manufacturing"])  # "#4477AA"
```

## Plot Functions

### 1. GWP Breakdown by Phase

Stacked bar chart showing lifecycle phase contributions.

```python
from src.viz.plots import plot_gwp_breakdown
import pandas as pd

# Load results
df = pd.read_csv("results/comparison.csv")

# Generate plot
fig = plot_gwp_breakdown(
    results_df=df,
    scenario_column="scenario_name",
    show_total=True  # Display total values on top
)

# Save
from src.viz.export import save_figure
save_figure(fig, Path("results/plots/breakdown.png"))
```

**Required Columns:**
- `scenario_name` (or custom column via `scenario_column`)
- `l1_manufacturing_kgco2`
- `l2_transport_kgco2`
- `l3_o_and_m_kgco2`
- `l4_eol_kgco2`
- `total_gwp_kgco2` (optional, for labels)

**Output Features:**
- Stacked bars with phase-specific colors
- Total GWP labeled on top of each bar
- Legend with phase names
- Grid for readability
- Rotated scenario labels

### 2. Scenario Comparison

Grouped bar chart comparing GWP intensity across scenarios.

```python
from src.viz.plots import plot_scenario_comparison

fig = plot_scenario_comparison(
    results_df=df,
    scenario_column="scenario_name",
    metric_column="intensity_gco2_per_kwh",
    structure_type_column="structure_type"
)
```

**Required Columns:**
- `scenario_name` (or custom)
- `intensity_gco2_per_kwh` (or custom metric)
- `structure_type` (optional, for coloring)

**Output Features:**
- Bars colored by structure type
- Intensity values labeled on top
- Legend showing structure types
- Optimized width for multiple scenarios

### 3. Component Contribution

Horizontal bar chart showing top N components by GWP.

```python
from src.viz.plots import plot_component_contribution

fig = plot_component_contribution(
    component_results=component_df,
    component_column="component_id",
    gwp_column="total_gwp_kgco2",
    top_n=15  # Show top 15 contributors
)
```

**Required Columns:**
- `component_id` (or custom)
- `total_gwp_kgco2` (or custom GWP column)

**Output Features:**
- Horizontal layout for long component names
- Sorted by GWP (largest at top)
- GWP values labeled on bars
- Cycling colors from component palette

## Figure Export

### Saving with Metadata

```python
from src.viz.export import save_figure

fig = plot_gwp_breakdown(df)

save_figure(
    fig=fig,
    output_path=Path("results/breakdown.png"),
    dpi=300,  # Publication quality
    metadata={
        "Title": "GWP Breakdown - Onshore 3MW",
        "Description": "Lifecycle phase analysis",
        "Scenario": "001-onshore-3mw-baseline"
    },
    close_after_save=True  # Free memory
)
```

**Embedded Metadata:**
- Software: "LCA Toolkit"
- Creation Time: ISO timestamp
- Custom fields from `metadata` dict
- Readable with `exiftool` or `pnginfo`

### Filename Generation

```python
from src.viz.export import generate_plot_filename

filename = generate_plot_filename(
    scenario_name="001-onshore-3mw",
    plot_type="breakdown",
    timestamp=None,  # Uses current time
    extension="png"
)
# Returns: "001-onshore-3mw_breakdown_20260122_143025.png"
```

## Color Palettes

### Colorblind-Safe Schemes

All palettes based on Paul Tol's qualitative schemes, tested for:
- Protanopia (red-blind)
- Deuteranopia (green-blind)
- Tritanopia (blue-blind)
- Grayscale printing

### Lifecycle Phase Colors
```python
"#4477AA"  # L1: Manufacturing (Blue)
"#66CCEE"  # L2: Transport (Cyan)
"#228833"  # L3: O&M (Green)
"#CCBB44"  # L4: End-of-Life (Yellow)
```

### Structure Type Colors
```python
"#4477AA"  # Onshore (Blue)
"#66CCEE"  # Bottom-Fixed (Cyan)
"#228833"  # Semi-submersible (Green)
"#CCBB44"  # Spar (Yellow)
"#EE6677"  # FAWT (Red)
"#AA3377"  # TLP (Purple)
```

### Component Contribution (10 colors)
Cycles through distinct colors for many components.

## Usage Examples

### Complete Workflow

```python
from pathlib import Path
import pandas as pd
from src.viz import (
    apply_style,
    plot_gwp_breakdown,
    plot_scenario_comparison,
    save_figure,
    generate_plot_filename
)

# Load results
df = pd.read_csv("results/comparison.csv")

# Apply style globally
apply_style()

# Generate breakdown plot
fig1 = plot_gwp_breakdown(df, show_total=True)
filename1 = generate_plot_filename("all-scenarios", "breakdown")
save_figure(fig1, Path(f"results/plots/{filename1}"))

# Generate comparison plot
fig2 = plot_scenario_comparison(df)
filename2 = generate_plot_filename("all-scenarios", "comparison")
save_figure(fig2, Path(f"results/plots/{filename2}"))

print("Plots saved to results/plots/")
```

### Custom Plot Configuration

```python
from src.viz.styles import load_style_config, get_plot_config

# Load custom config
config = load_style_config(Path("custom_styles.yaml"))

# Get plot-specific settings
breakdown_cfg = get_plot_config("gwp_breakdown", config)
figsize = breakdown_cfg["figsize"]
ylabel = breakdown_cfg["ylabel"]
```

## Journal Submission Standards

### Resolution
- **300 DPI minimum** (most journals)
- 600 DPI for line art (optional, configurable)
- PNG format with lossless compression

### Fonts
- **Serif fonts preferred** (Times New Roman, DejaVu Serif)
- 10pt body text
- 11pt titles
- 9pt legends

### Figure Size
- **6.5 inches width** (standard single-column)
- 4.5 inches height (typical)
- Adjustable via styles.yaml

### Color Requirements
- Colorblind-safe palettes
- Distinguishable in grayscale
- High contrast for printing

## Performance Notes

- **Plot generation:** 0.5-2 seconds per plot
- **PNG export (300 DPI):** 0.1-0.3 seconds
- **Memory usage:** 15-20 MB per figure
- **File size:** 150-200 KB per PNG

## Design Principles

### Principle 4: Publication-Quality Visualization
- 300 DPI enforced throughout
- Configurable via YAML, not hardcoded
- Meets journal standards without manual editing

### Principle 5: Configuration-Driven
- All styling externalized to styles.yaml
- No magic numbers in code
- Easy to customize for different journals

### Principle 6: Minimal Abstraction
- Direct matplotlib usage, no plotting framework
- Simple functions, not class hierarchies
- Straightforward API without complexity

## Troubleshooting

### Font Warnings
**Issue:** "Glyph 8322 (\N{SUBSCRIPT TWO}) missing from current font"

**Solution:** Install fonts with Unicode support or use `CO2` instead of `CO₂`

### Figure Not Closing
**Issue:** Memory usage increases with many plots

**Solution:** Set `close_after_save=True` or call `plt.close(fig)`

### Low Resolution Output
**Issue:** Plot looks pixelated

**Solution:** Verify `dpi=300` in save_figure call and styles.yaml

## Testing

### Visual Regression Tests
```bash
pytest tests/unit/test_plots.py -v
```

### Manual Verification
```bash
# Generate test plots
python -m src.cli.main plot breakdown results/comparison.csv

# Check DPI
exiftool results/plots/*.png | grep "X Resolution"
# Should show: 300
```

## References

- Paul Tol's Colour Schemes: https://personal.sron.nl/~pault/
- Matplotlib documentation: https://matplotlib.org/
- PNG specification: http://www.libpng.org/pub/png/spec/
