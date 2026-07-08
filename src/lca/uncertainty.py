"""Monte Carlo uncertainty analysis engine for wind turbine LCA.

Samples capacity factor (triangular) and EoL credit rate (uniform) to
produce N_SAMPLES intensity estimates per (structure, rated_power, material)
combination.

Usage:
    from src.lca.uncertainty import MCEngine
    engine = MCEngine(n_samples=10_000, seed=42)
    df = engine.run(structures=[...], rated_powers=[...], material_models=[...])
    engine.save(df, "results/latest/uncertainty/mc_raw_samples.parquet")
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Defaults match matrix.py defaults
DEFAULT_STRUCTURES = ["onshore", "bottom_fixed", "semisubmersible", "spar", "fawt"]
DEFAULT_POWERS_MW = [2.0, 5.0, 10.0, 15.0]
DEFAULT_MATERIAL_MODELS = ["gfrp", "cfrp", "rcfrp", "rrcfrp"]


class MCEngine:
    """Monte Carlo sampling engine for LCA intensity uncertainty analysis.

    Parameters
    ----------
    n_samples:
        Number of MC draws per (structure, rated_power, material) combination.
    seed:
        Random seed for reproducibility.
    assumptions_path:
        Path to model_assumptions.json.
    lci_dir:
        Path to the LCI data directory.
    """

    def __init__(
        self,
        n_samples: int = 10_000,
        seed: int = 42,
        assumptions_path: str | Path = "data/model_assumptions.json",
        lci_dir: str | Path = "data/lci",
        lifetime_years: int = 25,
        site_class: str = "baseline",
        assumption_point: str = "base",
    ) -> None:
        self.n_samples = n_samples
        self.rng = np.random.default_rng(seed)
        self.assumptions_path = Path(assumptions_path)
        self.lci_dir = Path(lci_dir)
        self.lifetime_years = lifetime_years
        self.site_class = site_class
        self.assumption_point = assumption_point

        self._assumptions: dict | None = None
        self._lci_data = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        structures: Sequence[str] = DEFAULT_STRUCTURES,
        rated_powers: Sequence[float] = DEFAULT_POWERS_MW,
        material_models: Sequence[str] = DEFAULT_MATERIAL_MODELS,
    ) -> pd.DataFrame:
        """Run MC sampling and return raw samples DataFrame.

        Columns:
            structure_type, rated_power_mw, material_model,
            sample_id, capacity_factor, eol_credit_rate,
            intensity_gco2_per_kwh
        """
        assumptions = self._load_assumptions()
        lci_data = self._load_lci()

        unc = assumptions["uncertainty"]
        cf_params = unc["site_class_cf_triangle"]
        eol_params = unc["eol_credit_rate_uniform"]

        # Pre-sample per structure (CF is structure-specific)
        cf_samples_by_structure: dict[str, np.ndarray] = {}
        for struct in structures:
            p = cf_params[struct]
            cf_samples_by_structure[struct] = self.rng.triangular(
                p["min"], p["mode"], p["max"], size=self.n_samples
            )

        # EoL credit rate is shared across structures (uniform)
        eol_samples: np.ndarray = self.rng.uniform(
            eol_params["min"], eol_params["max"], size=self.n_samples
        )

        records: list[dict] = []
        total_combos = len(structures) * len(rated_powers) * len(material_models)
        combo_idx = 0

        for struct in structures:
            cf_arr = cf_samples_by_structure[struct]
            for power in rated_powers:
                for model in material_models:
                    combo_idx += 1
                    logger.info(
                        "[%d/%d] MC: %s %.0fMW %s (%d samples)",
                        combo_idx, total_combos, struct, power, model, self.n_samples,
                    )
                    intensities = self._run_combo(
                        struct, power, model, cf_arr, eol_samples, assumptions, lci_data
                    )
                    for i in range(self.n_samples):
                        records.append(
                            {
                                "structure_type": struct,
                                "rated_power_mw": power,
                                "material_model": model,
                                "sample_id": i,
                                "capacity_factor": float(cf_arr[i]),
                                "eol_credit_rate": float(eol_samples[i]),
                                "intensity_gco2_per_kwh": float(intensities[i]),
                            }
                        )

        return pd.DataFrame(records)

    def save(self, df: pd.DataFrame, output_path: str | Path) -> Path:
        """Save raw samples DataFrame.

        Parquet is preferred for size/performance. If parquet engines are not
        available in the current environment, falls back to CSV.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # Explicit CSV request
        if out.suffix.lower() == ".csv":
            df.to_csv(out, index=False)
            logger.info("MC raw samples saved (CSV): %s (%d rows)", out, len(df))
            return out

        # Preferred parquet path
        try:
            df.to_parquet(out, index=False)
            logger.info("MC raw samples saved (Parquet): %s (%d rows)", out, len(df))
            return out
        except ImportError:
            fallback = out.with_suffix(".csv")
            df.to_csv(fallback, index=False)
            logger.warning(
                "Parquet engine unavailable; saved MC raw samples as CSV: %s (%d rows)",
                fallback,
                len(df),
            )
            return fallback

    def sample_triangular(
        self, lower: float, mode: float, upper: float, n: int | None = None
    ) -> np.ndarray:
        n = n or self.n_samples
        return self.rng.triangular(lower, mode, upper, size=n)

    def sample_uniform(
        self, low: float, high: float, n: int | None = None
    ) -> np.ndarray:
        n = n or self.n_samples
        return self.rng.uniform(low, high, size=n)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_assumptions(self) -> dict:
        if self._assumptions is None:
            self._assumptions = json.loads(self.assumptions_path.read_text())
        return self._assumptions

    def _load_lci(self):
        if self._lci_data is None:
            from src.lci.loaders import load_all_lci_data
            self._lci_data = load_all_lci_data(data_dir=self.lci_dir)
        return self._lci_data

    def _run_combo(
        self,
        structure: str,
        rated_power_mw: float,
        material_model: str,
        cf_samples: np.ndarray,
        eol_samples: np.ndarray,
        assumptions: dict,
        lci_data,
    ) -> np.ndarray:
        """Vectorized MC run for one (structure, power, material) combo.

        Key insight: L1 and L2 are CF-independent; L3 is CF-independent in
        this model (absolute kgCO2); L4 is EoL-credit-sensitive but CF-independent.
        Energy generation scales linearly with CF.

        Therefore:
            intensity_i = (L1 + L2 + L3 + L4(eol_i)) / (rated_power_mw * 8760 * lifetime * CF_i)

        This allows fully vectorized computation without N_samples LCACalculator calls.
        Returns array of shape (n_samples,) with intensity values.
        """
        from src.cli.commands.matrix import (
            _apply_material_model,
            _estimate_l2_from_events,
            _estimate_l3_from_events,
            _estimate_l4_from_events,
            _estimate_l4_proxy,
            _estimate_transport_gwp_proxy,
            _scale_structure_mass_by_power,
        )
        from src.lca.calculator import LCACalculator

        # --- Fixed setup: run once per combo ---
        scaled_lci = _scale_structure_mass_by_power(
            lci_data=lci_data,
            structure_type=structure,
            rated_power_mw=rated_power_mw,
        )
        model_lci = _apply_material_model(
            lci_data=scaled_lci,
            structure_type=structure,
            material_model=material_model,
            assumptions=assumptions,
            assumption_point=self.assumption_point,
            fawt_arm_center_share=None,
        )

        structure_components = [
            c for c in model_lci.components.values() if c.structure_type == structure
        ]
        structure_events = [
            e for e in model_lci.events if e.structure_type == structure
        ]
        total_mass_kg = sum(c.mass_kg * c.quantity for c in structure_components)

        # L1: run LCACalculator once at CF=base to get manufacturing GWP
        # (manufacturing GWP does not depend on CF)
        base_cf = assumptions["site_class_cf"]["baseline"][structure]["base"]
        scenario_name = f"mc-{structure}-{rated_power_mw:g}mw-{material_model}"
        calc_base = LCACalculator(
            lci_data=model_lci,
            structure_type=structure,
            rated_power_mw=rated_power_mw,
            lifetime_years=self.lifetime_years,
            capacity_factor=base_cf,
            scenario_name=scenario_name,
            enable_weight_cascade=False,
            log_iterations=False,
            write_detailed_log=False,
        )
        base_result = calc_base.calculate()
        l1 = base_result.l1_manufacturing_kgco2

        # L2: transport (CF-independent)
        l2_event = _estimate_l2_from_events(
            events=structure_events,
            structure_components=structure_components,
            vehicles=model_lci.vehicles,
            assumptions=assumptions,
        )
        l2_proxy = _estimate_transport_gwp_proxy(total_mass_kg, structure)
        l2 = l2_event if l2_event > 0 else l2_proxy

        # L3: O&M (CF-independent in absolute kgCO2 terms)
        l3_event = _estimate_l3_from_events(
            events=structure_events,
            structure_components=structure_components,
            vehicles=model_lci.vehicles,
            assumptions=assumptions,
            structure=structure,
            lifetime_years=self.lifetime_years,
            site_class=self.site_class,
            assumption_point=self.assumption_point,
        )
        l3_calc = base_result.l3_o_and_m_kgco2 + l3_event

        # L4 base (without EoL credit override, from model default)
        l4_base_event = _estimate_l4_from_events(
            events=structure_events,
            structure_components=structure_components,
            vehicles=model_lci.vehicles,
            assumptions=assumptions,
            structure=structure,
            assumption_point=self.assumption_point,
            eol_credit_rate=None,  # use model default
        )
        l4_base = base_result.l4_eol_kgco2 + l4_base_event

        # L4 sensitivity: compute credit sensitivity coefficient
        # L4(eol=0.0) - L4(eol=model_default) to get linear sensitivity
        l4_proxy_at_zero = _estimate_l4_proxy(
            structure_components=structure_components,
            structure=structure,
            assumptions=assumptions,
            assumption_point=self.assumption_point,
            eol_credit_rate=0.0,
        )
        l4_proxy_at_model = _estimate_l4_proxy(
            structure_components=structure_components,
            structure=structure,
            assumptions=assumptions,
            assumption_point=self.assumption_point,
            eol_credit_rate=None,
        )
        # Credit sensitivity: dL4/d(eol_rate) ≈ linear
        # L4(eol_i) = L4_base + (eol_i - model_default) * sensitivity
        model_default_credit = assumptions["l4_credit_realization"][structure].get(
            self.assumption_point,
            assumptions["l4_credit_realization"][structure]["base"],
        )
        if abs(l4_proxy_at_model - l4_proxy_at_zero) > 1e-10:
            credit_sensitivity = (l4_proxy_at_model - l4_proxy_at_zero) / model_default_credit
        else:
            credit_sensitivity = 0.0

        # --- Vectorized computation ---
        # Energy per sample: Power[MW] × 8760[h/yr] × Lifetime[yr] × CF_i × 1000[kWh/MWh]
        energy_mwh_per_sample = (
            rated_power_mw * 8760.0 * self.lifetime_years * cf_samples
        )  # shape (n_samples,)

        # L4 per sample: varies with eol_credit_rate
        # L4(eol_i) = L4_base + (eol_i - model_default_credit) * credit_sensitivity_overhead
        l4_per_sample = l4_base + (eol_samples - model_default_credit) * credit_sensitivity
        # (overhead portion from l4_base_event is CF-independent, so we adjust only proxy)

        # Total GWP per sample (scalar L1+L2+L3 + per-sample L4)
        total_gwp_per_sample = l1 + l2 + l3_calc + l4_per_sample  # shape (n_samples,)

        # Intensity: g-CO2/kWh = (kgCO2 * 1000) / (MWh * 1000)
        with np.errstate(divide="ignore", invalid="ignore"):
            intensities = np.where(
                energy_mwh_per_sample > 0,
                total_gwp_per_sample / energy_mwh_per_sample,  # kg-CO2 / MWh = g/kWh
                0.0,
            )

        return intensities
