import copy
import json
from pathlib import Path
import tempfile
import unittest

from science.component_spec import audit_design, cell_reference_at_temperature, load_component_spec

FOLDER = Path(__file__).resolve().parents[1] / "data/spacecraft/reference-lander-v1"


class ComponentSpecTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((FOLDER / "component-spec.json").read_text())

    def test_reference_preserves_reported_efficiency(self):
        row = cell_reference_at_temperature(self.spec, 301.15)
        self.assertEqual(row["reference_am0_efficiency"], .307)
        self.assertAlmostEqual(row["reference_am0_power_density_w_m2"], 415.371)
        self.assertAlmostEqual(row["rounded_table_power_density_w_m2"], 421.05)
        self.assertIsNone(row["uncertainty"])
        self.assertFalse(row["assembly_validated"])

    def test_domain_refuses_extrapolation(self):
        for temperature in (250, 288.149, 398.151, float("nan"), float("inf"), True, "301"):
            with self.subTest(temperature=temperature), self.assertRaises(ValueError):
                cell_reference_at_temperature(self.spec, temperature)
        cold = cell_reference_at_temperature(self.spec, 288.15)
        warm = cell_reference_at_temperature(self.spec, 398.15)
        self.assertGreater(cold["reference_am0_efficiency"], warm["reference_am0_efficiency"])

    def test_all_active_inputs_audited_without_mutation(self):
        design = json.loads((FOLDER / "design.json").read_text())
        original = copy.deepcopy(design)
        result = audit_design(design, self.spec)
        self.assertEqual(len(result["inputs"]), 18)
        self.assertEqual(len({r["input"] for r in result["inputs"]}), 18)
        self.assertTrue(all(r["promoted"] is False for r in result["inputs"]))
        self.assertEqual(design, original)

    def test_corrupt_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            spec = copy.deepcopy(self.spec)
            spec["source"]["path"] = "bad.pdf"
            (folder / "bad.pdf").write_bytes(b"not the source")
            path = folder / "spec.json"
            path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError, "checksum"):
                load_component_spec(path)


if __name__ == "__main__":
    unittest.main()
