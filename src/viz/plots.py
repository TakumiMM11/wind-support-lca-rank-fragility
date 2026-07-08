"""Plot functions for LCA visualization.

This module provides publication-quality plotting functions for lifecycle assessment results.
All plots apply the style configuration from styles.yaml.
"""

import logging
from typing import Any, Dict

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure

from src.viz.styles import apply_style, get_color_palette, get_plot_config

logger = logging.getLogger(__name__)


def plot_gwp_breakdown(
    results_df: pd.DataFrame,
    scenario_column: str = "scenario_name",
    show_total: bool = True,
) -> Figure:
    """Create stacked bar chart showing GWP breakdown by lifecycle phases.

    Args:
        results_df: DataFrame with columns for scenario and lifecycle phases
                    (l1_manufacturing_kgco2, l2_transport_kgco2, l3_o_and_m_kgco2, l4_eol_kgco2)
        scenario_column: Column name containing scenario identifiers (default: "scenario_name")
        show_total: Whether to show total GWP values on top of bars (default: True)

    Returns:
        Matplotlib Figure object

    Raises:
        ValueError: If required columns are missing

    Example:
        >>> df = pd.read_csv("results/comparison.csv")
        >>> fig = plot_gwp_breakdown(df)
        >>> save_figure(fig, Path("results/gwp_breakdown.png"))
    """
    # Apply style configuration
    apply_style()
    plot_cfg = get_plot_config("gwp_breakdown")
    colors = get_color_palette("lifecycle_phases")

    # Validate required columns
    required_cols = [
        scenario_column,
        "l1_manufacturing_kgco2",
        "l2_transport_kgco2",
        "l3_o_and_m_kgco2",
        "l4_eol_kgco2",
    ]
    missing_cols = [col for col in required_cols if col not in results_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Create figure
    figsize = plot_cfg.get("figsize", [6.5, 4.5])
    fig, ax = plt.subplots(figsize=figsize)

    # Prepare data
    scenarios = results_df[scenario_column].tolist()
    x_pos = range(len(scenarios))

    # Extract lifecycle phase data
    l1 = results_df["l1_manufacturing_kgco2"].values
    l2 = results_df["l2_transport_kgco2"].values
    l3 = results_df["l3_o_and_m_kgco2"].values
    l4 = results_df["l4_eol_kgco2"].values

    # Create stacked bar chart
    bar_width = 0.8

    ax.bar(
        x_pos,
        l1,
        bar_width,
        label="L1: Manufacturing",
        color=colors["l1_manufacturing"],
    )
    ax.bar(
        x_pos,
        l2,
        bar_width,
        bottom=l1,
        label="L2: Transport",
        color=colors["l2_transport"],
    )
    ax.bar(
        x_pos,
        l3,
        bar_width,
        bottom=l1 + l2,
        label="L3: O&M",
        color=colors["l3_o_and_m"],
    )
    ax.bar(
        x_pos,
        l4,
        bar_width,
        bottom=l1 + l2 + l3,
        label="L4: End-of-Life",
        color=colors["l4_eol"],
    )

    # Show total values on top
    if show_total and "total_gwp_kgco2" in results_df.columns:
        totals = results_df["total_gwp_kgco2"].values
        for i, total in enumerate(totals):
            ax.text(
                i,
                total,
                f"{total:,.0f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    # Configure axes
    ax.set_ylabel(plot_cfg.get("ylabel", "GWP (kg CO₂ eq)"))
    ax.set_xlabel(plot_cfg.get("xlabel", "Scenario"))
    ax.set_title(plot_cfg.get("title", "Lifecycle GWP Breakdown by Phase"))
    ax.set_xticks(x_pos)
    ax.set_xticklabels(scenarios, rotation=45, ha="right")
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))

    # Format y-axis with thousands separator
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:,.0f}"))

    plt.tight_layout()

    logger.info(f"Created GWP breakdown plot for {len(scenarios)} scenarios")
    return fig


def plot_component_contribution(
    component_results: pd.DataFrame,
    component_column: str = "component_id",
    gwp_column: str = "total_gwp_kgco2",
    top_n: int = 15,
) -> Figure:
    """Create horizontal bar chart showing component-level GWP contributions.

    Args:
        component_results: DataFrame with component-level GWP data
        component_column: Column name containing component identifiers
        gwp_column: Column name containing GWP values
        top_n: Number of top components to show (default: 15)

    Returns:
        Matplotlib Figure object

    Raises:
        ValueError: If required columns are missing

    Example:
        >>> df = pd.read_csv("results/component_gwp.csv")
        >>> fig = plot_component_contribution(df, top_n=10)
        >>> save_figure(fig, Path("results/component_contribution.png"))
    """
    # Apply style configuration
    apply_style()
    plot_cfg = get_plot_config("component_contribution")
    component_colors = get_color_palette("components")

    # Validate required columns
    required_cols = [component_column, gwp_column]
    missing_cols = [col for col in required_cols if col not in component_results.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Override top_n from config if not explicitly provided
    if top_n == 15:
        top_n = plot_cfg.get("top_n", 15)

    # Sort by GWP and take top N
    sorted_df = component_results.sort_values(gwp_column, ascending=True).tail(top_n)

    # Create figure
    figsize = plot_cfg.get("figsize", [6.5, 6.0])
    fig, ax = plt.subplots(figsize=figsize)

    # Prepare data
    components = sorted_df[component_column].tolist()
    gwp_values = sorted_df[gwp_column].values
    y_pos = range(len(components))

    # Assign colors (cycle through palette)
    bar_colors = [component_colors[i % len(component_colors)] for i in range(len(components))]

    # Create horizontal bar chart
    ax.barh(y_pos, gwp_values, color=bar_colors)

    # Add value labels on bars
    for i, value in enumerate(gwp_values):
        ax.text(
            value,
            i,
            f"  {value:,.0f}",
            va="center",
            ha="left",
            fontsize=8,
        )

    # Configure axes
    ax.set_xlabel(plot_cfg.get("xlabel", "GWP (kg CO₂ eq)"))
    ax.set_ylabel(plot_cfg.get("ylabel", "Component"))
    ax.set_title(plot_cfg.get("title", "Component-Level GWP Contribution"))
    ax.set_yticks(y_pos)
    ax.set_yticklabels(components)

    # Format x-axis with thousands separator
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:,.0f}"))

    plt.tight_layout()

    logger.info(f"Created component contribution plot for {len(components)} components")
    return fig


def plot_scenario_comparison(
    results_df: pd.DataFrame,
    scenario_column: str = "scenario_name",
    metric_column: str = "intensity_gco2_per_kwh",
    structure_type_column: str = "structure_type",
) -> Figure:
    """Create grouped bar chart comparing scenarios by GWP intensity.

    Args:
        results_df: DataFrame with scenario comparison data
        scenario_column: Column name containing scenario identifiers
        metric_column: Column name containing the metric to compare (default: intensity)
        structure_type_column: Column name containing structure types for coloring

    Returns:
        Matplotlib Figure object

    Raises:
        ValueError: If required columns are missing

    Example:
        >>> df = pd.read_csv("results/comparison.csv")
        >>> fig = plot_scenario_comparison(df)
        >>> save_figure(fig, Path("results/scenario_comparison.png"))
    """
    # Apply style configuration
    apply_style()
    plot_cfg = get_plot_config("scenario_comparison")
    structure_colors = get_color_palette("structure_types")

    # Validate required columns
    required_cols = [scenario_column, metric_column]
    missing_cols = [col for col in required_cols if col not in results_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Create figure
    figsize = plot_cfg.get("figsize", [8.0, 4.5])
    fig, ax = plt.subplots(figsize=figsize)

    # Prepare data
    scenarios = results_df[scenario_column].tolist()
    values = results_df[metric_column].values
    x_pos = range(len(scenarios))

    # Get colors based on structure type if available
    if structure_type_column in results_df.columns:
        bar_colors = [
            structure_colors.get(st, "#BBBBBB")
            for st in results_df[structure_type_column]
        ]
    else:
        # Use default color cycle
        bar_colors = ["#4477AA"] * len(scenarios)

    # Create bar chart
    bar_width = plot_cfg.get("bar_width", 0.8)
    bars = ax.bar(x_pos, values, bar_width, color=bar_colors)

    # Add value labels on top of bars
    for i, (bar, value) in enumerate(zip(bars, values)):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    # Configure axes
    ax.set_ylabel(plot_cfg.get("ylabel", "GWP Intensity (g CO₂ eq/kWh)"))
    ax.set_xlabel(plot_cfg.get("xlabel", "Scenario"))
    ax.set_title(plot_cfg.get("title", "Scenario Comparison by GWP Intensity"))
    ax.set_xticks(x_pos)
    ax.set_xticklabels(scenarios, rotation=45, ha="right")

    # Add legend for structure types if available
    if structure_type_column in results_df.columns:
        unique_structures = results_df[structure_type_column].unique()
        legend_handles = [
            plt.Rectangle((0, 0), 1, 1, fc=structure_colors.get(st, "#BBBBBB"))
            for st in unique_structures
        ]
        ax.legend(
            legend_handles,
            unique_structures,
            loc="upper left",
            bbox_to_anchor=(1, 1),
            title="Structure Type",
        )

    plt.tight_layout()

    logger.info(f"Created scenario comparison plot for {len(scenarios)} scenarios")
    return fig


__all__ = [
    "plot_gwp_breakdown",
    "plot_component_contribution",
    "plot_scenario_comparison",
]
