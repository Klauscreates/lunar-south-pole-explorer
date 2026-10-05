"""One-degree export must preserve raycast provenance and original samples."""

import unittest

import numpy as np

from science.errors import TerrainDataError
from science.horizon import HorizonProfile, build_one_degree_horizon_mask


def raycast(step_deg=0.5):
    azimuth = np.arange(0.0, 360.0, step_deg)
    return HorizonProfile(
        azimuth_deg=azimuth,
        elevation_deg=azimuth / 100.0,
        obstruction_distance_m=100.0 + azimuth,
        metadata={
            "algorithm": "highest-obstruction-multiscale-v1",
            "azimuth_step_deg": step_deg,
            "cache_key_sha256": "full-profile-sha256",
            "local_component_cache_key_sha256": "local-sha256",
            "outer_component_cache_key_sha256": "outer-sha256",
            "maximum_search_radius_m": 200_000.0,
        },
    )


class HorizonMaskTests(unittest.TestCase):
    def test_selects_360_original_integer_azimuth_rays(self):
        source = raycast()
        # The neighboring half-degree ray differs sharply. The mask must not
        # interpolate from it when an integer-azimuth ray already exists.
        source.elevation_deg[1] = 1000.0
        mask = build_one_degree_horizon_mask(source)
        self.assertEqual(len(mask["profile"]), 360)
        self.assertEqual(mask["profile"][0]["azimuth_deg"], 0)
        self.assertEqual(mask["profile"][1]["azimuth_deg"], 1)
        self.assertEqual(mask["profile"][1]["minimum_clearance_elevation_deg"], 0.01)
        self.assertEqual(mask["profile"][359]["obstruction_distance_m"], 459.0)
        self.assertEqual(mask["metadata"]["source_raycast_ray_count"], 720)
        self.assertEqual(mask["metadata"]["source_raycast_azimuth_step_deg"], 0.5)
        self.assertEqual(mask, build_one_degree_horizon_mask(source))

    def test_accepts_native_one_degree_raycast(self):
        mask = build_one_degree_horizon_mask(raycast(1.0))
        self.assertEqual(mask["metadata"]["source_raycast_ray_count"], 360)
        self.assertEqual(mask["profile"][180]["minimum_clearance_elevation_deg"], 1.8)

    def test_refuses_coarser_or_non_dividing_grid(self):
        for step in (2.0, 0.8):
            with self.subTest(step=step), self.assertRaises(TerrainDataError):
                build_one_degree_horizon_mask(raycast(step))

    def test_refuses_missing_and_irregular_rays(self):
        missing = raycast()
        missing.elevation_deg[0] = np.nan
        irregular = raycast()
        irregular.azimuth_deg[2] = 1.1
        negative_distance = raycast()
        negative_distance.obstruction_distance_m[2] = -1.0
        for source in (missing, irregular, negative_distance):
            with self.assertRaises(TerrainDataError):
                build_one_degree_horizon_mask(source)

    def test_refuses_undocumented_or_unidentified_source(self):
        undocumented = raycast()
        undocumented.metadata["algorithm"] = "made-up-values"
        unidentified = raycast()
        unidentified.metadata.pop("cache_key_sha256")
        for source in (undocumented, unidentified):
            with self.assertRaises(TerrainDataError):
                build_one_degree_horizon_mask(source)


if __name__ == "__main__":
    unittest.main()
