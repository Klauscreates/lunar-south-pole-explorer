import math
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import spiceypy

from science.config import SiteConfig, TimeRangeConfig
from science.ephemeris.kernels import KernelManifest
from science.ephemeris.spice import (
    KernelCoverageError,
    SpiceEphemerisProvider,
    _angular_diameter_arcsec,
    _require_coverage,
)
from science.errors import EphemerisError

WORKSPACE = Path(__file__).resolve().parents[1]
KERNEL_DIRECTORY = WORKSPACE / "data" / "kernels"
MANIFEST = KernelManifest.load()
HAVE_LOCKED_KERNELS = all(
    (KERNEL_DIRECTORY / spec.filename).is_file() for spec in MANIFEST.kernels
)


class SpiceGeometryUnitTests(unittest.TestCase):
    def test_apparent_mode_is_locked_to_cn_plus_s(self):
        with self.assertRaisesRegex(ValueError, r"locked.*CN\+S"):
            SpiceEphemerisProvider(
                KERNEL_DIRECTORY,
                auto_download=False,
                aberration_correction="LT+S",
            )

    def test_exact_pole_is_rejected_because_azimuth_is_undefined(self):
        provider = SpiceEphemerisProvider(
            KERNEL_DIRECTORY,
            auto_download=False,
        )
        start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        interval = TimeRangeConfig(
            start_utc=start,
            end_utc=start + timedelta(minutes=10),
            step_minutes=10,
        )
        with self.assertRaisesRegex(EphemerisError, "undefined at the exact"):
            provider.get_sun_positions(
                SiteConfig(latitude_deg=-90.0),
                terrain_elevation_m=0.0,
                time_range=interval,
            )

    def test_angular_diameter_uses_exact_full_angle(self):
        radius = 1.0
        distance = 2.0
        expected = math.degrees(2.0 * math.asin(0.5)) * 3600.0
        self.assertAlmostEqual(
            _angular_diameter_arcsec(radius, distance),
            expected,
            places=12,
        )

    def test_coverage_must_be_continuous_across_whole_request(self):
        with self.assertRaisesRegex(KernelCoverageError, "does not continuously"):
            _require_coverage(
                [(-100.0, 0.0), (1.0, 100.0)],
                -50.0,
                50.0,
                "test kernel",
            )


@unittest.skipUnless(
    HAVE_LOCKED_KERNELS,
    "ignored NAIF kernels are not present; run python -m science.ephemeris.kernels",
)
class SpiceEphemerisIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.interval = TimeRangeConfig(
            start_utc=self.start,
            end_utc=self.start + timedelta(minutes=10),
            step_minutes=10,
        )
        self.site = SiteConfig(
            name="South-pole regression site",
            latitude_deg=-89.9,
            longitude_deg_east=0.0,
            observer_height_m=2.0,
        )
        self.terrain_elevation_m = 628.229797
        self.provider = SpiceEphemerisProvider(
            KERNEL_DIRECTORY,
            auto_download=False,
        )

    def tearDown(self):
        spiceypy.kclear()

    def test_first_sample_matches_locked_de440_regression_and_horizons(self):
        # A caller-owned kernel proves that the provider restores CSPICE's
        # process-global pool after running with its isolated locked set.
        sentinel = (KERNEL_DIRECTORY / "naif0012.tls").resolve()
        spiceypy.kclear()
        spiceypy.furnsh(str(sentinel))

        sun, sun_metadata = self.provider.get_sun_positions(
            self.site,
            self.terrain_elevation_m,
            self.interval,
        )
        earth, earth_metadata = self.provider.get_earth_positions(
            self.site,
            self.terrain_elevation_m,
            self.interval,
        )

        self.assertEqual(len(sun), 2)
        self.assertEqual(len(earth), 2)
        self.assertEqual(sun[0].timestamp, self.start)
        self.assertEqual(earth[0].timestamp, self.start)
        self.assertAlmostEqual(sun[0].azimuth_deg, 302.828959528173, delta=1e-8)
        self.assertAlmostEqual(sun[0].elevation_deg, 1.037972507873, delta=1e-8)
        self.assertAlmostEqual(sun[0].distance_km, 150002001.58318105, delta=1e-5)
        self.assertAlmostEqual(
            sun[0].angular_diameter_arcsec,
            1913.293671412845,
            delta=1e-6,
        )
        self.assertAlmostEqual(earth[0].azimuth_deg, 358.807428663798, delta=1e-8)
        self.assertAlmostEqual(earth[0].elevation_deg, 6.492099487099, delta=1e-8)
        self.assertAlmostEqual(earth[0].distance_km, 369411.6686239745, delta=1e-5)
        self.assertAlmostEqual(
            earth[0].angular_diameter_arcsec,
            7122.950322649197,
            delta=1e-6,
        )

        horizons_sun = (302.828959535, 1.037972508, 150002001.58)
        horizons_earth = (358.807428905, 6.492099500, 369411.66861)
        self.assertLess(_circular_error(sun[0].azimuth_deg, horizons_sun[0]), 1e-5)
        self.assertLess(abs(sun[0].elevation_deg - horizons_sun[1]), 1e-5)
        self.assertLess(abs(sun[0].distance_km - horizons_sun[2]), 0.01)
        self.assertLess(
            _circular_error(earth[0].azimuth_deg, horizons_earth[0]),
            1e-5,
        )
        self.assertLess(abs(earth[0].elevation_deg - horizons_earth[1]), 1e-5)
        self.assertLess(abs(earth[0].distance_km - horizons_earth[2]), 0.01)

        for metadata in (sun_metadata, earth_metadata):
            self.assertEqual(metadata["center_frame"], "MOON_ME_DE440_ME421")
            self.assertEqual(
                metadata["apparent_state"]["aberration_correction"],
                "CN+S",
            )
            self.assertEqual(
                metadata["site_coordinates_used"]["terrain_elevation_m"],
                self.terrain_elevation_m,
            )
            self.assertTrue(
                metadata["kernel_coverage"]["requested_interval_fully_covered"]
            )
            self.assertEqual(
                len(metadata["kernel_manifest"]["kernels"]),
                len(MANIFEST.kernels),
            )

        self.assertEqual(spiceypy.ktotal("ALL"), 1)
        restored = Path(spiceypy.kdata(0, "ALL")[0]).resolve()
        self.assertEqual(restored, sentinel)

    def test_positive_east_longitude_matches_horizons_canary(self):
        """Lock the sign convention against an independent Horizons result."""
        site = SiteConfig(
            name="Positive-east longitude canary",
            latitude_deg=-89.9,
            longitude_deg_east=45.0,
            observer_height_m=2.0,
        )

        sun, sun_metadata = self.provider.get_sun_positions(
            site,
            self.terrain_elevation_m,
            self.interval,
        )
        earth, earth_metadata = self.provider.get_earth_positions(
            site,
            self.terrain_elevation_m,
            self.interval,
        )

        # NASA/JPL Horizons observer table retrieved 2026-09-28 with
        # CENTER=coord@301, COORD_TYPE=GEODETIC,
        # SITE_COORD='45,-89.9,0.630229797', APPARENT=AIRLESS,
        # EXTRA_PREC=YES, and epoch 2026-10-01T00:00:00Z. Negating the
        # longitude misses these azimuths by approximately 90 degrees.
        expected = {
            "Sun": (sun[0], 257.828781470, 0.962676129, 1913.294, 150002003.86),
            "Earth": (earth[0], 313.799202577, 6.461323489, 7122.932, 369412.59568),
        }
        for target, (
            sample,
            azimuth_deg,
            elevation_deg,
            diameter_arcsec,
            distance_km,
        ) in expected.items():
            with self.subTest(target=target):
                self.assertEqual(sample.timestamp, self.start)
                self.assertLess(
                    _circular_error(sample.azimuth_deg, azimuth_deg),
                    1e-5,
                )
                self.assertLess(abs(sample.elevation_deg - elevation_deg), 1e-5)
                self.assertLess(
                    abs(sample.angular_diameter_arcsec - diameter_arcsec),
                    0.01,
                )
                self.assertLess(abs(sample.distance_km - distance_km), 0.01)

        # On the spherical Moon, +45 degrees east gives equal, positive X/Y.
        # A longitude sign reversal flips Y while leaving X and Z unchanged.
        for metadata in (sun_metadata, earth_metadata):
            coordinates = metadata["site_coordinates_used"]
            self.assertEqual(coordinates["longitude_deg_east"], 45.0)
            x_km, y_km, z_km = coordinates["observer_position_in_frame_km"]
            self.assertGreater(x_km, 0.0)
            self.assertGreater(y_km, 0.0)
            self.assertLess(z_km, 0.0)
            self.assertAlmostEqual(x_km, y_km, delta=1e-12)


def _circular_error(left_deg: float, right_deg: float) -> float:
    return abs((left_deg - right_deg + 180.0) % 360.0 - 180.0)


if __name__ == "__main__":
    unittest.main()
