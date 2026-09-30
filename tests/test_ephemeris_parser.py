import unittest
from datetime import datetime, timezone

from science.ephemeris.horizons import parse_horizons_observer_table
from science.errors import EphemerisError


RAW_TABLE = """
Target body name: Sun (10) {source: DE441}
$$SOE
 2026-Oct-01 00:00:00,*,i, 302.828959535, 1.037972748, 1913.294, 1.5000200159E+08,
 2026-Oct-01 00:10:00,*,i, 302.744411863, 1.038013307, 1913.295, 1.5000121778E+08,
$$EOE
Column meaning follows.
"""


class HorizonsParserTests(unittest.TestCase):
    def test_parses_exact_requested_schema(self):
        rows = parse_horizons_observer_table(RAW_TABLE)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[0].timestamp,
            datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
        )
        self.assertAlmostEqual(rows[0].azimuth_deg, 302.828959535)
        self.assertAlmostEqual(rows[0].angular_radius_deg, 1913.294 / 7200.0)
        self.assertEqual(rows[0].solar_presence_code, "*")
        self.assertEqual(rows[0].interfering_body_code, "i")

    def test_fails_closed_without_ephemeris_markers(self):
        with self.assertRaises(EphemerisError):
            parse_horizons_observer_table("not an ephemeris")

    def test_fails_closed_on_unavailable_numeric_value(self):
        invalid = "$$SOE\n2026-Oct-01 00:00:00,*,i,n.a.,1,2,3,\n$$EOE"
        with self.assertRaises(EphemerisError):
            parse_horizons_observer_table(invalid)


if __name__ == "__main__":
    unittest.main()

