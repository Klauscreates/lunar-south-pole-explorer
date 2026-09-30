import math
import unittest

from science.config import PanelConfig
from science.power import estimate_solar_input


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


if __name__ == "__main__":
    unittest.main()

