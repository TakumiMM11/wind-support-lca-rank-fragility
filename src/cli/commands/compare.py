"""Compare command - Batch process and compare multiple scenarios.

This command executes multiple scenarios and generates a comparison report.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from glob import glob

import click
import pandas as pd
import yaml

from src.lca.calculator import LCACalculator
from src.lci.loaders import load_all_lci_data

logger = logging.getLogger(__name__)


@click.command()
@click.argument(
    "scenario_patterns",
    nargs=-1,
    required=True,
)
@click.option(
    "--output-file",
    "-o",
    type=click.Path(path_type=Path),
    help="Output comparison CSV file path (default: results/comparison_{timestamp}.csv)",
)
@click.pass_context
def compare(ctx, scenario_patterns, output_file):
    """Compare multiple scenarios by running them and aggregating results.

    SCENARIO_PATTERNS: One or more paths or glob patterns to scenario.yaml files

    Supports:
    - Multiple files: scenarios/001-*/scenario.yaml scenarios/002-*/scenario.yaml
    - Glob patterns: scenarios/*/scenario.yaml (all scenarios)
    - Filtered glob: scenarios/00*-onshore-*/scenario.yaml

    \b
    Examples:
        lca-toolkit compare scenarios/*/scenario.yaml
        lca-toolkit compare "scenarios/00*-*/scenario.yaml" --output-file comparison.csv
        lca-toolkit compare scenarios/001-*/scenario.yaml scenarios/002-*/scenario.yaml
    """
    verbose = ctx.obj.get("verbose", False)

    # Expand glob patterns to get list of scenario files
    scenario_files = []
    for pattern in scenario_patterns:
        pattern_path = Path(pattern)

        # Check if it's a direct file path (no wildcards)
        if "*" not in pattern and "?" not in pattern:
            if pattern_path.exists() and pattern_path.is_file():
                scenario_files.append(pattern_path)
            else:
                click.echo(f"Warning: File not found: {pattern}", err=True)
        else:
            # Glob pattern expansion
            matched_files = glob(pattern)
            scenario_files.extend([Path(f) for f in matched_files if Path(f).is_file()])

    if not scenario_files:
        click.echo("Error: No scenarios found matching the patterns", err=True)
        sys.exit(1)

    # Remove duplicates and sort
    scenario_files = sorted(set(scenario_files))

    total_scenarios = len(scenario_files)
    click.echo(f"Found {total_scenarios} scenario(s) to compare")

    # Load LCI data once (shared across all scenarios)
    click.echo("\nLoading shared LCI data...")
    try:
        data_dir = Path("data/lci")
        lci_data = load_all_lci_data(data_dir=data_dir)
        logger.info(
            f"Loaded {len(lci_data.materials)} materials, "
            f"{len(lci_data.components)} components, "
            f"{len(lci_data.dependencies)} dependencies"
        )
    except Exception as e:
        click.echo(f"Error: Failed to load LCI data", err=True)
        click.echo(f"  {str(e)}", err=True)
        sys.exit(2)

    # Process each scenario and collect results
    results = []
    successful = 0
    failed = 0

    for idx, scenario_file in enumerate(scenario_files, 1):
        scenario_name = scenario_file.parent.name
        click.echo(f"\n{'=' * 60}")
        click.echo(f"Processing scenario {idx} of {total_scenarios}: {scenario_name}")
        click.echo(f"{'=' * 60}")

        try:
            result_data = _execute_scenario(
                scenario_file=scenario_file,
                lci_data=lci_data,
                verbose=verbose,
            )
            results.append(result_data)
            successful += 1
            click.echo(f"✓ Successfully processed {scenario_name}")

        except Exception as e:
            failed += 1
            click.echo(f"✗ Error processing {scenario_name}: {str(e)}", err=True)
            logger.error(f"Failed to process {scenario_file}: {e}")
            continue

    # Check if we have any results
    if not results:
        click.echo("\nError: No scenarios were successfully processed", err=True)
        sys.exit(2)

    # Create comparison DataFrame
    comparison_df = pd.DataFrame(results)

    # Determine output path
    if output_file:
        output_path = output_file
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path("results") / f"comparison_{timestamp}.csv"

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save comparison CSV
    click.echo(f"\nSaving comparison results to {output_path}...")
    comparison_df.to_csv(output_path, index=False)

    # Print summary
    click.echo(f"\n{'=' * 60}")
    click.echo("COMPARISON SUMMARY")
    click.echo(f"{'=' * 60}")
    click.echo(f"Total scenarios: {total_scenarios}")
    click.echo(f"Successful: {successful}")
    click.echo(f"Failed: {failed}")
    click.echo(f"\nComparison saved to: {output_path}")

    # Print comparison table
    click.echo(f"\n{'=' * 60}")
    click.echo("RESULTS COMPARISON")
    click.echo(f"{'=' * 60}")

    # Format and display key columns
    display_df = comparison_df[[
        'scenario_id',
        'scenario_name',
        'structure_type',
        'rated_power_mw',
        'total_gwp_kgco2',
        'intensity_gco2_per_kwh'
    ]].copy()

    display_df['total_gwp_kgco2'] = display_df['total_gwp_kgco2'].apply(lambda x: f"{x:,.2f}")
    display_df['intensity_gco2_per_kwh'] = display_df['intensity_gco2_per_kwh'].apply(lambda x: f"{x:.4f}")

    click.echo(display_df.to_string(index=False))
    click.echo(f"{'=' * 60}")

    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


def _execute_scenario(scenario_file: Path, lci_data, verbose: bool) -> dict:
    """Execute a single scenario and return results as dict.

    Args:
        scenario_file: Path to scenario.yaml
        lci_data: Pre-loaded LCI data
        verbose: Verbose logging flag

    Returns:
        Dict with scenario results for comparison

    Raises:
        Exception: If scenario processing fails
    """
    # Load and parse YAML
    with open(scenario_file, "r", encoding="utf-8") as f:
        scenario_data = yaml.safe_load(f)

    if not scenario_data:
        raise ValueError("Scenario file is empty")

    # Extract required fields
    metadata = scenario_data.get("metadata", {})
    scenario_name = metadata.get("name", "unknown")
    scenario_id = metadata.get("id", "unknown")

    structure = scenario_data.get("structure", {})
    structure_type = structure.get("type")
    rated_power_mw = structure.get("rated_power_mw")
    lifetime_years = structure.get("lifetime_years")
    capacity_factor = structure.get("capacity_factor")

    calculation = scenario_data.get("calculation", {})
    enable_weight_cascade = calculation.get("weight_cascade", True)

    if not all([structure_type, rated_power_mw, lifetime_years, capacity_factor]):
        raise ValueError(
            f"Missing required fields in scenario {scenario_id}"
        )

    logger.info(f"Scenario: {scenario_name} (ID: {scenario_id})")
    logger.info(f"Structure: {structure_type}, Power: {rated_power_mw}MW")

    # Instantiate calculator
    calculator = LCACalculator(
        lci_data=lci_data,
        structure_type=structure_type,
        rated_power_mw=rated_power_mw,
        lifetime_years=lifetime_years,
        capacity_factor=capacity_factor,
        scenario_name=scenario_name,
        enable_weight_cascade=enable_weight_cascade,
        log_iterations=verbose,
    )

    # Execute calculation
    result = calculator.calculate()
    logger.info(f"Calculation completed for {scenario_name}")

    # Extract scenario directory name
    scenario_dir_name = scenario_file.parent.name

    # Return results as dict for comparison
    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "scenario_dir": scenario_dir_name,
        "structure_type": structure_type,
        "rated_power_mw": rated_power_mw,
        "lifetime_years": lifetime_years,
        "capacity_factor": capacity_factor,
        "l1_manufacturing_kgco2": result.l1_manufacturing_kgco2,
        "l2_transport_kgco2": result.l2_transport_kgco2,
        "l3_o_and_m_kgco2": result.l3_o_and_m_kgco2,
        "l4_eol_kgco2": result.l4_eol_kgco2,
        "total_gwp_kgco2": result.total_gwp_kgco2,
        "intensity_gco2_per_kwh": result.intensity_gco2_per_kwh,
        "energy_generation_mwh": result.energy_generation_mwh,
        "weight_cascade_iterations": result.weight_cascade_iterations,
        "weight_cascade_converged": result.weight_cascade_converged,
    }


__all__ = ["compare"]
