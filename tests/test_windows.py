import unittest
from datetime import datetime, timedelta, timezone

from science.windows import extract_boolean_windows


class WindowExtractionTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.timestamps = [
            self.start + timedelta(minutes=10 * index) for index in range(5)
        ]
        self.end = self.start + timedelta(minutes=40)

    def test_grid_aligned_run(self):
        windows = extract_boolean_windows(
            self.timestamps, [False, True, True, False, False], self.end
        )
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["start_utc"], "2026-10-01T00:10:00Z")
        self.assertEqual(windows[0]["end_utc"], "2026-10-01T00:30:00Z")
        self.assertEqual(windows[0]["duration_seconds"], 1200.0)

    def test_run_through_end(self):
        windows = extract_boolean_windows(
            self.timestamps, [False, False, True, True, True], self.end
        )
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["duration_seconds"], 1200.0)

    def test_zero_duration_state_at_end_is_ignored(self):
        windows = extract_boolean_windows(
            self.timestamps, [False, False, False, False, True], self.end
        )
        self.assertEqual(windows, [])


if __name__ == "__main__":
    unittest.main()

