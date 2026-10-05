"""Independent geometry checks and generated-study lineage/physics invariants."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from run_reference_lander import COLUMNS, DESIGN, EVIDENCE, IMPLEMENTATION_FILES, make_geometry
from science.spacecraft import evaluate_spacecraft_geometry, load_spacecraft_geometry

ROOT = Path(__file__).resolve().parents[1]


class ReferenceLanderTests(unittest.TestCase):
    def test_declared_payload_and_mast_cast_expected_north_shadow(self):
        # At zero elevation, nine grid points lie behind the payload and five
        # behind the mast. The two silhouettes do not overlap on this grid.
        with tempfile.TemporaryDirectory() as temporary:
            path, _ = make_geometry(json.loads(DESIGN.read_text()), Path(temporary))
            model = load_spacecraft_geometry(path)
            result = evaluate_spacecraft_geometry(
                model, sun_azimuth_deg=0, sun_elevation_deg=0,
                earth_azimuth_deg=270, earth_elevation_deg=0,
                yaw_deg=0, pitch_deg=0, roll_deg=0,
            )
            panel = result["panels"][0]
            self.assertEqual(panel["sample_count"], 64)
            self.assertEqual(panel["incidence_cosine"], 1)
            self.assertAlmostEqual(panel["unoccluded_sample_fraction"], 50/64)
            self.assertEqual(set(panel["obstruction_ids"]), {"antenna_mast", "forward_payload"})
            self.assertFalse(result["antennas"][0]["self_los_clear"])

    def test_generated_studies_match_every_site_epoch_and_input_revision(self):
        catalogue = json.loads((ROOT / "outputs/spacecraft/index.json").read_text())
        parents = json.loads((ROOT / "outputs/simulation-index.json").read_text())["sites"]
        self.assertEqual({s["site_id"] for s in catalogue["sites"]}, {s["id"] for s in parents})
        design_sha = hashlib.sha256(DESIGN.read_bytes()).hexdigest()
        evidence_sha = hashlib.sha256(EVIDENCE.read_bytes()).hexdigest()
        temperature_response = False
        heading_response = False
        structure_blocks = False
        for entry in catalogue["sites"]:
            data_path = ROOT / "outputs/spacecraft" / f"{entry['site_id']}.json"
            self.assertEqual(hashlib.sha256(data_path.read_bytes()).hexdigest(), entry["sha256"])
            data = json.loads(data_path.read_text())
            parent_entry = next(s for s in parents if s["id"] == entry["site_id"])
            parent_path = ROOT / "outputs" / ("simulation.json" if entry["site_id"] == "test-site-a"
                                             else f"candidates/{entry['site_id']}.json")
            parent = json.loads(parent_path.read_text())
            self.assertEqual(data["parent_sha256"], parent_entry["sha256"])
            self.assertEqual(data["design_sha256"], design_sha)
            self.assertEqual(data["evidence_sha256"], evidence_sha)
            for name in IMPLEMENTATION_FILES:
                self.assertEqual(data["implementation_sha256"][name], hashlib.sha256((ROOT / name).read_bytes()).hexdigest())
            self.assertFalse(data["flight_certified"])
            self.assertEqual(data["analysis_status"], "DESIGN_STUDY_UNVALIDATED")
            self.assertEqual(data["columns"], COLUMNS)
            self.assertEqual(data["timestamps"], [s["timestamp"] for s in parent["samples"]])
            self.assertEqual(len(data["scenarios"]), 10)
            scenarios = {s["id"]: s for s in data["scenarios"]}
            self.assertEqual(len(scenarios), 10)
            for scenario in scenarios.values():
                self.assertEqual(len(scenario["rows"]), len(data["timestamps"]))
                self.assertEqual(scenario["input_sha256"]["simulation"], parent_entry["sha256"])
                self.assertLess(scenario["maximum_interval_energy_residual_j"], 0.01)
                for row, sample in zip(scenario["rows"], parent["samples"]):
                    self.assertEqual(len(row), len(COLUMNS))
                    self.assertTrue(all(math.isfinite(row[i]) for i in (0,1,2,3,4,8,9)))
                    self.assertGreater(row[1], 0)
                    self.assertGreaterEqual(row[0], 0)
                    for i in (2,3,4):
                        self.assertTrue(0 <= row[i] <= 1)
                    self.assertEqual(row[6], sample["earth"]["clearance_deg"] > 0)
                    self.assertEqual(row[7], row[5] and row[6])
                    self.assertAlmostEqual(row[0], (row[8]+row[9])*row[2], delta=1e-5)
                    if sample["sun"]["visibility_fraction"] == 0 or row[3] == 0:
                        self.assertEqual(row[8], 0)
                    structure_blocks |= not row[5]
            cold = scenarios["north--low_load"]["rows"]
            warm = scenarios["north--added_load"]["rows"]
            south = scenarios["south--low_load"]["rows"]
            temperature_response |= any(b[1] > a[1] for a,b in zip(cold[1:], warm[1:]))
            heading_response |= any(a[0] != b[0] for a,b in zip(cold, south))
        self.assertTrue(temperature_response)
        self.assertTrue(heading_response)
        self.assertTrue(structure_blocks)

    def test_archival_numbers_are_consistent_but_not_model_validation(self):
        evidence = json.loads(EVIDENCE.read_text())
        transit = evidence["transit"]
        # Product of reported rounded averages is a coarse consistency check,
        # not an exact average of instantaneous power or model correlation.
        power = transit["reported_average_solar_voltage_v"] * transit["reported_average_solar_current_a"]
        self.assertAlmostEqual(power, transit["reported_average_solar_power_w"], delta=1)
        self.assertEqual(evidence["model_correlation_status"], "NOT_RUN")
        self.assertIn("not directly measured", transit["bcr_efficiency_evidence"])


if __name__ == "__main__":
    unittest.main()
