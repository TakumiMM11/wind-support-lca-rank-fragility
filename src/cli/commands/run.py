"""Run command - Execute LCA scenario calculation.

This command loads a scenario YAML file, validates it, executes the LCA calculation,
and saves results to CSV.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import click
import yaml
from pydantic import ValidationError

from src.lca.calculator import LCACalculator
from src.lci.loaders import load_all_lci_data

logger = logging.getLogger(__name__)


@click.command()
@click.argument(
    "scenario_pattern",
    type=str,
)
@click.pass_context
def run(ctx, scenario_pattern: str):
    """Execute LCA calculation for one or more scenarios.

    SCENARIO_PATTERN: Path to scenario.yaml file or glob pattern

    Supports:
    - Single file: scenarios/001-onshore-3mw-baseline/scenario.yaml
    - Glob pattern: scenarios/*/scenario.yaml (all scenarios)
    - Filtered glob: scenarios/00*-onshore-*/scenario.yaml

    \b
    Examples:
        lca-toolkit run scenarios/001-onshore-3mw-baseline/scenario.yaml
        lca-toolkit run "scenarios/*/scenario.yaml"
        lca-toolkit run "scenarios/00*-onshore-*/scenario.yaml" --verbose
    """
    # Get global options from context
    verbose = ctx.obj.get("verbose", False)
    output_dir = ctx.obj.get("output")

    # Expand glob pattern to get list of scenario files
    from glob import glob

    scenario_files = []
    pattern_path = Path(scenario_pattern)

    # Check if it's a direct file path (no wildcards)
    if "*" not in scenario_pattern and "?" not in scenario_pattern:
        if pattern_path.exists() and pattern_path.is_file():
            scenario_files = [pattern_path]
        else:
            click.echo(f"Error: File not found: {scenario_pattern}", err=True)
            sys.exit(1)
    else:
        # Glob pattern expansion
        matched_files = glob(scenario_pattern)
        scenario_files = [Path(f) for f in matched_files if Path(f).is_file()]

        if not scenario_files:
            click.echo(f"Error: No scenarios match pattern: {scenario_pattern}", err=True)
            sys.exit(1)

    # Sort scenarios for consistent processing order
    scenario_files = sorted(scenario_files)

    total_scenarios = len(scenario_files)
    successful = 0
    failed = 0
    failed_scenarios = []

    # Batch processing
    for idx, scenario_file in enumerate(scenario_files, 1):
        try:
            # Progress logging for batch
            if total_scenarios > 1:
                scenario_name = scenario_file.parent.name
                click.echo(f"\n{'=' * 60}")
                click.echo(f"Processing scenario {idx} of {total_scenarios}: {scenario_name}")
                click.echo(f"{'=' * 60}")

            logger.info(f"Loading scenario from: {scenario_file}")

            _process_single_scenario(ctx, scenario_file, verbose, output_dir)
            successful += 1

        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
            if exit_code == 0:
                successful += 1
                continue

            failed += 1
            failed_scenarios.append({
                'file': str(scenario_file),
                'error': f"Exited with status {exit_code}"
            })

            if total_scenarios == 1:
                raise
            else:
                click.echo(f"\n✗ Error processing {scenario_file.parent.name}:", err=True)
                click.echo(f"  Exited with status {exit_code}", err=True)
                logger.error(f"Failed to process {scenario_file}: exited with status {exit_code}")
                continue

        except Exception as e:
            failed += 1
            failed_scenarios.append({
                'file': str(scenario_file),
                'error': str(e)
            })

            if total_scenarios == 1:
                # For single scenario, re-raise the exception
                raise
            else:
                # For batch, log error and continue
                click.echo(f"\n✗ Error processing {scenario_file.parent.name}:", err=True)
                click.echo(f"  {str(e)}", err=True)
                logger.error(f"Failed to process {scenario_file}: {e}")
                continue

    # Print batch summary if multiple scenarios
    if total_scenarios > 1:
        click.echo(f"\n{'=' * 60}")
        click.echo("BATCH PROCESSING SUMMARY")
        click.echo(f"{'=' * 60}")
        click.echo(f"Total scenarios: {total_scenarios}")
        click.echo(f"Successful: {successful}")
        click.echo(f"Failed: {failed}")

        if failed_scenarios:
            click.echo(f"\nFailed scenarios:")
            for fs in failed_scenarios:
                click.echo(f"  - {Path(fs['file']).parent.name}: {fs['error']}")

        if failed > 0:
            sys.exit(2)
        else:
            click.echo(f"\n✓ All scenarios processed successfully!")


def _process_single_scenario(ctx, scenario_file: Path, verbose: bool, output_dir: Path = None):
    """Process a single scenario file.

    Args:
        ctx: Click context
        scenario_file: Path to scenario.yaml
        verbose: Verbose logging flag
        output_dir: Optional output directory override
    """
    try:
        logger.info(f"Processing scenario: {scenario_file}")

        # Load and parse YAML
        try:
            with open(scenario_file, "r", encoding="utf-8") as f:
                scenario_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            click.echo(f"Error: Invalid YAML syntax in {scenario_file}", err=True)
            click.echo(f"  {str(e)}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Error: Failed to read {scenario_file}", err=True)
            click.echo(f"  {str(e)}", err=True)
            sys.exit(1)

        # Validate scenario schema
        # Note: Full pydantic validation would be done here with ScenarioSchema
        # For now, we do basic validation
        if not scenario_data:
            click.echo("Error: Scenario file is empty", err=True)
            sys.exit(1)

        # Extract required fields
        try:
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
                    "Missing required fields in scenario: "
                    "structure.type, structure.rated_power_mw, structure.lifetime_years, structure.capacity_factor"
                )

        except (KeyError, ValueError) as e:
            click.echo(f"Error: Invalid scenario configuration", err=True)
            click.echo(f"  {str(e)}", err=True)
            click.echo("\nRequired fields:", err=True)
            click.echo("  - metadata.name", err=True)
            click.echo("  - structure.type", err=True)
            click.echo("  - structure.rated_power_mw", err=True)
            click.echo("  - structure.lifetime_years", err=True)
            click.echo("  - structure.capacity_factor", err=True)
            sys.exit(1)

        logger.info(f"Scenario: {scenario_name} (ID: {scenario_id})")
        logger.info(f"Structure: {structure_type}, Power: {rated_power_mw}MW, Lifetime: {lifetime_years}y")

        # Load LCI data
        click.echo("Loading LCI data...")
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
            click.echo("\nEnsure data/lci/ directory contains required CSV files:", err=True)
            click.echo("  - materials.csv", err=True)
            click.echo("  - components.csv", err=True)
            click.echo("  - weight_dependencies.csv", err=True)
            click.echo("  - transport_vehicles.csv", err=True)
            click.echo("  - lca_events.csv", err=True)
            sys.exit(2)

        # Instantiate calculator
        click.echo(f"Initializing calculator for {structure_type}...")
        try:
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
        except ValueError as e:
            click.echo(f"Error: Failed to initialize calculator", err=True)
            click.echo(f"  {str(e)}", err=True)
            sys.exit(2)

        # Execute calculation
        click.echo("Executing LCA calculation...")
        try:
            result = calculator.calculate()
            logger.info("Calculation completed successfully")
        except Exception as e:
            click.echo(f"Error: Calculation failed", err=True)
            click.echo(f"  {str(e)}", err=True)
            if verbose:
                import traceback

                traceback.print_exc()
            sys.exit(2)

        # Determine output path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if output_dir:
            # Use custom output directory
            output_path = output_dir / f"lca_results_{scenario_id}_{timestamp}.csv"
        else:
            # Use scenario's results directory
            scenario_dir = scenario_file.parent
            results_dir = scenario_dir / "results"
            output_path = results_dir / f"lca_results_{timestamp}.csv"

        # Save results
        click.echo(f"Saving results to {output_path}...")
        try:
            result.to_csv(output_path)
            # Find the most recent detailed log file
            import glob
            log_pattern = "results/lca_calculation_details_*.log"
            log_files = glob.glob(log_pattern)
            if log_files:
                latest_log = max(log_files, key=lambda p: Path(p).stat().st_mtime)
                click.echo(f"Detailed calculation log: {latest_log}")
        except Exception as e:
            click.echo(f"Error: Failed to save results", err=True)
            click.echo(f"  {str(e)}", err=True)
            sys.exit(2)

        # Print summary to stdout
        click.echo("\n" + "=" * 60)
        click.echo("LCA CALCULATION RESULTS")
        click.echo("=" * 60)
        click.echo(f"Scenario: {result.scenario_name}")
        click.echo(f"Structure: {result.structure_type}")
        click.echo("")
        click.echo("Lifecycle Phases:")
        click.echo(f"  L1 Manufacturing:    {result.l1_manufacturing_kgco2:>12,.2f} kg-CO2eq")
        click.echo(f"  L2 Transport:        {result.l2_transport_kgco2:>12,.2f} kg-CO2eq")
        click.echo(f"  L3 O&M:              {result.l3_o_and_m_kgco2:>12,.2f} kg-CO2eq")
        click.echo(f"  L4 End-of-Life:      {result.l4_eol_kgco2:>12,.2f} kg-CO2eq")
        click.echo(f"  {'─' * 58}")
        click.echo(f"  Total:               {result.total_gwp_kgco2:>12,.2f} kg-CO2eq")
        click.echo("")
        click.echo(f"GWP Intensity:         {result.intensity_gco2_per_kwh:>12.4f} g-CO2eq/kWh")
        click.echo(f"Lifetime Energy:       {result.energy_generation_mwh:>12,.2f} MWh")
        click.echo("")
        click.echo(f"Weight Cascade:        {result.weight_cascade_iterations} iterations")
        click.echo(f"Converged:             {'Yes' if result.weight_cascade_converged else 'No'}")
        click.echo("=" * 60)
        click.echo(f"\nResults saved to: {output_path}")

        if not result.weight_cascade_converged:
            click.echo("\nWarning: Weight cascade did not converge", err=True)

        return result

    except Exception as e:
        # Catch-all for unexpected errors
        click.echo(f"Error: Unexpected error occurred", err=True)
        click.echo(f"  {str(e)}", err=True)
        if ctx.obj.get("verbose"):
            import traceback

            traceback.print_exc()
        sys.exit(2)


__all__ = ["run"]
