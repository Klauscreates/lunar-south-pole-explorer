"""Prepare bounded NASA rasters and explicit provenance for the visual tile service.

Separate from the validated science engine. Never changes its input rasters or exports.
"""

import hashlib
import json
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/web_terrain"
PUBLIC = ROOT / "apps/web/public/terrain"
SVS = "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/"
PGDA = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_grid(name, data, bounds, resolution, source, **extra):
    if not np.all(np.isfinite(data)):
        raise ValueError(f"Non-finite raster: {name}")
    path = OUT / f"{name}.npy"
    np.save(path, data.astype("float32"))
    return dict(
        name=name,
        bounds=list(bounds),
        resolution_m=resolution,
        source_url=source,
        sha256=digest(path),
        shape=list(data.shape),
        **extra,
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 1,
        "radius_m": 1737400,
        "frame": "MOON_ME / DE421",
        "sources": [],
        "tile_size": 65,
        "maximum_level": 14,
        "resource_evidence": {
            "status": "Dataset not loaded",
            "types": [
                "hydrogen evidence",
                "ice stability",
                "direct observation",
                "model inference",
            ],
        },
    }
    for name in ("ldem_4.tif", "lroc_color_2k.jpg"):
        target = OUT / name if name.endswith("tif") else PUBLIC / name
        if not target.exists():
            urllib.request.urlretrieve(SVS + name, target)
    with rasterio.open(OUT / "ldem_4.tif") as src:
        # NASA SVS float TIFF is kilometres above 1737.4 km, 4 pixels/degree.
        data = src.read(1).astype("float32") * 1000
        manifest["sources"].append(
            save_grid(
                "global",
                data,
                [-180, -90, 180, 90],
                7580.8,
                SVS + "ldem_4.tif",
                units="m",
                registration="pixel centers",
                source_sha256=digest(OUT / "ldem_4.tif"),
            )
        )
    manifest["imagery"] = {
        "source_url": SVS + "lroc_color_2k.jpg",
        "sha256": digest(PUBLIC / "lroc_color_2k.jpg"),
        "width": 2048,
        "height": 1024,
        "purpose": "global LROC context; local detail uses DEM hillshade",
    }
    for meta_path in sorted((ROOT / "data/processed").glob("*.metadata.json")):
        meta = json.loads(meta_path.read_text())
        res = meta["source_pixel_size_m"][0]
        name = "local" if res == 10 else "regional"
        path = Path(meta["crop_path"])
        if digest(path) != meta["crop_sha256"]:
            raise ValueError(f"Science crop hash mismatch: {path}")
        with rasterio.open(path) as src:
            data = src.read(1)
            record = save_grid(
                name,
                data,
                src.bounds,
                res,
                meta["source_url"],
                source_sha256=meta["crop_sha256"],
            )
            # Average LOD pyramid is built once, never in the browser.
            record["pyramid"] = []
            for factor in (2, 4, 8, 16):
                lod = src.read(
                    1,
                    out_shape=(
                        max(2, src.height // factor),
                        max(2, src.width // factor),
                    ),
                    resampling=Resampling.average,
                )
                np.save(OUT / f"{name}_{factor}.npy", lod)
                record["pyramid"].append(factor)
            manifest["sources"].append(record)
    # Authoritative thematic products: a bounded 24 km crop, not a global claim.
    layers = {
        "slope": "LDSM_80S_20MPP_ADJ.TIF",
        "psr": "LPSR_80S_20MPP_ADJ.TIF",
        "height_error": "LDEM_80S_20MPP_ADJ_ERR.TIF",
        "slope_error": "LDSM_80S_20MPP_ADJ_ERR.TIF",
        "effective_resolution": "LDEM_80S_20MPP_ADJ_EFFRES.TIF",
        "count": "LDEC_80S_20MPP_ADJ.TIF",
    }
    env = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".TIF",
        "GDAL_HTTP_TIMEOUT": "60",
        "GDAL_HTTP_MAX_RETRY": "2",
        "GDAL_HTTP_MULTIRANGE": "SERIAL",
        "GDAL_HTTP_MULTIPLEX": "NO",
        "GDAL_HTTP_USERAGENT": "lunar-mission-planner/0.2",
        "VSI_CACHE": "TRUE",
        "CPL_VSIL_CURL_CHUNK_SIZE": "1048576",
    }
    for name, filename in layers.items():
        record_file = OUT / f"{name}.json"
        if record_file.exists() and (OUT / f"{name}.npy").exists():
            manifest["sources"].append(json.loads(record_file.read_text()))
            continue
        print(f"Cropping NASA {filename}", flush=True)
        try:
            with rasterio.Env(**env), rasterio.open(PGDA + filename) as src:
                window = (
                    from_bounds(-12000, -9000, 12000, 15000, src.transform)
                    .round_offsets()
                    .round_lengths()
                )
                data = src.read(1, window=window)
                if src.nodata is not None and np.any(data == src.nodata):
                    raise ValueError("Nodata in thematic crop")
                record = save_grid(
                    name,
                    data,
                    rasterio.windows.bounds(window, src.transform),
                    abs(src.transform.a),
                    PGDA + filename,
                    sampling="nearest" if name in ("psr", "count") else "bilinear",
                )
                record_file.write_text(json.dumps(record, indent=2))
                manifest["sources"].append(record)
        except (rasterio.errors.RasterioError, OSError, ValueError) as exc:
            manifest.setdefault("unavailable", {})[name] = str(exc)
            print(f"Unavailable: {name}: {exc}", flush=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (PUBLIC / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        json.dumps(
            {"sources": [x["name"] for x in manifest["sources"]], "output": str(OUT)}
        )
    )


if __name__ == "__main__":
    main()
