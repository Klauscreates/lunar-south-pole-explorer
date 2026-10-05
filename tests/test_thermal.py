import math
import unittest
from dataclasses import replace

from science.thermal import (
    PanelEnvironment,
    PanelThermalParameters,
    advance_panel_thermal_electrical,
    evaluate_panel_thermal_electrical,
)


def parameters(**overrides):
    baseline = PanelThermalParameters(
        collecting_area_m2=1.0,
        radiating_area_m2=2.0,
        heat_capacity_j_k=5_000.0,
        solar_absorptivity=0.9,
        ir_emissivity=0.8,
        reference_efficiency=0.3,
        reference_temperature_k=300.0,
        efficiency_temperature_coefficient_per_k=-0.004,
        mount_conductance_w_k=0.5,
    )
    return replace(baseline, **overrides)


def environment(**overrides):
    baseline = PanelEnvironment(
        direct_normal_irradiance_w_m2=1_361.0,
        terrain_visible_fraction=1.0,
        incidence_cosine=1.0,
        structural_unobstructed_fraction=1.0,
        wall_reflected_solar_irradiance_w_m2=0.0,
        lunar_ir_irradiance_w_m2=0.0,
        mount_temperature_k=280.0,
        radiation_sink_temperature_k=3.0,
    )
    return replace(baseline, **overrides)


class ThermalElectricalTests(unittest.TestCase):
    def test_reference_temperature_power_and_energy_partition(self):
        state = evaluate_panel_thermal_electrical(
            300.0, parameters(), environment()
        )
        self.assertAlmostEqual(state["direct_solar_incident_power_w"], 1_361.0)
        self.assertAlmostEqual(state["electrical_output_w"], 408.3)
        self.assertAlmostEqual(state["absorbed_solar_power_w"], 1_224.9)
        self.assertAlmostEqual(state["solar_heat_power_w"], 816.6)
        self.assertAlmostEqual(
            state["absorbed_solar_power_w"],
            state["solar_heat_power_w"] + state["electrical_output_w"],
        )

    def test_hot_cell_derates_electrical_output(self):
        cold = evaluate_panel_thermal_electrical(
            300.0, parameters(), environment()
        )
        hot = evaluate_panel_thermal_electrical(
            350.0, parameters(), environment()
        )
        self.assertAlmostEqual(hot["temperature_derated_efficiency"], 0.24)
        self.assertLess(hot["electrical_output_w"], cold["electrical_output_w"])
        self.assertGreater(hot["solar_heat_power_w"], cold["solar_heat_power_w"])

    def test_sunlit_interval_heats_cell_and_derates_output(self):
        start = evaluate_panel_thermal_electrical(
            300.0, parameters(), environment()
        )
        result = advance_panel_thermal_electrical(
            300.0, 600.0, parameters(), environment()
        )
        self.assertGreater(result["cell_temperature_k"], 300.0)
        self.assertLess(result["electrical_output_w"], start["electrical_output_w"])
        self.assertGreaterEqual(result["integration_substeps"], 2)
        self.assertAlmostEqual(
            result["thermal_storage_change_j"],
            result["integrated_net_thermal_energy_j"],
            delta=1e-5,
        )
        self.assertLess(abs(result["energy_balance_residual_j"]), 1e-5)

    def test_nighttime_cools_without_solar_or_ir(self):
        dark = environment(
            direct_normal_irradiance_w_m2=0.0,
            terrain_visible_fraction=0.0,
            lunar_ir_irradiance_w_m2=0.0,
            mount_temperature_k=180.0,
        )
        first = advance_panel_thermal_electrical(300.0, 600.0, parameters(), dark)
        second = advance_panel_thermal_electrical(
            first["cell_temperature_k"], 600.0, parameters(), dark
        )
        self.assertEqual(first["electrical_output_w"], 0.0)
        self.assertLess(second["cell_temperature_k"], first["cell_temperature_k"])
        self.assertGreater(first["cell_temperature_k"], 0.0)

    def test_wall_reflection_adds_power_without_reapplying_direct_occlusion(self):
        blocked = environment(
            structural_unobstructed_fraction=0.0,
            wall_reflected_solar_irradiance_w_m2=200.0,
        )
        state = evaluate_panel_thermal_electrical(300.0, parameters(), blocked)
        self.assertEqual(state["direct_solar_incident_power_w"], 0.0)
        self.assertEqual(state["direct_solar_electrical_power_w"], 0.0)
        self.assertAlmostEqual(state["wall_reflected_incident_power_w"], 200.0)
        self.assertAlmostEqual(state["wall_reflected_electrical_power_w"], 60.0)
        self.assertAlmostEqual(state["solar_heat_power_w"], 120.0)

    def test_external_lunar_ir_increases_temperature(self):
        dark = environment(
            direct_normal_irradiance_w_m2=0.0,
            terrain_visible_fraction=0.0,
            mount_temperature_k=200.0,
        )
        without_ir = advance_panel_thermal_electrical(
            300.0, 600.0, parameters(), dark
        )
        with_ir = advance_panel_thermal_electrical(
            300.0,
            600.0,
            parameters(),
            replace(dark, lunar_ir_irradiance_w_m2=100.0),
        )
        self.assertGreater(
            with_ir["cell_temperature_k"], without_ir["cell_temperature_k"]
        )
        self.assertAlmostEqual(with_ir["absorbed_lunar_ir_power_w"], 80.0)

    def test_direct_power_multiplies_all_three_occlusion_and_pointing_factors(self):
        partly_exposed = environment(
            terrain_visible_fraction=0.5,
            incidence_cosine=0.4,
            structural_unobstructed_fraction=0.25,
        )
        state = evaluate_panel_thermal_electrical(
            300.0, parameters(), partly_exposed
        )
        self.assertAlmostEqual(state["direct_solar_incident_power_w"], 68.05)
        self.assertAlmostEqual(state["direct_solar_electrical_power_w"], 20.415)

    def test_strong_derating_feedback_uses_more_implicit_substeps(self):
        result = advance_panel_thermal_electrical(
            300.0, 600.0, parameters(heat_capacity_j_k=100.0), environment()
        )
        self.assertGreater(result["integration_substeps"], 2)
        self.assertLess(abs(result["energy_balance_residual_j"]), 1e-5)

    def test_1009_epochs_near_equilibrium_preserve_energy_closure(self):
        # A full-week series previously reached a near-steady state where a
        # loose relative-temperature bisection stop produced >1e-6 J of
        # *numerical* imbalance, despite each physical term being finite.
        hardware = parameters(radiating_area_m2=0.5)
        boundary = environment(
            direct_normal_irradiance_w_m2=1_363.832502,
            incidence_cosine=0.9917232023692001,
            structural_unobstructed_fraction=0.75,
        )
        temperature = 416.38411200395353
        for epoch in range(1_009):
            # Minute variation emulates a real site's slowly changing Sun
            # geometry while retaining the exact formerly failing first step.
            current = replace(
                boundary,
                direct_normal_irradiance_w_m2=(
                    boundary.direct_normal_irradiance_w_m2
                    + 0.5 * math.sin(epoch * 0.02)
                ),
            )
            result = advance_panel_thermal_electrical(
                temperature, 600.0, hardware, current
            )
            self.assertTrue(math.isfinite(result["cell_temperature_k"]))
            self.assertLess(abs(result["energy_balance_residual_j"]), 1e-6)
            temperature = result["cell_temperature_k"]

    def test_efficiency_is_bounded_by_absorbed_solar_fraction(self):
        high_ref = parameters(reference_efficiency=0.8)
        very_cold = evaluate_panel_thermal_electrical(
            1.0, high_ref, environment()
        )
        very_hot = evaluate_panel_thermal_electrical(
            1_000.0, high_ref, environment()
        )
        self.assertEqual(very_cold["temperature_derated_efficiency"], 0.9)
        self.assertEqual(very_hot["temperature_derated_efficiency"], 0.0)
        self.assertLessEqual(
            very_cold["electrical_output_w"],
            very_cold["absorbed_solar_power_w"],
        )

    def test_zero_interval_preserves_state_and_reports_no_stored_energy(self):
        result = advance_panel_thermal_electrical(
            300.0, 0.0, parameters(), environment()
        )
        self.assertEqual(result["cell_temperature_k"], 300.0)
        self.assertEqual(result["integration_substeps"], 0)
        self.assertEqual(result["energy_balance_residual_j"], 0.0)

    def test_invalid_hardware_and_environment_fail_closed(self):
        bad_hardware = (
            parameters(collecting_area_m2=0.0),
            parameters(heat_capacity_j_k=math.nan),
            parameters(heat_capacity_j_k=10**400),
            parameters(solar_absorptivity=1.2),
            parameters(reference_efficiency=0.95),
            parameters(efficiency_temperature_coefficient_per_k=0.001),
            parameters(reference_temperature_k=0.0),
            parameters(mount_conductance_w_k=-1.0),
        )
        bad_environments = (
            environment(direct_normal_irradiance_w_m2=math.inf),
            environment(wall_reflected_solar_irradiance_w_m2=-1.0),
            environment(lunar_ir_irradiance_w_m2=math.nan),
            environment(incidence_cosine=1.1),
            environment(structural_unobstructed_fraction=-0.1),
            environment(mount_temperature_k=0.0),
            environment(radiation_sink_temperature_k=math.inf),
        )
        for hardware in bad_hardware:
            with self.subTest(hardware=hardware), self.assertRaises(ValueError):
                evaluate_panel_thermal_electrical(300.0, hardware, environment())
        for boundary in bad_environments:
            with self.subTest(boundary=boundary), self.assertRaises(ValueError):
                evaluate_panel_thermal_electrical(300.0, parameters(), boundary)

    def test_invalid_time_and_temperature_fail_closed(self):
        for previous, dt in (
            (0.0, 600.0),
            (-1.0, 600.0),
            (math.nan, 600.0),
            (300.0, math.inf),
            (300.0, -1.0),
            (300.0, True),
            (300.0, 3_000_001.0),
        ):
            with self.subTest(previous=previous, dt=dt), self.assertRaises(ValueError):
                advance_panel_thermal_electrical(
                    previous, dt, parameters(), environment()
                )

    def test_unbounded_derived_power_and_temperature_fail_closed(self):
        with self.assertRaises(ValueError):
            evaluate_panel_thermal_electrical(
                300.0,
                parameters(collecting_area_m2=1e300),
                environment(direct_normal_irradiance_w_m2=1e300),
            )
        with self.assertRaises(ValueError):
            advance_panel_thermal_electrical(
                300.0,
                600.0,
                parameters(heat_capacity_j_k=1.0),
                environment(direct_normal_irradiance_w_m2=1e200),
            )


if __name__ == "__main__":
    unittest.main()
