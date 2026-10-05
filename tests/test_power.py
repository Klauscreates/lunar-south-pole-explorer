import math
import unittest

from science.config import PanelConfig
from science.errors import ConfigurationError
from science.power import estimate_solar_input, panel_incidence


def sun_state(azimuth=90.0, elevation=30.0, fraction=1.0):
    return {
        "azimuth_deg": azimuth,
        "elevation_deg": elevation,
        "distance_km": 149_597_870.7,
        "visibility_fraction": fraction,
    }


class PowerModelTests(unittest.TestCase):
    def test_tracking_panel_uses_full_incidence(self):
        result = estimate_solar_input(
            sun_state(),
            PanelConfig(panel_area_m2=2.0, efficiency=0.25),
        )
        self.assertEqual(result["incidence_cosine"], 1.0)
        self.assertAlmostEqual(result["estimated_electrical_output_w"], 680.5)

    def test_horizontal_panel_uses_sine_of_elevation(self):
        result = estimate_solar_input(
            sun_state(elevation=30.0),
            PanelConfig(orientation_mode="horizontal_fixed"),
        )
        self.assertAlmostEqual(result["incidence_cosine"], 0.5, places=8)

    def test_partial_disk_scales_power(self):
        result = estimate_solar_input(
            sun_state(fraction=0.25),
            PanelConfig(panel_area_m2=1.0, efficiency=1.0),
        )
        self.assertAlmostEqual(result["estimated_incident_power_w"], 340.25)

    def test_custom_normal_uses_enu_convention(self):
        result = estimate_solar_input(
            sun_state(azimuth=90.0, elevation=0.0),
            PanelConfig(
                orientation_mode="custom_normal",
                custom_normal_enu=(1.0, 0.0, 0.0),
            ),
        )
        self.assertAlmostEqual(result["incidence_cosine"], 1.0, places=9)

    def test_low_sun_exposes_horizontal_cosine_loss(self):
        horizontal = estimate_solar_input(
            sun_state(azimuth=90.0, elevation=2.0),
            PanelConfig(orientation_mode="horizontal_fixed"),
        )
        self.assertAlmostEqual(
            horizontal["incidence_cosine"], math.sin(math.radians(2.0)), places=8
        )
        self.assertAlmostEqual(
            horizontal["estimated_electrical_output_w"],
            1361.0 * 0.30 * math.sin(math.radians(2.0)),
            places=5,
        )
        self.assertGreater(horizontal["cosine_loss_fraction"], 0.96)

    def test_fixed_vertical_panel_respects_normal_azimuth(self):
        panel = PanelConfig(
            orientation_mode="fixed_tilt",
            tilt_deg_from_horizontal=90.0,
            azimuth_deg=90.0,
        )
        facing = panel_incidence(90.0, 2.0, panel)
        opposite = panel_incidence(270.0, 2.0, panel)
        self.assertAlmostEqual(
            facing["incidence_cosine"], math.cos(math.radians(2.0)), places=8
        )
        self.assertEqual(opposite["incidence_cosine"], 0.0)
        self.assertGreater(opposite["incidence_angle_deg"], 90.0)
        self.assertEqual(facing["effective_panel_azimuth_deg"], 90.0)
        self.assertEqual(facing["effective_panel_tilt_deg"], 90.0)

    def test_gimbal_constraints_limit_yaw_and_tilt(self):
        panel = PanelConfig(
            orientation_mode="gimbal_limited",
            tracking_tilt_min_deg=0.0,
            tracking_tilt_max_deg=45.0,
            tracking_azimuth_center_deg=0.0,
            tracking_azimuth_half_range_deg=30.0,
        )
        result = panel_incidence(90.0, 2.0, panel)
        expected = (
            math.sin(math.radians(45.0))
            * math.cos(math.radians(2.0))
            * math.cos(math.radians(60.0))
            + math.cos(math.radians(45.0)) * math.sin(math.radians(2.0))
        )
        self.assertAlmostEqual(result["incidence_cosine"], expected, places=8)
        self.assertEqual(result["effective_panel_tilt_deg"], 45.0)
        self.assertEqual(result["effective_panel_azimuth_deg"], 30.0)
        self.assertTrue(result["tracking_limit_active"])

    def test_gimbal_wraps_azimuth_and_can_reach_sun(self):
        panel = PanelConfig(
            orientation_mode="gimbal_limited",
            tracking_tilt_max_deg=90.0,
            tracking_azimuth_center_deg=350.0,
            tracking_azimuth_half_range_deg=25.0,
        )
        result = panel_incidence(10.0, 2.0, panel)
        self.assertAlmostEqual(result["incidence_cosine"], 1.0, places=8)
        self.assertAlmostEqual(result["effective_panel_tilt_deg"], 88.0)
        self.assertEqual(result["effective_panel_azimuth_deg"], 10.0)
        self.assertFalse(result["tracking_limit_active"])

    def test_geometric_visibility_is_separate_from_panel_pointing(self):
        panel = PanelConfig(
            orientation_mode="fixed_tilt",
            tilt_deg_from_horizontal=90.0,
            azimuth_deg=90.0,
        )
        # An elevated observer may see a slightly negative-elevation Sun above
        # a depressed terrain horizon; do not discard that direction outright.
        visible = estimate_solar_input(
            sun_state(azimuth=90.0, elevation=-2.0), panel
        )
        blocked = estimate_solar_input(
            sun_state(azimuth=90.0, elevation=-2.0, fraction=0.0), panel
        )
        self.assertGreater(visible["estimated_electrical_output_w"], 0.0)
        self.assertEqual(blocked["estimated_electrical_output_w"], 0.0)
        self.assertFalse(blocked["panel_illuminated"])

    def test_invalid_pointing_envelopes_are_rejected(self):
        bad_panels = [
            PanelConfig(orientation_mode="fixed_tilt", tilt_deg_from_horizontal=181),
            PanelConfig(
                orientation_mode="gimbal_limited",
                tracking_tilt_min_deg=70,
                tracking_tilt_max_deg=60,
            ),
            PanelConfig(
                orientation_mode="gimbal_limited",
                tracking_azimuth_half_range_deg=200,
            ),
            PanelConfig(orientation_mode="fixed_tilt", azimuth_deg=float("nan")),
        ]
        for panel in bad_panels:
            with self.subTest(panel=panel), self.assertRaises(ConfigurationError):
                panel.validate()

    def test_invalid_sun_input_rejected(self):
        with self.assertRaises(ValueError):
            estimate_solar_input(sun_state(fraction=1.5), PanelConfig())
        with self.assertRaises(ValueError):
            estimate_solar_input(
                {**sun_state(), "distance_km": 0.0}, PanelConfig()
            )


if __name__ == "__main__":
    unittest.main()
