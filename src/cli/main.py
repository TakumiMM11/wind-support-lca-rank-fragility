"""LCA Toolkit CLI - Main Entry Point.

This module provides the command-line interface for the LCA Toolkit.
It uses click for argument parsing and command routing.

Usage:
    lca-toolkit --help
    lca-toolkit run scenarios/001-onshore-3mw-baseline/scenario.yaml --verbose
    lca-toolkit validate scenarios/002-fawt-10mw-cfrp/scenario.yaml
"""

import logging
import sys
from pathlib import Path

import click

# Version
__version__ = "0.1.0"


@click.group()
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging (INFO level)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(file_okay=False, path_type=Path),
    help="Output directory for results (default: scenario's results/ directory)",
)
@click.version_option(version=__version__, prog_name="lca-toolkit")
@click.pass_context
def cli(ctx, verbose, output):
    """LCA Toolkit - Wind Turbine Life Cycle Assessment Tool.

    A command-line tool for calculating environmental impacts of wind energy systems.

    \b
    Examples:
        # Run single scenario
        lca-toolkit run scenarios/001-onshore-3mw-baseline/scenario.yaml

        # Run with verbose logging
        lca-toolkit run scenarios/002-fawt-10mw-cfrp/scenario.yaml --verbose

        # Validate scenario configuration
        lca-toolkit validate scenarios/001-onshore-3mw-baseline/scenario.yaml

        # Run with custom output directory
        lca-toolkit run scenarios/001-onshore-3mw-baseline/scenario.yaml --output results/
    """
    # Initialize click context
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["output"] = output

    # Configure logging
    log_level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,  # Log to stderr, results to stdout
    )

    # Log startup
    if verbose:
        logger = logging.getLogger(__name__)
        logger.info(f"LCA Toolkit v{__version__}")
        logger.info(f"Log level: {logging.getLevelName(log_level)}")
        if output:
            logger.info(f"Output directory: {output}")


# Import and register commands
from src.cli.commands import run, validate, compare, matrix, plot

cli.add_command(run.run)
cli.add_command(validate.validate)
cli.add_command(compare.compare)
cli.add_command(matrix.matrix)
cli.add_command(plot.plot)


if __name__ == "__main__":
    cli()
