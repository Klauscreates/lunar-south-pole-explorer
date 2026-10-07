"""Deterministic JSON and flat CSV simulation exports."""

from __future__ import annotations

import csv
import json
import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, TextIO


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


@contextmanager
def _atomic_text_output(
    path: Path, *, newline: str | None = None, overwrite: bool = True
) -> Iterator[TextIO]:
    """Write beside the destination, then atomically replace it on success.

    A random, exclusively created temporary name cannot reuse a caller's
    ``output.json.tmp`` input. New files obey the process umask; replacement
    files retain the destination's mode. Without overwrite, a same-directory
    hard link publishes the completed file only if no destination exists.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        for _ in range(10):
            candidate = path.parent / f".{path.name[:32]}.{secrets.token_hex(16)}.tmp"
            try:
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            except FileExistsError:
                continue
            temporary = candidate
            break
        else:
            raise OSError("Cannot allocate a unique export temporary file")
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
            if overwrite and path.exists():
                os.fchmod(handle.fileno(), stat.S_IMODE(path.stat().st_mode))
            yield handle
        if overwrite:
            temporary.replace(path)
        else:
            os.link(temporary, path)
            temporary.unlink()
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(result: Dict[str, Any], path: Path, *, overwrite: bool = True, compact: bool = False) -> None:
    with _atomic_text_output(path, overwrite=overwrite) as handle:
        json.dump(result, handle, indent=None if compact else 2, separators=(',',':') if compact else None, sort_keys=False, allow_nan=False)


def write_csv(result: Dict[str, Any], path: Path, *, overwrite: bool = True) -> None:
    with _atomic_text_output(path, newline="", overwrite=overwrite) as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for sample in result["samples"]:
            writer.writerow(_flatten_sample(sample))


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
