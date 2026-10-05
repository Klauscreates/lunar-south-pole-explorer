"""Catalogue and retained-export guards for the multi-site science array."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from science.candidates import EVALUATED_SITES, NASA_COORDINATE_SOURCE
from science.comms import classify_comms_potential
from science.errors import SciencePipelineError
from run_candidate_array import paths_for, validate_result


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "outputs" / "simulation-index.json"
SCENARIOS = {
    "ideal_tracking", "fixed_vertical_north", "fixed_tilt_80_north", "limited_gimbal"
}


class CandidateCatalogueTests(unittest.TestCase):
    def test_nasa_reference_coordinates_and_status_are_explicit(self):
        by_id = {site.id: site for site in EVALUATED_SITES}
        self.assertEqual(len(by_id), 5)
        self.assertEqual(
            (by_id["connecting-ridge"].latitude_deg,
             by_id["connecting-ridge"].longitude_deg_east),
            (-89.4632, -137.49),
        )
        self.assertEqual(
            (by_id["haworth"].latitude_deg,
             by_id["haworth"].longitude_deg_east),
            (-86.7639, -22.777),
        )
        self.assertEqual(
            (by_id["malapert-massif"].latitude_deg,
             by_id["malapert-massif"].longitude_deg_east),
            (-85.9948, -0.23578),
        )
        self.assertEqual(
            (by_id["nobile-rim-1"].latitude_deg,
             by_id["nobile-rim-1"].longitude_deg_east),
            (-85.4381, 37.36667),
        )
        self.assertEqual(by_id["test-site-a"].kind, "validation")
        self.assertIsNone(by_id["test-site-a"].coordinate_source_url)
        self.assertEqual(
            by_id["connecting-ridge"].region_status,
            "historical_2022_cohort",
        )
        self.assertTrue(all(
            site.coordinate_source_url == NASA_COORDINATE_SOURCE
            for site in EVALUATED_SITES[1:]
        ))

    def test_validator_rejects_a_stale_or_incomplete_claim(self):
        site = EVALUATED_SITES[1]
        earth = {
            "elevation_deg": 3.0,
            "terrain_horizon_deg": 1.0,
            "clearance_deg": 2.0,
            "visibility_fraction": 1.0,
        }
        sample = {
            "power_scenarios": {key: {} for key in SCENARIOS},
            "earth": earth,
            "comms_potential": classify_comms_potential(earth),
        }
        result = {
            "schema_version": "1.3.0",
            "site": {
                "name": site.name,
                "latitude_deg": site.latitude_deg,
                "longitude_deg_east": site.longitude_deg_east,
            },
            "samples": [sample] * 1009,
            "time_range": {"sample_count": 1009},
            "horizon": {"profile": [{}] * 720},
            "horizon_mask": {
                "profile": [{"azimuth_deg": az} for az in range(360)]
            },
            "validation": {
                "overall_status": "PASS",
                "independent_spice": {"status": "PASS"},
            },
            "provenance_contract": {
                "validator_used_for_operational_samples": False,
                "operational_ephemeris": "NASA/JPL Horizons",
            },
            "data_sources": {
                "spice_validation": {"role": "independent_validator_only"}
            },
            "panel_scenarios": {key: {} for key in SCENARIOS},
        }
        validate_result(result, site)
        result["horizon_mask"]["profile"][42]["azimuth_deg"] = 43
        with self.assertRaisesRegex(SciencePipelineError, "horizon mask"):
            validate_result(result, site)
        result["horizon_mask"]["profile"][42]["azimuth_deg"] = 42
        result["validation"]["independent_spice"]["status"] = "FAIL"
        with self.assertRaisesRegex(SciencePipelineError, "validation"):
            validate_result(result, site)
        result["validation"]["independent_spice"]["status"] = "PASS"
        sample["comms_potential"] = {"potential_index_percent": 100}
        with self.assertRaisesRegex(SciencePipelineError, "communications matrix"):
            validate_result(result, site)


@unittest.skipUnless(INDEX.exists(), "Run run_candidate_array.py first")
class PublishedCandidateArrayTests(unittest.TestCase):
    def test_every_linked_series_matches_its_served_hash_and_contract(self):
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        self.assertEqual(index["schema_version"], "1.0.0")
        self.assertEqual(
            [entry["id"] for entry in index["sites"]],
            [site.id for site in EVALUATED_SITES],
        )
        for site, entry in zip(EVALUATED_SITES, index["sites"]):
            self.assertEqual(entry["kind"], site.kind)
            canonical, _, _ = paths_for(site)
            self.assertTrue(canonical.is_file(), site.id)
            self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), entry["sha256"])
            result = json.loads(canonical.read_text(encoding="utf-8"))
            validate_result(result, site)
            served = ROOT / "apps" / "web" / "public" / entry["data_url"].lstrip("/")
            if served.is_file():
                self.assertEqual(hashlib.sha256(served.read_bytes()).hexdigest(), entry["sha256"])


if __name__ == "__main__":
    unittest.main()
