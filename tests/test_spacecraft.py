"""Synthetic-only geometry tests; no test mesh represents flight hardware."""

import hashlib
import json
import math
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from science.errors import ConfigurationError
from science.spacecraft import evaluate_spacecraft_geometry, load_spacecraft_geometry


WALL_X_OBJ = """# TEST-ONLY wall, not a spacecraft CAD artifact
o wall_x
v 1 -1 -1
v 1 1 -1
v 1 1 1
v 1 -1 1
f 1 2 3
f 1 3 4
"""

WALL_Y_OBJ = """# TEST-ONLY forward wall
o wall_forward
v -1 1 -1
v 1 1 -1
v 1 1 1
v -1 1 1
f 1 2 3
f 1 3 4
"""


def _manifest(mesh_bytes, *, mesh_format="obj", panels=None, antennas=None):
    return {
        "schema_version": "1.0.0",
        "model_id": "synthetic_test_only",
        "provenance": {
            "source": "test-only hand-authored wall",
            "revision": "test-1",
            "spacecraft": "NONE--not-flight-hardware",
        },
        "mesh": {
            "path": f"synthetic.{mesh_format}",
            "sha256": hashlib.sha256(mesh_bytes).hexdigest(),
            "format": mesh_format,
            "units": "m",
            "scale_to_m": 1.0,
        },
        "panels": panels if panels is not None else [
            {
                "id": "array_a",
                "area_m2": 2.0,
                "normal_body": [1.0, 0.0, 0.0],
                "sample_points_m": [[0.0, 0.0, 0.0], [0.0, 3.0, 0.0]],
                "sample_weights": [0.25, 0.75],
            }
        ],
        "antennas": antennas if antennas is not None else [
            {"id": "earth_a", "phase_center_m": [0.0, 0.0, 0.0]},
            {"id": "earth_b", "phase_center_m": [0.0, 3.0, 0.0]},
        ],
    }


def _evaluate(model, **changes):
    params = dict(
        sun_azimuth_deg=90.0,
        sun_elevation_deg=0.0,
        earth_azimuth_deg=90.0,
        earth_elevation_deg=0.0,
        yaw_deg=0.0,
        pitch_deg=0.0,
        roll_deg=0.0,
    )
    params.update(changes)
    return evaluate_spacecraft_geometry(model, **params)


class SpacecraftGeometryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def load(self, mesh=WALL_X_OBJ, *, manifest=None, mesh_format="obj"):
        mesh_bytes = mesh.encode("utf-8") if isinstance(mesh, str) else mesh
        config = manifest or _manifest(mesh_bytes, mesh_format=mesh_format)
        (self.root / config["mesh"]["path"]).write_bytes(mesh_bytes)
        path = self.root / "model.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return load_spacecraft_geometry(path, allowed_root=self.root)

    def test_weighted_partial_panel_and_named_antenna_blocking(self):
        model = self.load()
        result = _evaluate(model)
        panel = result["panels"][0]
        self.assertEqual(result["model_status"], "CONFIGURED_UNVALIDATED")
        self.assertEqual(result["triangle_count"], 2)
        self.assertEqual(panel["ray_target"], "SUN_CENTER")
        self.assertEqual(panel["sample_count"], 2)
        self.assertEqual(panel["unoccluded_sample_fraction"], 0.75)
        self.assertEqual(panel["illuminated_sample_fraction"], 0.75)
        self.assertAlmostEqual(panel["incidence_cosine"], 1.0)
        self.assertAlmostEqual(panel["effective_direct_area_m2"], 1.5)
        self.assertEqual(panel["obstruction_ids"], ["wall_x"])
        self.assertEqual(panel["samples"][0]["obstruction_id"], "wall_x")
        self.assertAlmostEqual(panel["samples"][0]["hit_distance_m"], 1.0)
        self.assertEqual(result["antennas"][0]["ray_target"], "EARTH_CENTER")
        self.assertFalse(result["antennas"][0]["self_los_clear"])
        self.assertEqual(result["antennas"][0]["obstruction_ids"], ["wall_x"])
        self.assertTrue(result["antennas"][1]["self_los_clear"])
        self.assertIn("center-ray", result["panel_sampling_scope"])

    def test_opposite_and_grazing_directions_do_not_hit_wall(self):
        model = self.load()
        opposite = _evaluate(model, sun_azimuth_deg=270.0, earth_azimuth_deg=270.0)
        self.assertEqual(opposite["panels"][0]["unoccluded_sample_fraction"], 1.0)
        self.assertEqual(opposite["panels"][0]["incidence_cosine"], 0.0)
        self.assertEqual(opposite["panels"][0]["illuminated_sample_fraction"], 0.0)
        self.assertTrue(opposite["antennas"][0]["self_los_clear"])
        grazing = _evaluate(model, sun_azimuth_deg=0.0, earth_azimuth_deg=0.0)
        self.assertEqual(grazing["panels"][0]["unoccluded_sample_fraction"], 1.0)
        self.assertEqual(grazing["panels"][0]["incidence_cosine"], 0.0)
        self.assertTrue(grazing["antennas"][0]["self_los_clear"])
        near_grazing = _evaluate(model, earth_azimuth_deg=1e-8)
        self.assertTrue(near_grazing["antennas"][0]["self_los_clear"])

    def test_yaw_pitch_and_roll_follow_declared_body_to_enu_convention(self):
        panel = {
            "id": "forward_panel",
            "area_m2": 1.0,
            "normal_body": [0.0, 1.0, 0.0],
            "sample_points_m": [[0.0, 0.0, 0.0]],
            "sample_weights": [1.0],
        }
        manifest = _manifest(WALL_Y_OBJ.encode(), panels=[panel], antennas=[
            {"id": "forward_antenna", "phase_center_m": [0, 0, 0]}
        ])
        model = self.load(WALL_Y_OBJ, manifest=manifest)
        yaw_zero = _evaluate(model)
        yaw_east = _evaluate(model, yaw_deg=90.0)
        self.assertTrue(yaw_zero["antennas"][0]["self_los_clear"])
        self.assertFalse(yaw_east["antennas"][0]["self_los_clear"])
        self.assertAlmostEqual(yaw_east["panels"][0]["incidence_cosine"], 1.0)
        pitch_up = _evaluate(
            model, sun_azimuth_deg=0.0, sun_elevation_deg=90.0,
            earth_azimuth_deg=0.0, earth_elevation_deg=90.0,
            pitch_deg=90.0,
        )
        self.assertFalse(pitch_up["antennas"][0]["self_los_clear"])
        self.assertAlmostEqual(pitch_up["panels"][0]["incidence_cosine"], 1.0)
        # +roll lowers +X. A downward local ray maps to body +X at +90 roll.
        roll_matrix = _evaluate(model, roll_deg=90.0, earth_elevation_deg=-90.0)
        self.assertAlmostEqual(roll_matrix["earth_center_direction_body"][0], 1.0)

    def test_surface_origin_avoids_self_hit_but_nearby_wall_is_seen(self):
        near_wall = WALL_X_OBJ.replace("v 1 ", "v 0.000002 ")
        model = self.load(near_wall)
        result = _evaluate(model)
        self.assertFalse(result["antennas"][0]["self_los_clear"])
        self.assertAlmostEqual(result["antennas"][0]["hit_distance_m"], 2e-6, places=12)
        on_surface = WALL_X_OBJ.replace("v 1 ", "v 0 ")
        surface_model = self.load(on_surface)
        surface = _evaluate(surface_model)
        self.assertTrue(surface["antennas"][0]["self_los_clear"])

    def test_explicit_mesh_scale_and_binary_stl(self):
        # Test-only wall is authored in centimeters and explicitly scaled.
        centimeter_wall = WALL_X_OBJ.replace("v 1 ", "v 100 ").replace("-1", "-100")
        mesh_bytes = centimeter_wall.encode()
        manifest = _manifest(mesh_bytes)
        manifest["mesh"]["scale_to_m"] = 0.01
        model = self.load(centimeter_wall, manifest=manifest)
        self.assertFalse(_evaluate(model)["antennas"][0]["self_los_clear"])

        header = b"TEST ONLY binary STL".ljust(80, b"\0")
        vertices = (0, 0, 0, 1, -1, -1, 1, 1, -1, 1, 0, 1)
        binary = header + struct.pack("<I", 1) + struct.pack("<12fH", *vertices, 0)
        stl_model = self.load(binary, mesh_format="stl")
        self.assertFalse(_evaluate(stl_model)["antennas"][0]["self_los_clear"])
        self.assertEqual(_evaluate(stl_model)["antennas"][0]["obstruction_ids"], ["mesh"])

    def test_ascii_stl_and_invalid_geometry_fail_closed(self):
        ascii_stl = """solid test_wall
facet normal 1 0 0
outer loop
vertex 1 -1 -1
vertex 1 1 -1
vertex 1 0 1
endloop
endfacet
endsolid test_wall
"""
        model = self.load(ascii_stl, mesh_format="stl")
        self.assertEqual(_evaluate(model)["antennas"][0]["obstruction_ids"], ["test_wall"])
        invalid_meshes = [
            WALL_X_OBJ.replace("f 1 2 3", "f 1 1 1"),
            WALL_X_OBJ.replace("f 1 2 3", "f 1 2 3 4"),
            WALL_X_OBJ.replace("v 1 -1 -1", "v NaN -1 -1"),
        ]
        for mesh in invalid_meshes:
            with self.subTest(mesh=mesh[:50]), self.assertRaises(ConfigurationError):
                self.load(mesh)

    def test_bvh_chooses_nearest_named_obstruction_across_many_triangles(self):
        # More than eight triangles forces the acceleration tree to split.
        lines = ["# TEST ONLY stacked walls"]
        for distance in range(1, 13):
            first = 3 * (distance - 1) + 1
            lines.extend([
                f"o wall_{distance}",
                f"v {distance} -2 -2",
                f"v {distance} 2 -2",
                f"v {distance} 0 2",
                f"f {first} {first + 1} {first + 2}",
            ])
        model = self.load("\n".join(lines))
        result = _evaluate(model)
        self.assertEqual(result["triangle_count"], 12)
        self.assertEqual(result["antennas"][0]["obstruction_ids"], ["wall_1"])
        self.assertAlmostEqual(result["antennas"][0]["hit_distance_m"], 1.0)

    def test_manifest_checksum_sensor_and_path_validation(self):
        mesh_bytes = WALL_X_OBJ.encode()
        base = _manifest(mesh_bytes)
        mutations = [
            lambda data: data["mesh"].update(sha256="0" * 64),
            lambda data: data["mesh"].update(units="cm"),
            lambda data: data["mesh"].update(scale_to_m=math.inf),
            lambda data: data["mesh"].update(path="../outside.obj"),
            lambda data: data["panels"][0].update(normal_body=[0, 0, 0]),
            lambda data: data["panels"][0].update(sample_weights=[0.5, 0.2]),
            lambda data: data["panels"][0].update(sample_points_m=[[math.nan, 0, 0], [0, 3, 0]]),
            lambda data: data["antennas"].append(data["antennas"][0]),
        ]
        for mutate in mutations:
            data = json.loads(json.dumps(base))
            mutate(data)
            with self.subTest(mutation=mutate.__code__.co_firstlineno), self.assertRaises(ConfigurationError):
                if data["mesh"]["path"].startswith(".."):
                    (self.root / "synthetic.obj").write_bytes(mesh_bytes)
                    (self.root / "model.json").write_text(json.dumps(data))
                    load_spacecraft_geometry(self.root / "model.json", allowed_root=self.root)
                else:
                    self.load(manifest=data)
        good = self.load()
        with self.assertRaises(ConfigurationError):
            _evaluate(good, sun_azimuth_deg=float("nan"))
        with self.assertRaises(ConfigurationError):
            _evaluate(good, pitch_deg=91.0)
        with self.assertRaises(ConfigurationError):
            _evaluate(good, earth_azimuth_deg=1e308)

    def test_duplicate_keys_size_caps_and_symlink_escape_fail_closed(self):
        mesh_bytes = WALL_X_OBJ.encode()
        (self.root / "synthetic.obj").write_bytes(mesh_bytes)
        manifest_path = self.root / "model.json"
        manifest_path.write_text('{"schema_version":"1.0.0","schema_version":"1.0.0"}')
        with self.assertRaises(ConfigurationError):
            load_spacecraft_geometry(manifest_path, allowed_root=self.root)
        manifest_path.write_text(json.dumps(_manifest(mesh_bytes)))
        with patch("science.spacecraft.MAX_MESH_BYTES", 10):
            with self.assertRaises(ConfigurationError):
                load_spacecraft_geometry(manifest_path, allowed_root=self.root)
        with patch("science.spacecraft.MAX_MANIFEST_BYTES", 10):
            with self.assertRaises(ConfigurationError):
                load_spacecraft_geometry(manifest_path, allowed_root=self.root)

        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "external.obj"
            external.write_bytes(mesh_bytes)
            (self.root / "synthetic.obj").unlink()
            (self.root / "synthetic.obj").symlink_to(external)
            with self.assertRaises(ConfigurationError):
                load_spacecraft_geometry(manifest_path, allowed_root=self.root)


if __name__ == "__main__":
    unittest.main()
