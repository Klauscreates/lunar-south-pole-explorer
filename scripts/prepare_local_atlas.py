"""Bounded polar imagery atlas avoids thousands of narrow geographic image tiles.

4096x2048 is a display raster only; native point inspection still uses NASA grids.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from terrain_server import Terrain, png

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "apps/web/public/terrain"
terrain = Terrain()
width, height = 4096, 2048
lon, lat = np.meshgrid(
    -180 + (np.arange(width) + 0.5) / width * 360,
    -89.3 - (np.arange(height) + 0.5) / height * 0.7,
)
x, y = terrain.project(lon, lat)
files = {}
for kind in ("hillshade", "slope", "psr", "height_error"):
    rgba = np.zeros((height, width, 4), dtype="uint8")
    if kind == "hillshade":
        gray = np.zeros((height, width), dtype="float32")
        valid = np.zeros((height, width), dtype=bool)
        for name in ("regional", "local"):
            delta = terrain.grids[name][0]["resolution_m"]
            gx = (
                terrain.sample(name, x + delta, y)[0]
                - terrain.sample(name, x - delta, y)[0]
            ) / (2 * delta)
            gy = (
                terrain.sample(name, x, y + delta)[0]
                - terrain.sample(name, x, y - delta)[0]
            ) / (2 * delta)
            mask = terrain.sample(name, x, y)[1]
            intensity = np.clip(
                (0.65 - 0.7 * gx + 0.3 * gy) / np.sqrt(1 + gx * gx + gy * gy), 0.03, 1
            )
            gray = np.where(mask, 30 + 195 * intensity, gray)
            valid |= mask
        rgba[:, :, :3] = gray[:, :, None].astype("uint8")
        rgba[:, :, 3] = np.where(valid, 255, 0)
    elif kind in terrain.grids:
        values, valid = terrain.sample(kind, x, y)
        if kind == "psr":
            rgba[:, :, :3] = [137, 142, 220]
            rgba[:, :, 3] = np.where(valid & (values >= 0.5), 180, 0)
        else:
            t = np.clip(values / (20 if kind == "slope" else 5), 0, 1)
            stops = np.array(
                [[110, 160, 169], [213, 200, 136], [213, 133, 77], [172, 62, 69]]
            )
            for channel in range(3):
                rgba[:, :, channel] = np.interp(t, [0, 0.25, 0.5, 1], stops[:, channel])
            rgba[:, :, 3] = np.where(valid, 195, 0)
    path = OUT / f"local-{kind}.png"
    path.write_bytes(png(rgba))
    files[path.name] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }
    print(f"{path.name}: {path.stat().st_size:,} bytes", flush=True)
(OUT / "atlas.json").write_text(
    json.dumps(
        {
            "bounds_degrees": [-180, -90, 180, -89.3],
            "width": width,
            "height": height,
            "latitude_pixel_spacing_m": 0.7 * np.pi / 180 * 1737400 / height,
            "purpose": "display imagery; point values sampled from source rasters",
            "files": files,
        },
        indent=2,
    )
)
