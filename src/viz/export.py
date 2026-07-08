"""Figure export utilities for publication-quality output.

This module provides functions to save matplotlib figures with proper metadata,
resolution, and formatting for journal submission.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)


def save_figure(
    fig: Figure,
    output_path: Path,
    dpi: int = 300,
    metadata: Optional[Dict[str, str]] = None,
    close_after_save: bool = True,
) -> Path:
    """Save matplotlib figure with publication-quality settings.

    Args:
        fig: Matplotlib figure object to save
        output_path: Path where figure will be saved
        dpi: Resolution in dots per inch (default: 300 for publication)
        metadata: Optional metadata dict to embed in PNG (e.g., title, author, description)
        close_after_save: Whether to close the figure after saving (default: True)

    Returns:
        Path to saved figure

    Raises:
        OSError: If unable to write to output_path

    Example:
        >>> fig, ax = plt.subplots()
        >>> ax.plot([1, 2, 3], [1, 4, 9])
        >>> save_figure(
        ...     fig,
        ...     Path("results/plot.png"),
        ...     metadata={"Title": "Test Plot", "Author": "LCA Toolkit"}
        ... )
    """
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Prepare metadata
    png_metadata = {}
    if metadata:
        # Convert all values to strings for PNG metadata
        png_metadata = {k: str(v) for k, v in metadata.items()}

    # Add standard metadata
    png_metadata.setdefault("Software", "LCA Toolkit")
    png_metadata.setdefault("Creation Time", datetime.now().isoformat())

    # Save figure
    logger.info(f"Saving figure to {output_path} at {dpi} DPI")

    fig.savefig(
        output_path,
        dpi=dpi,
        bbox_inches="tight",
        pad_inches=0.1,
        metadata=png_metadata,
        format="png",
    )

    logger.info(f"Figure saved successfully: {output_path}")

    # Close figure to free memory
    if close_after_save:
        plt.close(fig)

    return output_path


def generate_plot_filename(
    scenario_name: str,
    plot_type: str,
    timestamp: Optional[datetime] = None,
    extension: str = "png",
) -> str:
    """Generate descriptive filename for plot.

    Args:
        scenario_name: Name of the scenario or "comparison" for multi-scenario plots
        plot_type: Type of plot (e.g., "breakdown", "comparison", "component")
        timestamp: Optional timestamp (default: current time)
        extension: File extension (default: "png")

    Returns:
        Filename string in format: {scenario}_{plot_type}_{timestamp}.{ext}

    Example:
        >>> generate_plot_filename("001-onshore-3mw", "breakdown")
        '001-onshore-3mw_breakdown_20260122_143025.png'
    """
    if timestamp is None:
        timestamp = datetime.now()

    timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
    return f"{scenario_name}_{plot_type}_{timestamp_str}.{extension}"


__all__ = ["save_figure", "generate_plot_filename"]
