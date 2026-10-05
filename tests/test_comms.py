import math
import unittest

from science.comms import classify_comms_potential


def earth_sample(elevation, horizon, visible_fraction=1.0):
    return {
        "elevation_deg": elevation,
        "terrain_horizon_deg": horizon,
        "clearance_deg": elevation - horizon,
        "visibility_fraction": visible_fraction,
    }


class CommsPotentialTests(unittest.TestCase):
    def test_center_below_or_on_skyline_has_zero_index(self):
        for elevation, horizon in ((1.0, 1.1), (1.0, 1.0)):
            with self.subTest(elevation=elevation, horizon=horizon):
                result = classify_comms_potential(earth_sample(elevation, horizon))
                self.assertEqual(result["classification"], "BLOCKED")
                self.assertEqual(result["potential_index_percent"], 0)
                self.assertFalse(result["center_clear"])

    def test_partial_disk_can_be_visible_with_center_blocked(self):
        result = classify_comms_potential(earth_sample(1.0, 1.1, 0.25))
        self.assertEqual(result["potential_index_percent"], 0)
        self.assertFalse(result["center_clear"])

    def test_low_absolute_elevation_is_marginal_including_two_degrees(self):
        for elevation in (0.5, 2.0):
            with self.subTest(elevation=elevation):
                result = classify_comms_potential(earth_sample(elevation, -1.0))
                self.assertEqual(result["classification"], "MARGINAL")
                self.assertEqual(result["potential_index_percent"], 30)
                self.assertTrue(result["center_clear"])

    def test_above_two_degrees_and_skyline_is_clear(self):
        result = classify_comms_potential(earth_sample(2.000001, 2.0, 0.5))
        self.assertEqual(result["classification"], "CLEAR")
        self.assertEqual(result["potential_index_percent"], 100)

    def test_invalid_or_inconsistent_geometry_fails_closed(self):
        invalid = [
            {"elevation_deg": 3.0},
            earth_sample(math.nan, 0.0),
            earth_sample(2.0, 0.0, 1.1),
            {**earth_sample(2.0, 1.0), "clearance_deg": 0.1},
        ]
        for sample in invalid:
            with self.subTest(sample=sample):
                with self.assertRaises(ValueError):
                    classify_comms_potential(sample)


if __name__ == "__main__":
    unittest.main()
