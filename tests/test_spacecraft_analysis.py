"""End-to-end spacecraft analysis tests using synthetic, non-flight fixtures only."""

from __future__ import annotations

import hashlib
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from pathlib import Path

from science.errors import ConfigurationError
from science.power import ASTRONOMICAL_UNIT_KM, direct_solar_irradiance_w_m2
from science.spacecraft_analysis import analyze_spacecraft_files
from science.visibility import disk_visible_fraction
from run_spacecraft_analysis import main as spacecraft_cli_main
from science.wall_albedo import WallFacet, estimate_wall_reflected_irradiance


_WALL_OBJ = """# TEST ONLY: planar obstruction, not rover or lander CAD
o body_wall
v {x} -1 -1
v {x} 1 -1
v {x} 1 1
v {x} -1 1
f 1 2 3
f 1 3 4
"""

_TIMESTAMPS = ("2026-10-01T00:00:00Z", "2026-10-01T00:10:00Z")
_GENERATED_SIMULATION = Path(__file__).resolve().parents[1] / "outputs" / "simulation.json"


def _write_json(path: Path, value: dict) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=True).encode()
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _simulation() -> dict:
    irradiance = direct_solar_irradiance_w_m2(ASTRONOMICAL_UNIT_KM)
    samples = []
    for index, timestamp in enumerate(_TIMESTAMPS):
        # The first epoch has a partially visible Earth disk but terrain-blocked
        # center; the next has a clear center. Neither is real ephemeris data.
        center_clearance = -0.1 if index == 0 else 1.0
        samples.append({
            "timestamp": timestamp,
            "sun": {
                "azimuth_deg": 90.0,
                "elevation_deg": 0.0,
                "distance_km": ASTRONOMICAL_UNIT_KM,
                "terrain_horizon_deg": -1.0,
                "clearance_deg": 1.0,
                "angular_radius_deg": 0.25,
                "visibility_fraction": 1.0,
            },
            "earth": {
                "azimuth_deg": 90.0,
                "elevation_deg": 0.0,
                "terrain_horizon_deg": -center_clearance,
                "clearance_deg": center_clearance,
                "angular_radius_deg": 1.0,
                "visibility_fraction": disk_visible_fraction(center_clearance, 1.0),
            },
            "power": {"direct_irradiance_w_m2": irradiance},
        })
    return {
        "schema_version": "1.3.0",
        "validation": {
            "overall_status": "PASS",
            "independent_spice": {"status": "PASS"},
        },
        "provenance_contract": {
            "operational_ephemeris": "NASA/JPL Horizons",
            "validator_used_for_operational_samples": False,
        },
        "site": {"name": "Synthetic test site, not a lunar candidate"},
        "samples": samples,
    }


def _thermal_parameters() -> dict:
    return {
        "collecting_area_m2": 1.0,
        "radiating_area_m2": 0.5,
        "heat_capacity_j_k": 5_000.0,
        "solar_absorptivity": 0.9,
        "ir_emissivity": 0.8,
        "reference_efficiency": 0.3,
        "reference_temperature_k": 300.0,
        "efficiency_temperature_coefficient_per_k": -0.004,
        "mount_conductance_w_k": 0.5,
    }


def _environment(wall_flux_w_m2: float = 0.0) -> dict:
    panel_boundary = {
        "wall_reflected_solar_irradiance_w_m2": wall_flux_w_m2,
        "lunar_ir_irradiance_w_m2": 0.0,
        "mount_temperature_k": 280.0,
        "radiation_sink_temperature_k": 3.0,
    }
    return {
        "schema_version": "1.0.0",
        "provenance": {
            "source": "test-only synthetic radiometric boundary",
            "revision": "test-1",
            "method": "chosen analytic input, not LOLA-derived albedo",
        },
        "samples": [
            {"timestamp": timestamp, "panels": {"array_a": panel_boundary.copy()}}
            for timestamp in _TIMESTAMPS
        ],
    }


class SpacecraftAnalysisIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def fixture(self, name: str, *, wall_x_m: float = 1.0,
                wall_flux_w_m2: float = 0.0) -> dict:
        folder = self.root / name
        folder.mkdir()
        mesh_path = folder / "synthetic.obj"
        mesh_path.write_text(_WALL_OBJ.format(x=wall_x_m), encoding="utf-8")
        mesh_sha = hashlib.sha256(mesh_path.read_bytes()).hexdigest()
        manifest = {
            "schema_version": "1.0.0",
            "model_id": "synthetic_test_wall_not_flight_hardware",
            "provenance": {
                "source": "test-only hand-authored wall",
                "revision": "test-1",
                "spacecraft": "NONE; not VIPER or flight hardware",
            },
            "mesh": {
                "path": "synthetic.obj",
                "sha256": mesh_sha,
                "format": "obj",
                "units": "m",
                "scale_to_m": 1.0,
            },
            "panels": [{
                "id": "array_a",
                "area_m2": 1.0,
                "normal_body": [1.0, 0.0, 0.0],
                "sample_points_m": [[0.0, 0.0, 0.0], [0.0, 3.0, 0.0]],
                "sample_weights": [0.25, 0.75],
            }],
            "antennas": [
                {"id": "earth_blocked", "phase_center_m": [0.0, 0.0, 0.0]},
                {"id": "earth_clear", "phase_center_m": [0.0, 3.0, 0.0]},
            ],
        }
        manifest_path = folder / "geometry.json"
        manifest_sha = _write_json(manifest_path, manifest)
        environment = _environment(wall_flux_w_m2)
        environment_path = folder / "environment.json"
        environment_sha = _write_json(environment_path, environment)
        simulation = _simulation()
        simulation_path = folder / "simulation.json"
        _write_json(simulation_path, simulation)
        hardware = {
            "schema_version": "1.0.0",
            "geometry_manifest": {"path": "geometry.json", "sha256": manifest_sha},
            "attitude_deg": {
                "yaw": 0.0,
                "pitch": 0.0,
                "roll": 0.0,
                "source": "test-only fixed ENU alignment",
            },
            "panels": {
                "array_a": {
                    "thermal_parameters": _thermal_parameters(),
                    "initial_cell_temperature_k": 300.0,
                }
            },
            "environment_profile": {
                "path": "environment.json",
                "sha256": environment_sha,
            },
        }
        hardware_path = folder / "hardware.json"
        _write_json(hardware_path, hardware)
        return {
            "simulation_path": simulation_path,
            "hardware_path": hardware_path,
            "manifest_path": manifest_path,
            "mesh_path": mesh_path,
            "environment_path": environment_path,
            "simulation": simulation,
            "hardware": hardware,
            "manifest": manifest,
            "environment": environment,
        }

    def analyze(self, fixture: dict) -> dict:
        return analyze_spacecraft_files(
            fixture["simulation_path"], fixture["hardware_path"]
        )

    def repin_environment(self, fixture: dict) -> None:
        digest = _write_json(fixture["environment_path"], fixture["environment"])
        fixture["hardware"]["environment_profile"]["sha256"] = digest
        _write_json(fixture["hardware_path"], fixture["hardware"])

    def test_end_to_end_self_shading_thermal_derating_and_center_los(self) -> None:
        blocked = self.fixture("blocked", wall_x_m=1.0)
        open_sky = self.fixture("open", wall_x_m=-1.0)
        shaded = self.analyze(blocked)
        unshaded = self.analyze(open_sky)

        self.assertEqual(shaded["analysis_status"], "CONFIGURED_UNVALIDATED")
        self.assertFalse(shaded["flight_certified"])
        self.assertEqual(shaded["sample_count"], len(_TIMESTAMPS))
        self.assertEqual([item["timestamp"] for item in shaded["samples"]], list(_TIMESTAMPS))
        self.assertEqual(shaded["model_id"], "synthetic_test_wall_not_flight_hardware")
        self.assertEqual(shaded["input_sha256"]["mesh"], hashlib.sha256(
            blocked["mesh_path"].read_bytes()
        ).hexdigest())

        first = shaded["samples"][0]
        later = shaded["samples"][1]
        first_panel = first["panels"][0]
        later_panel = later["panels"][0]
        open_panel = unshaded["samples"][0]["panels"][0]
        self.assertEqual(first_panel["geometry"]["unoccluded_sample_fraction"], 0.75)
        self.assertEqual(open_panel["geometry"]["unoccluded_sample_fraction"], 1.0)
        self.assertAlmostEqual(
            first_panel["thermal_electrical"]["direct_solar_incident_power_w"],
            1361.0 * 0.75,
        )
        self.assertGreater(
            open_panel["thermal_electrical"]["electrical_output_w"],
            first_panel["thermal_electrical"]["electrical_output_w"],
        )
        self.assertGreater(later_panel["thermal_electrical"]["cell_temperature_k"], 300.0)
        self.assertLess(
            later_panel["thermal_electrical"]["temperature_derated_efficiency"],
            first_panel["thermal_electrical"]["temperature_derated_efficiency"],
        )
        self.assertLess(
            later_panel["thermal_electrical"]["electrical_output_w"],
            first_panel["thermal_electrical"]["electrical_output_w"],
        )
        self.assertEqual(later_panel["integration_from_previous_epoch"]["elapsed_s"], 600.0)
        self.assertLess(abs(
            later_panel["integration_from_previous_epoch"]["energy_balance_residual_j"]
        ), 1e-5)

        initial_antennas = {item["id"]: item for item in first["antennas"]}
        later_antennas = {item["id"]: item for item in later["antennas"]}
        self.assertAlmostEqual(
            first["earth_disk_visible_fraction"], disk_visible_fraction(-0.1, 1.0)
        )
        self.assertFalse(initial_antennas["earth_clear"]["earth_center_terrain_clear"])
        self.assertTrue(initial_antennas["earth_clear"]["self_los_clear"])
        self.assertFalse(initial_antennas["earth_clear"]["earth_center_geometric_los_clear"])
        self.assertTrue(later_antennas["earth_clear"]["earth_center_geometric_los_clear"])
        self.assertFalse(later_antennas["earth_blocked"]["self_los_clear"])
        self.assertFalse(later_antennas["earth_blocked"]["earth_center_geometric_los_clear"])

    def test_reflected_wall_flux_is_explicit_input_and_warms_cell(self) -> None:
        no_reflection = self.analyze(self.fixture("dark_wall", wall_flux_w_m2=0.0))
        reflection = self.analyze(self.fixture("lit_wall", wall_flux_w_m2=200.0))
        at_start_dark = no_reflection["samples"][0]["panels"][0]["thermal_electrical"]
        at_start_lit = reflection["samples"][0]["panels"][0]["thermal_electrical"]
        later_dark = no_reflection["samples"][1]["panels"][0]["thermal_electrical"]
        later_lit = reflection["samples"][1]["panels"][0]["thermal_electrical"]
        self.assertEqual(at_start_dark["wall_reflected_incident_power_w"], 0.0)
        self.assertAlmostEqual(at_start_lit["wall_reflected_incident_power_w"], 200.0)
        self.assertAlmostEqual(at_start_lit["wall_reflected_electrical_power_w"], 60.0)
        self.assertAlmostEqual(
            at_start_lit["direct_solar_incident_power_w"],
            at_start_dark["direct_solar_incident_power_w"],
        )
        self.assertGreater(later_lit["cell_temperature_k"], later_dark["cell_temperature_k"])
        self.assertLess(
            later_lit["temperature_derated_efficiency"],
            later_dark["temperature_derated_efficiency"],
        )

    def test_synthetic_wall_albedo_solver_feeds_thermal_profile(self) -> None:
        # A small Lambertian test facet, not a LOLA-derived crater wall. Put
        # it east of the panel and face it northwest so a northward Sun can
        # illuminate the wall while the panel sees its reflecting front face.
        # The synthetic CAD wall is west of the panel, so it does not block
        # the specified wall-to-panel path.
        facet = WallFacet(
            center_enu_m=(4.0, 1.5, 0.0),
            normal_enu=(-1.0, 1.0, 0.0),
            area_m2=4.0,
            broadband_reflectance=0.9,
            sun_visible_fraction=1.0,
            panel_visible_fraction=1.0,
        )
        dark = self.fixture("albedo_dark", wall_x_m=-1.0)
        lit = self.fixture("albedo_lit", wall_x_m=-1.0)
        estimates = []
        for fixture in (dark, lit):
            for sample in fixture["simulation"]["samples"]:
                sample["sun"]["azimuth_deg"] = 0.0
            _write_json(fixture["simulation_path"], fixture["simulation"])

        for index, sample in enumerate(lit["simulation"]["samples"]):
            # These vectors are the ENU directions of this deliberately
            # synthetic sample's Sun (azimuth 0, elevation 0) and fixed panel.
            estimate = estimate_wall_reflected_irradiance(
                panel_position_enu_m=(0.0, 1.5, 0.0),
                panel_normal_enu=(1.0, 0.0, 0.0),
                sun_direction_enu=(0.0, 1.0, 0.0),
                direct_normal_irradiance_w_m2=sample["power"]["direct_irradiance_w_m2"],
                facets=[facet],
            )
            self.assertEqual(estimate["active_facet_count"], 1)
            self.assertEqual(estimate["assumed_clear_wall_to_panel_facet_count"], 0)
            estimates.append(estimate)
            lit["environment"]["samples"][index]["panels"]["array_a"][
                "wall_reflected_solar_irradiance_w_m2"
            ] = estimate["wall_reflected_solar_irradiance_w_m2"]
        lit["environment"]["provenance"]["method"] = (
            "test-only single-bounce Lambertian facet with explicit optical inputs"
        )
        self.repin_environment(lit)

        baseline = self.analyze(dark)
        with_reflection = self.analyze(lit)
        for index, expected in enumerate(estimates):
            unlit_panel = baseline["samples"][index]["panels"][0]["thermal_electrical"]
            lit_panel = with_reflection["samples"][index]["panels"][0]["thermal_electrical"]
            self.assertEqual(unlit_panel["direct_solar_incident_power_w"], 0.0)
            self.assertEqual(lit_panel["direct_solar_incident_power_w"], 0.0)
            self.assertEqual(unlit_panel["wall_reflected_incident_power_w"], 0.0)
            self.assertEqual(
                lit_panel["wall_reflected_incident_power_w"],
                expected["wall_reflected_solar_irradiance_w_m2"],
            )
            self.assertGreater(lit_panel["electrical_output_w"], 0.0)
        self.assertGreater(
            with_reflection["samples"][1]["panels"][0]["thermal_electrical"]["cell_temperature_k"],
            baseline["samples"][1]["panels"][0]["thermal_electrical"]["cell_temperature_k"],
        )

    def test_landing_heading_changes_integrated_panel_and_antenna_results(self) -> None:
        east_facing = self.fixture("east_facing")
        yawed = self.fixture("yawed_ninety")
        yawed["hardware"]["attitude_deg"]["yaw"] = 90.0
        _write_json(yawed["hardware_path"], yawed["hardware"])
        first = self.analyze(east_facing)["samples"][1]
        turned = self.analyze(yawed)["samples"][1]
        self.assertEqual(first["attitude_deg"]["yaw"], 0.0)
        self.assertEqual(turned["attitude_deg"]["yaw"], 90.0)
        self.assertAlmostEqual(first["panels"][0]["geometry"]["incidence_cosine"], 1.0)
        self.assertAlmostEqual(turned["panels"][0]["geometry"]["incidence_cosine"], 0.0)
        self.assertGreater(first["total_electrical_output_w"], 0.0)
        self.assertEqual(turned["total_electrical_output_w"], 0.0)
        first_antenna = next(
            item for item in first["antennas"] if item["id"] == "earth_blocked"
        )
        turned_antenna = next(
            item for item in turned["antennas"] if item["id"] == "earth_blocked"
        )
        self.assertFalse(first_antenna["earth_center_geometric_los_clear"])
        self.assertTrue(turned_antenna["earth_center_geometric_los_clear"])

    @unittest.skipUnless(
        _GENERATED_SIMULATION.is_file(),
        "Run run_simulation.py to create the real-ephemeris integration artifact",
    )
    def test_full_week_real_site_series_with_test_only_hardware(self) -> None:
        # The parent export contains real Horizons/SPICE/LOLA site geometry.
        # All vehicle CAD, pose, and radiometric boundaries below remain
        # synthetic and live only in TemporaryDirectory; this is not a VIPER
        # prediction or a new flight-qualified output artifact.
        parent = json.loads(_GENERATED_SIMULATION.read_text(encoding="utf-8"))
        self.assertEqual(len(parent["samples"]), 13249)
        fixture = self.fixture("full_week_test_only_hardware")
        boundary = _environment()["samples"][0]["panels"]["array_a"]
        fixture["environment"]["samples"] = [
            {"timestamp": sample["timestamp"], "panels": {"array_a": boundary.copy()}}
            for sample in parent["samples"]
        ]
        self.repin_environment(fixture)
        fixture["hardware"]["attitude_deg"]["yaw"] = 150.0
        _write_json(fixture["hardware_path"], fixture["hardware"])

        result = analyze_spacecraft_files(
            _GENERATED_SIMULATION, fixture["hardware_path"]
        )
        self.assertEqual(result["sample_count"], 13249)
        self.assertEqual(result["analysis_status"], "CONFIGURED_UNVALIDATED")
        self.assertFalse(result["flight_certified"])
        self.assertEqual(
            result["input_sha256"]["simulation"],
            hashlib.sha256(_GENERATED_SIMULATION.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            [item["timestamp"] for item in result["samples"]],
            [item["timestamp"] for item in parent["samples"]],
        )
        self.assertTrue(any(
            item["panels"][0]["thermal_electrical"]["direct_solar_incident_power_w"] > 0
            for item in result["samples"]
        ))
        self.assertTrue(all(
            math.isfinite(item["total_electrical_output_w"])
            for item in result["samples"]
        ))
        for actual, source in zip(result["samples"], parent["samples"]):
            self.assertEqual(
                actual["earth_disk_visible_fraction"], source["earth"]["visibility_fraction"]
            )
            self.assertEqual(
                actual["antennas"][0]["earth_center_terrain_clear"],
                source["earth"]["clearance_deg"] > 0.0,
            )

    def test_environment_epoch_count_and_exact_timestamp_alignment(self) -> None:
        fixture = self.fixture("timing")
        fixture["environment"]["samples"][1]["timestamp"] = "2026-10-01T00:10:00.001Z"
        self.repin_environment(fixture)
        with self.assertRaisesRegex(ConfigurationError, "timestamp mismatch"):
            self.analyze(fixture)

        fixture["environment"]["samples"].pop()
        self.repin_environment(fixture)
        with self.assertRaisesRegex(ConfigurationError, "cover every simulation epoch"):
            self.analyze(fixture)

    def test_checksum_tampering_fails_closed_at_each_artifact_boundary(self) -> None:
        cases = ("mesh", "geometry_manifest", "thermal_environment")
        for name in cases:
            with self.subTest(artifact=name):
                fixture = self.fixture(name)
                path = {
                    "mesh": fixture["mesh_path"],
                    "geometry_manifest": fixture["manifest_path"],
                    "thermal_environment": fixture["environment_path"],
                }[name]
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaises(ConfigurationError):
                    self.analyze(fixture)

    def test_missing_hardware_or_boundary_conditions_fail_closed(self) -> None:
        missing_panel = self.fixture("missing_panel")
        del missing_panel["hardware"]["panels"]["array_a"]
        _write_json(missing_panel["hardware_path"], missing_panel["hardware"])
        with self.assertRaisesRegex(ConfigurationError, "match every CAD panel ID"):
            self.analyze(missing_panel)

        missing_property = self.fixture("missing_property")
        del missing_property["hardware"]["panels"]["array_a"]["thermal_parameters"][
            "heat_capacity_j_k"
        ]
        _write_json(missing_property["hardware_path"], missing_property["hardware"])
        with self.assertRaises(ConfigurationError):
            self.analyze(missing_property)

        missing_wall_input = self.fixture("missing_wall_input")
        del missing_wall_input["environment"]["samples"][0]["panels"]["array_a"][
            "wall_reflected_solar_irradiance_w_m2"
        ]
        self.repin_environment(missing_wall_input)
        with self.assertRaises(ConfigurationError):
            self.analyze(missing_wall_input)

    def test_nonfinite_and_inconsistent_inputs_fail_closed(self) -> None:
        bad_flux = self.fixture("nan_wall_flux")
        bad_flux["environment"]["samples"][0]["panels"]["array_a"][
            "wall_reflected_solar_irradiance_w_m2"
        ] = math.nan
        self.repin_environment(bad_flux)
        with self.assertRaises(ConfigurationError):
            self.analyze(bad_flux)

        bad_attitude = self.fixture("infinite_attitude")
        bad_attitude["hardware"]["attitude_deg"]["pitch"] = math.inf
        _write_json(bad_attitude["hardware_path"], bad_attitude["hardware"])
        with self.assertRaises(ConfigurationError):
            self.analyze(bad_attitude)

        bad_sun = self.fixture("nonfinite_sun")
        bad_sun["simulation"]["samples"][0]["sun"]["elevation_deg"] = math.nan
        _write_json(bad_sun["simulation_path"], bad_sun["simulation"])
        with self.assertRaises(ConfigurationError):
            self.analyze(bad_sun)

        wrong_flux = self.fixture("wrong_baseline_irradiance")
        wrong_flux["simulation"]["samples"][0]["power"]["direct_irradiance_w_m2"] += 1.0
        _write_json(wrong_flux["simulation_path"], wrong_flux["simulation"])
        with self.assertRaisesRegex(ConfigurationError, "solar flux disagrees"):
            self.analyze(wrong_flux)

    def test_output_cannot_alias_any_input_artifact(self) -> None:
        fixture = self.fixture("output_alias")
        for key in (
            "simulation_path", "hardware_path", "manifest_path",
            "mesh_path", "environment_path",
        ):
            with self.subTest(artifact=key):
                with self.assertRaisesRegex(ConfigurationError, "must not replace"):
                    analyze_spacecraft_files(
                        fixture["simulation_path"],
                        fixture["hardware_path"],
                        output_path=fixture[key],
                    )

    def test_aggregate_only_geometry_and_raycast_budget(self) -> None:
        fixture = self.fixture("bounded_rays")
        result = self.analyze(fixture)
        self.assertNotIn("samples", result["samples"][0]["panels"][0]["geometry"])
        self.assertGreater(result["raycast_work_units"]["used"], 0)
        with patch("science.spacecraft_analysis.MAX_RAYCAST_WORK_UNITS", 1):
            with self.assertRaisesRegex(ConfigurationError, "work budget exceeded"):
                self.analyze(fixture)

    def test_cli_writes_separate_export_and_rejects_input_overwrite(self) -> None:
        fixture = self.fixture("cli")
        output = fixture["hardware_path"].parent / "analysis.json"
        args = [
            "--simulation", str(fixture["simulation_path"]),
            "--hardware", str(fixture["hardware_path"]),
            "--output", str(output),
        ]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(spacecraft_cli_main(args), 0)
        exported = json.loads(output.read_text(encoding="utf-8"))
        self.assertFalse(exported["flight_certified"])
        self.assertEqual(exported["sample_count"], len(_TIMESTAMPS))
        original_simulation = fixture["simulation_path"].read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(
                spacecraft_cli_main(
                    args[:-1] + [str(fixture["simulation_path"]), "--overwrite"]
                ),
                2,
            )
        self.assertEqual(fixture["simulation_path"].read_bytes(), original_simulation)


if __name__ == "__main__":
    unittest.main()
