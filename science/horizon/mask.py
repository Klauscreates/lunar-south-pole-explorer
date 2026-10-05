"""Publish a one-degree terrain visibility mask from actual LOLA raycasts.

The simulation uses a 0.5-degree, two-scale terrain horizon for Sun and Earth
occultation. Every integer azimuth in that profile is already an independently
sampled geodesic ray. Selecting those rays produces the requested 360-bin
mask without interpolating the DEM or repeating the expensive raycast.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict

import numpy as np

from science.errors import TerrainDataError
from science.horizon.engine import HorizonProfile


_RAYCAST_ALGORITHMS = {
    "spherical-geodesic-raycast-v1",
    "highest-obstruction-multiscale-v1",
}
_MASK_ALGORITHM = "direct-one-degree-ray-selection-v1"


def build_one_degree_horizon_mask(profile: HorizonProfile) -> Dict[str, Any]:
    """Return all 360 integer-azimuth obstruction thresholds as JSON data.

    The source must contain real radial ray samples at 1-degree intervals or
    finer, aligned to 0 degrees north. We deliberately reject a coarser or
    irregular skyline rather than manufacture apparent terrain knowledge by
    interpolating it. The resulting threshold is the minimum *center*
    elevation a point source needs to clear terrain at that azimuth; the
    production visibility classifier separately accounts for apparent disk
    size using the full-resolution source profile.
    """
    source_algorithm = profile.metadata.get("algorithm")
    if source_algorithm not in _RAYCAST_ALGORITHMS:
        raise TerrainDataError(
            "A one-degree horizon mask requires a documented terrain raycast"
        )
    source_key = profile.metadata.get("cache_key_sha256")
    if not isinstance(source_key, str) or not source_key:
        raise TerrainDataError("Terrain raycast is missing its provenance key")

    try:
        source_step = float(profile.metadata["azimuth_step_deg"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TerrainDataError("Terrain raycast has no valid azimuth step") from exc
    if not math.isfinite(source_step) or source_step <= 0.0:
        raise TerrainDataError("Terrain raycast azimuth step must be finite and positive")
    rays_per_degree = 1.0 / source_step
    rounded_rays_per_degree = round(rays_per_degree)
    if rounded_rays_per_degree < 1 or not math.isclose(
        rays_per_degree, rounded_rays_per_degree, abs_tol=1e-9, rel_tol=0.0
    ):
        raise TerrainDataError(
            "One-degree mask requires original ray samples at every integer "
            "azimuth; the source step must divide 1 degree"
        )

    azimuth = np.asarray(profile.azimuth_deg, dtype=np.float64)
    elevation = np.asarray(profile.elevation_deg, dtype=np.float64)
    distance = np.asarray(profile.obstruction_distance_m, dtype=np.float64)
    expected_source_count = 360 * rounded_rays_per_degree
    if any(
        array.ndim != 1 or array.size != expected_source_count
        for array in (azimuth, elevation, distance)
    ):
        raise TerrainDataError("Terrain raycast arrays have an incomplete azimuth grid")
    expected_source_azimuth = np.arange(expected_source_count) * source_step
    if not np.allclose(
        azimuth, expected_source_azimuth, rtol=0.0, atol=1e-8
    ):
        raise TerrainDataError(
            "Terrain raycast azimuth grid is not north-aligned or is irregular"
        )
    if not np.isfinite(elevation).all() or not np.isfinite(distance).all():
        raise TerrainDataError("Terrain horizon contains missing or non-finite rays")
    if np.any(distance <= 0.0):
        raise TerrainDataError("Terrain obstruction distances must be positive")

    indices = np.arange(360) * rounded_rays_per_degree
    selected_elevation = elevation[indices]
    selected_distance = distance[indices]
    cache_payload = {
        "algorithm": _MASK_ALGORITHM,
        "source_raycast_cache_key_sha256": source_key,
        "azimuth_step_deg": 1.0,
    }
    mask_key = hashlib.sha256(
        json.dumps(cache_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "metadata": {
            "algorithm": _MASK_ALGORITHM,
            "azimuth_convention": "0 deg north, 90 east, clockwise",
            "azimuth_step_deg": 1.0,
            "azimuth_ray_count": 360,
            "source_raycast_algorithm": source_algorithm,
            "source_raycast_azimuth_step_deg": source_step,
            "source_raycast_ray_count": expected_source_count,
            "source_raycast_cache_key_sha256": source_key,
            "mask_cache_key_sha256": mask_key,
            "selection_method": (
                "Exact original rays at integer azimuths; no azimuth "
                "interpolation or second DEM raycast"
            ),
            "minimum_clearance_definition": (
                "Point-source center elevation above the local tangent plane "
                "required to clear the LOLA terrain skyline"
            ),
            "visibility_classification_uses_full_resolution_profile": True,
            "maximum_search_radius_m": profile.metadata.get(
                "maximum_search_radius_m"
            ),
            "local_component_cache_key_sha256": profile.metadata.get(
                "local_component_cache_key_sha256"
            ),
            "outer_component_cache_key_sha256": profile.metadata.get(
                "outer_component_cache_key_sha256"
            ),
        },
        "profile": [
            {
                "azimuth_deg": azimuth_deg,
                "minimum_clearance_elevation_deg": round(float(angle), 9),
                "obstruction_distance_m": round(float(range_m), 3),
            }
            for azimuth_deg, angle, range_m in zip(
                range(360), selected_elevation, selected_distance
            )
        ],
    }
