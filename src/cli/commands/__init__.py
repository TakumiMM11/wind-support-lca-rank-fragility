"""CLI Commands.

This package contains individual command implementations:
- run: Execute single or batch scenarios
- compare: Batch scenario processing with comparison
- matrix: Cartesian product execution (structure × power × material model)
- validate: Validate scenario YAML
- plot: Generate visualizations (Phase 6)
"""

from src.cli.commands import run, validate, compare, matrix, plot

__all__ = ["run", "validate", "compare", "matrix", "plot"]
