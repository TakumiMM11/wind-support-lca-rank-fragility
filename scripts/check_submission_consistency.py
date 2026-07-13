#!/usr/bin/env python3
"""Check that archived outputs match the manuscript headline values."""

from __future__ import annotations

import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MATRIX = ROOT / "results" / "80_case_result_matrix.csv"
PAIRWISE = ROOT / "results" / "rank_fragility_pairwise.csv"
CONVERGENCE = ROOT / "results" / "mc_convergence_summary.csv"

EXPECTED_15MW_GFRP = {
    "onshore": {"intensity": 9.869547548286658, "cf": 0.30},
    "bottom_fixed": {"intensity": 9.223081985926331, "cf": 0.40},
    "fawt": {"intensity": 13.37252276671616, "cf": 0.42},
    "semisubmersible": {"intensity": 14.622867228926578, "cf": 0.42},
    "spar": {"intensity": 13.211077285874774, "cf": 0.42},
}

EXPECTED_BOTTOM_FIXED_ONSHORE = {
    "support_frequency": 0.6826,
    "reversal_frequency": 0.2516,
    "tie_frequency": 0.0658,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def assert_close(actual: float, expected: float, label: str, tol: float = 1e-6) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tol):
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def check_matrix() -> None:
    rows = read_csv(MATRIX)
    if len(rows) != 80:
        raise AssertionError(f"80-case matrix should contain 80 data rows, got {len(rows)}")

    lookup = {
        row["structure_type"]: row
        for row in rows
        if row["rated_power_mw"] == "15.0" and row["material_model"] == "gfrp"
    }
    missing = sorted(set(EXPECTED_15MW_GFRP) - set(lookup))
    if missing:
        raise AssertionError(f"Missing 15 MW GFRP structures: {', '.join(missing)}")

    for structure, expected in EXPECTED_15MW_GFRP.items():
        row = lookup[structure]
        assert_close(
            float(row["intensity_gco2_per_kwh"]),
            expected["intensity"],
            f"{structure} 15 MW GFRP intensity",
        )
        assert_close(
            float(row["capacity_factor"]),
            expected["cf"],
            f"{structure} 15 MW GFRP capacity factor",
        )


def check_pairwise() -> None:
    rows = read_csv(PAIRWISE)
    required = {"support_frequency", "reversal_frequency", "tie_frequency"}
    if not rows or not required.issubset(rows[0]):
        raise AssertionError("rank_fragility_pairwise.csv must expose support/reversal/tie columns")

    target = None
    for row in rows:
        support = float(row["support_frequency"])
        reversal = float(row["reversal_frequency"])
        tie = float(row["tie_frequency"])
        assert_close(support + reversal + tie, 1.0, f"{row['pair_label']} probabilities", tol=5e-4)
        if row["pair_member_a"] == "bottom_fixed" and row["pair_member_b"] == "onshore":
            target = row

    if target is None:
        raise AssertionError("Missing bottom_fixed vs onshore pairwise row")

    for key, expected in EXPECTED_BOTTOM_FIXED_ONSHORE.items():
        assert_close(float(target[key]), expected, f"bottom_fixed vs onshore {key}", tol=5e-4)


def check_convergence() -> None:
    rows = read_csv(CONVERGENCE)
    if not rows:
        raise AssertionError("mc_convergence_summary.csv is empty")
    required = {"n_samples", "mean_onshore", "mean_bottom_fixed", "support_frequency_bottom_fixed_vs_onshore"}
    if not required.issubset(rows[0]):
        raise AssertionError(
            "mc_convergence_summary.csv must expose support_frequency_bottom_fixed_vs_onshore"
        )
    final = rows[-1]
    if final["n_samples"] != "10000":
        raise AssertionError(f"Final convergence row should be n=10000, got {final['n_samples']}")
    assert_close(
        float(final["support_frequency_bottom_fixed_vs_onshore"]),
        EXPECTED_BOTTOM_FIXED_ONSHORE["support_frequency"],
        "convergence final support frequency",
        tol=5e-4,
    )


def main() -> None:
    check_matrix()
    check_pairwise()
    check_convergence()
    print("Submission consistency check passed.")
    print("15 MW GFRP matrix values, rank frequencies, and convergence labels match the manuscript.")


if __name__ == "__main__":
    main()
