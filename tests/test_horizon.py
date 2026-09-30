import tempfile
import unittest
from pathlib import Path

import numpy as np

from science.horizon.engine import HorizonProfile, combine_horizon_profiles


def profile(elevations, distances, key):
    values = np.asarray(elevations, dtype=np.float64)
    return HorizonProfile(
        azimuth_deg=np.arange(len(values), dtype=np.float64) * 90.0,
        elevation_deg=values,
        obstruction_distance_m=np.asarray(distances, dtype=np.float64),
        metadata={
            "cache_key_sha256": key,
            "azimuth_convention": "0 deg north, 90 east, clockwise",
            "azimuth_step_deg": 90.0,
            "maximum_search_radius_m": max(distances),
            "radial_step_m": min(distances),
            "lunar_reference_radius_m": 1_737_400.0,
            "observer_radius_m": 1_737_402.0,
            "observer_height_above_terrain_m": 2.0,
            "site_terrain_elevation_m": 0.0,
            "cache_hit": False,
        },
    )


class HorizonTests(unittest.TestCase):
    def test_periodic_interpolation_wraps_north(self):
        horizon = profile([0.0, 9.0, 18.0, 9.0], [1, 1, 1, 1], "a")
        self.assertAlmostEqual(horizon.elevation_at(45.0), 4.5)
        self.assertAlmostEqual(horizon.elevation_at(315.0), 4.5)
        self.assertAlmostEqual(horizon.elevation_at(-45.0), 4.5)

    def test_multiscale_profile_selects_highest_obstruction(self):
        local = profile([1.0, 5.0, -1.0, 3.0], [10, 20, 30, 40], "local")
        outer = profile([2.0, 4.0, 0.0, 8.0], [100, 200, 300, 400], "outer")
        with tempfile.TemporaryDirectory() as directory:
            merged = combine_horizon_profiles(local, outer, Path(directory))
        np.testing.assert_allclose(merged.elevation_deg, [2.0, 5.0, 0.0, 8.0])
        np.testing.assert_allclose(
            merged.obstruction_distance_m, [100.0, 20.0, 300.0, 400.0]
        )
        self.assertEqual(merged.metadata["local_dominant_azimuth_count"], 1)


if __name__ == "__main__":
    unittest.main()

