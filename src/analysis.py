"""Core calculations for the restored multi-support rank-fragility study.

The calculations intentionally stop at a cradle-to-gate material-production
proxy.  Physical-only masses never receive environmental coefficients, and
sample frequencies are conditional design-space diagnostics rather than
claims about the frequency of real projects.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm


CASE_ORDER = (
    "monopile_15mw",
    "volturnus_15mw",
    "windcrete_15mw",
    "activefloat_15mw",
    "tlp_15mw",
)
PRIMARY_CASE_ORDER = tuple(case_id for case_id in CASE_ORDER if case_id != "activefloat_15mw")
AUDIT_ONLY_CASES = ("activefloat_15mw",)
BOUNDARY_LAYERS = ("core_substructure", "station_keeping")


@dataclass(frozen=True)
class Inputs:
    components: pd.DataFrame
    physical: pd.DataFrame
    exclusions: pd.DataFrame
    legacy: pd.DataFrame
    sources: pd.DataFrame
    manifest: pd.DataFrame
    evidence_profile: pd.DataFrame
    missing_boundary_items: pd.DataFrame
    parameters: Mapping[str, object]
    robustness: Mapping[str, object]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def triangular_ppf(u: np.ndarray, lower: float, mode: float, upper: float) -> np.ndarray:
    if not (lower <= mode <= upper) or lower == upper:
        raise ValueError("triangular parameters must satisfy lower <= mode <= upper")
    fraction = (mode - lower) / (upper - lower)
    left = lower + np.sqrt(u * (upper - lower) * (mode - lower))
    right = upper - np.sqrt((1.0 - u) * (upper - lower) * (upper - mode))
    return np.where(u < fraction, left, right)


def triangular_draw(rng: np.random.Generator, block: Mapping[str, float], n: int) -> np.ndarray:
    return rng.triangular(float(block["min"]), float(block["mode"]), float(block["max"]), n)


def bounded_draw(
    rng: np.random.Generator,
    block: Mapping[str, float],
    n: int,
    distribution_shape: str,
) -> np.ndarray:
    """Draw from one of the declared, non-empirical stress-test shapes."""

    lower = float(block["min"])
    upper = float(block["max"])
    if lower == upper:
        return np.full(n, lower)
    if distribution_shape == "triangular":
        return triangular_draw(rng, block, n)
    if distribution_shape == "uniform":
        return rng.uniform(lower, upper, n)
    if distribution_shape == "discrete_endpoints":
        return np.where(rng.random(n) < 0.5, lower, upper)
    raise ValueError("unsupported conditional distribution shape: {}".format(distribution_shape))


def bounded_ppf(
    u: np.ndarray,
    block: Mapping[str, float],
    distribution_shape: str,
) -> np.ndarray:
    """Transform copula uniforms using one declared stress-test marginal."""

    lower = float(block["min"])
    upper = float(block["max"])
    if lower == upper:
        return np.full_like(u, lower, dtype=float)
    if distribution_shape == "triangular":
        return triangular_ppf(u, lower, float(block["mode"]), upper)
    if distribution_shape == "uniform":
        return lower + u * (upper - lower)
    if distribution_shape == "discrete_endpoints":
        return np.where(u < 0.5, lower, upper)
    raise ValueError("unsupported conditional distribution shape: {}".format(distribution_shape))


def _require_columns(frame: pd.DataFrame, name: str, required: Iterable[str]) -> None:
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError("{} is missing columns {}".format(name, sorted(missing)))


def load_inputs(input_dir: Path) -> Inputs:
    components = pd.read_csv(input_dir / "support_components.csv")
    physical = pd.read_csv(input_dir / "physical_mass_register.csv")
    exclusions = pd.read_csv(input_dir / "boundary_exclusions.csv")
    legacy = pd.read_csv(input_dir / "legacy_mapping_audit.csv")
    sources = pd.read_csv(input_dir / "source_register.csv")
    manifest = pd.read_csv(input_dir / "case_manifest.csv")
    evidence_profile = pd.read_csv(input_dir / "evidence_profile.csv")
    missing_boundary_items = pd.read_csv(input_dir / "missing_boundary_items.csv")
    parameters = json.loads((input_dir / "analysis_parameters.json").read_text(encoding="utf-8"))
    robustness = json.loads((input_dir / "robustness_scenarios.json").read_text(encoding="utf-8"))

    _require_columns(
        components,
        "support_components.csv",
        {
            "case_id", "design_label", "support_class", "rated_power_mw",
            "water_depth_m", "boundary_layer", "component_id", "component_name",
            "material_group", "mass_kg", "inventory_role", "evidence_status",
            "source_id", "source_locator", "derivation", "notes",
            "material_proxy_depth_status", "associated_engineering_model_depth_m",
        },
    )
    _require_columns(
        physical,
        "physical_mass_register.csv",
        {
            "case_id", "item_id", "item_name", "physical_mass_kg", "register_role",
            "material_proxy_treatment", "source_id", "source_locator", "rationale",
        },
    )
    _require_columns(
        legacy,
        "legacy_mapping_audit.csv",
        {
            "design_id", "mapping_case", "item_id", "item_name", "material_group",
            "burdened_mass_kg", "physical_only_mass_kg", "evidence_basis", "notes",
        },
    )
    _require_columns(
        manifest,
        "case_manifest.csv",
        {
            "case_id", "design_version", "analysis_tier", "headline_eligible",
            "point_estimate_status", "material_proxy_depth_status",
            "associated_engineering_model_depth_m", "principal_limitation",
        },
    )
    _require_columns(
        evidence_profile,
        "evidence_profile.csv",
        {
            "case_id", "analysis_tier_aux", "material_proxy_depth_status",
            "associated_engineering_model_depth_m", "source_directness_level",
            "source_directness_score", "material_identity_level",
            "material_identity_score", "boundary_completeness_level",
            "boundary_completeness_score", "version_consistency_level",
            "version_consistency_score", "coefficient_specificity_level",
            "coefficient_specificity_score", "blocking_issue_flag",
            "blocking_issue", "eligibility_rule_id", "eligibility_result",
            "headline_eligible", "source_ids", "notes",
        },
    )
    _require_columns(
        missing_boundary_items,
        "missing_boundary_items.csv",
        {
            "case_id", "missing_item_id", "missing_item_class", "boundary_layer",
            "reported_mass_kg", "material_identity_status", "reference_source_id",
            "source_status", "notes",
        },
    )

    if tuple(components["case_id"].drop_duplicates()) != CASE_ORDER:
        raise ValueError("support_components case order or membership differs from the frozen five cases")
    if set(components["boundary_layer"]) != set(BOUNDARY_LAYERS):
        raise ValueError("exactly the core_substructure and station_keeping layers are required")
    if components["component_id"].duplicated().any() or physical["item_id"].duplicated().any():
        raise ValueError("component and physical-register IDs must be unique")
    if (components["mass_kg"] <= 0).any() or (
        physical["physical_mass_kg"].dropna() <= 0
    ).any():
        raise ValueError("all asserted masses must be positive")
    if set(components["inventory_role"]) != {"burdened_material"}:
        raise ValueError("all component rows must be burdened material rows")
    if set(components["material_group"]) - set(parameters["material_gwp_kgco2_per_kg"]):
        raise ValueError("a component uses a material without a coefficient")
    if set(components["evidence_status"]) - set(parameters["evidence_mass_multiplier"]):
        raise ValueError("a component uses an unsupported evidence class")
    if set(components["source_id"]) - set(sources["source_id"]):
        raise ValueError("a component source_id is missing from source_register.csv")
    coefficient_source_ids = {
        block.get("source_id")
        for block in parameters["material_gwp_kgco2_per_kg"].values()
    }
    if None in coefficient_source_ids or coefficient_source_ids - set(sources["source_id"]):
        raise ValueError("every material coefficient must resolve to source_register.csv")
    if set(physical["material_proxy_treatment"]) & {"burdened_material"}:
        raise ValueError("physical-only rows must never be burdened")
    residual_placeholder = physical.set_index("item_id").loc["af_unmapped_residual"]
    if (
        pd.notna(residual_placeholder["physical_mass_kg"])
        or residual_placeholder["register_role"]
        != "audit_only_unit_dependent_placeholder"
        or residual_placeholder["material_proxy_treatment"]
        != "audit_only_unit_dependent_placeholder"
    ):
        raise ValueError("ActiveFloat residual must remain a mass-free audit placeholder")
    other_physical = physical[physical["item_id"] != "af_unmapped_residual"]
    if other_physical["physical_mass_kg"].isna().any():
        raise ValueError("only the ActiveFloat unit-dependent residual may have no mass")
    if set(parameters["deployment_capacity_factor"]) != set(CASE_ORDER):
        raise ValueError("capacity-factor blocks must contain the frozen five cases")
    if set(manifest["case_id"]) != set(CASE_ORDER) or manifest["case_id"].duplicated().any():
        raise ValueError("case_manifest.csv must contain each frozen case exactly once")
    if set(evidence_profile["case_id"]) != set(CASE_ORDER) or evidence_profile["case_id"].duplicated().any():
        raise ValueError("evidence_profile.csv must contain each frozen case exactly once")
    if set(missing_boundary_items["case_id"]) != set(CASE_ORDER):
        raise ValueError("missing_boundary_items.csv must link at least one item to every frozen case")
    if missing_boundary_items["reported_mass_kg"].notna().any():
        raise ValueError("missing boundary items must not invent reported masses")
    if set(missing_boundary_items["material_identity_status"]) != {"unknown"}:
        raise ValueError("missing anchor/scour identities must remain unknown")
    registered = set(sources["source_id"])
    profile_source_ids = {
        source_id
        for source_ids in evidence_profile["source_ids"]
        for source_id in str(source_ids).split("|")
    }
    if profile_source_ids - registered:
        raise ValueError("an evidence-profile source ID is missing from source_register.csv")
    if set(missing_boundary_items["reference_source_id"]) - registered:
        raise ValueError("a missing-boundary source ID is missing from source_register.csv")
    active_profile = evidence_profile.set_index("case_id").loc["activefloat_15mw"]
    if (
        str(active_profile["eligibility_result"]) != "non_headline_unresolved_unit"
        or str(active_profile["headline_eligible"]).lower() != "no"
    ):
        raise ValueError("ActiveFloat must remain non-headline while the rebar unit is unresolved")
    if (
        manifest.set_index("case_id").loc["activefloat_15mw", "point_estimate_status"]
        != "audit_only_unit_endpoints"
    ):
        raise ValueError("ActiveFloat point-estimate status must remain audit-only")
    active_components = components[components["case_id"] == "activefloat_15mw"]
    primary_components = components[components["case_id"] != "activefloat_15mw"]
    if not active_components["water_depth_m"].isna().all():
        raise ValueError("ActiveFloat material-proxy depth must remain unspecified")
    if primary_components["water_depth_m"].isna().any() or (
        primary_components["water_depth_m"] <= 0
    ).any():
        raise ValueError("primary comparison cases require positive source depths")
    if set(active_components["material_proxy_depth_status"]) != {"not_specified"}:
        raise ValueError("ActiveFloat material-proxy depth status must be not_specified")
    if not active_components["associated_engineering_model_depth_m"].eq(200).all():
        raise ValueError("ActiveFloat associated engineering model depth must be 200 m")
    active_manifest = manifest.set_index("case_id").loc["activefloat_15mw"]
    active_evidence = evidence_profile.set_index("case_id").loc["activefloat_15mw"]
    for register_name, row in (
        ("case manifest", active_manifest),
        ("evidence profile", active_evidence),
    ):
        if (
            row["material_proxy_depth_status"] != "not_specified"
            or float(row["associated_engineering_model_depth_m"]) != 200.0
        ):
            raise ValueError(
                "ActiveFloat {} must separate unspecified proxy depth from the 200 m associated model".format(
                    register_name
                )
            )
    if (
        manifest.set_index("case_id").loc["tlp_15mw", "point_estimate_status"]
        != "conditional_product_proxy"
        or evidence_profile.set_index("case_id").loc["tlp_15mw", "eligibility_result"]
        != "conditional_product_proxy"
    ):
        raise ValueError("TLP status must be conditional_product_proxy")
    return Inputs(
        components,
        physical,
        exclusions,
        legacy,
        sources,
        manifest,
        evidence_profile,
        missing_boundary_items,
        parameters,
        robustness,
    )


def denominator_kwh(power_mw: float, lifetime_years: float, capacity_factor: float) -> float:
    return power_mw * 1000.0 * 8760.0 * lifetime_years * capacity_factor


def central_component_results(
    inputs: Inputs,
    *,
    include_audit_only: bool = False,
) -> pd.DataFrame:
    coefficients = {
        key: float(value["central"])
        for key, value in inputs.parameters["material_gwp_kgco2_per_kg"].items()
    }
    result = inputs.components.copy()
    result["material_gwp_kgco2_per_kg"] = result["material_group"].map(coefficients)
    result["material_production_gwp_kgco2"] = (
        result["mass_kg"] * result["material_gwp_kgco2_per_kg"]
    )
    totals = result.groupby("case_id")["material_production_gwp_kgco2"].transform("sum")
    result["share_of_case_proxy"] = result["material_production_gwp_kgco2"] / totals
    if not include_audit_only:
        result = result[~result["case_id"].isin(AUDIT_ONLY_CASES)].copy()
    return result


def central_case_results(inputs: Inputs) -> pd.DataFrame:
    contributions = central_component_results(inputs, include_audit_only=True)
    metadata = (
        inputs.components.groupby("case_id", sort=False)
        .agg(
            design_label=("design_label", "first"),
            support_class=("support_class", "first"),
            rated_power_mw=("rated_power_mw", "first"),
            water_depth_m=("water_depth_m", "first"),
        )
    )
    core = (
        contributions[contributions["boundary_layer"] == "core_substructure"]
        .groupby("case_id")["material_production_gwp_kgco2"]
        .sum()
    )
    station = (
        contributions[contributions["boundary_layer"] == "station_keeping"]
        .groupby("case_id")["material_production_gwp_kgco2"]
        .sum()
        .reindex(metadata.index, fill_value=0.0)
    )
    mass_core = (
        contributions[contributions["boundary_layer"] == "core_substructure"]
        .groupby("case_id")["mass_kg"]
        .sum()
    )
    mass_station = (
        contributions[contributions["boundary_layer"] == "station_keeping"]
        .groupby("case_id")["mass_kg"]
        .sum()
        .reindex(metadata.index, fill_value=0.0)
    )
    result = metadata.copy()
    result["core_burdened_mass_kg"] = mass_core
    result["stationkeeping_burdened_mass_kg"] = mass_station
    result["core_proxy_gwp_kgco2"] = core
    result["stationkeeping_proxy_gwp_kgco2"] = station
    result["core_plus_stationkeeping_proxy_gwp_kgco2"] = core + station
    equal_cf = float(inputs.parameters["equal_yield_capacity_factor"])
    life = float(inputs.parameters["lifetime_years"])
    result["equal_yield_capacity_factor"] = equal_cf
    result["equal_yield_lifetime_kwh"] = [
        denominator_kwh(power, life, equal_cf) for power in result["rated_power_mw"]
    ]
    result["core_intensity_gco2_per_kwh"] = (
        result["core_proxy_gwp_kgco2"] * 1000.0 / result["equal_yield_lifetime_kwh"]
    )
    result["core_plus_stationkeeping_intensity_gco2_per_kwh"] = (
        result["core_plus_stationkeeping_proxy_gwp_kgco2"]
        * 1000.0
        / result["equal_yield_lifetime_kwh"]
    )
    result = result.reset_index().merge(inputs.manifest, on="case_id", how="left", validate="one_to_one")
    result["result_namespace"] = np.where(
        result["case_id"].isin(AUDIT_ONLY_CASES),
        "audit_only_unit_endpoints",
        "primary_conditional",
    )
    audit_mask = result["case_id"].isin(AUDIT_ONLY_CASES)
    no_point_estimate_columns = (
        "water_depth_m",
        "core_burdened_mass_kg",
        "stationkeeping_burdened_mass_kg",
        "core_proxy_gwp_kgco2",
        "stationkeeping_proxy_gwp_kgco2",
        "core_plus_stationkeeping_proxy_gwp_kgco2",
        "equal_yield_capacity_factor",
        "equal_yield_lifetime_kwh",
        "core_intensity_gco2_per_kwh",
        "core_plus_stationkeeping_intensity_gco2_per_kwh",
    )
    result.loc[audit_mask, list(no_point_estimate_columns)] = np.nan
    result["central_rank_core_equal_yield"] = (
        result["core_proxy_gwp_kgco2"].rank(method="min").astype("Int64")
    )
    result["central_rank_equal_yield"] = (
        result["core_plus_stationkeeping_proxy_gwp_kgco2"]
        .rank(method="min")
        .astype("Int64")
    )
    return result


def legacy_correction_results(inputs: Inputs) -> pd.DataFrame:
    coefficients = {
        key: float(value["central"])
        for key, value in inputs.parameters["material_gwp_kgco2_per_kg"].items()
    }
    frame = inputs.legacy.copy()
    frame["coefficient"] = frame["material_group"].map(coefficients).fillna(0.0)
    frame["proxy_gwp_kgco2"] = frame["burdened_mass_kg"] * frame["coefficient"]
    summary = (
        frame.groupby(["design_id", "mapping_case"], sort=False)
        .agg(
            burdened_mass_kg=("burdened_mass_kg", "sum"),
            physical_only_mass_kg=("physical_only_mass_kg", "sum"),
            proxy_gwp_kgco2=("proxy_gwp_kgco2", "sum"),
        )
        .reset_index()
    )
    pivot = summary.pivot(index="design_id", columns="mapping_case", values="proxy_gwp_kgco2")
    summary = summary.merge(
        pd.DataFrame(
            {
                "design_id": pivot.index,
                "correction_delta_gwp_kgco2": (
                    pivot["source_corrected"] - pivot["legacy_mapping"]
                ).values,
                "correction_fraction": (
                    pivot["source_corrected"] / pivot["legacy_mapping"] - 1.0
                ).values,
            }
        ),
        on="design_id",
        how="left",
    )
    return summary


def _correlated_capacity_factors(
    rng: np.random.Generator,
    parameters: Mapping[str, object],
    n: int,
    distribution_shape: str = "triangular",
    rho_override: float | None = None,
) -> Dict[str, np.ndarray]:
    rho = (
        float(parameters["capacity_factor_gaussian_copula_rho"])
        if rho_override is None
        else float(rho_override)
    )
    if not 0.0 <= rho < 1.0:
        raise ValueError("capacity-factor copula rho must be in [0, 1)")
    size = len(CASE_ORDER)
    correlation = np.full((size, size), rho)
    np.fill_diagonal(correlation, 1.0)
    normal_draws = rng.multivariate_normal(np.zeros(size), correlation, size=n)
    uniforms = norm.cdf(normal_draws)
    result = {}
    blocks = parameters["deployment_capacity_factor"]
    for column, case_id in enumerate(CASE_ORDER):
        block = blocks[case_id]
        result[case_id] = bounded_ppf(uniforms[:, column], block, distribution_shape)
    return result


def conditional_samples(
    inputs: Inputs,
    *,
    n: int,
    seed: int,
    distribution_shape: str = "triangular",
    windcrete_reinforcement_upper_fraction: float | None = None,
    capacity_factor_copula_rho: float | None = None,
) -> pd.DataFrame:
    """Generate conditional design-space samples under explicit audit choices."""

    p = inputs.parameters
    rng = np.random.default_rng(int(seed))

    material_draws = {
        material: bounded_draw(rng, block, n, distribution_shape)
        for material, block in p["material_gwp_kgco2_per_kg"].items()
    }
    cf_draws = _correlated_capacity_factors(
        rng,
        p,
        n,
        distribution_shape=distribution_shape,
        rho_override=capacity_factor_copula_rho,
    )
    mass_draws: Dict[Tuple[str, str], np.ndarray] = {}
    for case_id in CASE_ORDER:
        for evidence, block in p["evidence_mass_multiplier"].items():
            mass_draws[(case_id, evidence)] = bounded_draw(
                rng, block, n, distribution_shape
            )

    equal_cf = float(p["equal_yield_capacity_factor"])
    power = float(p["rated_power_mw"])
    life = float(p["lifetime_years"])
    equal_denom = denominator_kwh(power, life, equal_cf)
    activefloat_density = bounded_draw(
        rng, p["activefloat_concrete_density_kg_per_m3"], n, distribution_shape
    )
    reinforcement_block = dict(p["windcrete_omitted_reinforcement_ratio"])
    if windcrete_reinforcement_upper_fraction is not None:
        upper = float(windcrete_reinforcement_upper_fraction)
        if not float(reinforcement_block["min"]) <= upper <= float(reinforcement_block["max"]):
            raise ValueError("reinforcement upper fraction is outside the declared package range")
        reinforcement_block["max"] = upper
        reinforcement_block["mode"] = min(float(reinforcement_block["mode"]), upper)
    reinforcement_ratio = bounded_draw(rng, reinforcement_block, n, distribution_shape)

    output: Dict[str, np.ndarray] = {"sample_id": np.arange(n, dtype=int)}
    for material, values in material_draws.items():
        output["coef_{}".format(material)] = values
    output["windcrete_omitted_reinforcement_ratio"] = reinforcement_ratio
    output["activefloat_concrete_density_kg_per_m3"] = activefloat_density

    for case_id in CASE_ORDER:
        rows = inputs.components[inputs.components["case_id"] == case_id]
        burden_core = np.zeros(n)
        burden_station = np.zeros(n)
        for row in rows.itertuples(index=False):
            mass = float(row.mass_kg)
            if row.component_id == "af_concrete":
                mass_values = mass * activefloat_density / 2400.0
            else:
                mass_values = mass
            contribution = (
                mass_values
                * mass_draws[(case_id, row.evidence_status)]
                * material_draws[row.material_group]
            )
            if row.boundary_layer == "core_substructure":
                burden_core = burden_core + contribution
            else:
                burden_station = burden_station + contribution
        if case_id == "windcrete_15mw":
            concrete_mass = float(rows.loc[rows["component_id"] == "wc_concrete", "mass_kg"].iloc[0])
            burden_core = burden_core + concrete_mass * reinforcement_ratio * material_draws["steel"]
        burden = burden_core + burden_station
        output["{}_core_proxy_gwp_kgco2".format(case_id)] = burden_core
        output["{}_proxy_gwp_kgco2".format(case_id)] = burden
        output["{}_core_equal_yield_gco2_per_kwh".format(case_id)] = burden_core * 1000.0 / equal_denom
        output["{}_equal_yield_gco2_per_kwh".format(case_id)] = burden * 1000.0 / equal_denom
        output["{}_capacity_factor".format(case_id)] = cf_draws[case_id]
        deployment_denom = power * 1000.0 * 8760.0 * life * cf_draws[case_id]
        output["{}_deployment_gco2_per_kwh".format(case_id)] = burden * 1000.0 / deployment_denom
    return pd.DataFrame(output)


def monte_carlo_samples(inputs: Inputs) -> pd.DataFrame:
    """Generate primary samples while preserving the frozen non-ActiveFloat stream."""

    p = inputs.parameters
    samples = conditional_samples(
        inputs,
        n=int(p["monte_carlo"]["n_samples"]),
        seed=int(p["monte_carlo"]["seed"]),
        distribution_shape="triangular",
        windcrete_reinforcement_upper_fraction=None,
        capacity_factor_copula_rho=None,
    )
    audit_columns = [
        column
        for column in samples.columns
        if column.startswith("activefloat_15mw_")
        or column == "activefloat_concrete_density_kg_per_m3"
    ]
    return samples.drop(columns=audit_columns)


def _pairwise_table(samples: pd.DataFrame, suffix: str, tie_threshold: float) -> pd.DataFrame:
    rows = []
    for case_a, case_b in combinations(PRIMARY_CASE_ORDER, 2):
        a = samples["{}_{}".format(case_a, suffix)].to_numpy()
        b = samples["{}_{}".format(case_b, suffix)].to_numpy()
        relative_gap = np.abs(a - b) / ((np.abs(a) + np.abs(b)) / 2.0)
        tie = relative_gap <= tie_threshold
        a_lower = (a < b) & ~tie
        b_lower = (b < a) & ~tie
        rows.append(
            {
                "estimand": suffix,
                "case_a": case_a,
                "case_b": case_b,
                "sample_fraction_a_lower": float(a_lower.mean()),
                "sample_fraction_b_lower": float(b_lower.mean()),
                "sample_fraction_tie": float(tie.mean()),
                "median_gap_a_minus_b": float(np.median(a - b)),
                "p05_gap_a_minus_b": float(np.quantile(a - b, 0.05)),
                "p95_gap_a_minus_b": float(np.quantile(a - b, 0.95)),
            }
        )
    return pd.DataFrame(rows)


def pairwise_rank_results(inputs: Inputs, samples: pd.DataFrame) -> pd.DataFrame:
    tie_threshold = float(inputs.parameters["monte_carlo"]["tie_threshold"])
    result = pd.concat(
        [
            _pairwise_table(samples, "core_equal_yield_gco2_per_kwh", tie_threshold),
            _pairwise_table(samples, "equal_yield_gco2_per_kwh", tie_threshold),
            _pairwise_table(samples, "deployment_gco2_per_kwh", tie_threshold),
        ],
        ignore_index=True,
    )
    eligible = inputs.manifest.set_index("case_id")["headline_eligible"].astype(str).str.lower().eq("yes")
    result["headline_comparison"] = [
        bool(eligible.loc[a] and eligible.loc[b])
        for a, b in zip(result["case_a"], result["case_b"])
    ]
    result["comparison_scope"] = np.where(
        result["headline_comparison"], "headline_conditional", "extended_evidence_limited"
    )
    return result


def boundary_layer_rank_shifts(inputs: Inputs, samples: pd.DataFrame) -> pd.DataFrame:
    """Classify how adding station keeping changes each sampled pairwise order."""

    tie_threshold = float(inputs.parameters["monte_carlo"]["tie_threshold"])
    eligible = (
        inputs.manifest.set_index("case_id")["headline_eligible"]
        .astype(str)
        .str.lower()
        .eq("yes")
    )
    rows = []
    for case_a, case_b in combinations(PRIMARY_CASE_ORDER, 2):
        core_a = samples[f"{case_a}_core_equal_yield_gco2_per_kwh"].to_numpy()
        core_b = samples[f"{case_b}_core_equal_yield_gco2_per_kwh"].to_numpy()
        full_a = samples[f"{case_a}_equal_yield_gco2_per_kwh"].to_numpy()
        full_b = samples[f"{case_b}_equal_yield_gco2_per_kwh"].to_numpy()

        core_gap = core_a - core_b
        full_gap = full_a - full_b
        core_tie = np.abs(core_gap) / ((np.abs(core_a) + np.abs(core_b)) / 2.0) <= tie_threshold
        full_tie = np.abs(full_gap) / ((np.abs(full_a) + np.abs(full_b)) / 2.0) <= tie_threshold
        strict = ~core_tie & ~full_tie
        preserved = strict & (np.sign(core_gap) == np.sign(full_gap))
        reversed_order = strict & (np.sign(core_gap) != np.sign(full_gap))
        tie_transition = core_tie | full_tie
        rows.append(
            {
                "case_a": case_a,
                "case_b": case_b,
                "sample_fraction_strict_order_preserved": float(preserved.mean()),
                "sample_fraction_strict_order_reversed": float(reversed_order.mean()),
                "sample_fraction_with_tie_in_either_layer": float(tie_transition.mean()),
                "sample_fraction_core_tie": float(core_tie.mean()),
                "sample_fraction_full_tie": float(full_tie.mean()),
                "headline_comparison": bool(eligible.loc[case_a] and eligible.loc[case_b]),
            }
        )
    return pd.DataFrame(rows)


def rank_distribution(samples: pd.DataFrame, suffix: str) -> pd.DataFrame:
    matrix = np.column_stack(
        [samples["{}_{}".format(case_id, suffix)].to_numpy() for case_id in PRIMARY_CASE_ORDER]
    )
    order = np.argsort(matrix, axis=1)
    ranks = np.empty_like(order)
    ranks[np.arange(len(order))[:, None], order] = np.arange(
        1, len(PRIMARY_CASE_ORDER) + 1
    )
    rows = []
    for index, case_id in enumerate(PRIMARY_CASE_ORDER):
        row = {"estimand": suffix, "case_id": case_id}
        for rank in range(1, len(PRIMARY_CASE_ORDER) + 1):
            row["sample_fraction_exact_rank_{}".format(rank)] = float(
                (ranks[:, index] == rank).mean()
            )
        row["mean_rank"] = float(ranks[:, index].mean())
        rows.append(row)
    return pd.DataFrame(rows)


def sample_summary(samples: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for case_id in PRIMARY_CASE_ORDER:
        for estimand in (
            "core_proxy_gwp_kgco2",
            "proxy_gwp_kgco2",
            "core_equal_yield_gco2_per_kwh",
            "equal_yield_gco2_per_kwh",
            "deployment_gco2_per_kwh",
        ):
            values = samples["{}_{}".format(case_id, estimand)].to_numpy()
            rows.append(
                {
                    "case_id": case_id,
                    "estimand": estimand,
                    "mean": float(np.mean(values)),
                    "median": float(np.median(values)),
                    "p05": float(np.quantile(values, 0.05)),
                    "p95": float(np.quantile(values, 0.95)),
                    "minimum": float(np.min(values)),
                    "maximum": float(np.max(values)),
                }
            )
    return pd.DataFrame(rows)


def activefloat_rebar_unit_endpoints(inputs: Inputs) -> pd.DataFrame:
    """Return the two exclusive readings of the reported ActiveFloat rebar entry.

    The source table reports the number 2550 under a kg header.  The package's
    existing inventory treats it as tonnes after a scale cross-check.  Neither
    endpoint is promoted to a headline or central estimate here.
    """

    rows = inputs.components[inputs.components["case_id"] == "activefloat_15mw"]
    rebar = rows.loc[rows["component_id"] == "af_rebar"].iloc[0]
    concrete_mass = float(rows.loc[rows["component_id"] == "af_concrete", "mass_kg"].iloc[0])
    physical_register = inputs.physical.set_index("item_id")
    platform_total_mass = float(
        physical_register.loc["af_platform_total_crosscheck", "physical_mass_kg"]
    )
    platform_total_source_id = str(
        physical_register.loc["af_platform_total_crosscheck", "source_id"]
    )
    coefficients = {
        material: float(block["central"])
        for material, block in inputs.parameters["material_gwp_kgco2_per_kg"].items()
    }
    core_without_rebar = 0.0
    station = 0.0
    for component in rows.itertuples(index=False):
        if component.component_id == "af_rebar":
            continue
        burden = float(component.mass_kg) * coefficients[component.material_group]
        if component.boundary_layer == "core_substructure":
            core_without_rebar += burden
        else:
            station += burden
    denominator = denominator_kwh(
        float(inputs.parameters["rated_power_mw"]),
        float(inputs.parameters["lifetime_years"]),
        float(inputs.parameters["equal_yield_capacity_factor"]),
    )
    scenarios = (
        (
            "reported_header_kg_literal",
            "kg",
            2550.0,
            False,
            "Literal reading of 2550 under the source table's kg header",
        ),
        (
            "reported_value_interpreted_as_tonnes",
            "tonne",
            2550.0 * 1000.0,
            True,
            "Legacy package path interpreted the value as tonnes after a platform-scale cross-check; this flag records provenance and does not select a central endpoint",
        ),
    )
    output = []
    for scenario_id, interpreted_unit, rebar_mass, legacy_tonnes_path, provenance in scenarios:
        residual_mass = platform_total_mass - concrete_mass - rebar_mass
        if residual_mass <= 0:
            raise ValueError("ActiveFloat physical residual endpoint must be positive")
        core_burden = core_without_rebar + rebar_mass * coefficients["steel"]
        full_burden = core_burden + station
        output.append(
            {
                "unit_scenario_id": scenario_id,
                "reported_entry_value": 2550.0,
                "reported_header_unit": "kg",
                "interpreted_unit": interpreted_unit,
                "interpreted_rebar_mass_kg": rebar_mass,
                "mass_ratio_to_literal_kg_reading": rebar_mass / 2550.0,
                "source_platform_total_physical_mass_kg": platform_total_mass,
                "mapped_concrete_physical_mass_kg": concrete_mass,
                "physical_residual_endpoint_kg": residual_mass,
                "physical_residual_endpoint_t": residual_mass / 1000.0,
                "physical_total_source_id": platform_total_source_id,
                "physical_residual_derivation": "source platform total minus mapped concrete mass minus scenario-specific interpreted rebar mass",
                "physical_residual_semantics": "physical_only_unit_dependent_endpoint_no_material_identity",
                "source_id": str(rebar["source_id"]),
                "source_locator": str(rebar["source_locator"]),
                "legacy_package_assumed_tonnes_path": legacy_tonnes_path,
                "provenance_note": provenance,
                "fixed_factor_basis": "package reference material factors; all other ActiveFloat inventory rows fixed",
                "core_proxy_gwp_kgco2_endpoint": core_burden,
                "core_plus_stationkeeping_proxy_gwp_kgco2_endpoint": full_burden,
                "core_intensity_gco2_per_kwh_endpoint": core_burden * 1000.0 / denominator,
                "core_plus_stationkeeping_intensity_gco2_per_kwh_endpoint": full_burden
                * 1000.0
                / denominator,
                "headline_eligible": False,
                "no_central_claim": True,
                "endpoint_semantics": "exclusive_unit_audit_endpoint",
            }
        )
    return pd.DataFrame(output)


def _relative_tie(a: np.ndarray, b: np.ndarray, tie_threshold: float) -> np.ndarray:
    scale = (np.abs(a) + np.abs(b)) / 2.0
    return np.divide(
        np.abs(a - b),
        scale,
        out=np.zeros_like(scale, dtype=float),
        where=scale != 0.0,
    ) <= tie_threshold


def _aggregate_replicate_fractions(
    frame: pd.DataFrame,
    group_columns: Sequence[str],
    fraction_columns: Sequence[str],
    replicate_seeds: Sequence[int],
    n_samples_per_replicate: int,
) -> pd.DataFrame:
    rows = []
    for group_key, group in frame.groupby(list(group_columns), sort=False, dropna=False):
        key_values = group_key if isinstance(group_key, tuple) else (group_key,)
        row = dict(zip(group_columns, key_values))
        for column in fraction_columns:
            values = group[column].to_numpy(dtype=float)
            row[column] = float(values.mean())
            row["replicate_sd_{}".format(column)] = float(values.std(ddof=0))
            row["replicate_min_{}".format(column)] = float(values.min())
            row["replicate_max_{}".format(column)] = float(values.max())
        row["n_replicates"] = len(replicate_seeds)
        row["n_samples_per_replicate"] = int(n_samples_per_replicate)
        row["n_samples_total"] = int(n_samples_per_replicate) * len(replicate_seeds)
        row["replicate_seeds"] = "|".join(str(seed) for seed in replicate_seeds)
        row["interpretation"] = "conditional_design_space_sample_fraction"
        row["no_central_claim"] = True
        rows.append(row)
    return pd.DataFrame(rows)


def robustness_audit_results(
    inputs: Inputs,
    *,
    n_samples_per_replicate: int | None = None,
    replicate_seeds: Sequence[int] | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate rank diagnostics across declared marginal, range, and tie choices."""

    config = inputs.robustness
    n = (
        int(config["n_samples_per_replicate"])
        if n_samples_per_replicate is None
        else int(n_samples_per_replicate)
    )
    seeds = tuple(
        int(seed)
        for seed in (
            config["replicate_seeds"] if replicate_seeds is None else replicate_seeds
        )
    )
    if n <= 0 or not seeds:
        raise ValueError("robustness audit requires positive samples and at least one seed")
    estimands = (
        "core_equal_yield_gco2_per_kwh",
        "equal_yield_gco2_per_kwh",
        "deployment_gco2_per_kwh",
    )
    pair_replicates = []
    order_replicates = []
    distribution_shapes = tuple(config["distribution_shapes"])
    reinforcement_uppers = tuple(
        float(value) for value in config["windcrete_reinforcement_upper_fractions"]
    )
    rhos = tuple(float(value) for value in config["capacity_factor_gaussian_copula_rhos"])
    tie_thresholds = tuple(float(value) for value in config["tie_thresholds"])
    target_pairs = tuple(tuple(item) for item in config["target_pairs"])
    reported_order = tuple(config["ab_reported_order"])

    for distribution_shape in distribution_shapes:
        for reinforcement_upper in reinforcement_uppers:
            for rho in rhos:
                scenario_id = "{}__rebar_{:.3f}__rho_{:.1f}".format(
                    distribution_shape, reinforcement_upper, rho
                )
                for replicate_seed in seeds:
                    samples = conditional_samples(
                        inputs,
                        n=n,
                        seed=replicate_seed,
                        distribution_shape=distribution_shape,
                        windcrete_reinforcement_upper_fraction=reinforcement_upper,
                        capacity_factor_copula_rho=rho,
                    )
                    for tie_threshold in tie_thresholds:
                        for case_a, case_b, comparison_group in target_pairs:
                            for estimand in estimands:
                                a = samples["{}_{}".format(case_a, estimand)].to_numpy()
                                b = samples["{}_{}".format(case_b, estimand)].to_numpy()
                                tie = _relative_tie(a, b, tie_threshold)
                                a_lower = (a < b) & ~tie
                                b_lower = (b < a) & ~tie
                                pair_replicates.append(
                                    {
                                        "scenario_id": scenario_id,
                                        "distribution_shape": distribution_shape,
                                        "windcrete_reinforcement_upper_fraction": reinforcement_upper,
                                        "capacity_factor_copula_rho": rho,
                                        "tie_threshold": tie_threshold,
                                        "comparison_group": comparison_group,
                                        "case_a": case_a,
                                        "case_b": case_b,
                                        "estimand": estimand,
                                        "replicate_seed": replicate_seed,
                                        "sample_fraction_a_lower": float(a_lower.mean()),
                                        "sample_fraction_b_lower": float(b_lower.mean()),
                                        "sample_fraction_tie": float(tie.mean()),
                                    }
                                )
                        for estimand in estimands:
                            ordered_values = [
                                samples["{}_{}".format(case_id, estimand)].to_numpy()
                                for case_id in reported_order
                            ]
                            ties = np.zeros(n, dtype=bool)
                            for first, second in combinations(ordered_values, 2):
                                ties |= _relative_tie(first, second, tie_threshold)
                            strict_reported = (
                                (ordered_values[0] < ordered_values[1])
                                & (ordered_values[1] < ordered_values[2])
                                & ~ties
                            )
                            other_strict = ~ties & ~strict_reported
                            order_replicates.append(
                                {
                                    "scenario_id": scenario_id,
                                    "distribution_shape": distribution_shape,
                                    "windcrete_reinforcement_upper_fraction": reinforcement_upper,
                                    "capacity_factor_copula_rho": rho,
                                    "tie_threshold": tie_threshold,
                                    "reported_order": "<".join(reported_order),
                                    "estimand": estimand,
                                    "replicate_seed": replicate_seed,
                                    "sample_fraction_strict_reported_order": float(
                                        strict_reported.mean()
                                    ),
                                    "sample_fraction_other_strict_order": float(other_strict.mean()),
                                    "sample_fraction_with_any_tie": float(ties.mean()),
                                }
                            )

    pair_group_columns = (
        "scenario_id",
        "distribution_shape",
        "windcrete_reinforcement_upper_fraction",
        "capacity_factor_copula_rho",
        "tie_threshold",
        "comparison_group",
        "case_a",
        "case_b",
        "estimand",
    )
    pair_fraction_columns = (
        "sample_fraction_a_lower",
        "sample_fraction_b_lower",
        "sample_fraction_tie",
    )
    order_group_columns = (
        "scenario_id",
        "distribution_shape",
        "windcrete_reinforcement_upper_fraction",
        "capacity_factor_copula_rho",
        "tie_threshold",
        "reported_order",
        "estimand",
    )
    order_fraction_columns = (
        "sample_fraction_strict_reported_order",
        "sample_fraction_other_strict_order",
        "sample_fraction_with_any_tie",
    )
    pairwise = _aggregate_replicate_fractions(
        pd.DataFrame(pair_replicates),
        pair_group_columns,
        pair_fraction_columns,
        seeds,
        n,
    )
    ordering = _aggregate_replicate_fractions(
        pd.DataFrame(order_replicates),
        order_group_columns,
        order_fraction_columns,
        seeds,
        n,
    )
    return pairwise, ordering


def missing_burden_parity_thresholds(inputs: Inputs, reference: pd.DataFrame) -> pd.DataFrame:
    """Link unreported anchor/scour items to material-equivalent parity gaps."""

    burdens = reference.set_index("case_id")["core_plus_stationkeeping_proxy_gwp_kgco2"]
    steel_factor = float(inputs.parameters["material_gwp_kgco2_per_kg"]["steel"]["central"])
    concrete_factor = float(
        inputs.parameters["material_gwp_kgco2_per_kg"]["concrete"]["central"]
    )
    rows = []
    for item in inputs.missing_boundary_items.itertuples(index=False):
        if item.case_id in AUDIT_ONLY_CASES:
            continue
        case_burden = float(burdens.loc[item.case_id])
        higher_cases = burdens[burdens > case_burden].sort_values()
        if higher_cases.empty:
            rows.append(
                {
                    "case_id": item.case_id,
                    "missing_item_id": item.missing_item_id,
                    "missing_item_class": item.missing_item_class,
                    "boundary_layer": item.boundary_layer,
                    "comparison_case_id": "",
                    "comparison_status": "no_higher_fixed_reference_burden",
                    "fixed_reference_gap_gwp_kgco2": np.nan,
                    "steel_equivalent_mass_to_parity_kg": np.nan,
                    "concrete_equivalent_mass_to_parity_kg": np.nan,
                    "reported_missing_mass_kg": np.nan,
                    "material_identity_status": item.material_identity_status,
                    "reference_source_id": item.reference_source_id,
                    "source_status": item.source_status,
                    "threshold_semantics": "no_actual_mass_or_material_identity_asserted",
                    "no_central_claim": True,
                }
            )
            continue
        for comparison_case_id, comparison_burden in higher_cases.items():
            gap = float(comparison_burden - case_burden)
            rows.append(
                {
                    "case_id": item.case_id,
                    "missing_item_id": item.missing_item_id,
                    "missing_item_class": item.missing_item_class,
                    "boundary_layer": item.boundary_layer,
                    "comparison_case_id": comparison_case_id,
                    "comparison_status": "material_equivalent_threshold_available",
                    "fixed_reference_gap_gwp_kgco2": gap,
                    "steel_equivalent_mass_to_parity_kg": gap / steel_factor,
                    "concrete_equivalent_mass_to_parity_kg": gap / concrete_factor,
                    "reported_missing_mass_kg": np.nan,
                    "material_identity_status": item.material_identity_status,
                    "reference_source_id": item.reference_source_id,
                    "source_status": item.source_status,
                    "threshold_semantics": "equivalent_threshold_only_no_actual_mass_asserted",
                    "no_central_claim": True,
                }
            )
    return pd.DataFrame(rows)


def analytic_corner_bounds(inputs: Inputs) -> pd.DataFrame:
    p = inputs.parameters
    rows = []
    for case_id in PRIMARY_CASE_ORDER:
        case_rows = inputs.components[inputs.components["case_id"] == case_id]
        low = 0.0
        high = 0.0
        for row in case_rows.itertuples(index=False):
            coefficient = p["material_gwp_kgco2_per_kg"][row.material_group]
            mass_multiplier = p["evidence_mass_multiplier"][row.evidence_status]
            mass_low = float(row.mass_kg)
            mass_high = float(row.mass_kg)
            if row.component_id == "af_concrete":
                mass_low *= float(p["activefloat_concrete_density_kg_per_m3"]["min"]) / 2400.0
                mass_high *= float(p["activefloat_concrete_density_kg_per_m3"]["max"]) / 2400.0
            low += mass_low * float(mass_multiplier["min"]) * float(coefficient["min"])
            high += mass_high * float(mass_multiplier["max"]) * float(coefficient["max"])
        if case_id == "windcrete_15mw":
            concrete_mass = float(case_rows.loc[case_rows["component_id"] == "wc_concrete", "mass_kg"].iloc[0])
            ratio = p["windcrete_omitted_reinforcement_ratio"]
            steel = p["material_gwp_kgco2_per_kg"]["steel"]
            low += concrete_mass * float(ratio["min"]) * float(steel["min"])
            high += concrete_mass * float(ratio["max"]) * float(steel["max"])
        rows.append({"case_id": case_id, "corner_min_gwp_kgco2": low, "corner_max_gwp_kgco2": high})
    return pd.DataFrame(rows)


def reversal_thresholds(inputs: Inputs, central: pd.DataFrame) -> pd.DataFrame:
    burdens = central.set_index("case_id")[
        "core_plus_stationkeeping_proxy_gwp_kgco2"
    ].dropna()
    steel = float(inputs.parameters["material_gwp_kgco2_per_kg"]["steel"]["central"])
    concrete = float(inputs.parameters["material_gwp_kgco2_per_kg"]["concrete"]["central"])
    rows = []
    for lower, higher in combinations(burdens.sort_values().index, 2):
        gap = float(burdens[higher] - burdens[lower])
        rows.append(
            {
                "lower_central_case": lower,
                "higher_central_case": higher,
                "central_gap_gwp_kgco2": gap,
                "unmodelled_steel_on_lower_to_reach_parity_kg": gap / steel,
                "unmodelled_concrete_on_lower_to_reach_parity_kg": gap / concrete,
            }
        )
    return pd.DataFrame(rows)


def rating_transfer_results(inputs: Inputs, central: pd.DataFrame) -> pd.DataFrame:
    p = inputs.parameters["rating_transfer"]
    ratings = [float(value) for value in p["ratings_mw"]]
    exponents = [float(value) for value in p["structural_scaling_exponents"]]
    rows = []
    for row in central.itertuples(index=False):
        reference = float(row.core_plus_stationkeeping_intensity_gco2_per_kwh)
        if not np.isfinite(reference):
            continue
        for exponent in exponents:
            for rating in ratings:
                ratio = rating / 15.0
                rows.append(
                    {
                        "case_id": row.case_id,
                        "rating_mw": rating,
                        "structural_scaling_exponent": exponent,
                        "relative_intensity_to_15mw": ratio ** (exponent - 1.0),
                        "analytic_intensity_gco2_per_kwh": reference * ratio ** (exponent - 1.0),
                        "engineered_design": False,
                    }
                )
    return pd.DataFrame(rows)


def qa_results(inputs: Inputs, central: pd.DataFrame, pairwise: pd.DataFrame) -> pd.DataFrame:
    comp = inputs.components.set_index("component_id")
    physical = inputs.physical.set_index("item_id")
    activefloat_endpoints = activefloat_rebar_unit_endpoints(inputs).set_index(
        "unit_scenario_id"
    )
    tests = [
        (
            "windcrete substructure mass closes",
            np.isclose(comp.loc["wc_concrete", "mass_kg"] + comp.loc["wc_solid_ballast", "mass_kg"], 36550000.0),
        ),
        (
            "VolturnUS published component sum closes",
            np.isclose(
                comp.loc["vs_hull", "mass_kg"]
                + comp.loc["vs_fixed_ballast", "mass_kg"]
                + physical.loc["vs_seawater_ballast", "physical_mass_kg"],
                17754000.0,
            ),
        ),
        (
            "VolturnUS total closes after unresolved interface is restored physically",
            np.isclose(
                comp.loc["vs_hull", "mass_kg"]
                + comp.loc["vs_fixed_ballast", "mass_kg"]
                + physical.loc["vs_seawater_ballast", "physical_mass_kg"]
                + physical.loc["vs_interface_point_mass", "physical_mass_kg"],
                17854000.0,
            ),
        ),
        (
            "TLP tendon derivation closes",
            np.isclose(comp.loc["tlp_tendons", "mass_kg"], 9.0 * 79.809 * 14.6, rtol=0.0, atol=0.01),
        ),
        (
            "all primary conditional burdens are positive",
            bool(
                (
                    central.loc[
                        central["result_namespace"] == "primary_conditional",
                        "core_plus_stationkeeping_proxy_gwp_kgco2",
                    ]
                    > 0
                ).all()
            ),
        ),
        (
            "pairwise sample fractions sum to one",
            bool(
                np.allclose(
                    pairwise[
                        [
                            "sample_fraction_a_lower",
                            "sample_fraction_b_lower",
                            "sample_fraction_tie",
                        ]
                    ].sum(axis=1),
                    1.0,
                )
            ),
        ),
        (
            "physical register has no material coefficient column",
            "material_group" not in inputs.physical.columns,
        ),
        (
            "ActiveFloat residual register is a mass-free audit placeholder",
            bool(
                pd.isna(physical.loc["af_unmapped_residual", "physical_mass_kg"])
                and physical.loc["af_unmapped_residual", "register_role"]
                == "audit_only_unit_dependent_placeholder"
            ),
        ),
        (
            "ActiveFloat physical residual endpoints close from source total",
            bool(
                np.isclose(
                    activefloat_endpoints.loc[
                        "reported_header_kg_literal", "physical_residual_endpoint_kg"
                    ],
                    13984650.0,
                )
                and np.isclose(
                    activefloat_endpoints.loc[
                        "reported_value_interpreted_as_tonnes",
                        "physical_residual_endpoint_kg",
                    ],
                    11437200.0,
                )
            ),
        ),
        (
            "TLP source design depth is 103 m",
            bool(
                inputs.components.loc[
                    inputs.components["case_id"] == "tlp_15mw", "water_depth_m"
                ].eq(103).all()
            ),
        ),
        (
            "ActiveFloat unresolved unit is non-headline",
            str(
                inputs.evidence_profile.set_index("case_id").loc[
                    "activefloat_15mw", "eligibility_result"
                ]
            )
            == "non_headline_unresolved_unit",
        ),
        (
            "ActiveFloat baseline burden intensity and rank are not asserted",
            bool(
                central.set_index("case_id")
                .loc[
                    "activefloat_15mw",
                    [
                        "water_depth_m",
                        "core_burdened_mass_kg",
                        "stationkeeping_burdened_mass_kg",
                        "core_proxy_gwp_kgco2",
                        "stationkeeping_proxy_gwp_kgco2",
                        "core_plus_stationkeeping_proxy_gwp_kgco2",
                        "equal_yield_capacity_factor",
                        "equal_yield_lifetime_kwh",
                        "core_intensity_gco2_per_kwh",
                        "core_plus_stationkeeping_intensity_gco2_per_kwh",
                        "central_rank_core_equal_yield",
                        "central_rank_equal_yield",
                    ],
                ]
                .isna()
                .all()
            ),
        ),
        (
            "ActiveFloat associated engineering model is separated at 200 m",
            bool(
                central.set_index("case_id").loc[
                    "activefloat_15mw", "material_proxy_depth_status"
                ]
                == "not_specified"
                and central.set_index("case_id").loc[
                    "activefloat_15mw", "associated_engineering_model_depth_m"
                ]
                == 200
            ),
        ),
        (
            "TLP status is conditional product proxy",
            bool(
                central.set_index("case_id").loc[
                    "tlp_15mw", "point_estimate_status"
                ]
                == "conditional_product_proxy"
            ),
        ),
        (
            "ActiveFloat is absent from primary pairwise results",
            bool(
                ~pairwise[["case_a", "case_b"]]
                .isin(AUDIT_ONLY_CASES)
                .any(axis=None)
            ),
        ),
        (
            "missing boundary register asserts no mass",
            bool(inputs.missing_boundary_items["reported_mass_kg"].isna().all()),
        ),
    ]
    return pd.DataFrame(
        {"check": [item[0] for item in tests], "passed": [bool(item[1]) for item in tests]}
    )
