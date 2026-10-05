#!/usr/bin/env python3
"""Print the live R1 property audit and manufacturer-range coverage as JSON."""
import hashlib
import json
from pathlib import Path

from science.component_spec import audit_design, cell_reference_at_temperature, load_component_spec

ROOT = Path(__file__).resolve().parent


def main():
    folder = ROOT / "data/spacecraft/reference-lander-v1"
    spec = load_component_spec(folder / "component-spec.json")
    design_path = folder / "design.json"
    design = json.loads(design_path.read_text())
    result = audit_design(design, spec)
    result["component_source_sha256"] = spec["source"]["sha256"]
    result["cell_reference"] = cell_reference_at_temperature(spec, 301.15)
    result["existing_study_coverage"] = []
    index = json.loads((ROOT / "outputs/spacecraft/index.json").read_text())
    low, high = spec["coefficient_temperature_range_k"]
    for entry in index["sites"]:
        path = ROOT / "outputs/spacecraft" / f"{entry['site_id']}.json"
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Study checksum mismatch")
        data = json.loads(path.read_text())
        if data["design_sha256"] != hashlib.sha256(design_path.read_bytes()).hexdigest():
            raise ValueError("Study uses stale design")
        column = data["columns"].index("cell_temperature_k")
        temperatures = [row[column] for scenario in data["scenarios"] for row in scenario["rows"]]
        result["existing_study_coverage"].append({
            "site_id": entry["site_id"], "epochs": len(temperatures),
            "outside_cell_coefficient_range": sum(not low <= t <= high for t in temperatures),
            "minimum_k": min(temperatures), "maximum_k": max(temperatures),
            "interpretation": "Coverage of assumed R1 temperatures, not measured cell temperatures",
        })
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
