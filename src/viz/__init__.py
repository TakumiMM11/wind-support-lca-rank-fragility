"""Visualization module for LCA Toolkit.

This package provides publication-quality plotting functions for lifecycle assessment results.
All plots follow journal submission standards (300 DPI, serif fonts, colorblind-safe palettes).

Modules:
- styles: Style configuration loading and application
- plots: Core plotting functions (breakdown, comparison, component)
- export: Figure export with metadata
"""

from src.viz.export import generate_plot_filename, save_figure
from src.viz.plots import (
    plot_component_contribution,
    plot_gwp_breakdown,
    plot_scenario_comparison,
)
from src.viz.styles import apply_style, get_color_palette, get_plot_config, load_style_config

__all__ = [
    "load_style_config",
    "apply_style",
    "get_color_palette",
    "get_plot_config",
    "plot_gwp_breakdown",
    "plot_component_contribution",
    "plot_scenario_comparison",
    "save_figure",
    "generate_plot_filename",
]
