"""Reproducible CPU tile-generation measurements, separate from WebGL frame rate."""

import json
from pathlib import Path
from time import perf_counter

import numpy as np
from terrain_server import Terrain

terrain = Terrain()
keys = [("height", 10, x, 1023) for x in range(1016, 1032)]
cold = []
sizes = []
for key in keys:
    start = perf_counter()
    body, _ = terrain.tile(*key)
    cold.append((perf_counter() - start) * 1000)
    sizes.append(len(body))
warm = []
for key in keys:
    start = perf_counter()
    terrain.tile(*key)
    warm.append((perf_counter() - start) * 1000)
result = {
    "samples": len(keys),
    "polar_tile_shape": [513, 17],
    "tile_bytes": sizes[0],
    "cold_median_ms": float(np.median(cold)),
    "cold_p95_ms": float(np.percentile(cold, 95)),
    "warm_median_ms": float(np.median(warm)),
    "scope": "CPU generation only, not network or WebGL render FPS",
}
path = Path(__file__).resolve().parents[1] / "outputs/web-terrain-profile.json"
path.write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
