import unittest
from datetime import datetime, timedelta, timezone

from science.config import SiteConfig, TimeRangeConfig
from science.ephemeris.spice import SpiceEphemerisProvider
from tests.test_spice_ephemeris import KERNEL_DIRECTORY, HAVE_LOCKED_KERNELS


@unittest.skipUnless(HAVE_LOCKED_KERNELS, "Pinned NAIF kernels required")
class TimeAuditTests(unittest.TestCase):
    def test_periodic_time_correction_and_explicit_qualification(self):
        provider = SpiceEphemerisProvider(KERNEL_DIRECTORY, auto_download=False)
        corrections = []
        for month in (1, 4, 7, 10):
            start = datetime(2026, month, 1, tzinfo=timezone.utc)
            samples, metadata = provider.get_earth_positions(SiteConfig(), 0.0,
                TimeRangeConfig(start, start + timedelta(minutes=10), 10))
            audit = metadata["time_conversion_audit"]["samples"]
            self.assertEqual(len(audit), len(samples))
            for entry in audit:
                self.assertLessEqual(entry["roundtrip_error_seconds"], 1e-6)
                self.assertLess(abs(entry["tdb_minus_tt_seconds"]), 0.002)
            corrections.append(audit[0]["tdb_minus_tt_seconds"])
            self.assertFalse(metadata["qualification"]["flight_ready"])
            self.assertIn("UNKNOWN", metadata["qualification"]["antenna_phase_center"])
        self.assertGreater(max(corrections) - min(corrections), 0.003)

    def test_leap_second_is_included_by_cspice(self):
        start = datetime(2016, 12, 31, 23, 50, tzinfo=timezone.utc)
        _, metadata = SpiceEphemerisProvider(KERNEL_DIRECTORY, auto_download=False).get_earth_positions(
            SiteConfig(), 0.0, TimeRangeConfig(start, start + timedelta(minutes=10), 10))
        rows = metadata["time_conversion_audit"]["samples"]
        self.assertAlmostEqual(rows[1]["tdb_seconds_past_j2000"] - rows[0]["tdb_seconds_past_j2000"],
            601.0, delta=0.001)
