"""Fail-closed consistency and reference-trace validation."""

from __future__ import annotations

import math
import statistics
from datetime import datetime
from typing import Any, Dict, Sequence

from science.ephemeris.base import EphemerisSample


# Pinned NAIF pck00011.tpc equatorial radii. Keeping this value aligned with
# the local SPICE kernel avoids introducing a 0.4 m rounding bias for Earth.
TARGET_EQUATORIAL_RADIUS_KM = {"Sun": 695_700.0, "Earth": 6_378.1366}


def compare_ephemeris_series(
    target_name: str,
    reference_samples: Sequence[EphemerisSample],
    candidate_samples: Sequence[EphemerisSample],
    *,
    maximum_angular_separation_deg: float,
    maximum_elevation_error_deg: float = 1.0 / 3600.0,
    maximum_range_error_ppm: float = 1.0,
    maximum_diameter_error_arcsec: float = 0.01,
) -> Dict[str, Any]:
    """Compare an independent ephemeris series with a reference series.

    Azimuth differences are circular so a pair such as 359.999 and 0.001
    degrees is treated as a 0.002 degree difference. The primary pass/fail
    quantity is the great-circle separation between the two local-sky unit
    vectors rather than either coordinate in isolation.
    """
    if not reference_samples or not candidate_samples:
        raise ValueError(f"No {target_name} ephemeris samples to compare")
    if len(reference_samples) != len(candidate_samples):
        raise ValueError(
            f"{target_name} ephemeris length mismatch: "
            f"{len(reference_samples)} reference versus "
            f"{len(candidate_samples)} candidate samples"
        )
    tolerances = {
        "angular separation": maximum_angular_separation_deg,
        "elevation error": maximum_elevation_error_deg,
        "range error": maximum_range_error_ppm,
        "angular-diameter error": maximum_diameter_error_arcsec,
    }
    if any(value <= 0.0 for value in tolerances.values()):
        raise ValueError("Ephemeris comparison tolerances must be positive")

    records = []
    for reference, candidate in zip(reference_samples, candidate_samples):
        if reference.timestamp != candidate.timestamp:
            raise ValueError(
                f"{target_name} timestamp mismatch: "
                f"{reference.timestamp.isoformat()} versus "
                f"{candidate.timestamp.isoformat()}"
            )
        for label, sample in (("reference", reference), ("candidate", candidate)):
            values = (
                sample.azimuth_deg,
                sample.elevation_deg,
                sample.angular_diameter_arcsec,
                sample.distance_km,
            )
            if not all(math.isfinite(value) for value in values):
                raise ValueError(
                    f"Non-finite {target_name} {label} ephemeris value at "
                    f"{sample.timestamp.isoformat()}"
                )
            if sample.distance_km <= 0.0 or sample.angular_diameter_arcsec <= 0.0:
                raise ValueError(
                    f"Non-positive {target_name} {label} range or disk size at "
                    f"{sample.timestamp.isoformat()}"
                )
        azimuth_error = _signed_circular_error_deg(
            candidate.azimuth_deg, reference.azimuth_deg
        )
        elevation_error = candidate.elevation_deg - reference.elevation_deg
        separation = _local_sky_separation_deg(reference, candidate)
        range_error_km = candidate.distance_km - reference.distance_km
        diameter_error_arcsec = (
            candidate.angular_diameter_arcsec
            - reference.angular_diameter_arcsec
        )
        records.append(
            {
                "timestamp_utc": reference.timestamp.isoformat().replace(
                    "+00:00", "Z"
                ),
                "reference_azimuth_deg": reference.azimuth_deg,
                "candidate_azimuth_deg": candidate.azimuth_deg,
                "azimuth_error_deg": azimuth_error,
                "reference_elevation_deg": reference.elevation_deg,
                "candidate_elevation_deg": candidate.elevation_deg,
                "elevation_error_deg": elevation_error,
                "angular_separation_deg": separation,
                "range_error_km": range_error_km,
                "range_error_ppm": 1_000_000.0
                * range_error_km
                / reference.distance_km,
                "angular_diameter_error_arcsec": diameter_error_arcsec,
            }
        )

    absolute_azimuth = [abs(record["azimuth_error_deg"]) for record in records]
    absolute_elevation = [
        abs(record["elevation_error_deg"]) for record in records
    ]
    angular_separation = [record["angular_separation_deg"] for record in records]
    absolute_range_ppm = [abs(record["range_error_ppm"]) for record in records]
    absolute_diameter = [
        abs(record["angular_diameter_error_arcsec"]) for record in records
    ]
    worst_index = max(
        range(len(records)), key=lambda index: angular_separation[index]
    )
    maximum_separation = angular_separation[worst_index]
    failures = []
    if maximum_separation > maximum_angular_separation_deg:
        failures.append("angular separation exceeds tolerance")
    if max(absolute_elevation) > maximum_elevation_error_deg:
        failures.append("elevation error exceeds tolerance")
    if max(absolute_range_ppm) > maximum_range_error_ppm:
        failures.append("range error exceeds tolerance")
    if max(absolute_diameter) > maximum_diameter_error_arcsec:
        failures.append("angular-diameter error exceeds tolerance")

    return {
        "status": "FAIL" if failures else "PASS",
        "target": target_name,
        "sample_count": len(records),
        "reference_provider": "NASA/JPL Horizons",
        "candidate_provider": "local NAIF SPICE",
        "pass_criterion": {
            "rule": "all maximum-error thresholds must pass",
            "maximum_allowed_deg": maximum_angular_separation_deg,
            "maximum_allowed_arcsec": maximum_angular_separation_deg * 3600.0,
            "maximum_elevation_error_arcsec": (
                maximum_elevation_error_deg * 3600.0
            ),
            "maximum_range_error_ppm": maximum_range_error_ppm,
            "maximum_angular_diameter_error_arcsec": (
                maximum_diameter_error_arcsec
            ),
        },
        "failure_reasons": failures,
        "azimuth_error_deg": _signed_error_summary(
            [record["azimuth_error_deg"] for record in records]
        ),
        "azimuth_error_arcsec": _error_summary(
            [value * 3600.0 for value in absolute_azimuth]
        ),
        "elevation_error_deg": _signed_error_summary(
            [record["elevation_error_deg"] for record in records]
        ),
        "elevation_error_arcsec": _error_summary(
            [value * 3600.0 for value in absolute_elevation]
        ),
        "angular_separation_deg": _error_summary(angular_separation),
        "angular_separation_arcsec": _error_summary(
            [value * 3600.0 for value in angular_separation]
        ),
        "range_error_km": _signed_error_summary(
            [record["range_error_km"] for record in records]
        ),
        "range_error_ppm": _signed_error_summary(
            [record["range_error_ppm"] for record in records]
        ),
        "angular_diameter_error_arcsec": _signed_error_summary(
            [record["angular_diameter_error_arcsec"] for record in records]
        ),
        "worst_position_sample": records[worst_index],
        "representative_samples": [
            records[0],
            records[len(records) // 2],
            records[-1],
        ],
    }


def _signed_circular_error_deg(candidate: float, reference: float) -> float:
    return (candidate - reference + 180.0) % 360.0 - 180.0


def _local_sky_separation_deg(
    reference: EphemerisSample, candidate: EphemerisSample
) -> float:
    reference_vector = _enu_unit_vector(
        reference.azimuth_deg, reference.elevation_deg
    )
    candidate_vector = _enu_unit_vector(
        candidate.azimuth_deg, candidate.elevation_deg
    )
    cosine = sum(
        left * right for left, right in zip(reference_vector, candidate_vector)
    )
    cross = (
        reference_vector[1] * candidate_vector[2]
        - reference_vector[2] * candidate_vector[1],
        reference_vector[2] * candidate_vector[0]
        - reference_vector[0] * candidate_vector[2],
        reference_vector[0] * candidate_vector[1]
        - reference_vector[1] * candidate_vector[0],
    )
    sine = math.sqrt(sum(component * component for component in cross))
    return math.degrees(math.atan2(sine, max(-1.0, min(1.0, cosine))))


def _enu_unit_vector(azimuth_deg: float, elevation_deg: float) -> tuple:
    azimuth = math.radians(azimuth_deg)
    elevation = math.radians(elevation_deg)
    horizontal = math.cos(elevation)
    return (
        horizontal * math.sin(azimuth),
        horizontal * math.cos(azimuth),
        math.sin(elevation),
    )


def _error_summary(values: Sequence[float]) -> Dict[str, float]:
    ordered = sorted(float(value) for value in values)
    if not ordered or not all(math.isfinite(value) for value in ordered):
        raise ValueError("Error summary requires finite values")
    percentile_index = min(
        len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1
    )
    return {
        "maximum": round(ordered[-1], 12),
        "mean": round(statistics.fmean(ordered), 12),
        "rms": round(math.sqrt(statistics.fmean(value * value for value in ordered)), 12),
        "p95": round(ordered[percentile_index], 12),
    }


def _signed_error_summary(values: Sequence[float]) -> Dict[str, float]:
    summary = _error_summary([abs(float(value)) for value in values])
    summary["signed_bias"] = round(statistics.fmean(values), 12)
    return summary


def validate_ephemeris_series(
    target_name: str,
    samples: Sequence[EphemerisSample],
    expected_start: datetime,
    expected_end: datetime,
    step_minutes: int,
) -> Dict[str, Any]:
    if not samples:
        raise ValueError(f"No {target_name} ephemeris samples to validate")
    timestamp_errors = []
    for index, sample in enumerate(samples):
        expected = expected_start.timestamp() + index * step_minutes * 60
        timestamp_errors.append(abs(sample.timestamp.timestamp() - expected))
        if not 0.0 <= sample.azimuth_deg < 360.0:
            raise ValueError(f"Invalid {target_name} azimuth: {sample.azimuth_deg}")
        if not -90.0 <= sample.elevation_deg <= 90.0:
            raise ValueError(
                f"Invalid {target_name} elevation: {sample.elevation_deg}"
            )
        if sample.distance_km <= 0.0 or sample.angular_diameter_arcsec <= 0.0:
            raise ValueError(f"Invalid {target_name} range/angular diameter")
    if samples[0].timestamp != expected_start or samples[-1].timestamp != expected_end:
        raise ValueError(f"{target_name} ephemeris endpoints do not match request")

    physical_radius = TARGET_EQUATORIAL_RADIUS_KM[target_name]
    diameter_errors_arcsec = []
    for sample in samples:
        computed_diameter_arcsec = math.degrees(
            2.0 * math.asin(physical_radius / sample.distance_km)
        ) * 3600.0
        diameter_errors_arcsec.append(
            abs(computed_diameter_arcsec - sample.angular_diameter_arcsec)
        )

    return {
        "status": "PASS",
        "validation_mode": "Horizons source-integrity consistency",
        "position_reference": "NASA/JPL Horizons values are used directly",
        "independent_position_error_deg": None,
        "independent_position_validation_note": (
            "This block checks the operational Horizons response for parser, "
            "cadence, range, angle-bound, and disk-size consistency. Independent "
            "position errors are reported separately under "
            "validation.independent_spice."
        ),
        "sample_count": len(samples),
        "first_timestamp_utc": samples[0].timestamp.isoformat().replace(
            "+00:00", "Z"
        ),
        "last_timestamp_utc": samples[-1].timestamp.isoformat().replace(
            "+00:00", "Z"
        ),
        "maximum_timestamp_grid_error_seconds": max(timestamp_errors),
        "angular_diameter_crosscheck": {
            "formula": "2 * asin(equatorial_radius / apparent_range)",
            "target_equatorial_radius_km": physical_radius,
            "maximum_absolute_error_arcsec": round(
                max(diameter_errors_arcsec), 6
            ),
            "mean_absolute_error_arcsec": round(
                sum(diameter_errors_arcsec) / len(diameter_errors_arcsec), 6
            ),
        },
        "reference_samples": [
            _reference_sample(samples[0]),
            _reference_sample(samples[len(samples) // 2]),
            _reference_sample(samples[-1]),
        ],
    }


def _reference_sample(sample: EphemerisSample) -> Dict[str, Any]:
    return {
        "timestamp_utc": sample.timestamp.isoformat().replace("+00:00", "Z"),
        "azimuth_deg": sample.azimuth_deg,
        "elevation_deg": sample.elevation_deg,
        "angular_diameter_arcsec": sample.angular_diameter_arcsec,
        "distance_km": sample.distance_km,
    }
