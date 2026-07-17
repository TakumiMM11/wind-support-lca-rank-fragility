import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.analysis import (
    PRIMARY_CASE_ORDER,
    activefloat_rebar_unit_endpoints,
    analytic_corner_bounds,
    boundary_layer_rank_shifts,
    central_case_results,
    central_component_results,
    load_inputs,
    missing_burden_parity_thresholds,
    monte_carlo_samples,
    pairwise_rank_results,
    qa_results,
    rank_distribution,
    rating_transfer_results,
    robustness_audit_results,
    sample_summary,
)
from scripts.run_analysis import figure_1_source_data, figure_2_source_data


ROOT = Path(__file__).resolve().parents[1]


def test_registers_and_central_results_close():
    inputs = load_inputs(ROOT / "inputs")
    central = central_case_results(inputs)
    assert len(central) == 5
    assert set(central["central_rank_equal_yield"].dropna()) == {1, 2, 3, 4}
    assert set(central["central_rank_core_equal_yield"].dropna()) == {1, 2, 3, 4}
    assert central["headline_eligible"].astype(str).str.lower().eq("yes").sum() == 3
    assert (central["core_plus_stationkeeping_proxy_gwp_kgco2"].dropna() > 0).all()
    assert central.set_index("case_id").loc["tlp_15mw", "water_depth_m"] == 103
    expected_intensities = {
        "monopile_15mw": 2.3595419294049433,
        "volturnus_15mw": 10.331373021050124,
        "windcrete_15mw": 2.990510663550047,
        "tlp_15mw": 4.8400926260408585,
    }
    actual = central.set_index("case_id")[
        "core_plus_stationkeeping_intensity_gco2_per_kwh"
    ]
    for case_id, expected in expected_intensities.items():
        assert np.isclose(actual.loc[case_id], expected, rtol=0.0, atol=1e-12)
    active = central.set_index("case_id").loc["activefloat_15mw"]
    assert active["point_estimate_status"] == "audit_only_unit_endpoints"
    assert active["result_namespace"] == "audit_only_unit_endpoints"
    assert active[
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
        ]
    ].isna().all()
    assert active["material_proxy_depth_status"] == "not_specified"
    assert active["associated_engineering_model_depth_m"] == 200
    assert central.set_index("case_id").loc[
        "tlp_15mw", "point_estimate_status"
    ] == "conditional_product_proxy"


def test_activefloat_depth_semantics_and_tlp_status_are_input_consistent():
    inputs = load_inputs(ROOT / "inputs")
    active_components = inputs.components[
        inputs.components["case_id"] == "activefloat_15mw"
    ]
    assert active_components["water_depth_m"].isna().all()
    assert set(active_components["material_proxy_depth_status"]) == {"not_specified"}
    assert active_components["associated_engineering_model_depth_m"].eq(200).all()
    assert inputs.components.loc[
        inputs.components["case_id"] != "activefloat_15mw", "water_depth_m"
    ].notna().all()
    manifest = inputs.manifest.set_index("case_id")
    evidence = inputs.evidence_profile.set_index("case_id")
    for register in (manifest, evidence):
        assert register.loc["activefloat_15mw", "material_proxy_depth_status"] == "not_specified"
        assert register.loc[
            "activefloat_15mw", "associated_engineering_model_depth_m"
        ] == 200
    assert manifest.loc["tlp_15mw", "point_estimate_status"] == "conditional_product_proxy"
    assert evidence.loc["tlp_15mw", "eligibility_result"] == "conditional_product_proxy"


def test_physical_register_never_has_material_mapping():
    inputs = load_inputs(ROOT / "inputs")
    assert "material_group" not in inputs.physical.columns
    assert set(inputs.physical["material_proxy_treatment"]) == {
        "excluded_from_material_proxy",
        "crosscheck_only",
        "excluded_pending_identity",
        "audit_only_unit_dependent_placeholder",
    }
    residual = inputs.physical.set_index("item_id").loc["af_unmapped_residual"]
    assert pd.isna(residual["physical_mass_kg"])
    assert residual["register_role"] == "audit_only_unit_dependent_placeholder"


def test_monte_carlo_is_seed_reproducible_and_sample_fractions_close():
    inputs = load_inputs(ROOT / "inputs")
    first = monte_carlo_samples(inputs)
    second = monte_carlo_samples(inputs)
    columns = [column for column in first if column.endswith("equal_yield_gco2_per_kwh")]
    assert np.array_equal(first[columns].to_numpy(), second[columns].to_numpy())
    pairwise = pairwise_rank_results(inputs, first)
    assert not any("activefloat" in column for column in first.columns)
    assert not pairwise[["case_a", "case_b"]].isin(["activefloat_15mw"]).any(axis=None)
    assert np.allclose(
        pairwise[
            [
                "sample_fraction_a_lower",
                "sample_fraction_b_lower",
                "sample_fraction_tie",
            ]
        ].sum(axis=1),
        1.0,
    )
    central = central_case_results(inputs)
    assert qa_results(inputs, central, pairwise)["passed"].all()
    shifts = boundary_layer_rank_shifts(inputs, first)
    assert not shifts[["case_a", "case_b"]].isin(["activefloat_15mw"]).any(axis=None)
    assert np.allclose(
        shifts[
            [
                "sample_fraction_strict_order_preserved",
                "sample_fraction_strict_order_reversed",
                "sample_fraction_with_tie_in_either_layer",
            ]
        ].sum(axis=1),
        1.0,
    )


def test_shared_material_draws_are_single_columns():
    inputs = load_inputs(ROOT / "inputs")
    samples = monte_carlo_samples(inputs)
    assert {"coef_steel", "coef_concrete", "coef_aggregate", "coef_cfrp"} <= set(samples)
    assert samples["coef_steel"].nunique() > 1000


def test_activefloat_is_absent_from_every_primary_derived_result():
    inputs = load_inputs(ROOT / "inputs")
    samples = monte_carlo_samples(inputs)
    central = central_case_results(inputs)
    assert "activefloat_15mw" not in set(central_component_results(inputs)["case_id"])
    assert "activefloat_15mw" not in set(sample_summary(samples)["case_id"])
    assert "activefloat_15mw" not in set(analytic_corner_bounds(inputs)["case_id"])
    assert "activefloat_15mw" not in set(rating_transfer_results(inputs, central)["case_id"])
    assert "activefloat_15mw" not in set(
        rank_distribution(samples, "equal_yield_gco2_per_kwh")["case_id"]
    )
    assert set(PRIMARY_CASE_ORDER) == {
        "monopile_15mw",
        "volturnus_15mw",
        "windcrete_15mw",
        "tlp_15mw",
    }


def test_every_material_coefficient_has_a_registered_source():
    inputs = load_inputs(ROOT / "inputs")
    registered = set(inputs.sources["source_id"])
    assert {
        block["source_id"]
        for block in inputs.parameters["material_gwp_kgco2_per_kg"].values()
    } <= registered

    profile_source_ids = {
        source_id
        for source_ids in inputs.evidence_profile["source_ids"]
        for source_id in source_ids.split("|")
    }
    assert profile_source_ids <= registered
    assert set(inputs.missing_boundary_items["reference_source_id"]) <= registered


def test_activefloat_unit_endpoints_are_exclusive_nonheadline_audits():
    inputs = load_inputs(ROOT / "inputs")
    endpoints = activefloat_rebar_unit_endpoints(inputs).set_index("unit_scenario_id")
    literal = endpoints.loc["reported_header_kg_literal"]
    assumed_tonnes = endpoints.loc["reported_value_interpreted_as_tonnes"]
    assert assumed_tonnes["interpreted_rebar_mass_kg"] / literal[
        "interpreted_rebar_mass_kg"
    ] == 1000.0
    assert assumed_tonnes["interpreted_rebar_mass_kg"] == inputs.components.set_index(
        "component_id"
    ).loc["af_rebar", "mass_kg"]
    assert bool(assumed_tonnes["legacy_package_assumed_tonnes_path"])
    assert not bool(literal["legacy_package_assumed_tonnes_path"])
    assert "does not select a central endpoint" in assumed_tonnes["provenance_note"]
    assert endpoints["no_central_claim"].all()
    assert not endpoints["headline_eligible"].any()
    assert set(endpoints["source_id"]) <= set(inputs.sources["source_id"])
    assert literal["physical_residual_endpoint_kg"] == 13984650.0
    assert literal["physical_residual_endpoint_t"] == 13984.65
    assert assumed_tonnes["physical_residual_endpoint_kg"] == 11437200.0
    assert assumed_tonnes["physical_residual_endpoint_t"] == 11437.2
    assert endpoints["physical_residual_semantics"].eq(
        "physical_only_unit_dependent_endpoint_no_material_identity"
    ).all()


def test_robustness_matrix_is_deterministic_and_fraction_columns_close():
    inputs = load_inputs(ROOT / "inputs")
    kwargs = {"n_samples_per_replicate": 400, "replicate_seeds": (101, 202)}
    first_pairwise, first_ordering = robustness_audit_results(inputs, **kwargs)
    second_pairwise, second_ordering = robustness_audit_results(inputs, **kwargs)
    assert first_pairwise.equals(second_pairwise)
    assert first_ordering.equals(second_ordering)
    assert np.allclose(
        first_pairwise[
            [
                "sample_fraction_a_lower",
                "sample_fraction_b_lower",
                "sample_fraction_tie",
            ]
        ].sum(axis=1),
        1.0,
    )
    assert np.allclose(
        first_ordering[
            [
                "sample_fraction_strict_reported_order",
                "sample_fraction_other_strict_order",
                "sample_fraction_with_any_tie",
            ]
        ].sum(axis=1),
        1.0,
    )
    assert first_pairwise["no_central_claim"].all()
    assert first_ordering["no_central_claim"].all()
    assert not any("probability" in column for column in first_pairwise.columns)
    assert not any("probability" in column for column in first_ordering.columns)
    assert set(first_pairwise["distribution_shape"]) == {
        "triangular",
        "uniform",
        "discrete_endpoints",
    }
    assert set(first_pairwise["windcrete_reinforcement_upper_fraction"]) == {
        0.05,
        0.125,
    }
    assert set(first_pairwise["capacity_factor_copula_rho"]) == {0.0, 0.6, 0.9}
    assert set(first_pairwise["tie_threshold"]) == {0.005, 0.01, 0.02}


def test_missing_anchor_scour_thresholds_do_not_invent_mass_or_identity():
    inputs = load_inputs(ROOT / "inputs")
    thresholds = missing_burden_parity_thresholds(inputs, central_case_results(inputs))
    assert set(thresholds["case_id"]) == set(PRIMARY_CASE_ORDER)
    assert thresholds["reported_missing_mass_kg"].isna().all()
    assert set(thresholds["material_identity_status"]) == {"unknown"}
    available = thresholds[
        thresholds["comparison_status"] == "material_equivalent_threshold_available"
    ]
    assert (available["steel_equivalent_mass_to_parity_kg"] > 0).all()
    assert (available["concrete_equivalent_mass_to_parity_kg"] > 0).all()
    assert thresholds["no_central_claim"].all()


def test_figure_sources_make_activefloat_unranked_and_exclude_it_from_heatmap():
    inputs = load_inputs(ROOT / "inputs")
    samples = monte_carlo_samples(inputs)
    summary = sample_summary(samples)
    pairwise = pairwise_rank_results(inputs, samples)
    endpoints = activefloat_rebar_unit_endpoints(inputs)
    figure_1 = figure_1_source_data(summary, endpoints)
    ranked = figure_1[figure_1["plot_role"] == "ranked_conditional_bar"]
    active = figure_1[figure_1["case_id"] == "activefloat_15mw"]
    assert set(ranked["case_id"]) == set(PRIMARY_CASE_ORDER)
    assert len(active) == 2
    assert set(active["plot_role"]) == {"unranked_unit_endpoint"}
    assert not active["ranked_for_figure"].any()
    assert np.allclose(
        sorted(active["total_value_gco2_per_kwh"]),
        sorted(endpoints["core_plus_stationkeeping_intensity_gco2_per_kwh_endpoint"]),
    )
    figure_2 = figure_2_source_data(pairwise, 0.01)
    assert len(figure_2) == 2 * 4 * 4
    assert "activefloat_15mw" not in set(figure_2["row_case_id"])
    assert "activefloat_15mw" not in set(figure_2["column_case_id"])
    assert figure_2["reported_material_conditional_sample_fraction"].between(0, 1).all()
    for _, panel in figure_2.groupby("estimand"):
        assert panel["row_case_id"].nunique() == 4
        assert panel["column_case_id"].nunique() == 4


def test_generated_figure_manifest_declares_common_scale_and_source_hashes():
    manifest = json.loads((ROOT / "figures" / "figure_manifest.json").read_text())
    figure_1 = manifest["figures"]["Figure_1_multisupport_baseline"]
    figure_2 = manifest["figures"]["Figure_2_rank_stability"]
    assert "unranked" in figure_1["caption_short"].lower()
    assert figure_2["color_scale"] == [0.0, 1.0]
    assert "ActiveFloat excluded" in figure_2["filters"]
    assert set(figure_1["source_data"]) == set(figure_1["source_sha256"])
    assert set(figure_2["source_data"]) == set(figure_2["source_sha256"])
    assert manifest["case_point_estimate_status"]["tlp_15mw"] == "conditional_product_proxy"
    assert manifest["activefloat_depth_semantics"] == {
        "material_proxy_depth_status": "not_specified",
        "associated_engineering_model_depth_m": 200,
        "interpretation": "the 200 m value belongs to an associated engineering model and is not assigned to the material proxy",
    }
    assert (ROOT / "analysis" / "figure_1_plot_data.csv").is_file()
    assert (ROOT / "analysis" / "figure_2_heatmap_values.csv").is_file()
