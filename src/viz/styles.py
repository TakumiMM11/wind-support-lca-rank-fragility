"""Visualization style configuration and application.

This module provides functions to load and apply matplotlib style configurations
from styles.yaml for publication-quality figures.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union, List

import matplotlib.pyplot as plt
import yaml

logger = logging.getLogger(__name__)

# Cache for loaded style configuration
_style_config: Optional[Dict[str, Any]] = None


def load_style_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load style configuration from YAML file.

    Args:
        config_path: Path to styles.yaml. If None, uses default location (src/viz/styles.yaml)

    Returns:
        Dict containing style configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    global _style_config

    # Return cached config if available
    if _style_config is not None and config_path is None:
        return _style_config

    # Determine config path
    if config_path is None:
        # Default location: src/viz/styles.yaml
        config_path = Path(__file__).parent / "styles.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Style configuration not found: {config_path}")

    # Load YAML
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config:
        raise ValueError(f"Empty or invalid style configuration: {config_path}")

    # Cache for future use
    if config_path == Path(__file__).parent / "styles.yaml":
        _style_config = config

    logger.info(f"Loaded style configuration from {config_path}")
    return config


def apply_style(config: Optional[Dict[str, Any]] = None) -> None:
    """Apply matplotlib style configuration.

    This function updates matplotlib rcParams with the loaded configuration.
    It should be called at the start of each plot function.

    Args:
        config: Style configuration dict. If None, loads from default location.

    Example:
        >>> apply_style()  # Load and apply default config
        >>> fig, ax = plt.subplots()
        >>> # Create plot...
    """
    if config is None:
        config = load_style_config()

    mpl_config = config.get("matplotlib", {})

    # Apply figure settings
    if "figure" in mpl_config:
        for key, value in mpl_config["figure"].items():
            plt.rcParams[f"figure.{key}"] = value

    # Apply font settings
    if "font" in mpl_config:
        for key, value in mpl_config["font"].items():
            plt.rcParams[f"font.{key}"] = value

    # Apply axes settings
    if "axes" in mpl_config:
        for key, value in mpl_config["axes"].items():
            plt.rcParams[f"axes.{key}"] = value

    # Apply grid settings
    if "grid" in mpl_config:
        for key, value in mpl_config["grid"].items():
            plt.rcParams[f"grid.{key}"] = value

    # Apply legend settings
    if "legend" in mpl_config:
        for key, value in mpl_config["legend"].items():
            plt.rcParams[f"legend.{key}"] = value

    # Apply savefig settings
    if "savefig" in mpl_config:
        for key, value in mpl_config["savefig"].items():
            plt.rcParams[f"savefig.{key}"] = value

    logger.debug("Applied matplotlib style configuration")


def get_color_palette(palette_name: str, config: Optional[Dict[str, Any]] = None) -> Union[Dict[str, str], List[str]]:
    """Get a color palette from configuration.

    Args:
        palette_name: Name of the palette (e.g., "lifecycle_phases", "structure_types", "components")
        config: Style configuration dict. If None, loads from default location.

    Returns:
        Dict mapping names to colors, or list of colors for "components" palette

    Raises:
        KeyError: If palette_name doesn't exist in configuration

    Example:
        >>> colors = get_color_palette("lifecycle_phases")
        >>> l1_color = colors["l1_manufacturing"]
    """
    if config is None:
        config = load_style_config()

    colors = config.get("colors", {})
    if palette_name not in colors:
        raise KeyError(f"Color palette '{palette_name}' not found in configuration")

    return colors[palette_name]


def get_plot_config(plot_name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get plot-specific configuration.

    Args:
        plot_name: Name of the plot (e.g., "gwp_breakdown", "component_contribution")
        config: Style configuration dict. If None, loads from default location.

    Returns:
        Dict containing plot-specific settings

    Raises:
        KeyError: If plot_name doesn't exist in configuration

    Example:
        >>> plot_cfg = get_plot_config("gwp_breakdown")
        >>> figsize = plot_cfg["figsize"]
    """
    if config is None:
        config = load_style_config()

    plots = config.get("plots", {})
    if plot_name not in plots:
        raise KeyError(f"Plot configuration '{plot_name}' not found")

    return plots[plot_name]


__all__ = ["load_style_config", "apply_style", "get_color_palette", "get_plot_config"]
