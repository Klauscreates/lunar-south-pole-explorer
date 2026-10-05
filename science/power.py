"""Direct solar input with explicit panel pointing and cosine losses.

The baseline model uses Horizons' local azimuth/elevation angles to construct
a unit Sun vector in east/north/up coordinates. It models direct beam
irradiance only; the opt-in spacecraft analysis layer reuses its range-scaled
flux and adds configured CAD occlusion and thermal-electrical response. The
baseline export remains an explicitly idealized panel scenario.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Tuple

from science.config import PanelConfig


ASTRONOMICAL_UNIT_KM = 149_597_870.700
NOMINAL_SOLAR_IRRADIANCE_W_M2_AT_1_AU = 1361.0


def direct_solar_irradiance_w_m2(distance_km: float) -> float:
    """Return the unoccluded solar beam flux at a validated Sun range.

    Hardware-specific analysis reuses this same range scaling before applying
    terrain, CAD self-shadowing, panel incidence, and thermal-electrical losses.
    """
    distance = float(distance_km)
    if not math.isfinite(distance) or distance <= 0.0:
        raise ValueError("Sun distance must be finite and positive")
    return NOMINAL_SOLAR_IRRADIANCE_W_M2_AT_1_AU * (
        ASTRONOMICAL_UNIT_KM / distance
    ) ** 2


def estimate_solar_input(
    sun: Dict[str, Any], panel: PanelConfig
) -> Dict[str, Any]:
    """Estimate incident and electrical power from direct solar irradiance.

    This is intentionally not a spacecraft electrical-system model. It omits
    temperature, degradation, wiring/conversion losses, dust, and battery/load
    behavior. Terrain occultation is represented by apparent disk fraction.
    """
    panel.validate()
    distance_km = float(sun["distance_km"])
    visible_fraction = float(sun["visibility_fraction"])
    if not math.isfinite(visible_fraction) or not 0.0 <= visible_fraction <= 1.0:
        raise ValueError("Sun visibility fraction must be within [0, 1]")
    irradiance = direct_solar_irradiance_w_m2(distance_km)
    pointing = panel_incidence(
        float(sun["azimuth_deg"]),
        float(sun["elevation_deg"]),
        panel,
    )
    incidence_cosine = pointing["incidence_cosine"]
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
        **pointing,
        "relative_irradiance_vs_1au": round(
            (ASTRONOMICAL_UNIT_KM / distance_km) ** 2, 9
        ),
        "direct_irradiance_w_m2": round(irradiance, 6),
        "estimated_incident_power_w": round(incident_power, 6),
        "estimated_electrical_output_w": round(electrical_power, 6),
    }


def panel_incidence(
    sun_azimuth_deg: float, sun_elevation_deg: float, panel: PanelConfig
) -> Dict[str, Any]:
    """Return the beam-to-panel angle and projected-area factor.

    A panel normal points out of the collecting face. Azimuth is clockwise
    from north in the local ENU frame. A 0-degree tilt from horizontal faces
    Up; 90 degrees is vertical. A blocked Sun may still have a positive
    incidence cosine; terrain visibility is applied separately to power.
    """
    panel.validate()
    if not math.isfinite(sun_azimuth_deg) or not (
        math.isfinite(sun_elevation_deg)
        and -90.0 <= sun_elevation_deg <= 90.0
    ):
        raise ValueError("Sun azimuth/elevation must be finite valid angles")

    sun_direction = _normal_from_tilt_azimuth(
        90.0 - sun_elevation_deg, sun_azimuth_deg
    )
    normal, constrained = _panel_normal(
        sun_azimuth_deg, sun_elevation_deg, sun_direction, panel
    )
    raw_cosine = sum(a * b for a, b in zip(sun_direction, normal))
    raw_cosine = min(1.0, max(-1.0, raw_cosine))
    if abs(raw_cosine) < 1e-12:
        raw_cosine = 0.0
    incidence_cosine = max(0.0, raw_cosine)
    tilt = math.degrees(math.acos(min(1.0, max(-1.0, normal[2]))))
    azimuth = math.degrees(math.atan2(normal[0], normal[1])) % 360.0
    return {
        "sun_direction_enu": [round(value, 9) for value in sun_direction],
        "panel_normal_enu": [round(value, 9) for value in normal],
        "effective_panel_tilt_deg": round(tilt, 6),
        "effective_panel_azimuth_deg": round(azimuth, 6),
        "incidence_angle_deg": round(math.degrees(math.acos(raw_cosine)), 6),
        "incidence_cosine": round(incidence_cosine, 9),
        "cosine_loss_fraction": round(1.0 - incidence_cosine, 9),
        "tracking_limit_active": constrained,
    }


def _panel_normal(
    sun_azimuth_deg: float,
    sun_elevation_deg: float,
    sun_direction: Tuple[float, float, float],
    panel: PanelConfig,
) -> Tuple[Tuple[float, float, float], bool]:
    if panel.orientation_mode == "sun_tracking":
        return sun_direction, False
    if panel.orientation_mode == "horizontal_fixed":
        return (0.0, 0.0, 1.0), False
    if panel.orientation_mode == "custom_normal":
        magnitude = math.hypot(*panel.custom_normal_enu)
        return tuple(value / magnitude for value in panel.custom_normal_enu), False
    if panel.orientation_mode == "fixed_tilt":
        return _normal_from_tilt_azimuth(
            panel.tilt_deg_from_horizontal, panel.azimuth_deg
        ), False

    # A two-axis mount can choose any tilt/yaw inside this mechanical box.
    # For nonzero tilt the closest permitted yaw maximizes the dot product.
    yaw_offset = _signed_azimuth_difference(
        sun_azimuth_deg, panel.tracking_azimuth_center_deg
    )
    allowed_yaw_offset = min(
        panel.tracking_azimuth_half_range_deg,
        max(-panel.tracking_azimuth_half_range_deg, yaw_offset),
    )
    effective_azimuth = panel.tracking_azimuth_center_deg + allowed_yaw_offset
    azimuth_error = math.radians(
        _signed_azimuth_difference(sun_azimuth_deg, effective_azimuth)
    )
    horizontal_projection = math.cos(math.radians(sun_elevation_deg)) * math.cos(
        azimuth_error
    )
    vertical_projection = math.sin(math.radians(sun_elevation_deg))
    tilt_candidates = [panel.tracking_tilt_min_deg, panel.tracking_tilt_max_deg]
    optimum_tilt = math.degrees(
        math.atan2(horizontal_projection, vertical_projection)
    )
    if panel.tracking_tilt_min_deg <= optimum_tilt <= panel.tracking_tilt_max_deg:
        tilt_candidates.append(optimum_tilt)
    effective_tilt = max(
        tilt_candidates,
        key=lambda tilt: horizontal_projection * math.sin(math.radians(tilt))
        + vertical_projection * math.cos(math.radians(tilt)),
    )
    unconstrained_tilt = 90.0 - sun_elevation_deg
    constrained = (
        abs(_signed_azimuth_difference(sun_azimuth_deg, effective_azimuth)) > 1e-8
        or abs(effective_tilt - unconstrained_tilt) > 1e-8
    )
    return _normal_from_tilt_azimuth(effective_tilt, effective_azimuth), constrained


def _normal_from_tilt_azimuth(
    tilt_deg: float, azimuth_deg: float
) -> Tuple[float, float, float]:
    tilt = math.radians(tilt_deg)
    azimuth = math.radians(azimuth_deg)
    return (
        math.sin(tilt) * math.sin(azimuth),
        math.sin(tilt) * math.cos(azimuth),
        math.cos(tilt),
    )


def _signed_azimuth_difference(target_deg: float, origin_deg: float) -> float:
    """Shortest signed target minus origin, in [-180, 180)."""
    return (target_deg - origin_deg + 180.0) % 360.0 - 180.0


def _incidence_cosine(
    azimuth_deg: float, elevation_deg: float, panel: PanelConfig
) -> float:
    """Compatibility shim for callers of the original private helper."""
    return panel_incidence(azimuth_deg, elevation_deg, panel)["incidence_cosine"]
