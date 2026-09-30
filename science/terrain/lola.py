"""Authoritative NASA PGDA/LOLA cloud-optimized GeoTIFF ingestion."""

from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.errors import RasterioIOError
from rasterio.windows import Window, from_bounds
from scipy.ndimage import map_coordinates

from science.config import SiteConfig, TerrainConfig, utc_iso
from science.errors import TerrainDataError


PGDA_PRODUCT_URL = "https://pgda.gsfc.nasa.gov/products/90"
PGDA_PRODUCT_TITLE = "A New View of the Lunar South Pole from LOLA"
PGDA_DATASET_DOI = "https://doi.org/10.60903/gsfcpgda-lola-spole"
PGDA_PSR_URL = (
    "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LPSR_80S_20MPP_ADJ.TIF"
)
PGDA_CITATION = (
    "Barker et al., A New View of the Lunar South Pole from LOLA, "
    "NASA GSFC Planetary Geology, Geophysics and Geochemistry Laboratory, "
    "doi:10.60903/gsfcpgda-lola-spole"
)


@dataclass(frozen=True)
class PreparedTerrain:
    crop_path: Path
    site_x_m: float
    site_y_m: float
    site_elevation_m: float
    source_resolution_m: float
    crs_wkt: str
    metadata: Dict[str, Any]


def sample_pgda_psr_classification(
    site: SiteConfig,
    lunar_radius_m: float,
    cache_dir: Path,
) -> Dict[str, Any]:
    """Sample NASA PGDA's published 20 m binary permanent-shadow map.

    This is an independent broad-behavior check, not a time-matched comparison
    and not a replacement for the ephemeris/terrain calculation.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key_payload = {
        "source": PGDA_PSR_URL,
        "latitude_deg": site.latitude_deg,
        "longitude_deg_east": site.longitude_deg_east,
        "lunar_radius_m": lunar_radius_m,
        "sampling": "nearest-categorical-v1",
    }
    key_hash = hashlib.sha256(
        json.dumps(key_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cache_path = cache_dir / f"pgda_psr_{key_hash[:20]}.json"
    if cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            payload["cache_hit"] = True
            return payload
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass

    raster_env = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "GDAL_HTTP_MULTIRANGE": "SERIAL",
        "GDAL_HTTP_MULTIPLEX": "NO",
        "GDAL_HTTP_MAX_RETRY": "10",
        "GDAL_HTTP_RETRY_DELAY": "2",
        "GDAL_HTTP_TCP_KEEPALIVE": "YES",
        "GDAL_HTTP_USERAGENT": "lunar-mission-planner/0.1",
        "VSI_CACHE": "TRUE",
        "VSI_CACHE_SIZE": "67108864",
        "CPL_VSIL_CURL_CHUNK_SIZE": "1048576",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".TIF,.tif",
    }
    last_error: Optional[Exception] = None
    for attempt in range(3):
        try:
            with rasterio.Env(**raster_env), rasterio.open(PGDA_PSR_URL) as source:
                if source.crs is None:
                    raise TerrainDataError("PGDA PSR map does not declare a CRS")
                x_m, y_m = _site_projected_xy(site, lunar_radius_m, source.crs)
                value = float(next(source.sample([(x_m, y_m)]))[0])
                if not math.isfinite(value) or value not in (0.0, 1.0):
                    raise TerrainDataError(
                        f"Unexpected PGDA PSR categorical value: {value}"
                    )
                payload = {
                    "dataset": "NASA PGDA LOLA Permanently Shadowed Region map",
                    "product_page": PGDA_PRODUCT_URL,
                    "dataset_doi": PGDA_DATASET_DOI,
                    "source_url": PGDA_PSR_URL,
                    "source_http": _http_metadata(PGDA_PSR_URL),
                    "source_pixel_size_m": abs(float(source.transform.a)),
                    "source_shape_pixels": [source.height, source.width],
                    "source_crs_wkt": source.crs.to_wkt(),
                    "reference_frame": "MOON_ME, JPL DE421",
                    "site_projected_xy_m": [x_m, y_m],
                    "categorical_value": value,
                    "classification": "PSR" if value == 1.0 else "NOT_PSR",
                    "sampling": "nearest pixel for categorical raster",
                    "retrieved_utc": utc_iso(datetime.now(timezone.utc)),
                    "cache_key_sha256": key_hash,
                    "cache_path": str(cache_path.resolve()),
                    "cache_hit": False,
                }
                temporary = cache_path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(payload, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                temporary.replace(cache_path)
                return payload
        except (RasterioIOError, OSError, TerrainDataError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise TerrainDataError(
        f"NASA PGDA PSR validation sample failed after 3 attempts: {last_error}"
    ) from last_error


def prepare_lola_crop(
    site: SiteConfig,
    config: TerrainConfig,
    processed_dir: Path,
) -> PreparedTerrain:
    """Acquire and cache only the source raster window needed for raycasting.

    Remote sources are accessed as COGs through GDAL HTTP range requests. A
    local, lossless Float32 GeoTIFF crop is written atomically and hashed.
    Existing crops are reused only when their metadata key matches exactly.
    """
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    cache_key_payload = {
        "source": config.source,
        "latitude_deg": site.latitude_deg,
        "longitude_deg_east": site.longitude_deg_east,
        "search_radius_m": config.search_radius_m,
        "lunar_radius_m": config.lunar_radius_m,
        "algorithm": "lola-cog-square-crop-v1",
    }
    cache_key = hashlib.sha256(
        json.dumps(cache_key_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    crop_path = processed_dir / f"lola_crop_{cache_key}.tif"
    metadata_path = processed_dir / f"lola_crop_{cache_key}.metadata.json"

    if crop_path.exists() and metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            actual_hash = _sha256_file(crop_path)
            if actual_hash != metadata.get("crop_sha256"):
                raise TerrainDataError(
                    f"Cached LOLA crop checksum mismatch: {crop_path}"
                )
            metadata_changed = False
            for key, value in {
                "dataset": PGDA_PRODUCT_TITLE,
                "product_page": PGDA_PRODUCT_URL,
                "dataset_doi": PGDA_DATASET_DOI,
                "citation": PGDA_CITATION,
            }.items():
                if metadata.get(key) != value:
                    metadata[key] = value
                    metadata_changed = True
            if metadata_changed:
                metadata_path.write_text(
                    json.dumps(metadata, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
            with rasterio.open(crop_path) as dataset:
                site_x, site_y = _site_projected_xy(
                    site, config.lunar_radius_m, dataset.crs
                )
                elevation = sample_raster_bilinear(dataset, site_x, site_y)
                resolution = abs(float(dataset.transform.a))
                return PreparedTerrain(
                    crop_path=crop_path,
                    site_x_m=site_x,
                    site_y_m=site_y,
                    site_elevation_m=elevation,
                    source_resolution_m=resolution,
                    crs_wkt=dataset.crs.to_wkt() if dataset.crs else "",
                    metadata=metadata,
                )
        except (OSError, json.JSONDecodeError, RasterioIOError, TerrainDataError):
            # A corrupt/incomplete cache is never trusted; reacquire atomically.
            pass

    http_metadata = _http_metadata(config.source)
    raster_env = {
        # NASA's static server has intermittently returned empty/403 responses
        # when GDAL fans ranges out concurrently for this >4 GiB COG. Serialized
        # ranges are slower but reproducible for the small crop used here.
        "GDAL_HTTP_MULTIRANGE": "SERIAL",
        "GDAL_HTTP_MULTIPLEX": "NO",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "GDAL_HTTP_RETRY_CODES": "403,429,500,502,503,504",
        "GDAL_HTTP_MAX_RETRY": "10",
        "GDAL_HTTP_RETRY_DELAY": "2",
        "GDAL_HTTP_TCP_KEEPALIVE": "YES",
        "GDAL_HTTP_USERAGENT": "lunar-mission-planner/0.1",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".TIF,.tif",
        "VSI_CACHE": "TRUE",
        "VSI_CACHE_SIZE": "67108864",
        "CPL_VSIL_CURL_CHUNK_SIZE": "1048576",
    }
    last_error: Optional[Exception] = None
    for attempt in range(3):
        try:
            with rasterio.Env(**raster_env):
                with rasterio.open(config.source) as source:
                    if source.crs is None:
                        raise TerrainDataError("LOLA source does not declare a CRS")
                    if source.count != 1:
                        raise TerrainDataError(
                            f"Expected one terrain band, found {source.count}"
                        )
                    site_x, site_y = _site_projected_xy(
                        site, config.lunar_radius_m, source.crs
                    )
                    pixel_size_x = abs(float(source.transform.a))
                    pixel_size_y = abs(float(source.transform.e))
                    margin = 2.0 * max(pixel_size_x, pixel_size_y)
                    requested = from_bounds(
                        site_x - config.search_radius_m - margin,
                        site_y - config.search_radius_m - margin,
                        site_x + config.search_radius_m + margin,
                        site_y + config.search_radius_m + margin,
                        transform=source.transform,
                    ).round_offsets().round_lengths()
                    full = Window(0, 0, source.width, source.height)
                    window = requested.intersection(full)
                    if (
                        window.width < requested.width
                        or window.height < requested.height
                    ):
                        raise TerrainDataError(
                            "Requested horizon radius extends beyond the LOLA raster"
                        )
                    terrain = source.read(1, window=window).astype(
                        np.float32, copy=False
                    )
                    if terrain.size == 0 or not np.isfinite(terrain).any():
                        raise TerrainDataError(
                            "LOLA crop contains no finite elevation samples"
                        )
                    if not np.isfinite(terrain).all():
                        invalid = int((~np.isfinite(terrain)).sum())
                        raise TerrainDataError(
                            f"LOLA crop contains {invalid} missing elevation samples"
                        )
                    transform = source.window_transform(window)
                    source_tags = source.tags()
                    source_shape = [source.height, source.width]
                    source_bounds = list(source.bounds)
                    source_crs_wkt = source.crs.to_wkt()
                    source_dtype = source.dtypes[0]
                break
        except (RasterioIOError, OSError, TerrainDataError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    else:
        raise TerrainDataError(
            "NASA PGDA/LOLA terrain acquisition failed after 3 attempts: "
            f"{last_error}"
        ) from last_error

    profile = {
        "driver": "GTiff",
        "height": int(terrain.shape[0]),
        "width": int(terrain.shape[1]),
        "count": 1,
        "dtype": "float32",
        "crs": source_crs_wkt,
        "transform": transform,
        "compress": "deflate",
        "predictor": 3,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "nodata": math.nan,
    }
    temporary_crop = crop_path.with_suffix(".tmp.tif")
    with rasterio.open(temporary_crop, "w", **profile) as destination:
        destination.write(terrain, 1)
        destination.update_tags(
            source_url=config.source,
            source_product=PGDA_PRODUCT_TITLE,
            source_reference_frame="MOON_ME (JPL DE421)",
            crop_algorithm="lola-cog-square-crop-v1",
        )
    temporary_crop.replace(crop_path)

    with rasterio.open(crop_path) as crop:
        site_elevation = sample_raster_bilinear(crop, site_x, site_y)
        crop_bounds = list(crop.bounds)
        crop_shape = [crop.height, crop.width]

    metadata: Dict[str, Any] = {
        "dataset": PGDA_PRODUCT_TITLE,
        "product_page": PGDA_PRODUCT_URL,
        "dataset_doi": PGDA_DATASET_DOI,
        "source_url": config.source,
        "citation": PGDA_CITATION,
        "source_http": http_metadata,
        "source_shape_pixels": source_shape,
        "source_bounds_m": source_bounds,
        "source_crs_wkt": source_crs_wkt,
        "source_dtype": source_dtype,
        "source_pixel_size_m": [pixel_size_x, pixel_size_y],
        "vertical_units": "meters above 1737.4 km lunar reference sphere",
        "reference_frame": "MOON_ME, JPL DE421",
        "projection": "South polar stereographic; ocentric spherical Moon",
        "pixel_registration": "pixel area; source described by PGDA as GMT pixel-registered centers",
        "crop_path": str(crop_path.resolve()),
        "crop_sha256": _sha256_file(crop_path),
        "crop_shape_pixels": crop_shape,
        "crop_bounds_m": crop_bounds,
        "crop_key_sha256_prefix": cache_key,
        "crop_created_utc": utc_iso(datetime.now(timezone.utc)),
        "site_projected_xy_m": [site_x, site_y],
        "site_elevation_m_bilinear": site_elevation,
    }
    temporary_metadata = metadata_path.with_suffix(".tmp")
    temporary_metadata.write_text(
        json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary_metadata.replace(metadata_path)
    return PreparedTerrain(
        crop_path=crop_path,
        site_x_m=site_x,
        site_y_m=site_y,
        site_elevation_m=site_elevation,
        source_resolution_m=pixel_size_x,
        crs_wkt=source_crs_wkt,
        metadata=metadata,
    )


def sample_raster_bilinear(
    dataset: rasterio.io.DatasetReader, x_m: float, y_m: float
) -> float:
    """Sample a pixel-centered raster using bilinear interpolation."""
    inverse = ~dataset.transform
    col_corner, row_corner = inverse * (x_m, y_m)
    # Affine inverse coordinates describe pixel corners; scipy array indices
    # describe pixel centers at integer indices.
    row = row_corner - 0.5
    col = col_corner - 0.5
    row0 = max(0, int(math.floor(row)) - 1)
    col0 = max(0, int(math.floor(col)) - 1)
    row1 = min(dataset.height, int(math.ceil(row)) + 2)
    col1 = min(dataset.width, int(math.ceil(col)) + 2)
    if row1 - row0 < 2 or col1 - col0 < 2:
        raise TerrainDataError("Terrain sample lies too close to raster boundary")
    window = Window(col0, row0, col1 - col0, row1 - row0)
    values = dataset.read(1, window=window)
    sampled = map_coordinates(
        values,
        [[row - row0], [col - col0]],
        order=1,
        mode="constant",
        cval=np.nan,
        prefilter=False,
    )[0]
    if not np.isfinite(sampled):
        raise TerrainDataError("Terrain elevation sample is missing or invalid")
    return float(sampled)


def _site_projected_xy(
    site: SiteConfig, lunar_radius_m: float, destination_crs: CRS
) -> Tuple[float, float]:
    lunar_geographic = CRS.from_proj4(
        f"+proj=longlat +R={lunar_radius_m:.6f} +no_defs"
    )
    transformer = Transformer.from_crs(
        lunar_geographic, destination_crs, always_xy=True
    )
    x, y = transformer.transform(site.longitude_deg_east, site.latitude_deg)
    if not math.isfinite(x) or not math.isfinite(y):
        raise TerrainDataError("Site coordinate could not be projected into DEM CRS")
    return float(x), float(y)


def _http_metadata(source: str) -> Dict[str, Any]:
    if not source.lower().startswith(("http://", "https://")):
        return {"transport": "local-file"}
    requests = [
        urllib.request.Request(
            source,
            method="HEAD",
            headers={
                "User-Agent": "LunarMissionPlanner/0.1 scientific-prototype"
            },
        ),
        # Some NASA static-file routes reject HEAD but permit byte ranges.
        urllib.request.Request(
            source,
            method="GET",
            headers={
                "User-Agent": "LunarMissionPlanner/0.1 scientific-prototype",
                "Range": "bytes=0-0",
            },
        ),
    ]
    last_error: Optional[Exception] = None
    for request in requests:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content_range = response.headers.get("Content-Range")
                total_length = None
                if content_range and "/" in content_range:
                    total_length = _optional_int(content_range.rsplit("/", 1)[1])
                if total_length is None:
                    total_length = _optional_int(
                        response.headers.get("Content-Length")
                    )
                return {
                    "transport": "HTTPS range-readable COG",
                    "content_length_bytes": total_length,
                    "last_modified": response.headers.get("Last-Modified"),
                    "etag": response.headers.get("ETag"),
                    "accept_ranges": response.headers.get("Accept-Ranges"),
                    "content_type": response.headers.get("Content-Type"),
                    "verification_method": request.get_method(),
                }
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
    raise TerrainDataError(
        f"Could not verify authoritative terrain source: {last_error}"
    ) from last_error


def _optional_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
