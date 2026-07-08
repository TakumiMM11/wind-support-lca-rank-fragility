"""Plot command - Generate publication-quality visualizations from LCA results.

This command creates plots from CSV result files with 300 DPI resolution,
colorblind-safe colors, and journal-ready formatting.
"""

import logging
import sys
from datetime import datetime
from glob import glob
from pathlib import Path

import click
import pandas as pd

from src.viz.export import generate_plot_filename, save_figure
from src.viz.plots import (
    plot_component_contribution,
    plot_gwp_breakdown,
    plot_scenario_comparison,
)

logger = logging.getLogger(__name__)


@click.command()
@click.argument(
    "plot_type",
    type=click.Choice(["breakdown", "comparison", "component"], case_sensitive=False),
)
@click.argument(
    "result_files",
    nargs=-1,
    required=True,
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    help="Output directory for plots (default: results/plots/)",
)
@click.option(
    "--top-n",
    type=int,
    default=15,
    help="Number of top components to show (component plot only, default: 15)",
)
@click.pass_context
def plot(ctx, plot_type, result_files, output_dir, top_n):
    """Generate publication-quality plots from LCA result CSV files.

    PLOT_TYPE: Type of plot to generate (breakdown, comparison, component)

    RESULT_FILES: One or more paths or glob patterns to result CSV files

    Plot Types:

    \b
    - breakdown: Stacked bar chart showing lifecycle phase contributions (L1-L4)
    - comparison: Grouped bar chart comparing GWP intensity across scenarios
    - component: Horizontal bar chart showing top component contributions

    \b
    Examples:
        # GWP breakdown from single scenario
        lca-toolkit plot breakdown scenarios/001-onshore-3mw-baseline/results/lca_results_*.csv

        # Compare all scenarios
        lca-toolkit plot comparison results/comparison_*.csv

        # Component contribution (top 10)
        lca-toolkit plot component results/component_gwp.csv --top-n 10

        # Use glob patterns
        lca-toolkit plot breakdown "scenarios/*/results/lca_results_*.csv"
    """
    verbose = ctx.obj.get("verbose", False)

    # Determine output directory
    if output_dir is None:
        output_dir = Path("results/plots")
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Expand glob patterns to get list of result files
    csv_files = []
    for pattern in result_files:
        pattern_path = Path(pattern)

        # Check if it's a direct file path (no wildcards)
        if "*" not in pattern and "?" not in pattern:
            if pattern_path.exists() and pattern_path.is_file():
                csv_files.append(pattern_path)
            else:
                click.echo(f"Warning: File not found: {pattern}", err=True)
        else:
            # Glob pattern expansion
            matched_files = glob(pattern)
            csv_files.extend([Path(f) for f in matched_files if Path(f).is_file()])

    if not csv_files:
        click.echo("Error: No result files found matching the patterns", err=True)
        sys.exit(1)

    # Remove duplicates and sort
    csv_files = sorted(set(csv_files))
    click.echo(f"Found {len(csv_files)} result file(s)")

    # Load CSV data
    click.echo(f"Loading CSV data...")
    try:
        if len(csv_files) == 1:
            results_df = pd.read_csv(csv_files[0])
            scenario_name = csv_files[0].stem.replace("lca_results_", "").replace("comparison_", "")
        else:
            # Concatenate multiple CSV files
            dfs = []
            for csv_file in csv_files:
                df = pd.read_csv(csv_file)
                dfs.append(df)
            results_df = pd.concat(dfs, ignore_index=True)
            scenario_name = "comparison"

        logger.info(f"Loaded {len(results_df)} rows from {len(csv_files)} file(s)")

    except Exception as e:
        click.echo(f"Error: Failed to load CSV data", err=True)
        click.echo(f"  {str(e)}", err=True)
        sys.exit(2)

    # Generate plot based on type
    click.echo(f"\\nGenerating {plot_type} plot...")
    try:
        if plot_type == "breakdown":
            fig = plot_gwp_breakdown(results_df)

        elif plot_type == "comparison":
            fig = plot_scenario_comparison(results_df)

        elif plot_type == "component":
            # For component plot, we need component-level data
            # Check if we have the right columns
            if "component_id" not in results_df.columns:
                click.echo(
                    "Error: Component plot requires 'component_id' column in CSV",
                    err=True,
                )
                click.echo(
                    "Hint: This plot type works with component-level export data",
                    err=True,
                )
                sys.exit(3)

            fig = plot_component_contribution(results_df, top_n=top_n)

        else:
            click.echo(f"Error: Unknown plot type: {plot_type}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: Failed to generate plot", err=True)
        click.echo(f"  {str(e)}", err=True)
        if verbose:
            import traceback
            click.echo(traceback.format_exc(), err=True)
        sys.exit(2)

    # Save figure
    timestamp = datetime.now()
    filename = generate_plot_filename(scenario_name, plot_type, timestamp)
    output_path = output_dir / filename

    click.echo(f"Saving plot to {output_path}...")
    try:
        metadata = {
            "Title": f"{plot_type.capitalize()} Plot - {scenario_name}",
            "Description": f"LCA {plot_type} visualization",
            "Plot Type": plot_type,
            "Scenarios": scenario_name,
            "Generated": timestamp.isoformat(),
        }
        save_figure(fig, output_path, metadata=metadata)

    except Exception as e:
        click.echo(f"Error: Failed to save plot", err=True)
        click.echo(f"  {str(e)}", err=True)
        sys.exit(2)

    # Success
    click.echo(f"\\n{'=' * 60}")
    click.echo(f"Plot saved successfully: {output_path}")
    click.echo(f"{'=' * 60}")
    sys.exit(0)


__all__ = ["plot"]
