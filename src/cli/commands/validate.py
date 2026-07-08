"""Validate command - Check scenario configuration validity.

This command loads and validates a scenario YAML file without executing calculations.
It checks:
- YAML syntax
- Required fields presence
- Field types and ranges
- Structure type validity
"""

import logging
import sys
from pathlib import Path

import click
import yaml

logger = logging.getLogger(__name__)

# Valid structure types
VALID_STRUCTURE_TYPES = {"onshore", "bottom_fixed", "semisubmersible", "spar", "fawt"}


@click.command()
@click.argument(
    "scenario_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.pass_context
def validate(ctx, scenario_file: Path):
    """Validate scenario configuration without running calculation.

    SCENARIO_FILE: Path to scenario.yaml file

    \b
    Examples:
        lca-toolkit validate scenarios/001-onshore-3mw-baseline/scenario.yaml
        lca-toolkit validate scenarios/002-fawt-10mw-cfrp/scenario.yaml --verbose
    """
    verbose = ctx.obj.get("verbose", False)
    errors = []
    warnings = []

    click.echo(f"Validating scenario: {scenario_file}")
    click.echo("")

    # Step 1: Load YAML
    try:
        with open(scenario_file, "r", encoding="utf-8") as f:
            scenario_data = yaml.safe_load(f)
        click.echo("✓ YAML syntax valid")
    except yaml.YAMLError as e:
        click.echo(f"✗ Invalid YAML syntax:", err=True)
        click.echo(f"  {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Failed to read file:", err=True)
        click.echo(f"  {str(e)}", err=True)
        sys.exit(1)

    if not scenario_data:
        click.echo("✗ Scenario file is empty", err=True)
        sys.exit(1)

    # Step 2: Check metadata
    click.echo("✓ File readable")
    click.echo("")
    click.echo("Checking metadata...")

    metadata = scenario_data.get("metadata", {})
    if not metadata:
        errors.append("Missing 'metadata' section")
    else:
        # Check metadata fields
        if not metadata.get("id"):
            errors.append("Missing metadata.id")
        if not metadata.get("name"):
            errors.append("Missing metadata.name")
        if not metadata.get("description"):
            warnings.append("Missing metadata.description (recommended)")

        if "id" in metadata:
            click.echo(f"  ID: {metadata['id']}")
        if "name" in metadata:
            click.echo(f"  Name: {metadata['name']}")

    # Step 3: Check structure configuration
    click.echo("")
    click.echo("Checking structure configuration...")

    structure = scenario_data.get("structure", {})
    if not structure:
        errors.append("Missing 'structure' section")
    else:
        # Check structure type
        structure_type = structure.get("type")
        if not structure_type:
            errors.append("Missing structure.type")
        elif structure_type not in VALID_STRUCTURE_TYPES:
            errors.append(
                f"Invalid structure.type '{structure_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_STRUCTURE_TYPES))}"
            )
        else:
            click.echo(f"  Type: {structure_type}")

        # Check rated power
        rated_power = structure.get("rated_power_mw")
        if rated_power is None:
            errors.append("Missing structure.rated_power_mw")
        elif not isinstance(rated_power, (int, float)) or rated_power <= 0:
            errors.append(f"Invalid structure.rated_power_mw: must be positive number, got {rated_power}")
        else:
            click.echo(f"  Rated Power: {rated_power} MW")

        # Check lifetime
        lifetime = structure.get("lifetime_years")
        if lifetime is None:
            errors.append("Missing structure.lifetime_years")
        elif not isinstance(lifetime, int) or lifetime <= 0:
            errors.append(f"Invalid structure.lifetime_years: must be positive integer, got {lifetime}")
        else:
            click.echo(f"  Lifetime: {lifetime} years")

        # Check capacity factor
        capacity_factor = structure.get("capacity_factor")
        if capacity_factor is None:
            errors.append("Missing structure.capacity_factor")
        elif not isinstance(capacity_factor, (int, float)) or not 0 <= capacity_factor <= 1:
            errors.append(f"Invalid structure.capacity_factor: must be 0-1, got {capacity_factor}")
        else:
            click.echo(f"  Capacity Factor: {capacity_factor:.2f}")

    # Step 4: Check materials (optional, but warn if missing)
    click.echo("")
    click.echo("Checking materials configuration...")

    materials = scenario_data.get("materials", {})
    if not materials:
        warnings.append("No materials section found (will use defaults from data/lci/components.csv)")
        click.echo("  No custom materials defined (using defaults)")
    else:
        click.echo(f"  {len(materials)} custom material assignments")

    # Step 5: Check transport (optional)
    click.echo("")
    click.echo("Checking transport configuration...")

    transport = scenario_data.get("transport", {})
    if not transport:
        warnings.append("No transport section found (may use defaults)")
        click.echo("  No custom transport defined (using defaults)")
    else:
        click.echo(f"  {len(transport)} transport stages defined")

    # Step 6: Check calculation options
    click.echo("")
    click.echo("Checking calculation options...")

    calculation = scenario_data.get("calculation", {})
    if calculation:
        weight_cascade = calculation.get("weight_cascade", True)
        click.echo(f"  Weight cascade: {weight_cascade}")

        phases = calculation.get("phases", [])
        if phases:
            click.echo(f"  Phases: {', '.join(phases)}")
    else:
        click.echo("  Using default calculation options")

    # Step 7: Check output configuration
    click.echo("")
    click.echo("Checking output configuration...")

    output = scenario_data.get("output", {})
    if output:
        results_dir = output.get("results_dir", "results")
        click.echo(f"  Results directory: {results_dir}")

        formats = output.get("formats", ["csv"])
        click.echo(f"  Output formats: {', '.join(formats)}")
    else:
        click.echo("  Using default output configuration")

    # Print summary
    click.echo("")
    click.echo("=" * 60)

    if errors:
        click.echo(f"✗ VALIDATION FAILED - {len(errors)} error(s) found:", err=True)
        click.echo("")
        for i, error in enumerate(errors, 1):
            click.echo(f"  {i}. {error}", err=True)
        click.echo("")

        if warnings:
            click.echo(f"⚠ {len(warnings)} warning(s):", err=True)
            for i, warning in enumerate(warnings, 1):
                click.echo(f"  {i}. {warning}", err=True)
            click.echo("")

        click.echo("=" * 60)
        sys.exit(1)

    elif warnings:
        click.echo(f"⚠ VALIDATION PASSED with {len(warnings)} warning(s):")
        click.echo("")
        for i, warning in enumerate(warnings, 1):
            click.echo(f"  {i}. {warning}")
        click.echo("")
        click.echo("=" * 60)
        click.echo("✓ Scenario configuration is valid (with warnings)")
        sys.exit(0)

    else:
        click.echo("✓ VALIDATION PASSED - No errors or warnings")
        click.echo("=" * 60)
        click.echo("✓ Scenario configuration is valid")
        sys.exit(0)


__all__ = ["validate"]
