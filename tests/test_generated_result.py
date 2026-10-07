import hashlib
import json
import math
import unittest
from pathlib import Path
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from science.windows import build_window_summary
from science.export import write_csv

OUTPUT = Path(__file__).resolve().parents[1] / "outputs" / "simulation.json"
CSV_OUTPUT = OUTPUT.with_suffix(".csv")

# Captured from the last Horizons-only operational export before the SPICE
# validator was enabled. Validator provenance is intentionally excluded: this
# regression locks only the displayed samples, derived windows, and flat CSV.
PRE_SPICE_SAMPLES_SHA256 = (
    "de363fccd44c5275f87e4402cd1079045337e968dd064a4f5c2cfc4e63737c7b"
)
PRE_SPICE_WINDOWS_SHA256 = (
    "7dd17e1914eb3b183eca94bf6a972644da808c674f3e3e86b7c3186c94de054b"
)
PRE_SPICE_CSV_SHA256 = (
    "a16bed59fafbf305437dd7e14ed9fc70faf68905dbf4294acb7503fb77ee80c0"
)
LEGACY_POWER_FIELDS = {
    "geometric_sunlight_available",
    "panel_illuminated",
    "orientation_mode",
    "incidence_cosine",
    "relative_irradiance_vs_1au",
    "direct_irradiance_w_m2",
    "estimated_incident_power_w",
    "estimated_electrical_output_w",
}


def _canonical_sha256(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@unittest.skipUnless(
    OUTPUT.exists(), "Run run_simulation.py to create integration artifact"
)
class GeneratedResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads(OUTPUT.read_text(encoding="utf-8"))

    def test_expected_full_quarter_dimensions(self):
        self.assertEqual(self.result["schema_version"], "1.3.0")
        self.assertEqual(len(self.result["samples"]), 13249)
        self.assertEqual(len(self.result["horizon"]["profile"]), 720)
        self.assertEqual(len(self.result["horizon_mask"]["profile"]), 360)
        self.assertEqual(self.result["validation"]["overall_status"], "PASS")

    def test_one_degree_mask_uses_exact_existing_rays(self):
        full = self.result["horizon"]["profile"]
        mask = self.result["horizon_mask"]["profile"]
        for azimuth, point in enumerate(mask):
            self.assertEqual(point["azimuth_deg"], azimuth)
            self.assertEqual(
                point["minimum_clearance_elevation_deg"],
                full[2 * azimuth]["elevation_deg"],
            )

    def test_required_local_spice_crosscheck_passes_all_epochs(self):
        validation = self.result["validation"]["independent_spice"]
        self.assertEqual(validation["status"], "PASS")
        self.assertTrue(validation["required"])
        self.assertFalse(validation["used_for_simulation"])
        self.assertEqual(validation["targets"]["sun"]["sample_count"], 13249)
        self.assertEqual(validation["targets"]["earth"]["sample_count"], 13249)
        self.assertLess(
            validation["targets"]["sun"]["angular_separation_arcsec"]["maximum"],
            1.0,
        )
        self.assertLess(
            validation["targets"]["earth"]["angular_separation_arcsec"]["maximum"],
            1.0,
        )

    def test_validator_does_not_change_operational_series_windows_or_csv(self):
        legacy_samples = []
        # Preserve the original week byte-for-byte; the extension must not
        # retroactively alter any previously published geometry or power.
        original_week = self.result["samples"][:1009]
        for sample in original_week:
            legacy = {
                key: value for key, value in sample.items()
                if key not in {"power_scenarios", "comms_potential"}
            }
            legacy["power"] = {
                key: value for key, value in sample["power"].items()
                if key in LEGACY_POWER_FIELDS
            }
            legacy_samples.append(legacy)
        self.assertEqual(
            _canonical_sha256(legacy_samples),
            PRE_SPICE_SAMPLES_SHA256,
        )
        self.assertEqual(
            _canonical_sha256(build_window_summary(original_week, datetime(2026,10,8,tzinfo=timezone.utc))),
            PRE_SPICE_WINDOWS_SHA256,
        )
        self.assertTrue(CSV_OUTPUT.is_file(), "Canonical CSV export is missing")
        with TemporaryDirectory() as directory:
            csv_path = Path(directory) / "original-week.csv"
            write_csv({"samples": original_week}, csv_path)
            self.assertEqual(hashlib.sha256(csv_path.read_bytes()).hexdigest(), PRE_SPICE_CSV_SHA256)

    def test_spice_kernel_set_is_pinned_and_covers_interval(self):
        source = self.result["data_sources"]["spice_validation"]
        self.assertEqual(source["role"], "independent_validator_only")
        self.assertFalse(source["used_for_operational_samples"])
        for target in ("sun", "earth"):
            metadata = source[target]
            self.assertEqual(metadata["center_frame"], "MOON_ME_DE440_ME421")
            self.assertTrue(
                metadata["kernel_coverage"]["requested_interval_fully_covered"]
            )
            kernels = metadata["kernel_manifest"]["kernels"]
            self.assertEqual(len(kernels), 5)
            self.assertTrue(all(len(kernel["sha256"]) == 64 for kernel in kernels))

    def test_first_reference_epoch_is_real_horizons_result(self):
        sample = self.result["samples"][0]
        self.assertEqual(sample["timestamp"], "2026-10-01T00:00:00Z")
        self.assertAlmostEqual(sample["sun"]["azimuth_deg"], 302.828959535, places=8)
        self.assertAlmostEqual(sample["earth"]["azimuth_deg"], 358.807428905, places=8)

    def test_all_exported_numbers_are_finite(self):
        for sample in self.result["samples"]:
            for body_name in ("sun", "earth"):
                body = sample[body_name]
                for key in (
                    "azimuth_deg",
                    "elevation_deg",
                    "terrain_horizon_deg",
                    "clearance_deg",
                    "visibility_fraction",
                ):
                    self.assertTrue(math.isfinite(body[key]), f"{body_name}.{key}")

    def test_combined_durations_partition_requested_span(self):
        combined = self.result["windows"]["combined"]
        total = sum(value["total_duration_seconds"] for value in combined.values())
        self.assertEqual(total, 92 * 24 * 3600)

    def test_published_pgda_psr_crosscheck(self):
        crosscheck = self.result["validation"]["terrain"]["published_psr_crosscheck"]
        self.assertEqual(crosscheck["status"], "PASS")
        self.assertEqual(crosscheck["source"]["categorical_value"], 0.0)
        self.assertEqual(crosscheck["source"]["classification"], "NOT_PSR")


if __name__ == "__main__":
    unittest.main()
