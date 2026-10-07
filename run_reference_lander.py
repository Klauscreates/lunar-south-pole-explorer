#!/usr/bin/env python3
"""Build reproducible reference-design studies over the five validated sites.

All spacecraft properties/boundaries are declared design assumptions. The
Surveyor VII record is archival evidence only, never a calibration of R1.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import tempfile

from science.errors import ConfigurationError
from science.export import write_json
from science.spacecraft_analysis import analyze_spacecraft_files

ROOT = Path(__file__).resolve().parent
DESIGN = ROOT / "data/spacecraft/reference-lander-v1/design.json"
EVIDENCE = ROOT / "data/spacecraft/surveyor7/evidence.json"
OUT = ROOT / "outputs/spacecraft"
IMPLEMENTATION_FILES = [
    "run_reference_lander.py", "science/spacecraft.py", "science/spacecraft_analysis.py",
    "science/thermal.py", "science/power.py", "science/visibility.py",
]
COLUMNS = [
    "electrical_w", "cell_temperature_k", "efficiency", "incidence_cosine",
    "unoccluded_fraction", "earth_self_clear", "earth_terrain_clear", "earth_los_clear",
    "direct_incident_w", "reflected_incident_w",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_geometry(design: dict, folder: Path) -> tuple[Path, dict]:
    """Tessellate the declared cuboids; the definition is the source geometry."""
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
             (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
             (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)]
    lines = ["# Project-authored reference design R1, not mission CAD; metres"]
    offset = 1
    for box in design["boxes"]:
        low, high = box["min"], box["max"]
        if len(low) != 3 or len(high) != 3 or any(
            not math.isfinite(a) or not math.isfinite(b) or a >= b
            for a, b in zip(low, high)
        ):
            raise ConfigurationError("Invalid reference-design cuboid")
        x, y, z = low
        X, Y, Z = high
        vertices = [(x, y, z), (X, y, z), (X, Y, z), (x, Y, z),
                    (x, y, Z), (X, y, Z), (X, Y, Z), (x, Y, Z)]
        lines.append(f"o {box['id']}")
        lines.extend("v " + " ".join(str(v) for v in point) for point in vertices)
        lines.extend("f " + " ".join(str(i + offset) for i in face) for face in faces)
        offset += 8
    mesh = folder / "reference.obj"
    mesh.write_text("\n".join(lines) + "\n", encoding="utf-8")
    panel = design["panel"]
    n = panel["samples_per_side"]
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 32:
        raise ConfigurationError("Reference panel sample count is invalid")
    x0, x1 = panel["x_bounds_m"]
    z0, z1 = panel["z_bounds_m"]
    if x1 <= x0 or z1 <= z0 or not math.isclose((x1-x0)*(z1-z0), panel["area_m2"]):
        raise ConfigurationError("Reference panel area disagrees with active surface")
    samples = [[x0+(i+.5)*(x1-x0)/n, panel["plane_y_m"], z0+(j+.5)*(z1-z0)/n]
               for i in range(n) for j in range(n)]
    manifest = {
        "schema_version": "1.0.0", "model_id": design["model_id"],
        "provenance": {"source": "Project-authored design.json; geometry is defined, not measured",
                       "revision": "R1", "spacecraft": design["identity"]},
        "mesh": {"path": mesh.name, "sha256": sha(mesh), "format": "obj",
                 "units": "m", "scale_to_m": 1},
        "panels": [{"id": panel["id"], "area_m2": panel["area_m2"],
                    "normal_body": panel["normal_body"], "sample_points_m": samples,
                    "sample_weights": [1 / (n*n)] * (n*n)}],
        "antennas": [design["antenna"]],
    }
    path = folder / "geometry.json"
    write_json(manifest, path)
    return path, manifest


def main() -> None:
    design = json.loads(DESIGN.read_text())
    evidence = json.loads(EVIDENCE.read_text())
    pdf = EVIDENCE.parent / "sources/19690008977.pdf"
    if not pdf.is_file() or sha(pdf) != evidence["source"]["sha256"]:
        raise ConfigurationError("Download and verify the Surveyor VII source PDF before rebuilding")
    index = json.loads((ROOT / "outputs/simulation-index.json").read_text())
    parents = []
    for site in index["sites"]:
        site_id = site["id"]
        if not all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in site_id):
            raise ConfigurationError("Invalid site identifier")
        path = ROOT / "outputs" / ("simulation.json" if site_id == "test-site-a"
                                   else f"candidates/{site_id}.json")
        if sha(path) != site["sha256"]:
            raise ConfigurationError(f"Parent checksum mismatch: {site_id}")
        parents.append((site, path, json.loads(path.read_text())))

    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    with tempfile.TemporaryDirectory(prefix="lunar-reference-") as temporary:
        folder = Path(temporary)
        geometry_path, manifest = make_geometry(design, folder)
        # Keep the exact tiny generated geometry available for independent review.
        (OUT / "reference.obj").write_bytes((folder / "reference.obj").read_bytes())
        write_json(manifest, OUT / "geometry.json")
        for site, parent_path, parent in parents:
            scenarios = []
            for boundary in design["boundary_cases"]:
                flux = {k: v for k, v in boundary.items() if k not in {"id", "label"}}
                environment = {
                    "schema_version": "1.0.0",
                    "provenance": {"source": design["boundary_source"], "revision": "R1",
                                   "method": "Constant panel-plane sensitivity case; no site radiometry"},
                    "samples": [{"timestamp": s["timestamp"], "panels": {"array": flux}}
                                for s in parent["samples"]],
                }
                environment_path = folder / "environment.json"
                write_json(environment, environment_path)
                for pose in design["attitudes"]:
                    hardware = {
                        "schema_version": "1.0.0",
                        "geometry_manifest": {"path": geometry_path.name, "sha256": sha(geometry_path)},
                        "attitude_deg": {k: pose[k] for k in ("yaw", "pitch", "roll")},
                        "panels": {"array": {"thermal_parameters": design["thermal_parameters"],
                                             "initial_cell_temperature_k": design["initial_cell_temperature_k"]}},
                        "environment_profile": {"path": environment_path.name, "sha256": sha(environment_path)},
                    }
                    hardware["attitude_deg"]["source"] = "Commanded reference-design scenario; not a surveyed spacecraft pose"
                    hardware_path = folder / "hardware.json"
                    write_json(hardware, hardware_path)
                    result = analyze_spacecraft_files(parent_path, hardware_path)
                    rows = []
                    maximum_residual = 0.0
                    for s in result["samples"]:
                        p, a = s["panels"][0], s["antennas"][0]
                        t, g = p["thermal_electrical"], p["geometry"]
                        residual = p["integration_from_previous_epoch"]
                        if residual:
                            maximum_residual = max(maximum_residual, abs(residual["energy_balance_residual_j"]))
                        rows.append([
                            round(t["electrical_output_w"], 6), round(t["cell_temperature_k"], 6),
                            round(t["temperature_derated_efficiency"], 9), round(g["incidence_cosine"], 9),
                            round(g["unoccluded_sample_fraction"], 9), a["self_los_clear"],
                            a["earth_center_terrain_clear"], a["earth_center_geometric_los_clear"],
                            round(t["direct_solar_incident_power_w"], 6), round(t["wall_reflected_incident_power_w"], 6),
                        ])
                    scenarios.append({
                        "id": f"{pose['id']}--{boundary['id']}", "pose_id": pose["id"],
                        "boundary_id": boundary["id"], "input_sha256": result["input_sha256"],
                        "maximum_interval_energy_residual_j": maximum_residual, "rows": rows,
                    })
            artifact = {
                "schema_version": "1.0.0", "analysis_status": "DESIGN_STUDY_UNVALIDATED",
                "flight_certified": False, "site_id": site["id"], "parent_sha256": site["sha256"],
                "design_sha256": sha(DESIGN), "evidence_sha256": sha(EVIDENCE),
                "implementation_sha256": {name: sha(ROOT / name) for name in IMPLEMENTATION_FILES},
                "design": design, "historical_evidence": evidence, "columns": COLUMNS,
                "timestamps": [s["timestamp"] for s in parent["samples"]], "scenarios": scenarios,
            }
            path = OUT / f"{site['id']}.json"
            write_json(artifact, path, compact=True)
            entries.append({"site_id": site["id"], "url": f"/data/spacecraft/{path.name}",
                            "sha256": sha(path), "parent_sha256": site["sha256"]})
            print(f"{site['name']}: {len(scenarios)} design scenarios × {len(parent['samples'])} epochs", flush=True)
    write_json({"schema_version": "1.0.0", "model_id": design["model_id"], "sites": entries}, OUT / "index.json")


if __name__ == "__main__":
    main()
