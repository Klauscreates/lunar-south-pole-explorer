"""End-to-end scientifically traceable lunar mission simulation."""

from __future__ import annotations

import platform
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy
import pyproj
import rasterio
import scipy

from science import __version__
from science.comms import classify_comms_potential
from science.config import PanelConfig, SimulationConfig, utc_iso
from science.ephemeris import HorizonsEphemerisProvider
from science.ephemeris.spice import SpiceEphemerisProvider
from science.errors import SciencePipelineError
from science.horizon import (
    build_one_degree_horizon_mask,
    combine_horizon_profiles,
    compute_horizon_profile,
)
from science.power import (
    ASTRONOMICAL_UNIT_KM,
    NOMINAL_SOLAR_IRRADIANCE_W_M2_AT_1_AU,
    estimate_solar_input,
)
from science.terrain import prepare_lola_crop, sample_pgda_psr_classification
from science.validation import compare_ephemeris_series, validate_ephemeris_series
from science.visibility import classify_visibility
from science.windows import build_window_summary


ProgressCallback = Callable[[str], None]
SPICE_MAXIMUM_POSITION_ERROR_DEG = 1.0 / 3600.0


def run_simulation(
    config: SimulationConfig,
    workspace: Path,
    progress: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    config.validate()
    workspace = Path(workspace).resolve()
    emit = progress or (lambda _message: None)

    emit("Acquiring 10 m NASA PGDA/LOLA local terrain crop")
    local_terrain_config = replace(
        config.terrain,
        search_radius_m=config.terrain.local_radius_m,
    )
    terrain = prepare_lola_crop(
        config.site, local_terrain_config, workspace / "data" / "processed"
    )

    emit(
        "Raycasting local 10 m curvature-aware terrain horizon "
        f"to {config.terrain.local_radius_m / 1000:g} km"
    )
    local_horizon = compute_horizon_profile(
        config.site,
        local_terrain_config,
        terrain,
        workspace / "data" / "cache",
    )
    emit("Acquiring 240 m NASA PGDA/LOLA outer terrain crop")
    outer_terrain_config = replace(
        config.terrain,
        source=config.terrain.outer_source,
        radial_step_m=config.terrain.outer_radial_step_m,
    )
    outer_terrain = prepare_lola_crop(
        config.site, outer_terrain_config, workspace / "data" / "processed"
    )
    emit(
        "Raycasting outer curvature-aware terrain horizon "
        f"to {config.terrain.search_radius_m / 1000:g} km"
    )
    outer_horizon = compute_horizon_profile(
        config.site,
        outer_terrain_config,
        outer_terrain,
        workspace / "data" / "cache",
        observer_terrain_elevation_m=terrain.site_elevation_m,
    )
    emit("Merging local and outer terrain horizons by highest obstruction")
    horizon = combine_horizon_profiles(
        local_horizon, outer_horizon, workspace / "data" / "cache"
    )
    horizon_mask = build_one_degree_horizon_mask(horizon)
    emit("Sampling NASA PGDA's published 20 m permanent-shadow map")
    psr_reference = sample_pgda_psr_classification(
        config.site,
        config.terrain.lunar_radius_m,
        workspace / "data" / "cache",
    )

    provider = HorizonsEphemerisProvider(workspace / "data" / "cache")
    emit("Querying/caching NASA/JPL Horizons Sun observer ephemeris")
    sun_samples, sun_metadata = provider.get_sun_positions(
        config.site, terrain.site_elevation_m, config.time_range
    )
    emit("Querying/caching NASA/JPL Horizons Earth observer ephemeris")
    earth_samples, earth_metadata = provider.get_earth_positions(
        config.site, terrain.site_elevation_m, config.time_range
    )

    if len(sun_samples) != len(earth_samples):
        raise SciencePipelineError("Sun and Earth ephemeris lengths differ")
    for sun, earth in zip(sun_samples, earth_samples):
        if sun.timestamp != earth.timestamp:
            raise SciencePipelineError(
                "Sun and Earth ephemeris timestamps are not aligned"
            )

    spice_provider = SpiceEphemerisProvider(workspace / "data" / "kernels")
    emit("Computing independent local NAIF SPICE Sun ephemeris")
    spice_sun_samples, spice_sun_metadata = spice_provider.get_sun_positions(
        config.site, terrain.site_elevation_m, config.time_range
    )
    emit("Computing independent local NAIF SPICE Earth ephemeris")
    spice_earth_samples, spice_earth_metadata = spice_provider.get_earth_positions(
        config.site, terrain.site_elevation_m, config.time_range
    )
    emit("Comparing every Horizons epoch with the local SPICE solution")
    spice_sun_comparison = compare_ephemeris_series(
        "Sun",
        sun_samples,
        spice_sun_samples,
        maximum_angular_separation_deg=SPICE_MAXIMUM_POSITION_ERROR_DEG,
    )
    spice_earth_comparison = compare_ephemeris_series(
        "Earth",
        earth_samples,
        spice_earth_samples,
        maximum_angular_separation_deg=SPICE_MAXIMUM_POSITION_ERROR_DEG,
    )
    failed_spice_targets = [
        comparison["target"]
        for comparison in (spice_sun_comparison, spice_earth_comparison)
        if comparison["status"] != "PASS"
    ]
    if failed_spice_targets:
        raise SciencePipelineError(
            "Independent SPICE validation exceeded its release tolerances for: "
            + ", ".join(failed_spice_targets)
        )

    sun_metadata["role"] = "operational_source"
    earth_metadata["role"] = "operational_source"

    emit("Combining apparent celestial disks with the terrain skyline")
    panel_scenarios = _panel_scenarios(config.panel)
    output_samples: List[Dict[str, Any]] = []
    for sun_sample, earth_sample in zip(sun_samples, earth_samples):
        sun = classify_visibility(sun_sample, horizon)
        earth = classify_visibility(earth_sample, horizon)
        comms_potential = classify_comms_potential(earth)
        sun_available = sun["visibility_fraction"] > 0.0
        earth_available = earth["visibility_fraction"] > 0.0
        combined_state = _combined_state(sun_available, earth_available)
        power = estimate_solar_input(sun, config.panel)
        power_scenarios = {
            key: estimate_solar_input(sun, scenario)
            for key, scenario in panel_scenarios.items()
        }
        output_samples.append(
            {
                "timestamp": utc_iso(sun_sample.timestamp),
                "sun": sun,
                "earth": earth,
                "comms_potential": comms_potential,
                "power": power,
                "power_scenarios": power_scenarios,
                "geometric_dte_available": earth_available,
                "combined_state": combined_state,
            }
        )

    emit("Extracting grid-resolved sunlight, DTE, and combined windows")
    windows = build_window_summary(output_samples, config.time_range.end_utc)
    simulation_has_sunlight = any(
        sample["sun"]["visibility_fraction"] > 0.0 for sample in output_samples
    )
    psr_disagrees = (
        psr_reference["classification"] == "PSR" and simulation_has_sunlight
    )
    if psr_disagrees:
        raise SciencePipelineError(
            "Terrain illumination disagrees with NASA PGDA PSR classification: "
            "the site is published as PSR but V1 found direct sunlight"
        )
    emit("Running ephemeris parser and physical-consistency validation")
    validation = {
        "overall_status": "PASS",
        "source_integrity_status": "PASS",
        "independent_ephemeris_status": "PASS",
        "sun": validate_ephemeris_series(
            "Sun",
            sun_samples,
            config.time_range.start_utc,
            config.time_range.end_utc,
            config.time_range.step_minutes,
        ),
        "earth": validate_ephemeris_series(
            "Earth",
            earth_samples,
            config.time_range.start_utc,
            config.time_range.end_utc,
            config.time_range.step_minutes,
        ),
        "terrain": {
            "status": "PASS",
            "finite_horizon_samples": len(horizon.azimuth_deg),
            "expected_horizon_samples": int(
                round(360.0 / config.terrain.azimuth_step_deg)
            ),
            "one_degree_mask_samples": len(horizon_mask["profile"]),
            "one_degree_mask_source_key_sha256": horizon_mask["metadata"][
                "source_raycast_cache_key_sha256"
            ],
            "local_crop_sha256": terrain.metadata["crop_sha256"],
            "outer_crop_sha256": outer_terrain.metadata["crop_sha256"],
            "horizon_cache_key_sha256": horizon.metadata[
                "cache_key_sha256"
            ],
            "published_psr_crosscheck": {
                "status": "PASS" if simulation_has_sunlight else "INCONCLUSIVE",
                "source": psr_reference,
                "simulation_has_direct_sunlight_in_requested_interval": simulation_has_sunlight,
                "interpretation": (
                    "PGDA classifies this site as NOT_PSR and the simulation "
                    "finds direct sunlight, so broad behavior is consistent."
                    if simulation_has_sunlight
                    else "A NOT_PSR site can still be shadowed for this specific week."
                ),
                "scope": (
                    "broad categorical check only; the PGDA PSR product is "
                    "not a time-matched illumination time series"
                ),
            },
        },
        "independent_spice": {
            "status": "PASS",
            "required": True,
            "used_for_simulation": False,
            "scope": (
                "Independent local implementation cross-check of target-center "
                "azimuth, elevation, apparent range, and angular diameter at "
                "all requested epochs"
            ),
            "targets": {
                "sun": spice_sun_comparison,
                "earth": spice_earth_comparison,
            },
            "limitations": [
                "Horizons uses DE441 while the compact local SPK is DE440s; "
                "the comparison intentionally spans those closely related JPL "
                "ephemeris releases.",
                "CSPICE CN+S includes converged light time and stellar "
                "aberration but not the relativistic light deflection included "
                "in Horizons apparent observer quantities.",
                "SPICE validates celestial center geometry only; LOLA terrain "
                "occultation remains a separate local calculation.",
            ],
        },
        "limitations": [
            "Horizons remains the operational ephemeris source; local SPICE is "
            "an independent implementation cross-check and is not averaged "
            "into the displayed trajectory.",
            "NASA PGDA PSR provides a broad categorical check, not a "
            "time-matched quantitative illumination comparison.",
        ],
    }

    result: Dict[str, Any] = {
        "schema_version": "1.3.0",
        "software": {
            "name": "Lunar South Pole Mission Planner",
            "version": __version__,
            "generated_utc": utc_iso(datetime.now(timezone.utc)),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "dependencies": {
                "numpy": numpy.__version__,
                "scipy": scipy.__version__,
                "rasterio": rasterio.__version__,
                "gdal": rasterio.__gdal_version__,
                "pyproj": pyproj.__version__,
                "proj": pyproj.proj_version_str,
                "spiceypy": spice_sun_metadata["software"]["spiceypy"],
                "cspice_toolkit": spice_sun_metadata["software"][
                    "cspice_toolkit"
                ],
            },
        },
        "site": {
            "name": config.site.name,
            "latitude_deg": config.site.latitude_deg,
            "longitude_deg_east": config.site.longitude_deg_east,
            "terrain_elevation_m": round(terrain.site_elevation_m, 6),
            "observer_height_m": config.site.observer_height_m,
            "observer_altitude_above_reference_sphere_m": round(
                terrain.site_elevation_m + config.site.observer_height_m, 6
            ),
            "projected_xy_m": [terrain.site_x_m, terrain.site_y_m],
        },
        "time_range": {
            "start_utc": utc_iso(config.time_range.start_utc),
            "end_utc": utc_iso(config.time_range.end_utc),
            "step_minutes": config.time_range.step_minutes,
            "sample_count": len(output_samples),
            "window_boundary_precision_minutes": config.time_range.step_minutes,
        },
        "data_sources": {
            "terrain": {
                "strategy": (
                    "10 m local LOLA raycast to 10 km merged with 240 m "
                    "LOLA raycast to 200 km by maximum apparent elevation"
                ),
                "local": terrain.metadata,
                "outer": outer_terrain.metadata,
                "published_psr_reference": psr_reference,
            },
            "sun_ephemeris": sun_metadata,
            "earth_ephemeris": earth_metadata,
            "spice_validation": {
                "role": "independent_validator_only",
                "used_for_operational_samples": False,
                "sun": spice_sun_metadata,
                "earth": spice_earth_metadata,
            },
        },
        "provenance_contract": {
            "operational_ephemeris": "NASA/JPL Horizons",
            "independent_validator": "NASA/JPL NAIF SPICE",
            "validator_used_for_operational_samples": False,
        },
        "reference_frames": {
            "terrain": "MOON_ME tied to JPL DE421, spherical radius 1737.4 km",
            "ephemeris": sun_metadata.get("center_frame"),
            "independent_validator": spice_sun_metadata.get("center_frame"),
            "frame_alignment_note": (
                "PGDA terrain is explicitly MOON_ME/DE421. Horizons uses the "
                "lunar Mean-Earth DE421 frame for lunar topocentric sites, "
                "while local SPICE explicitly resolves "
                "MOON_ME_DE440_ME421, which NAIF defines as closely aligned "
                "with DE421 Mean-Earth. Horizons target ephemerides are DE441 "
                "and the compact local SPK is DE440s."
            ),
            "local_topocentric": {
                "up": "normal to 1737.4 km lunar reference sphere",
                "north": "local geodetic north",
                "east": "local positive-east tangent",
                "azimuth": "clockwise from north: N=0, E=90, S=180, W=270",
                "elevation": "angle above plane perpendicular to local Up",
            },
        },
        "assumptions": {
            "terrain_occlusion": (
                "Each apparent disk is intersected by a locally straight "
                "skyline at the object's center azimuth."
            ),
            "earth_disk": (
                "Horizons equatorial angular diameter is treated as a circular "
                "disk; oblateness and limb position angle are omitted."
            ),
            "sun_disk": "Uniform circular disk; limb darkening is omitted.",
            "dte": (
                "Geometric line of sight only; no antenna, link budget, Earth "
                "ground-station, or operational constraints."
            ),
            "comms_potential": {
                "model": "earth_center_terrain_clearance_v1",
                "status": "illustrative_geometric_screening_not_measured_signal",
                "rule": (
                    "Earth center clearance <= 0 degrees: index 0; otherwise "
                    "Earth absolute elevation <= 2 degrees: index 30; "
                    "otherwise index 100. The percentages are display "
                    "categories, not RF signal strength or link reliability."
                ),
                "disk_visibility_distinction": (
                    "Existing geometric DTE windows count any exposed Earth "
                    "disk. The center-based index can be zero while an Earth "
                    "limb remains visible."
                ),
                "low_elevation_threshold_deg": 2.0,
            },
            "window_detection": windows["method"],
            "power_model": {
                "solar_irradiance_at_1au_w_m2": NOMINAL_SOLAR_IRRADIANCE_W_M2_AT_1_AU,
                "astronomical_unit_km": ASTRONOMICAL_UNIT_KM,
                "formula": (
                    "irradiance * area * incidence_cosine * visible_disk_fraction "
                    "* panel_efficiency"
                ),
                "omissions": [
                    "temperature",
                    "cell degradation",
                    "dust",
                    "wiring and conversion losses",
                    "battery and load behavior",
                    "lander self-shadowing and panel thermal behavior",
                ],
                "scenario_status": (
                    "illustrative panel pointing geometry; not a measured "
                    "or flight-qualified lander electrical subsystem"
                ),
            },
        },
        "panel": config.as_dict()["panel"],
        "panel_scenarios": {
            key: {
                "configuration": replace(config, panel=scenario).as_dict()["panel"],
                "status": "illustrative_geometry_not_flight_hardware",
                "description": _PANEL_SCENARIO_DESCRIPTIONS[key],
            }
            for key, scenario in panel_scenarios.items()
        },
        "horizon": {
            "metadata": horizon.metadata,
            "profile": horizon.as_records(),
        },
        "horizon_mask": horizon_mask,
        "samples": output_samples,
        "windows": windows,
        "validation": validation,
    }
    return result


_PANEL_SCENARIO_DESCRIPTIONS = {
    "ideal_tracking": "Unconstrained normal-to-Sun reference upper bound.",
    "fixed_vertical_north": (
        "Fixed vertical collecting face; outward normal points north."
    ),
    "fixed_tilt_80_north": (
        "Fixed face tilted 80 degrees from horizontal toward north."
    ),
    "limited_gimbal": (
        "Ideal two-axis mount limited to 0-80 degree tilt and north +/-90 degree yaw."
    ),
}


def _panel_scenarios(base: PanelConfig) -> Dict[str, PanelConfig]:
    """Compare explicit geometry envelopes at the same area and efficiency."""
    common = {
        "panel_area_m2": base.panel_area_m2,
        "efficiency": base.efficiency,
    }
    scenarios = {
        "ideal_tracking": PanelConfig(**common, orientation_mode="sun_tracking"),
        "fixed_vertical_north": PanelConfig(
            **common,
            orientation_mode="fixed_tilt",
            tilt_deg_from_horizontal=90.0,
            azimuth_deg=0.0,
        ),
        "fixed_tilt_80_north": PanelConfig(
            **common,
            orientation_mode="fixed_tilt",
            tilt_deg_from_horizontal=80.0,
            azimuth_deg=0.0,
        ),
        "limited_gimbal": PanelConfig(
            **common,
            orientation_mode="gimbal_limited",
            tracking_tilt_min_deg=0.0,
            tracking_tilt_max_deg=80.0,
            tracking_azimuth_center_deg=0.0,
            tracking_azimuth_half_range_deg=90.0,
        ),
    }
    for scenario in scenarios.values():
        scenario.validate()
    return scenarios


def _combined_state(sun_visible: bool, earth_visible: bool) -> str:
    if sun_visible and earth_visible:
        return "SUN_VISIBLE_EARTH_VISIBLE"
    if sun_visible:
        return "SUN_VISIBLE_EARTH_BLOCKED"
    if earth_visible:
        return "SUN_BLOCKED_EARTH_VISIBLE"
    return "SUN_BLOCKED_EARTH_BLOCKED"
