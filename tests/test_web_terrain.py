"""Visual terrain must retain lunar datum, source values and seamless tile edges."""

import json
import unittest
from pathlib import Path

import numpy as np

from scripts.terrain_server import Terrain, png

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    (ROOT / "data/web_terrain/manifest.json").exists(), "Prepare web terrain first"
)
class WebTerrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.terrain = Terrain()

    def test_reference_site_retains_science_elevation(self):
        point = self.terrain.inspect(0, -89.9)
        self.assertAlmostEqual(point["elevation_m"], 628.2297973632812, places=6)
        self.assertEqual(point["resolution_m"], 10)
        self.assertEqual(point["frame"], "MOON_ME / DE421")

    def test_positive_east_projection_has_positive_x(self):
        x, y = self.terrain.project(np.array([45]), np.array([-89.9]))
        self.assertGreater(x[0], 0)
        self.assertAlmostEqual(x[0], y[0], places=9)

    def test_polar_height_tiles_match_shared_edge(self):
        level, y = 9, 511
        left, _ = self.terrain.tile("height", level, 510, y)
        right, _ = self.terrain.tile("height", level, 511, y)
        left = np.frombuffer(left, dtype="<f4").reshape(513, 17)
        right = np.frombuffer(right, dtype="<f4").reshape(513, 17)
        np.testing.assert_allclose(left[:, -1], right[:, 0], atol=1e-4)
        self.assertTrue(np.isfinite(left).all())

    def test_global_and_polar_shapes_are_explicit(self):
        body, mime = self.terrain.tile("height", 0, 0, 0)
        self.assertEqual(len(body), 65 * 65 * 4)
        self.assertEqual(mime, "application/octet-stream")
        body, _ = self.terrain.tile("height", 6, 64, 63)
        self.assertEqual(len(body), 17 * 513 * 4)

    def test_global_heights_are_metres_not_kilometres(self):
        values = self.terrain.grids["global"][1]
        self.assertGreater(float(values.max()), 5000)
        self.assertLess(float(values.min()), -5000)
        self.assertLess(float(values.max()), 15000)

    def test_nasa_thematic_values_and_no_coverage(self):
        point = self.terrain.inspect(0, -89.9)
        self.assertAlmostEqual(point["slope"], 22.3145103455, places=5)
        self.assertEqual(point["psr"], 0)
        self.assertGreater(point["effective_resolution"], 0)
        outside = self.terrain.inspect(0, 0)
        self.assertIsNone(outside["slope"])
        self.assertIsNone(outside["psr"])

    def test_thematic_provenance_retained(self):
        manifest = json.loads(
            (ROOT / "apps/web/public/terrain/manifest.json").read_text()
        )
        self.assertEqual(manifest["radius_m"], 1737400)
        self.assertEqual(len(manifest["sources"]), 9)
        for source in manifest["sources"]:
            self.assertTrue(source["source_url"].startswith("https://"))
            self.assertEqual(len(source["sha256"]), 64)

    def test_overlay_png_has_alpha_channel(self):
        image = png(np.zeros((4, 4, 4), dtype="uint8"))
        self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(image[25], 6)
