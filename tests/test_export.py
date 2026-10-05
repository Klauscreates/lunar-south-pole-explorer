"""Atomic export and input-preservation regression tests."""

from __future__ import annotations

import math
import stat
import tempfile
import unittest
from pathlib import Path

from science.export import write_csv, write_json


class AtomicExportTests(unittest.TestCase):
    def test_json_does_not_reuse_existing_legacy_temp_path(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "analysis.json"
            legacy_temp = Path(folder) / "analysis.json.tmp"
            legacy_temp.write_text("pinned input artifact", encoding="utf-8")
            write_json({"status": "ok"}, output)
            self.assertEqual(legacy_temp.read_text(encoding="utf-8"), "pinned input artifact")
            self.assertIn('"status": "ok"', output.read_text(encoding="utf-8"))
            self.assertEqual(
                sorted(item.name for item in Path(folder).iterdir()),
                ["analysis.json", "analysis.json.tmp"],
            )

    def test_csv_does_not_reuse_existing_legacy_temp_path(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "analysis.csv"
            legacy_temp = Path(folder) / "analysis.csv.tmp"
            legacy_temp.write_text("pinned input artifact", encoding="utf-8")
            write_csv({"samples": []}, output)
            self.assertEqual(legacy_temp.read_text(encoding="utf-8"), "pinned input artifact")
            self.assertIn("timestamp_utc", output.read_text(encoding="utf-8"))

    def test_failed_json_export_preserves_destination_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "analysis.json"
            output.write_text("previous valid result", encoding="utf-8")
            with self.assertRaises(ValueError):
                write_json({"invalid": math.nan}, output)
            self.assertEqual(output.read_text(encoding="utf-8"), "previous valid result")
            self.assertEqual([item.name for item in Path(folder).iterdir()], ["analysis.json"])

    def test_overwrite_preserves_existing_file_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "analysis.json"
            output.write_text("old", encoding="utf-8")
            output.chmod(0o640)
            write_json({"new": True}, output)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o640)

    def test_no_overwrite_never_replaces_an_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "analysis.json"
            write_json({"first": True}, output, overwrite=False)
            original = output.read_bytes()
            with self.assertRaises(FileExistsError):
                write_json({"second": True}, output, overwrite=False)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual([item.name for item in Path(folder).iterdir()], ["analysis.json"])


if __name__ == "__main__":
    unittest.main()
