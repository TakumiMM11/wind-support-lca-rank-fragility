"""LCA Calculator Module.

This module orchestrates the complete LCA calculation workflow:
1. Apply material substitutions from scenario
2. Execute weight cascade
3. Calculate manufacturing GWP
4. Calculate transport GWP
5. Calculate O&M GWP
6. Calculate end-of-life GWP
7. Aggregate results

The calculator follows the legacy system's phase structure:
- L1: Manufacturing (component production)
- L2: Transport (A4 phase)
- L3: Operations & Maintenance (B phase)
- L4: End-of-Life (C phase)
"""

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.lca.gwp import GWPResult, aggregate_gwp_by_phase, calculate_gwp
from src.lca.weight_cascade import WeightCascadeResult, calculate_weight_cascade
from src.lci.models import Component, LCAEvent, LCIData, TransportVehicle

logger = logging.getLogger(__name__)


@dataclass
class LCAResult:
    """Complete LCA calculation result.

    Attributes:
        scenario_name: Name of the scenario
        structure_type: Structure type (onshore, bottom_fixed, etc.)
        l1_manufacturing_kgco2: Manufacturing phase GWP
        l2_transport_kgco2: Transport phase GWP
        l3_o_and_m_kgco2: Operations & Maintenance phase GWP
        l4_eol_kgco2: End-of-Life phase GWP
        total_gwp_kgco2: Total lifecycle GWP
        intensity_gco2_per_kwh: GWP intensity per kWh
        energy_generation_mwh: Lifetime energy generation
        weight_cascade_iterations: Number of weight cascade iterations
        weight_cascade_converged: Whether weight cascade converged
        component_breakdown: Component-level GWP breakdown
        metadata: Additional metadata (timestamp, parameters, etc.)
    """

    scenario_name: str
    structure_type: str
    l1_manufacturing_kgco2: float
    l2_transport_kgco2: float
    l3_o_and_m_kgco2: float
    l4_eol_kgco2: float
    total_gwp_kgco2: float
    intensity_gco2_per_kwh: float
    energy_generation_mwh: float
    weight_cascade_iterations: int
    weight_cascade_converged: bool
    component_breakdown: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_csv(self, output_path: Path) -> None:
        """Export LCA results to CSV file.

        Args:
            output_path: Path to output CSV file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "scenario_name",
                "structure_type",
                "rated_power_mw",
                "lifetime_years",
                "capacity_factor",
                "l1_manufacturing_kgco2",
                "l2_transport_kgco2",
                "l3_o_and_m_kgco2",
                "l4_eol_kgco2",
                "total_gwp_kgco2",
                "intensity_gco2_per_kwh",
                "energy_generation_mwh",
                "weight_cascade_iterations",
                "weight_cascade_converged",
                "generated_at",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(
                {
                    "scenario_name": self.scenario_name,
                    "structure_type": self.structure_type,
                    "rated_power_mw": float(self.metadata.get("rated_power_mw", "0") or 0),
                    "lifetime_years": int(float(self.metadata.get("lifetime_years", "0") or 0)),
                    "capacity_factor": float(self.metadata.get("capacity_factor", "0") or 0),
                    "l1_manufacturing_kgco2": self.l1_manufacturing_kgco2,
                    "l2_transport_kgco2": self.l2_transport_kgco2,
                    "l3_o_and_m_kgco2": self.l3_o_and_m_kgco2,
                    "l4_eol_kgco2": self.l4_eol_kgco2,
                    "total_gwp_kgco2": self.total_gwp_kgco2,
                    "intensity_gco2_per_kwh": self.intensity_gco2_per_kwh,
                    "energy_generation_mwh": self.energy_generation_mwh,
                    "weight_cascade_iterations": self.weight_cascade_iterations,
                    "weight_cascade_converged": self.weight_cascade_converged,
                    "generated_at": datetime.now().isoformat(),
                }
            )

        logger.info(f"Results exported to {output_path}")


class LCACalculator:
    """LCA Calculator orchestrating complete calculation workflow."""

    def __init__(
        self,
        lci_data: LCIData,
        structure_type: str,
        rated_power_mw: float,
        lifetime_years: int,
        capacity_factor: float,
        scenario_name: str = "default",
        enable_weight_cascade: bool = True,
        log_iterations: bool = False,
        write_detailed_log: bool = True,
    ):
        """Initialize LCA calculator.

        Args:
            lci_data: Complete LCI data (materials, components, dependencies, etc.)
            structure_type: Structure type (onshore, bottom_fixed, semisubmersible, spar, fawt)
            rated_power_mw: Turbine rated power in MW
            lifetime_years: Project lifetime in years
            capacity_factor: Capacity factor (0.0-1.0)
            scenario_name: Scenario name for results
            enable_weight_cascade: Enable weight cascade algorithm
            log_iterations: Enable iteration logging for weight cascade
            write_detailed_log: Write detailed per-run calculation log
        """
        self.lci_data = lci_data
        self.structure_type = structure_type
        self.rated_power_mw = rated_power_mw
        self.lifetime_years = lifetime_years
        self.capacity_factor = capacity_factor
        self.scenario_name = scenario_name
        self.enable_weight_cascade = enable_weight_cascade
        self.log_iterations = log_iterations
        self.write_detailed_log = write_detailed_log

        # Filter components for this structure type
        self.components = {
            comp_id: comp
            for comp_id, comp in lci_data.components.items()
            if comp.structure_type == structure_type
        }

        if not self.components:
            raise ValueError(
                f"No components found for structure_type='{structure_type}'. "
                f"Available types: {set(c.structure_type for c in lci_data.components.values())}"
            )

        logger.info(f"Initialized LCACalculator for {structure_type} with {len(self.components)} components")

    def calculate(self) -> LCAResult:
        """Execute complete LCA calculation.

        Returns:
            LCAResult with complete lifecycle assessment

        Raises:
            ValueError: If calculation fails
        """
        logger.info(f"Starting LCA calculation for scenario '{self.scenario_name}'")
        logger.info(f"Structure: {self.structure_type}, Power: {self.rated_power_mw}MW, Lifetime: {self.lifetime_years}y")

        # Step 1: Execute weight cascade
        cascade_result = self._execute_weight_cascade()

        # Step 2: Calculate manufacturing GWP
        manufacturing_gwp = self._calculate_manufacturing_gwp(cascade_result.updated_components)

        # Step 3: Calculate transport GWP
        transport_gwp = self._calculate_transport_gwp()

        # Step 4: Calculate O&M GWP
        o_and_m_gwp = self._calculate_o_and_m()

        # Step 5: Calculate EoL GWP
        eol_gwp = self._calculate_eol()

        # Step 6: Aggregate results
        aggregated = aggregate_gwp_by_phase(
            manufacturing_gwp=manufacturing_gwp.total_gwp_kgco2,
            transport_gwp=transport_gwp,
            o_and_m_gwp=o_and_m_gwp,
            eol_gwp=eol_gwp,
            component_breakdown=manufacturing_gwp.component_breakdown,
            energy_generation_mwh=manufacturing_gwp.energy_generation_mwh,
        )

        # Build component breakdown for CSV export
        component_breakdown_list = [
            {
                "component_id": comp.component_id,
                "component_name": comp.component_name,
                "mass_kg": comp.mass_kg,
                "material_id": comp.material_id,
                "gwp_kgco2": comp.gwp_kgco2,
                "gwp_per_kg": comp.gwp_per_kg,
            }
            for comp in manufacturing_gwp.component_breakdown
        ]

        result = LCAResult(
            scenario_name=self.scenario_name,
            structure_type=self.structure_type,
            l1_manufacturing_kgco2=manufacturing_gwp.total_gwp_kgco2,
            l2_transport_kgco2=transport_gwp,
            l3_o_and_m_kgco2=o_and_m_gwp,
            l4_eol_kgco2=eol_gwp,
            total_gwp_kgco2=aggregated.total_gwp_kgco2,
            intensity_gco2_per_kwh=aggregated.intensity_gco2_per_kwh,
            energy_generation_mwh=aggregated.energy_generation_mwh,
            weight_cascade_iterations=cascade_result.iterations,
            weight_cascade_converged=cascade_result.convergence_achieved,
            component_breakdown=component_breakdown_list,
            metadata={
                "timestamp": datetime.now().isoformat(),
                "rated_power_mw": str(self.rated_power_mw),
                "lifetime_years": str(self.lifetime_years),
                "capacity_factor": str(self.capacity_factor),
            },
        )

        logger.info(f"LCA calculation complete: Total GWP = {result.total_gwp_kgco2:.2f} kg-CO2eq")
        logger.info(f"GWP intensity = {result.intensity_gco2_per_kwh:.4f} g-CO2eq/kWh")

        if self.write_detailed_log:
            # Write detailed calculation log for debugging
            self._write_detailed_log(
                cascade_result=cascade_result,
                manufacturing_gwp=manufacturing_gwp,
                transport_gwp=transport_gwp,
                o_and_m_gwp=o_and_m_gwp,
                eol_gwp=eol_gwp,
                result=result,
            )

        return result

    def _execute_weight_cascade(self) -> WeightCascadeResult:
        """Execute weight cascade algorithm."""
        if not self.enable_weight_cascade:
            logger.info("Weight cascade disabled, using baseline masses")
            return WeightCascadeResult(
                updated_components=self.components.copy(),
                iterations=0,
                convergence_achieved=True,
                metadata={"note": "Weight cascade disabled"},
            )

        logger.info("Executing weight cascade...")
        cascade_result = calculate_weight_cascade(
            components=self.components,
            dependencies=self.lci_data.dependencies,
            structure_type=self.structure_type,
            convergence_threshold=0.005,
            max_iterations=10,
            log_iterations=self.log_iterations,
        )

        logger.info(
            f"Weight cascade: {cascade_result.iterations} iterations, "
            f"converged={cascade_result.convergence_achieved}"
        )

        return cascade_result

    def _calculate_manufacturing_gwp(self, components: Dict[str, Component]) -> GWPResult:
        """Calculate manufacturing phase GWP."""
        logger.info("Calculating manufacturing GWP...")
        gwp_result = calculate_gwp(
            components=components,
            materials=self.lci_data.materials,
            rated_power_mw=self.rated_power_mw,
            lifetime_years=self.lifetime_years,
            capacity_factor=self.capacity_factor,
        )

        logger.info(f"Manufacturing GWP: {gwp_result.total_gwp_kgco2:.2f} kg-CO2eq")
        return gwp_result

    def _calculate_transport_gwp(self) -> float:
        """Calculate transport phase (A4) GWP.

        Simplified calculation: Aggregate LCAEvent records with phase='A4'.
        """
        logger.info("Calculating transport GWP...")

        # Filter transport events for this structure
        transport_events = [
            event
            for event in self.lci_data.events
            if event.structure_type == self.structure_type and event.phase == "A4"
        ]

        total_transport_gwp = sum(event.gwp_kgco2 for event in transport_events)

        logger.info(f"Transport GWP: {total_transport_gwp:.2f} kg-CO2eq ({len(transport_events)} events)")

        return total_transport_gwp

    def _calculate_o_and_m(self) -> float:
        """Calculate Operations & Maintenance phase (B) GWP.

        Aggregates LCAEvent records with phase='B'.
        """
        logger.info("Calculating O&M GWP...")

        # Filter O&M events for this structure
        o_and_m_events = [
            event
            for event in self.lci_data.events
            if event.structure_type == self.structure_type and event.phase == "B"
        ]

        total_o_and_m_gwp = sum(event.gwp_kgco2 for event in o_and_m_events)

        logger.info(f"O&M GWP: {total_o_and_m_gwp:.2f} kg-CO2eq ({len(o_and_m_events)} events)")

        return total_o_and_m_gwp

    def _calculate_eol(self) -> float:
        """Calculate End-of-Life phase (C) GWP.

        Aggregates LCAEvent records with phase='C'.
        """
        logger.info("Calculating EoL GWP...")

        # Filter EoL events for this structure
        eol_events = [
            event
            for event in self.lci_data.events
            if event.structure_type == self.structure_type and event.phase == "C"
        ]

        total_eol_gwp = sum(event.gwp_kgco2 for event in eol_events)

        logger.info(f"EoL GWP: {total_eol_gwp:.2f} kg-CO2eq ({len(eol_events)} events)")

        return total_eol_gwp

    def _compute_material_changes(self, material_overrides: Optional[Dict[str, str]] = None) -> None:
        """Apply material substitutions from scenario.

        Args:
            material_overrides: Dict mapping component_id -> new_material_id
        """
        if not material_overrides:
            return

        logger.info(f"Applying material overrides: {material_overrides}")

        for comp_id, new_material_id in material_overrides.items():
            if comp_id in self.components:
                old_material = self.components[comp_id].material_id
                self.components[comp_id].material_id = new_material_id
                logger.info(f"Component '{comp_id}': {old_material} → {new_material_id}")
            else:
                logger.warning(f"Component '{comp_id}' not found in {self.structure_type} components")

    def _write_detailed_log(
        self,
        cascade_result: "WeightCascadeResult",
        manufacturing_gwp: "GWPResult",
        transport_gwp: float,
        o_and_m_gwp: float,
        eol_gwp: float,
        result: "LCAResult",
    ) -> None:
        """Write detailed calculation log for debugging.

        Args:
            cascade_result: Weight cascade calculation result
            manufacturing_gwp: Manufacturing phase GWP result
            transport_gwp: Transport phase total GWP
            o_and_m_gwp: O&M phase total GWP
            eol_gwp: End-of-Life phase total GWP
            result: Final LCA result
        """
        from pathlib import Path
        import csv
        from collections import defaultdict

        # Generate log filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"lca_calculation_details_{timestamp}.log"
        log_path = Path("results") / log_filename

        # Ensure results directory exists
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with open(log_path, "w", encoding="utf-8") as f:
            # Header
            f.write("=" * 80 + "\n")
            f.write("LCA DETAILED CALCULATION LOG\n")
            f.write("=" * 80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Scenario: {self.scenario_name}\n")
            f.write(f"Structure Type: {self.structure_type}\n")
            f.write(f"Rated Power: {self.rated_power_mw} MW\n")
            f.write(f"Lifetime: {self.lifetime_years} years\n")
            f.write(f"Capacity Factor: {self.capacity_factor}\n")
            f.write("\n")

            # Weight Cascade Details
            f.write("=" * 80 + "\n")
            f.write("WEIGHT CASCADE ANALYSIS\n")
            f.write("=" * 80 + "\n")
            f.write(f"Enabled: {self.enable_weight_cascade}\n")
            f.write(f"Iterations: {cascade_result.iterations}\n")
            f.write(f"Converged: {cascade_result.convergence_achieved}\n")
            f.write("\n")

            f.write("Component Mass Changes:\n")
            f.write(f"{'Component ID':<30} {'Base Mass (kg)':<20} {'Final Mass (kg)':<20} {'Change (%)':<15}\n")
            f.write("-" * 85 + "\n")
            for comp_id, comp in cascade_result.updated_components.items():
                mass_change_pct = ((comp.mass_kg - comp.base_mass_kg) / comp.base_mass_kg * 100) if comp.base_mass_kg > 0 else 0
                f.write(
                    f"{comp_id:<30} {comp.base_mass_kg:<20,.2f} {comp.mass_kg:<20,.2f} {mass_change_pct:<15.2f}\n"
                )
            f.write("\n")

            # L1: Manufacturing Phase Details
            f.write("=" * 80 + "\n")
            f.write("L1: MANUFACTURING PHASE (DETAILED CALCULATION)\n")
            f.write("=" * 80 + "\n")
            f.write(f"Total Manufacturing GWP: {manufacturing_gwp.total_gwp_kgco2:,.2f} kg-CO2eq\n")
            f.write("\n")

            f.write("Component-Level Breakdown:\n")
            f.write(f"{'Component':<30} {'Mass (kg)':<15} {'Material':<20} {'GWP/kg':<15} {'GWP (kg-CO2eq)':<20} {'%':<10}\n")
            f.write("-" * 110 + "\n")
            for comp in manufacturing_gwp.component_breakdown:
                percentage = (comp.gwp_kgco2 / manufacturing_gwp.total_gwp_kgco2 * 100) if manufacturing_gwp.total_gwp_kgco2 > 0 else 0
                f.write(
                    f"{comp.component_name:<30} {comp.mass_kg:<15,.2f} {comp.material_id:<20} {comp.gwp_per_kg:<15.4f} {comp.gwp_kgco2:<20,.2f} {percentage:<10.2f}\n"
                )
            f.write("-" * 110 + "\n")
            f.write(f"{'TOTAL':<30} {'':<15} {'':<20} {'':<15} {manufacturing_gwp.total_gwp_kgco2:<20,.2f} {'100.00':<10}\n")
            f.write("\n")

            # Material aggregation
            f.write("Material-Level Aggregation:\n")
            material_totals = defaultdict(lambda: {"mass": 0.0, "gwp": 0.0})
            for comp in manufacturing_gwp.component_breakdown:
                material_totals[comp.material_id]["mass"] += comp.mass_kg
                material_totals[comp.material_id]["gwp"] += comp.gwp_kgco2

            f.write(f"{'Material':<20} {'Total Mass (kg)':<20} {'Total GWP (kg-CO2eq)':<25} {'%':<10}\n")
            f.write("-" * 75 + "\n")
            for material_id in sorted(material_totals.keys()):
                data = material_totals[material_id]
                percentage = (data["gwp"] / manufacturing_gwp.total_gwp_kgco2 * 100) if manufacturing_gwp.total_gwp_kgco2 > 0 else 0
                f.write(
                    f"{material_id:<20} {data['mass']:<20,.2f} {data['gwp']:<25,.2f} {percentage:<10.2f}\n"
                )
            f.write("\n")

            # L2: Transport Phase Details
            f.write("=" * 80 + "\n")
            f.write("L2: TRANSPORT PHASE\n")
            f.write("=" * 80 + "\n")
            f.write(f"Total Transport GWP: {transport_gwp:,.2f} kg-CO2eq\n")
            f.write("\n")

            transport_events = [
                event
                for event in self.lci_data.events
                if event.structure_type == self.structure_type and event.phase == "A4"
            ]
            if transport_events:
                f.write("Transport Events:\n")
                f.write(f"{'Event ID':<30} {'Vehicle Type':<20} {'Distance (km)':<15} {'Trips':<10} {'GWP (kg-CO2eq)':<20}\n")
                f.write("-" * 95 + "\n")
                for event in transport_events:
                    f.write(
                        f"{event.event_id:<30} {event.vehicle_type:<20} {event.distance_km:<15,.2f} {event.trips:<10} {event.gwp_kgco2:<20,.2f}\n"
                    )
            else:
                f.write("No transport events defined for this structure type.\n")
            f.write("\n")

            # L3: O&M Phase Details
            f.write("=" * 80 + "\n")
            f.write("L3: OPERATIONS & MAINTENANCE PHASE\n")
            f.write("=" * 80 + "\n")
            f.write(f"Total O&M GWP: {o_and_m_gwp:,.2f} kg-CO2eq\n")
            f.write("\n")

            o_and_m_events = [
                event
                for event in self.lci_data.events
                if event.structure_type == self.structure_type and event.phase == "B"
            ]
            if o_and_m_events:
                f.write("O&M Events:\n")
                f.write(f"{'Event ID':<30} {'Event Type':<20} {'Frequency/Year':<15} {'GWP (kg-CO2eq)':<20}\n")
                f.write("-" * 85 + "\n")
                for event in o_and_m_events:
                    freq = event.metadata.get("frequency_per_year", "N/A")
                    f.write(
                        f"{event.event_id:<30} {event.event_type:<20} {str(freq):<15} {event.gwp_kgco2:<20,.2f}\n"
                    )
            else:
                f.write("No O&M events defined for this structure type.\n")
            f.write("\n")

            # L4: End-of-Life Phase Details
            f.write("=" * 80 + "\n")
            f.write("L4: END-OF-LIFE PHASE\n")
            f.write("=" * 80 + "\n")
            f.write(f"Total EoL GWP: {eol_gwp:,.2f} kg-CO2eq\n")
            f.write("\n")

            eol_events = [
                event
                for event in self.lci_data.events
                if event.structure_type == self.structure_type and event.phase == "C"
            ]
            if eol_events:
                f.write("EoL Events:\n")
                f.write(f"{'Event ID':<30} {'Event Type':<20} {'Component':<20} {'GWP (kg-CO2eq)':<20}\n")
                f.write("-" * 90 + "\n")
                for event in eol_events:
                    f.write(
                        f"{event.event_id:<30} {event.event_type:<20} {event.component_ref:<20} {event.gwp_kgco2:<20,.2f}\n"
                    )
            else:
                f.write("No EoL events defined for this structure type.\n")
            f.write("\n")

            # Final Summary
            f.write("=" * 80 + "\n")
            f.write("FINAL SUMMARY\n")
            f.write("=" * 80 + "\n")
            f.write(f"{'Phase':<40} {'GWP (kg-CO2eq)':<20} {'Percentage (%)':<20}\n")
            f.write("-" * 80 + "\n")
            total = result.total_gwp_kgco2
            f.write(f"{'L1: Manufacturing':<40} {result.l1_manufacturing_kgco2:<20,.2f} {(result.l1_manufacturing_kgco2/total*100 if total > 0 else 0):<20.2f}\n")
            f.write(f"{'L2: Transport':<40} {result.l2_transport_kgco2:<20,.2f} {(result.l2_transport_kgco2/total*100 if total > 0 else 0):<20.2f}\n")
            f.write(f"{'L3: O&M':<40} {result.l3_o_and_m_kgco2:<20,.2f} {(result.l3_o_and_m_kgco2/total*100 if total > 0 else 0):<20.2f}\n")
            f.write(f"{'L4: End-of-Life':<40} {result.l4_eol_kgco2:<20,.2f} {(result.l4_eol_kgco2/total*100 if total > 0 else 0):<20.2f}\n")
            f.write("-" * 80 + "\n")
            f.write(f"{'TOTAL':<40} {total:<20,.2f} {'100.00':<20}\n")
            f.write("\n")

            f.write("Performance Metrics:\n")
            f.write(f"  Lifetime Energy Generation: {result.energy_generation_mwh:,.2f} MWh\n")
            f.write(f"  GWP Intensity: {result.intensity_gco2_per_kwh:.4f} g-CO2eq/kWh\n")
            f.write("\n")

            f.write("Calculation Verification:\n")
            phase_sum = result.l1_manufacturing_kgco2 + result.l2_transport_kgco2 + result.l3_o_and_m_kgco2 + result.l4_eol_kgco2
            f.write(f"  Sum of phases: {phase_sum:,.2f} kg-CO2eq\n")
            f.write(f"  Reported total: {total:,.2f} kg-CO2eq\n")
            f.write(f"  Difference: {abs(phase_sum - total):.6f} kg-CO2eq (should be ~0)\n")
            f.write("\n")

            f.write("=" * 80 + "\n")
            f.write("END OF DETAILED CALCULATION LOG\n")
            f.write("=" * 80 + "\n")

        logger.info(f"Detailed calculation log written to: {log_path}")


__all__ = [
    "LCAResult",
    "LCACalculator",
]
