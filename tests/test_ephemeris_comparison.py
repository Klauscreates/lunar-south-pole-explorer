import unittest
from datetime import datetime, timezone

from science.ephemeris.base import EphemerisSample
from science.validation import compare_ephemeris_series


def sample(azimuth_deg: float, elevation_deg: float) -> EphemerisSample:
    return EphemerisSample(
        timestamp=datetime(2026, 10, 1, tzinfo=timezone.utc),
        azimuth_deg=azimuth_deg,
        elevation_deg=elevation_deg,
        angular_diameter_arcsec=1.0,
        distance_km=1000.0,
        solar_presence_code="",
        interfering_body_code="",
    )


class EphemerisComparisonTests(unittest.TestCase):
    def test_azimuth_error_wraps_across_zero(self):
        result = compare_ephemeris_series(
            "Sun",
            [sample(359.999, 0.0)],
            [sample(0.001, 0.0)],
            maximum_angular_separation_deg=0.01,
        )

        record = result["representative_samples"][0]
        self.assertAlmostEqual(record["azimuth_error_deg"], 0.002, places=9)
        self.assertAlmostEqual(record["angular_separation_deg"], 0.002, places=9)
        self.assertEqual(result["status"], "PASS")

    def test_true_local_sky_separation_controls_status(self):
        result = compare_ephemeris_series(
            "Earth",
            [sample(30.0, 20.0)],
            [sample(30.0, 20.02)],
            maximum_angular_separation_deg=0.01,
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertAlmostEqual(
            result["angular_separation_deg"]["maximum"], 0.02, places=9
        )

    def test_timestamp_mismatch_fails_closed(self):
        candidate = sample(30.0, 20.0)
        candidate = EphemerisSample(
            timestamp=datetime(2026, 10, 1, 0, 10, tzinfo=timezone.utc),
            azimuth_deg=candidate.azimuth_deg,
            elevation_deg=candidate.elevation_deg,
            angular_diameter_arcsec=candidate.angular_diameter_arcsec,
            distance_km=candidate.distance_km,
            solar_presence_code="",
            interfering_body_code="",
        )

        with self.assertRaisesRegex(ValueError, "timestamp mismatch"):
            compare_ephemeris_series(
                "Earth",
                [sample(30.0, 20.0)],
                [candidate],
                maximum_angular_separation_deg=0.01,
            )


if __name__ == "__main__":
    unittest.main()
