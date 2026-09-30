"""Spherical-lunar terrain raycasting with cached, interpolable skylines."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import rasterio
from pyproj import CRS, Geod, Transformer
from scipy.ndimage import map_coordinates

from science.config import SiteConfig, TerrainConfig, utc_iso
from science.errors import TerrainDataError
from science.terrain.lola import PreparedTerrain


@dataclass(frozen=True)
class HorizonProfile:
    azimuth_deg: np.ndarray
    elevation_deg: np.ndarray
    obstruction_distance_m: np.ndarray
    metadata: Dict[str, Any]

    def elevation_at(self, azimuth_deg: float) -> float:
        """Periodic linear interpolation of skyline elevation by azimuth."""
        normalized = float(azimuth_deg) % 360.0
        extended_azimuth = np.append(self.azimuth_deg, 360.0)
        extended_elevation = np.append(self.elevation_deg, self.elevation_deg[0])
        return float(np.interp(normalized, extended_azimuth, extended_elevation))

    def as_records(self) -> List[Dict[str, float]]:
        return [
            {
                "azimuth_deg": round(float(azimuth), 6),
                "elevation_deg": round(float(elevation), 9),
                "obstruction_distance_m": round(float(distance), 3),
            }
            for azimuth, elevation, distance in zip(
                self.azimuth_deg,
                self.elevation_deg,
                self.obstruction_distance_m,
            )
        ]


def compute_horizon_profile(
    site: SiteConfig,
    config: TerrainConfig,
    terrain: PreparedTerrain,
    cache_dir: Path,
    observer_terrain_elevation_m: float = None,  # type: ignore[assignment]
) -> HorizonProfile:
    """Compute the maximum topocentric terrain elevation at every azimuth.

    Geographic destinations are generated along spherical geodesics in the
    local clockwise-from-north azimuth convention. Candidate elevations use
    exact spherical chord geometry, not a flat-Earth approximation:

        elevation = atan2(r_t cos(sigma) - r_o, r_t sin(sigma))

    where sigma is central angle, r_t target radius, and r_o observer radius.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if observer_terrain_elevation_m is None:
        observer_terrain_elevation_m = terrain.site_elevation_m
    key_payload = {
        "terrain_crop_sha256": terrain.metadata["crop_sha256"],
        "latitude_deg": site.latitude_deg,
        "longitude_deg_east": site.longitude_deg_east,
        "observer_height_m": site.observer_height_m,
        "site_elevation_m": observer_terrain_elevation_m,
        "search_radius_m": config.search_radius_m,
        "azimuth_step_deg": config.azimuth_step_deg,
        "radial_step_m": config.radial_step_m,
        "lunar_radius_m": config.lunar_radius_m,
        "algorithm": "spherical-geodesic-raycast-v1",
    }
    cache_key = hashlib.sha256(
        json.dumps(key_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cache_path = cache_dir / f"horizon_{cache_key[:20]}.json"
    if cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return HorizonProfile(
                azimuth_deg=np.asarray(payload["azimuth_deg"], dtype=np.float64),
                elevation_deg=np.asarray(payload["elevation_deg"], dtype=np.float64),
                obstruction_distance_m=np.asarray(
                    payload["obstruction_distance_m"], dtype=np.float64
                ),
                metadata={**payload["metadata"], "cache_hit": True},
            )
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass

    azimuths = np.arange(
        0.0, 360.0, config.azimuth_step_deg, dtype=np.float64
    )
    # Do not claim terrain information inside one source pixel. Starting at
    # the configured radial step keeps the angular calculation commensurate
    # with the DEM's sampling scale.
    distances = np.arange(
        config.radial_step_m,
        config.search_radius_m + 0.5 * config.radial_step_m,
        config.radial_step_m,
        dtype=np.float64,
    )
    if distances.size == 0:
        raise TerrainDataError("Horizon raycast produced no radial samples")

    azimuth_grid, distance_grid = np.meshgrid(
        azimuths, distances, indexing="ij"
    )
    geod = Geod(a=config.lunar_radius_m, b=config.lunar_radius_m)
    longitude_grid, latitude_grid, _ = geod.fwd(
        np.full(azimuth_grid.shape, site.longitude_deg_east),
        np.full(azimuth_grid.shape, site.latitude_deg),
        azimuth_grid,
        distance_grid,
    )

    lunar_geographic = CRS.from_proj4(
        f"+proj=longlat +R={config.lunar_radius_m:.6f} +no_defs"
    )
    with rasterio.open(terrain.crop_path) as dataset:
        transformer = Transformer.from_crs(
            lunar_geographic, dataset.crs, always_xy=True
        )
        projected_x, projected_y = transformer.transform(
            longitude_grid, latitude_grid
        )
        inverse = ~dataset.transform
        col_corner, row_corner = inverse * (projected_x, projected_y)
        rows = np.asarray(row_corner) - 0.5
        cols = np.asarray(col_corner) - 0.5
        raster = dataset.read(1)

    terrain_elevations = map_coordinates(
        raster,
        [rows, cols],
        order=1,
        mode="constant",
        cval=np.nan,
        prefilter=False,
    )
    if not np.isfinite(terrain_elevations).all():
        invalid = int((~np.isfinite(terrain_elevations)).sum())
        raise TerrainDataError(
            f"{invalid} horizon rays left the valid terrain crop; "
            "increase crop margin or reduce search radius"
        )

    central_angle_rad = distance_grid / config.lunar_radius_m
    observer_radius_m = (
        config.lunar_radius_m
        + observer_terrain_elevation_m
        + site.observer_height_m
    )
    target_radius_m = config.lunar_radius_m + terrain_elevations
    vertical_m = (
        target_radius_m * np.cos(central_angle_rad) - observer_radius_m
    )
    horizontal_m = target_radius_m * np.sin(central_angle_rad)
    apparent_elevation_deg = np.degrees(
        np.arctan2(vertical_m, horizontal_m)
    )
    max_indices = np.argmax(apparent_elevation_deg, axis=1)
    skyline = apparent_elevation_deg[
        np.arange(apparent_elevation_deg.shape[0]), max_indices
    ]
    obstruction_distance = distances[max_indices]

    metadata: Dict[str, Any] = {
        "algorithm": "spherical-geodesic-raycast-v1",
        "azimuth_convention": "0 deg north, 90 east, clockwise",
        "azimuth_step_deg": config.azimuth_step_deg,
        "interpolation": (
            "bilinear DEM sampling along spherical geodesics; periodic linear "
            "interpolation between horizon azimuth rays"
        ),
        "radial_step_m": config.radial_step_m,
        "maximum_search_radius_m": config.search_radius_m,
        "radial_sample_count_per_ray": int(distances.size),
        "azimuth_ray_count": int(azimuths.size),
        "lunar_reference_radius_m": config.lunar_radius_m,
        "observer_radius_m": observer_radius_m,
        "observer_height_above_terrain_m": site.observer_height_m,
        "site_terrain_elevation_m": observer_terrain_elevation_m,
        "raster_site_elevation_m": terrain.site_elevation_m,
        "curvature_model": "spherical chord geometry",
        "dem_crop_sha256": terrain.metadata["crop_sha256"],
        "created_utc": utc_iso(datetime.now(timezone.utc)),
        "cache_path": str(cache_path.resolve()),
        "cache_key_sha256": cache_key,
        "cache_hit": False,
        "horizon_min_deg": float(np.min(skyline)),
        "horizon_max_deg": float(np.max(skyline)),
    }
    payload = {
        "azimuth_deg": azimuths.tolist(),
        "elevation_deg": skyline.tolist(),
        "obstruction_distance_m": obstruction_distance.tolist(),
        "metadata": metadata,
    }
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary.replace(cache_path)
    return HorizonProfile(
        azimuth_deg=azimuths,
        elevation_deg=skyline,
        obstruction_distance_m=obstruction_distance,
        metadata=metadata,
    )


def combine_horizon_profiles(
    local: HorizonProfile,
    outer: HorizonProfile,
    cache_dir: Path,
) -> HorizonProfile:
    """Select the highest obstruction across aligned multi-scale profiles."""
    if local.azimuth_deg.shape != outer.azimuth_deg.shape or not np.allclose(
        local.azimuth_deg, outer.azimuth_deg, atol=1e-12, rtol=0.0
    ):
        raise TerrainDataError("Multi-scale horizon azimuth grids do not align")
    select_local = local.elevation_deg >= outer.elevation_deg
    elevation = np.where(select_local, local.elevation_deg, outer.elevation_deg)
    distance = np.where(
        select_local,
        local.obstruction_distance_m,
        outer.obstruction_distance_m,
    )
    key_payload = {
        "local": local.metadata["cache_key_sha256"],
        "outer": outer.metadata["cache_key_sha256"],
        "algorithm": "highest-obstruction-multiscale-v1",
    }
    cache_key = hashlib.sha256(
        json.dumps(key_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cache_path = Path(cache_dir) / f"horizon_combined_{cache_key[:20]}.json"
    metadata: Dict[str, Any] = {
        "algorithm": "highest-obstruction-multiscale-v1",
        "azimuth_convention": local.metadata["azimuth_convention"],
        "azimuth_step_deg": local.metadata["azimuth_step_deg"],
        "interpolation": (
            "maximum apparent elevation across the 10 m local and 240 m "
            "outer spherical-geodesic raycasts; periodic linear interpolation"
        ),
        "maximum_search_radius_m": outer.metadata["maximum_search_radius_m"],
        "local_search_radius_m": local.metadata["maximum_search_radius_m"],
        "local_radial_step_m": local.metadata["radial_step_m"],
        "outer_radial_step_m": outer.metadata["radial_step_m"],
        "lunar_reference_radius_m": local.metadata["lunar_reference_radius_m"],
        "observer_radius_m": local.metadata["observer_radius_m"],
        "observer_height_above_terrain_m": local.metadata[
            "observer_height_above_terrain_m"
        ],
        "site_terrain_elevation_m": local.metadata[
            "site_terrain_elevation_m"
        ],
        "curvature_model": "spherical chord geometry in both scales",
        "local_component_cache_key_sha256": local.metadata[
            "cache_key_sha256"
        ],
        "outer_component_cache_key_sha256": outer.metadata[
            "cache_key_sha256"
        ],
        "local_dominant_azimuth_count": int(select_local.sum()),
        "outer_dominant_azimuth_count": int((~select_local).sum()),
        "created_utc": utc_iso(datetime.now(timezone.utc)),
        "cache_path": str(cache_path.resolve()),
        "cache_key_sha256": cache_key,
        "cache_hit": local.metadata.get("cache_hit", False)
        and outer.metadata.get("cache_hit", False),
        "horizon_min_deg": float(np.min(elevation)),
        "horizon_max_deg": float(np.max(elevation)),
    }
    payload = {
        "azimuth_deg": local.azimuth_deg.tolist(),
        "elevation_deg": elevation.tolist(),
        "obstruction_distance_m": distance.tolist(),
        "metadata": metadata,
    }
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary.replace(cache_path)
    return HorizonProfile(
        azimuth_deg=local.azimuth_deg,
        elevation_deg=elevation,
        obstruction_distance_m=distance,
        metadata=metadata,
    )
