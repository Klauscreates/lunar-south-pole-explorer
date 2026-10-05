"""Illustrative direct-to-Earth geometry screening, not a radio link budget.

The requested 0/30/100 display index deliberately tests the Earth *center*
against the authoritative interpolated terrain skyline. The existing DTE
window metric remains disk-aware: an exposed limb can make that metric true
while this conservative center-based index is zero. Neither metric says that
an Earth ground station or a flight antenna has a working RF link.
"""

from __future__ import annotations

import math
from typing import Any, Dict


MODEL_ID = "earth_center_terrain_clearance_v1"
LOW_ELEVATION_THRESHOLD_DEG = 2.0


def classify_comms_potential(earth: Dict[str, Any]) -> Dict[str, Any]:
    """Map one classified Horizons/LOLA Earth sample to a display category.

    Zero requires the Earth center to be strictly above the local skyline.
    Exactly 2 degrees absolute Earth elevation is marginal, so the strong
    category begins only above that threshold. The percentages are category
    markers, not received signal power, probability, or link reliability.
    """
    try:
        elevation = float(earth["elevation_deg"])
        terrain_horizon = float(earth["terrain_horizon_deg"])
        clearance = float(earth["clearance_deg"])
        visible_fraction = float(earth["visibility_fraction"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Earth visibility sample is incomplete") from exc
    if not all(math.isfinite(value) for value in (
        elevation, terrain_horizon, clearance, visible_fraction
    )):
        raise ValueError("Earth visibility sample contains a nonfinite value")
    if not 0.0 <= visible_fraction <= 1.0:
        raise ValueError("Earth disk fraction must be within [0, 1]")
    if not math.isclose(
        elevation - terrain_horizon, clearance, rel_tol=0.0, abs_tol=5e-8
    ):
        raise ValueError("Earth skyline clearance is inconsistent with geometry")

    center_clear = clearance > 0.0
    if not center_clear:
        classification, potential_index_percent = "BLOCKED", 0
    elif elevation <= LOW_ELEVATION_THRESHOLD_DEG:
        classification, potential_index_percent = "MARGINAL", 30
    else:
        classification, potential_index_percent = "CLEAR", 100
    return {
        "model": MODEL_ID,
        "classification": classification,
        "potential_index_percent": potential_index_percent,
        "center_clear": center_clear,
        "low_elevation_threshold_deg": LOW_ELEVATION_THRESHOLD_DEG,
    }
