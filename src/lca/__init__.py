"""LCA Calculation Layer.

This module implements weight cascade algorithms, GWP calculations,
and scenario execution logic.
"""

from src.lca.calculator import LCACalculator, LCAResult
from src.lca.gwp import (
    ComponentGWP,
    GWPResult,
    PhaseGWP,
    aggregate_gwp_by_phase,
    calculate_gwp,
    normalize_gwp,
)
from src.lca.weight_cascade import WeightCascadeResult, calculate_weight_cascade

__all__ = [
    # Calculator
    "LCACalculator",
    "LCAResult",
    # Weight Cascade
    "WeightCascadeResult",
    "calculate_weight_cascade",
    # GWP
    "ComponentGWP",
    "PhaseGWP",
    "GWPResult",
    "calculate_gwp",
    "aggregate_gwp_by_phase",
    "normalize_gwp",
]
