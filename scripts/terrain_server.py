"""Local, read-only web terrain service. Small geographic tiles, bounded LRU cache.

Heightmaps contain true metres over the 1737.4 km lunar sphere. Geographic tiles
are 2x1 at level zero; rows run north to south. Theme maps are visualization only.
"""

import hashlib
import json
import math
import re
import struct
import zlib
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/web_terrain"
RADIUS = 1737400.0


class Terrain:
    def __init__(self):
        self.manifest = json.loads((DATA / "manifest.json").read_text())
        self.grids = {}
        for record in self.manifest["sources"]:
            path = DATA / (record["name"] + ".npy")
            if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError(f"Terrain integrity failure: {path}")
            self.grids[record["name"]] = (record, np.load(path, mmap_mode="r"))
        self.pyramids = {
            (name, factor): np.load(DATA / f"{name}_{factor}.npy", mmap_mode="r")
            for name in ("local", "regional")
            for factor in (2, 4, 8, 16)
        }

    @staticmethod
    def project(lon, lat):
        rho = 2 * RADIUS * np.tan(np.radians(90 + lat) / 2)
        return rho * np.sin(np.radians(lon)), rho * np.cos(np.radians(lon))

    def sample(self, name, x, y, spacing=0):
        record, values = self.grids[name]
        if name in ("local", "regional") and spacing > record["resolution_m"] * 2:
            factor = min(16, 2 ** int(math.log2(spacing / record["resolution_m"])))
            values = self.pyramids[(name, factor)]
        left, bottom, right, top = record["bounds"]
        rows = (top - y) / (top - bottom) * values.shape[0] - 0.5
        cols = (x - left) / (right - left) * values.shape[1] - 0.5
        valid = (x >= left) & (x <= right) & (y >= bottom) & (y <= top)
        result = map_coordinates(
            values,
            [rows.ravel(), cols.ravel()],
            order=0 if name in ("psr", "count") else 1,
            mode="nearest",
        ).reshape(x.shape)
        return result, valid

    def heights(self, lon, lat, spacing=0):
        result, _ = self.sample("global", lon, lat)
        x, y = self.project(lon, lat)
        for name in ("regional", "local"):
            height, valid = self.sample(name, x, y, spacing)
            left, bottom, right, top = self.grids[name][0]["bounds"]
            # Feather only the visualization crop border to avoid vertical seams.
            border = 480 if name == "regional" else 240
            blend = np.clip(
                np.minimum.reduce([x - left, right - x, y - bottom, top - y]) / border,
                0,
                1,
            )
            result = np.where(valid, result * (1 - blend) + height * blend, result)
        return result

    def inspect(self, lon, lat):
        x, y = self.project(np.array([lon]), np.array([lat]))
        output = {"latitude": lat, "longitude": lon, "frame": "MOON_ME / DE421"}
        for name in ("local", "regional"):
            value, valid = self.sample(name, x, y)
            if valid[0]:
                output.update(
                    elevation_m=float(value[0]),
                    dataset=self.grids[name][0]["source_url"].split("/")[-1],
                    resolution_m=self.grids[name][0]["resolution_m"],
                )
                break
        else:
            value, _ = self.sample("global", np.array([lon]), np.array([lat]))
            output.update(
                elevation_m=float(value[0]),
                dataset="NASA SVS / LOLA ldem_4.tif",
                resolution_m=7580.8,
            )
        for name in (
            "slope",
            "height_error",
            "slope_error",
            "effective_resolution",
            "count",
            "psr",
        ):
            if name in self.grids:
                value, valid = self.sample(name, x, y)
                output[name] = float(value[0]) if valid[0] else None
        return output

    @lru_cache(maxsize=512)  # noqa: B019 - one process-lifetime Terrain, bounded cache.
    def tile(self, kind, level, tx, ty):
        extent = 180 / 2**level
        west, north = -180 + tx * extent, 90 - ty * extent
        polar = kind == "height" and north <= -80
        width, size = (
            (17, 513) if polar else ((65, 65) if kind == "height" else (256, 256))
        )
        # Heightmap includes edges; imagery samples pixel centers.
        axis = (
            np.linspace(0, 1, size)
            if kind == "height"
            else (np.arange(size) + 0.5) / size
        )
        xaxis = np.linspace(0, 1, width) if kind == "height" else axis
        lon, lat = np.meshgrid(west + xaxis * extent, north - axis * extent)
        spacing = math.radians(extent) * RADIUS / (size - 1)
        if kind == "height":
            return self.heights(lon, lat, spacing).astype(
                "<f4"
            ).tobytes(), "application/octet-stream"
        x, y = self.project(lon, lat)
        rgba = np.zeros((size, size, 4), dtype=np.uint8)
        if kind in ("slope", "psr", "height_error"):
            if kind not in self.grids:
                return png(rgba), "image/png"
            values, valid = self.sample(kind, x, y)
            if kind == "psr":
                rgba[:, :, :3] = [137, 142, 220]
                rgba[:, :, 3] = np.where(valid & (values >= 0.5), 175, 0)
            else:
                limit = 20 if kind == "slope" else 5
                t = np.clip(values / limit, 0, 1)
                stops = np.array(
                    [[110, 160, 169], [213, 200, 136], [213, 133, 77], [172, 62, 69]]
                )
                for channel in range(3):
                    rgba[:, :, channel] = np.interp(
                        t, [0, 0.25, 0.5, 1], stops[:, channel]
                    )
                rgba[:, :, 3] = np.where(valid, 195, 0)
        else:
            # Relief texture from real DEM gradients, fixed cartographic light.
            h = self.heights(lon, lat, spacing)
            delta = max(10, min(240, spacing))
            name = "local" if spacing < 120 else "regional"
            gx = (
                self.sample(name, x + delta, y, spacing)[0]
                - self.sample(name, x - delta, y, spacing)[0]
            ) / (2 * delta)
            gy = (
                self.sample(name, x, y + delta, spacing)[0]
                - self.sample(name, x, y - delta, spacing)[0]
            ) / (2 * delta)
            light = np.clip(
                (1 - 0.8 * gx + 0.5 * gy) / np.sqrt(1 + gx * gx + gy * gy), 0.08, 1.7
            )
            gray = np.clip(115 * light + (h / 10000) * 15, 24, 210).astype("uint8")
            rgba[:, :, :3] = gray[:, :, None]
            valid = self.sample("regional", x, y)[1]
            rgba[:, :, 3] = np.where(valid, 255, 0)
        return png(rgba), "image/png"


def png(rgba):
    def chunk(name, data):
        return (
            struct.pack(">I", len(data))
            + name
            + data
            + struct.pack(">I", zlib.crc32(name + data))
        )

    h, w, _ = rgba.shape
    raw = b"".join(b"\0" + row.tobytes() for row in rgba)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 3))
        + chunk(b"IEND", b"")
    )


class Handler(BaseHTTPRequestHandler):
    terrain = None
    protocol_version = "HTTP/1.1"
    timeout = 15

    def do_GET(self):
        path = urlparse(self.path)
        try:
            match = re.fullmatch(
                r"/(height|hillshade|slope|psr|height_error)/(\d+)/(\d+)/(\d+)",
                path.path,
            )
            if match:
                kind, level, x, y = match.groups()
                level, x, y = int(level), int(x), int(y)
                if (
                    not 0 <= level <= 14
                    or not 0 <= x < 2 ** (level + 1)
                    or not 0 <= y < 2**level
                ):
                    raise ValueError("Tile outside supported pyramid")
                body, mime = self.terrain.tile(kind, level, x, y)
            elif path.path == "/inspect":
                query = parse_qs(path.query)
                lon, lat = float(query["lon"][0]), float(query["lat"][0])
                if (
                    not math.isfinite(lon + lat)
                    or not -180 <= lon <= 180
                    or not -90 <= lat <= 90
                ):
                    raise ValueError("Invalid lunar coordinates")
                body = json.dumps(self.terrain.inspect(lon, lat)).encode()
                mime = "application/json"
            elif path.path == "/health":
                body, mime = (
                    json.dumps(
                        {"status": "ok", "cache": str(self.terrain.tile.cache_info())}
                    ).encode(),
                    "application/json",
                )
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(body)
        except (ValueError, KeyError) as exc:
            self.send_error(400, str(exc))
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


class TerrainHTTPServer(ThreadingHTTPServer):
    # Camera flights burst concurrent height + imagery requests. The stdlib's
    # five-connection backlog is too small; keep-alive also avoids reconnect churn.
    request_queue_size = 128
    daemon_threads = True


if __name__ == "__main__":
    Handler.terrain = Terrain()
    print("NASA terrain service ready on http://127.0.0.1:8766", flush=True)
    TerrainHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
