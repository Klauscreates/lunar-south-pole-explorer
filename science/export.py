"""Deterministic JSON and flat CSV simulation exports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable


CSV_FIELDS = [
    "timestamp_utc",
    "sun_azimuth_deg",
    "sun_elevation_deg",
    "sun_angular_radius_deg",
    "sun_distance_km",
    "sun_terrain_horizon_deg",
    "sun_clearance_deg",
    "sun_visibility_fraction",
    "sun_state",
    "earth_azimuth_deg",
    "earth_elevation_deg",
    "earth_angular_radius_deg",
    "earth_distance_km",
    "earth_terrain_horizon_deg",
    "earth_clearance_deg",
    "earth_visibility_fraction",
    "earth_state",
    "combined_state",
    "direct_irradiance_w_m2",
    "incidence_cosine",
    "estimated_incident_power_w",
    "estimated_electrical_output_w",
]


def write_json(result: Dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, indent=2, sort_keys=False, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def write_csv(result: Dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for sample in result["samples"]:
            writer.writerow(_flatten_sample(sample))
    temporary.replace(path)


def _flatten_sample(sample: Dict[str, Any]) -> Dict[str, Any]:
    sun = sample["sun"]
    earth = sample["earth"]
    power = sample["power"]
    return {
        "timestamp_utc": sample["timestamp"],
        "sun_azimuth_deg": sun["azimuth_deg"],
        "sun_elevation_deg": sun["elevation_deg"],
        "sun_angular_radius_deg": sun["angular_radius_deg"],
        "sun_distance_km": sun["distance_km"],
        "sun_terrain_horizon_deg": sun["terrain_horizon_deg"],
        "sun_clearance_deg": sun["clearance_deg"],
        "sun_visibility_fraction": sun["visibility_fraction"],
        "sun_state": sun["state"],
        "earth_azimuth_deg": earth["azimuth_deg"],
        "earth_elevation_deg": earth["elevation_deg"],
        "earth_angular_radius_deg": earth["angular_radius_deg"],
        "earth_distance_km": earth["distance_km"],
        "earth_terrain_horizon_deg": earth["terrain_horizon_deg"],
        "earth_clearance_deg": earth["clearance_deg"],
        "earth_visibility_fraction": earth["visibility_fraction"],
        "earth_state": earth["state"],
        "combined_state": sample["combined_state"],
        "direct_irradiance_w_m2": power["direct_irradiance_w_m2"],
        "incidence_cosine": power["incidence_cosine"],
        "estimated_incident_power_w": power["estimated_incident_power_w"],
        "estimated_electrical_output_w": power[
            "estimated_electrical_output_w"
        ],
    }

