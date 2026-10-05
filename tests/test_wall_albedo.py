import math
import unittest
from dataclasses import replace

from science.wall_albedo import WallFacet, estimate_wall_reflected_irradiance


def facet(**overrides):
    baseline = WallFacet(
        center_enu_m=(2.0, 0.0, 0.0),
        normal_enu=(-1.0, 0.0, 0.0),
        area_m2=1.0,
        broadband_reflectance=0.5,
        sun_visible_fraction=1.0,
    )
    return replace(baseline, **overrides)


def estimate(facets, **overrides):
    arguments = {
        "panel_position_enu_m": (0.0, 0.0, 0.0),
        "panel_normal_enu": (1.0, 0.0, 0.0),
        "sun_direction_enu": (-1.0, 0.0, 0.0),
        "direct_normal_irradiance_w_m2": 1_000.0,
        "facets": facets,
    }
    arguments.update(overrides)
    return estimate_wall_reflected_irradiance(**arguments)


class WallAlbedoTests(unittest.TestCase):
    def test_lambertian_view_factor_and_inverse_square(self):
        near = estimate([facet()])
        far = estimate([facet(center_enu_m=(4.0, 0.0, 0.0))])
        expected = 1_000.0 * 0.5 / (math.pi * 2.0**2)
        self.assertAlmostEqual(
            near["wall_reflected_solar_irradiance_w_m2"], expected
        )
        self.assertAlmostEqual(
            far["wall_reflected_solar_irradiance_w_m2"], expected / 4.0
        )
        self.assertAlmostEqual(
            near["total_panel_to_wall_view_factor"], 1.0 / (4.0 * math.pi)
        )
        self.assertEqual(near["facet_count"], 1)
        self.assertEqual(near["active_facet_count"], 1)
        self.assertEqual(near["assumed_clear_wall_to_panel_facet_count"], 1)

    def test_panel_wall_and_sun_orientation_gate_reflection(self):
        self.assertEqual(
            estimate(
                [facet()], panel_normal_enu=(-1.0, 0.0, 0.0)
            )["wall_reflected_solar_irradiance_w_m2"],
            0.0,
        )
        self.assertEqual(
            estimate([facet(normal_enu=(1.0, 0.0, 0.0))])[
                "wall_reflected_solar_irradiance_w_m2"
            ],
            0.0,
        )
        self.assertEqual(
            estimate([facet()], sun_direction_enu=(1.0, 0.0, 0.0))[
                "wall_reflected_solar_irradiance_w_m2"
            ],
            0.0,
        )

    def test_visibility_and_reflectance_are_explicit_multipliers(self):
        baseline = estimate([facet()])["wall_reflected_solar_irradiance_w_m2"]
        quarter_eighth = estimate(
            [facet(sun_visible_fraction=0.25, panel_visible_fraction=0.5)]
        )
        self.assertAlmostEqual(
            quarter_eighth["wall_reflected_solar_irradiance_w_m2"],
            baseline / 8.0,
        )
        self.assertEqual(
            quarter_eighth["assumed_clear_wall_to_panel_facet_count"], 0
        )
        for blocked in (
            facet(sun_visible_fraction=0.0),
            facet(panel_visible_fraction=0.0),
            facet(broadband_reflectance=0.0),
        ):
            with self.subTest(blocked=blocked):
                result = estimate([blocked])
                self.assertEqual(
                    result["wall_reflected_solar_irradiance_w_m2"], 0.0
                )
                self.assertEqual(result["active_facet_count"], 0)

    def test_multiple_finite_facets_sum_without_default_albedo(self):
        facets = [facet(), facet(center_enu_m=(4.0, 0.0, 0.0))]
        result = estimate(facets)
        self.assertAlmostEqual(
            result["wall_reflected_solar_irradiance_w_m2"],
            1_000.0 * 0.5 / math.pi * (1.0 / 4.0 + 1.0 / 16.0),
        )
        self.assertEqual(result["facet_count"], 2)
        self.assertEqual(result["active_facet_count"], 2)
        self.assertLess(
            result["wall_reflected_solar_irradiance_w_m2"], 1_000.0
        )
        empty = estimate([])
        self.assertEqual(empty["wall_reflected_solar_irradiance_w_m2"], 0.0)
        self.assertEqual(empty["facet_count"], 0)
        with self.assertRaises(TypeError):
            WallFacet(
                center_enu_m=(2.0, 0.0, 0.0),
                normal_enu=(-1.0, 0.0, 0.0),
                area_m2=1.0,
                sun_visible_fraction=1.0,
            )

    def test_invalid_inputs_and_near_field_facets_fail_closed(self):
        bad_calls = (
            lambda: estimate([facet()], direct_normal_irradiance_w_m2=-1.0),
            lambda: estimate([facet()], direct_normal_irradiance_w_m2=math.nan),
            lambda: estimate([facet()], direct_normal_irradiance_w_m2=10**400),
            lambda: estimate([facet()], panel_normal_enu=(0.0, 0.0, 0.0)),
            lambda: estimate([facet()], sun_direction_enu=(math.inf, 0.0, 0.0)),
            lambda: estimate([facet()], panel_position_enu_m=(math.nan, 0, 0)),
            lambda: estimate([facet(area_m2=0.0)]),
            lambda: estimate([facet(area_m2=2.0)]),
            lambda: estimate([facet(center_enu_m=(0.0, 0.0, 0.0))]),
            lambda: estimate([facet(broadband_reflectance=-0.1)]),
            lambda: estimate([facet(broadband_reflectance=1.1)]),
            lambda: estimate([facet(sun_visible_fraction=1.1)]),
            lambda: estimate([facet(panel_visible_fraction=-0.1)]),
            lambda: estimate([facet(normal_enu=(0.0, 0.0, 0.0))]),
            lambda: estimate([{}]),
            lambda: estimate(None),
        )
        for invalid in bad_calls:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                invalid()

    def test_overlapping_facets_cannot_exceed_unit_view_factor(self):
        # A supplied scene with repeated near-identical patches overfills the
        # panel hemisphere. Reject instead of reporting unphysical flux.
        patches = [
            facet(center_enu_m=(2.0, offset * 1e-4, 0.0))
            for offset in range(16)
        ]
        with self.assertRaisesRegex(ValueError, "view factor exceeds one"):
            estimate(patches)


if __name__ == "__main__":
    unittest.main()
