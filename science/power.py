"""Transparent first-order direct solar input model."""

from __future__ import annotations

import math
from typing import Any, Dict

from science.config import PanelConfig


ASTRONOMICAL_UNIT_KM = 149_597_870.700
NOMINAL_SOLAR_IRRADIANCE_W_M2_AT_1_AU = 1361.0


def estimate_solar_input(
    sun: Dict[str, Any], panel: PanelConfig
) -> Dict[str, Any]:
    """Estimate incident and electrical power from direct solar irradiance.

    This is intentionally not a spacecraft electrical-system model. It omits
    temperature, degradation, wiring/conversion losses, dust, and battery/load
    behavior. Terrain occultation is represented by apparent disk fraction.
    """
    distance_km = float(sun["distance_km"])
    irradiance = NOMINAL_SOLAR_IRRADIANCE_W_M2_AT_1_AU * (
        ASTRONOMICAL_UNIT_KM / distance_km
    ) ** 2
    incidence_cosine = _incidence_cosine(
        float(sun["azimuth_deg"]),
        float(sun["elevation_deg"]),
        panel,
    )
    visible_fraction = float(sun["visibility_fraction"])
    geometric_available = visible_fraction > 0.0 and incidence_cosine > 0.0
    incident_power = (
        irradiance
        * panel.panel_area_m2
        * incidence_cosine
        * visible_fraction
    )
    electrical_power = incident_power * panel.efficiency
    return {
        "geometric_sunlight_available": visible_fraction > 0.0,
        "panel_illuminated": geometric_available,
        "orientation_mode": panel.orientation_mode,
        "incidence_cosine": round(incidence_cosine, 9),
        "relative_irradiance_vs_1au": round(
            (ASTRONOMICAL_UNIT_KM / distance_km) ** 2, 9
        ),
        "direct_irradiance_w_m2": round(irradiance, 6),
        "estimated_incident_power_w": round(incident_power, 6),
        "estimated_electrical_output_w": round(electrical_power, 6),
    }


def _incidence_cosine(
    azimuth_deg: float, elevation_deg: float, panel: PanelConfig
) -> float:
    if panel.orientation_mode == "sun_tracking":
        return 1.0
    elevation = math.radians(elevation_deg)
    if panel.orientation_mode == "horizontal_fixed":
        return max(0.0, math.sin(elevation))

    azimuth = math.radians(azimuth_deg)
    sun_east = math.cos(elevation) * math.sin(azimuth)
    sun_north = math.cos(elevation) * math.cos(azimuth)
    sun_up = math.sin(elevation)
    east, north, up = panel.custom_normal_enu
    norm = math.sqrt(east * east + north * north + up * up)
    dot = (sun_east * east + sun_north * north + sun_up * up) / norm
    return max(0.0, dot)

