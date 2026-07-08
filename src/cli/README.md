# CLI (Command-Line Interface) Layer

This module provides the command-line interface for the LCA Toolkit using Click framework.

## Purpose

The CLI layer provides:
- **User-Friendly Commands:** run, compare, matrix, plot, validate
- **Global Flags:** --verbose, --output
- **Batch Processing:** Glob pattern support for multiple scenarios
- **Error Handling:** Clear, actionable error messages
- **Progress Reporting:** Visual feedback for long operations

## Module Structure

```
src/cli/
├── main.py              # CLI entry point and global options
├── commands/
│   ├── __init__.py      # Command exports
│   ├── run.py           # Run command (single/batch scenarios)
│   ├── compare.py       # Compare command (multi-scenario analysis)
│   ├── matrix.py        # Matrix command (structure × power × material model)
│   ├── plot.py          # Plot command (visualization generation)
│   └── validate.py      # Validate command (YAML schema check)
└── __init__.py
```

## Commands

### `run` - Execute LCA Calculation

Run LCA calculation for one or more scenarios.

**Usage:**
```bash
lca-toolkit run SCENARIO_PATTERN [--verbose] [--output DIR]
```

**Arguments:**
- `SCENARIO_PATTERN`: Path or glob pattern to scenario.yaml file(s)

**Options:**
- `--verbose, -v`: Enable detailed logging (INFO level)
- `--output, -o`: Output directory (default: scenario's results/)

**Examples:**
```bash
# Single scenario
lca-toolkit run scenarios/001-onshore-3mw-baseline/scenario.yaml

# All scenarios (glob pattern)
lca-toolkit run "scenarios/*/scenario.yaml"

# Filtered scenarios
lca-toolkit run "scenarios/00[1-3]-*/scenario.yaml"

# With verbose logging
lca-toolkit run "scenarios/*/scenario.yaml" --verbose

# Custom output directory
lca-toolkit run scenario.yaml --output my_results/
```

**Output:**
- CSV file: `scenario_name/results/lca_results_YYYYMMDD_HHMMSS.csv`
- Progress messages for batch processing
- Summary: "X successful, Y failed" for batch operations

**Exit Codes:**
- `0`: All scenarios succeeded
- `1`: Single scenario failed
- `2`: Batch processing had failures (partial success)

### `compare` - Batch Scenario Comparison

Process multiple scenarios and generate comparison CSV.

**Usage:**
```bash
lca-toolkit compare SCENARIO_PATTERNS... [--output-file FILE]
```

**Arguments:**
- `SCENARIO_PATTERNS`: One or more paths or glob patterns

**Options:**
- `--output-file, -o`: Output CSV path (default: results/comparison_YYYYMMDD_HHMMSS.csv)

**Examples:**
```bash
# Compare all scenarios
lca-toolkit compare "scenarios/*/scenario.yaml"

# Compare specific scenarios
lca-toolkit compare scenarios/001-*/scenario.yaml scenarios/002-*/scenario.yaml

# Custom output file
lca-toolkit compare "scenarios/*/scenario.yaml" --output-file my_comparison.csv
```

**Output:**
- Comparison CSV with columns:
  - `scenario_id`, `scenario_name`, `scenario_dir`
  - `structure_type`, `rated_power_mw`, `lifetime_years`, `capacity_factor`
  - `l1_manufacturing_kgco2`, `l2_transport_kgco2`, `l3_o_and_m_kgco2`, `l4_eol_kgco2`
  - `total_gwp_kgco2`, `intensity_gco2_per_kwh`, `energy_generation_mwh`
  - `weight_cascade_iterations`, `weight_cascade_converged`

**Performance Optimization:**
- LCI data loaded once and shared across scenarios
- ~60% faster than running scenarios individually

### `matrix` - Cartesian Batch Calculation

Run one command for all combinations of structure type, rated power, and material model.

**Usage:**
```bash
lca-toolkit matrix [OPTIONS]
```

**Key Options:**
- `--structures`: Comma-separated structures (default: all 5)
- `--rated-powers`: Comma-separated MW values (default: `2,5,10,15`)
- `--material-models`: `gfrp,cfrp,rcfrp,rrcfrp` (default: all)
- `--lifetime-years`: Lifetime years (default: `25`)
- `--capacity-factor`: Fixed CF for all structures (optional)
- `--weight-cascade/--no-weight-cascade`: Enable/disable cascade (default: disabled)
- `--site-class`: Site condition class from assumptions (`baseline`, `high_resource`, `challenging`)
- `--assumption-point`: `min/base/max` parameter point from assumptions
- `--assumptions-file`: Assumption register JSON path (default: `data/model_assumptions.json`)
- `--output-file, -o`: Output CSV path (default: `results/latest/matrix_latest.csv`)
- `--archive-old/--no-archive-old`: Archive previous output before overwrite (default: on)

**Examples:**
```bash
# Full matrix (5 structures × 4 powers × 4 materials = 80 runs)
lca-toolkit matrix

# Custom subset
lca-toolkit matrix \
  --structures onshore,bottom_fixed,fawt \
  --rated-powers 5,10,15 \
  --material-models gfrp,cfrp \
  --output-file results/matrix_subset.csv

# Recommended "latest only" workflow
./scripts/update_latest_matrix.sh
```

### `plot` - Generate Visualizations

Create publication-quality plots from result CSV files.

**Usage:**
```bash
lca-toolkit plot PLOT_TYPE RESULT_FILES... [--output-dir DIR] [--top-n N]
```

**Arguments:**
- `PLOT_TYPE`: breakdown | comparison | component
- `RESULT_FILES`: One or more paths or glob patterns to CSV files

**Options:**
- `--output-dir, -o`: Output directory (default: results/plots/)
- `--top-n N`: Top N components to show (component plot only, default: 15)

**Plot Types:**

1. **breakdown** - Stacked bar chart by lifecycle phase
   ```bash
   lca-toolkit plot breakdown results/comparison.csv
   ```

2. **comparison** - Grouped bar chart comparing scenarios
   ```bash
   lca-toolkit plot comparison results/comparison_*.csv
   ```

3. **component** - Horizontal bar chart by component
   ```bash
   lca-toolkit plot component results/component_gwp.csv --top-n 10
   ```

**Output:**
- PNG file: `{scenario}_{plot_type}_YYYYMMDD_HHMMSS.png`
- 300 DPI resolution
- Embedded metadata

### `validate` - Check Scenario YAML

Validate scenario YAML schema without executing calculation.

**Usage:**
```bash
lca-toolkit validate SCENARIO_FILE
```

**Arguments:**
- `SCENARIO_FILE`: Path to scenario.yaml

**Examples:**
```bash
lca-toolkit validate scenarios/001-onshore-3mw-baseline/scenario.yaml
```

**Output:**
- Success: "✓ Scenario is valid"
- Failure: Detailed validation errors with field names

## Global Options

### `--verbose, -v`

Enable detailed logging (INFO level). Logs go to stderr, results to stdout.

**Example:**
```bash
lca-toolkit --verbose run scenario.yaml
```

**Log Output:**
```
2026-01-22 14:30:15 [INFO] lca.loaders: Loaded 50 materials, 120 components
2026-01-22 14:30:15 [INFO] lca.weight_cascade: Iteration 1: max change 0.015
2026-01-22 14:30:15 [INFO] lca.weight_cascade: Converged after 3 iterations
2026-01-22 14:30:16 [INFO] lca.gwp: Total GWP: 2,223,310 kg-CO2
```

### `--output, -o`

Specify output directory for results.

**Example:**
```bash
lca-toolkit --output custom_results/ run scenario.yaml
```

### `--version`

Display version information.

```bash
lca-toolkit --version
# Output: lca-toolkit, version 0.1.0
```

### `--help`

Show help for command or subcommand.

```bash
lca-toolkit --help              # Main help
lca-toolkit run --help          # Run command help
lca-toolkit compare --help      # Compare command help
lca-toolkit plot --help         # Plot command help
```

## Batch Processing

### Glob Pattern Support

All commands support glob patterns for batch operations:

**Wildcards:**
- `*`: Match any characters
- `?`: Match single character
- `[abc]`: Match one of a, b, c
- `[0-9]`: Match digits 0-9
- `**`: Match directories recursively (not needed for scenarios)

**Examples:**
```bash
# All scenarios
"scenarios/*/scenario.yaml"

# Onshore scenarios only
"scenarios/*-onshore-*/scenario.yaml"

# Scenarios 001-003
"scenarios/00[1-3]-*/scenario.yaml"

# Multiple patterns
scenarios/001-*/scenario.yaml scenarios/002-*/scenario.yaml
```

**Important:** Quote glob patterns to prevent shell expansion:
```bash
lca-toolkit run "scenarios/*/scenario.yaml"  # Correct
lca-toolkit run scenarios/*/scenario.yaml    # May fail (shell expands)
```

### Error Handling in Batch Mode

Batch processing continues on failure:

```bash
lca-toolkit run "scenarios/*/scenario.yaml"

# Output:
Processing scenario 1 of 5: 001-onshore-3mw-baseline
✓ Successfully processed 001-onshore-3mw-baseline

Processing scenario 2 of 5: 002-fawt-10mw-cfrp
✗ Error processing 002-fawt-10mw-cfrp: Missing material 'unknown'

Processing scenario 3 of 5: 003-floating-10mw
✓ Successfully processed 003-floating-10mw

...

Summary:
  Total scenarios: 5
  Successful: 4
  Failed: 1

Failed scenarios:
  - 002-fawt-10mw-cfrp: Missing material 'unknown'
```

**Exit code:** 2 (indicating partial failure)

## Progress Reporting

### Visual Separators

Batch operations use 60-character separators for clarity:

```
============================================================
Processing scenario 3 of 10: 003-semisubmersible-10mw
============================================================
```

### Progress Indicators

- Current/total: "Processing scenario 3 of 10"
- Scenario name: Clear identification
- Success/failure markers: ✓ / ✗

## Error Messages

### Clear Error Format

```
Error: Failed to load LCI data
  File not found: data/lci/materials.csv

Hint: Ensure CSV files exist in data/lci/ directory
```

### Actionable Hints

Error messages include suggestions:
- File paths for missing files
- Valid options for invalid choices
- Example commands for common tasks

### Validation Errors

```
Error: Invalid scenario YAML
  Field: rated_power_mw
  Issue: Must be between 0 and 20 MW, got 25
  Location: scenarios/test/scenario.yaml:6
```

## Exit Codes

| Code | Meaning | Example |
|------|---------|---------|
| 0 | Success | All operations completed successfully |
| 1 | Error | Single scenario failed, invalid arguments |
| 2 | Partial Success | Batch operation had failures but some succeeded |
| 3 | Configuration Error | Invalid YAML, missing files |

## Logging

### Log Levels

**WARNING (default):**
- Errors only
- Summary information
- Suitable for production use

**INFO (--verbose):**
- Detailed progress
- Data loading stats
- Calculation iterations
- Useful for debugging

### Log Format

```
YYYY-MM-DD HH:MM:SS [LEVEL] module: message
```

Example:
```
2026-01-22 14:30:15 [INFO] lca.loaders: Loaded 50 materials
```

### Log Destination

- **stderr**: All logging output
- **stdout**: Results and user output
- Allows redirection: `lca-toolkit run scenario.yaml > output.txt 2> errors.log`

## Performance

### Typical Execution Times

| Operation | Time |
|-----------|------|
| Single scenario | 2-5 seconds |
| Batch (10 scenarios) | 20-30 seconds |
| Compare (10 scenarios) | 15-25 seconds (faster, shared LCI load) |
| Plot generation | 1-2 seconds |

### Memory Usage

- Single scenario: ~50 MB
- Batch processing: ~100 MB (constant)
- Plot generation: +20 MB per plot

## Design Principles

### Principle 1: Simple Module Separation
- Clear command structure (run, compare, plot, validate)
- Each command in separate file
- No command interdependencies

### Principle 2: Data Transparency
- Verbose logging available
- Progress reporting for long operations
- Clear error messages with context

### Principle 3: Pragmatic Layering
- CLI layer doesn't contain business logic
- Orchestrates lci, lca, and viz modules
- Thin wrapper around core functionality

## Testing

### Integration Tests

```bash
pytest tests/integration/test_cli_run.py -v
```

### Manual Testing

```bash
# Test single scenario
lca-toolkit run scenarios/001-onshore-3mw-baseline/scenario.yaml

# Test batch processing
lca-toolkit run "scenarios/00[1-3]-*/scenario.yaml"

# Test error handling
lca-toolkit run nonexistent.yaml

# Test validation
lca-toolkit validate scenarios/001-onshore-3mw-baseline/scenario.yaml
```

## Extending the CLI

### Adding New Commands

1. Create new file: `src/cli/commands/my_command.py`
2. Define Click command:
   ```python
   @click.command()
   @click.argument('arg')
   @click.pass_context
   def my_command(ctx, arg):
       """Command description."""
       # Implementation
   ```
3. Register in `src/cli/main.py`:
   ```python
   from src.cli.commands import my_command
   cli.add_command(my_command.my_command)
   ```
4. Export in `src/cli/commands/__init__.py`

### Adding Global Options

Edit `src/cli/main.py` in the `@cli.group()` decorator:
```python
@click.option('--my-option', help='My option')
@click.pass_context
def cli(ctx, verbose, output, my_option):
    ctx.obj['my_option'] = my_option
```

## References

- Click documentation: https://click.palletsprojects.com/
- Python argparse: https://docs.python.org/3/library/argparse.html
- UNIX exit codes: https://tldp.org/LDP/abs/html/exitcodes.html
