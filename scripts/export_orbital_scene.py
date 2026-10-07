"""Reproducible geometric Moon-centered scene export, separate from apparent LOS."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import spiceypy as spice

from science.ephemeris.kernels import KernelRepository
from science.ephemeris.spice import _isolated_kernel_pool

ROOT = Path(__file__).resolve().parents[1]


def build_scene() -> dict:
    repository = KernelRepository(ROOT / "data/kernels", auto_download=False)
    kernels = repository.resolve()  # Checks every pinned size and SHA-256.
    frame = repository.manifest.reference_frame_name
    index = json.loads((ROOT/'outputs/simulation-index.json').read_text())
    coverage = index['time_range']
    start = datetime.fromisoformat(coverage['start_utc'].replace('Z','+00:00'))
    rows = []
    with _isolated_kernel_pool(spice, kernels):
        radii = {name.lower(): spice.bodvrd(name, "RADII", 3)[1].tolist()
                 for name in ("EARTH", "SUN", "MOON")}
        for i in range(coverage['sample_count']):
            utc = (start + timedelta(minutes=10 * i)).isoformat().replace("+00:00", "Z")
            et = spice.str2et(utc)
            earth = spice.spkpos("EARTH", et, frame, "NONE", "MOON")[0]
            sun = spice.spkpos("SUN", et, frame, "NONE", "MOON")[0]
            rotation = spice.pxform("IAU_EARTH", frame, et)
            if not np.isfinite(np.concatenate([earth, sun, rotation.flatten()])).all():
                raise ValueError(f"Non-finite geometry at {utc}")
            if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-12) or not np.isclose(np.linalg.det(rotation), 1):
                raise ValueError(f"Invalid rotation at {utc}")
            rows.append({"utc": utc, "earth_km": earth.tolist(), "sun_km": sun.tolist(),
                         "earth_fixed_to_scene": rotation.flatten().tolist()})
    return {"schema": 1, "frame": frame, "origin": "MOON", "correction": "NONE",
            "step_seconds": 600, "earth_orientation": "IAU_EARTH (text PCK; not precision ITRF/EOP)",
            "matrix_layout": "row-major", "radii_km": radii, "samples": rows,
            "provenance": {"spiceypy": spice.__version__, "cspice": spice.tkvrsn("TOOLKIT"),
                           "kernel_manifest_sha256": repository.manifest.sha256,
                           "kernels": [{k: v for k, v in kernel.as_provenance().items() if k != "local_path"} for kernel in kernels]}}


def main() -> None:
    data = (json.dumps(build_scene(), separators=(",", ":"), allow_nan=False) + "\n").encode()
    destination = ROOT / "outputs/orbital-scene.json"
    destination.write_bytes(data)
    manifest = {"url": "/data/orbital-scene.json", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    (ROOT / "outputs/orbital-index.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Exported geometric epochs from simulation coverage, verified kernels; {manifest['sha256']}")


if __name__ == "__main__":
    main()
