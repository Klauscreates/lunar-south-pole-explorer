"""Extended-disk terrain occultation classification."""

from __future__ import annotations

import math
from typing import Any, Dict

from science.ephemeris.base import EphemerisSample
from science.horizon.engine import HorizonProfile


FULLY_VISIBLE = "FULLY_VISIBLE"
PARTIALLY_VISIBLE = "PARTIALLY_VISIBLE"
BLOCKED = "BLOCKED"


def disk_visible_fraction(clearance_deg: float, angular_radius_deg: float) -> float:
    """Fraction of a circular apparent disk above a locally straight skyline.

    The skyline is approximated as a straight edge across the small apparent
    disk. Limb darkening, local skyline curvature within the disk, and
    atmospheric refraction are intentionally excluded (the Moon is airless).
    """
    if angular_radius_deg <= 0.0:
        return 1.0 if clearance_deg > 0.0 else 0.0
    ratio = clearance_deg / angular_radius_deg
    if ratio <= -1.0:
        return 0.0
    if ratio >= 1.0:
        return 1.0
    fraction = (
        math.acos(-ratio) + ratio * math.sqrt(max(0.0, 1.0 - ratio * ratio))
    ) / math.pi
    return min(1.0, max(0.0, fraction))


def classify_visibility(
    sample: EphemerisSample, horizon: HorizonProfile
) -> Dict[str, Any]:
    terrain_horizon_deg = horizon.elevation_at(sample.azimuth_deg)
    clearance_deg = sample.elevation_deg - terrain_horizon_deg
    fraction = disk_visible_fraction(clearance_deg, sample.angular_radius_deg)
    if fraction <= 0.0:
        state = BLOCKED
        fraction = 0.0
    elif fraction >= 1.0:
        state = FULLY_VISIBLE
        fraction = 1.0
    else:
        state = PARTIALLY_VISIBLE
    return {
        "azimuth_deg": round(sample.azimuth_deg, 9),
        "elevation_deg": round(sample.elevation_deg, 9),
        "angular_radius_deg": round(sample.angular_radius_deg, 9),
        "angular_diameter_arcsec": round(sample.angular_diameter_arcsec, 6),
        "distance_km": round(sample.distance_km, 6),
        "terrain_horizon_deg": round(terrain_horizon_deg, 9),
        "clearance_deg": round(clearance_deg, 9),
        "visibility_fraction": round(fraction, 9),
        "state": state,
    }

