import math
import unittest

from science.visibility import disk_visible_fraction


class DiskVisibilityTests(unittest.TestCase):
    def test_center_on_skyline_is_half_visible(self):
        self.assertAlmostEqual(disk_visible_fraction(0.0, 0.25), 0.5, places=12)

    def test_full_disk_thresholds(self):
        self.assertEqual(disk_visible_fraction(0.25, 0.25), 1.0)
        self.assertEqual(disk_visible_fraction(-0.25, 0.25), 0.0)

    def test_visible_fraction_is_symmetric(self):
        positive = disk_visible_fraction(0.1, 0.25)
        negative = disk_visible_fraction(-0.1, 0.25)
        self.assertAlmostEqual(positive + negative, 1.0, places=12)

    def test_point_target_fallback(self):
        self.assertEqual(disk_visible_fraction(0.1, 0.0), 1.0)
        self.assertEqual(disk_visible_fraction(-0.1, 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()

