"""Opt-in, single-bounce wall-reflected solar irradiance on a panel plane.

Every terrain facet and its *broadband* reflectance must be supplied by the
caller. A LOLA elevation model resolves shape, not optical reflectance. This
module does not infer lunar albedo, wall illumination, intervening occlusion,
or infrared emission. In particular, an omitted panel-visibility fraction
means an explicitly reported clear wall-to-panel path, not a ray-cast result.

Facets are treated as small planar Lambertian reflectors. For facet ``i`` the
panel-plane contribution is

    E_i = E_sun * f_sun * rho * cos(sun, wall)
          * cos(wall, panel) * cos(panel, wall) * A / (pi * r**2)
          * f_wall_to_panel.

``E_sun`` is direct-normal solar irradiance in W/m²; facet area and ENU
positions are in m² and metres. The result is W/m² already incident on the
panel face, suitable for ``PanelEnvironment.wall_reflected_solar_irradiance_w_m2``.
Do not multiply it by direct-beam panel incidence or terrain visibility again.

This centroid-quadrature approximation is not a spectral BRDF, interreflection,
or flight thermal/optical model. It is deliberately invalid for near-field
facets whose area is large relative to squared panel distance. Subdivide such
facets or use resolved surface integration.

View-factor basis: NASA/CP-2005-213431, pp. 164-165,
https://ntrs.nasa.gov/api/citations/20050206360/downloads/20050206360.pdf
Lambertian BRDF definition: NIST SCATMECH,
https://pages.nist.gov/SCATMECH/docs/lambert.htm
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Any, Dict, Iterable, Optional, Tuple


Vec3 = Tuple[float, float, float]

# A conservative sampling guard: a facet whose characteristic area is more
# than one quarter of distance squared needs subdivision before centroid use.
MAX_FACET_AREA_OVER_DISTANCE_SQUARED = 0.25
MAX_WALL_FACETS = 100_000
_VIEW_FACTOR_TOLERANCE = 1e-10


def _finite_number(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _fraction(name: str, value: float) -> float:
    number = _finite_number(name, value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be within [0, 1]")
    return number


def _vector(name: str, values: Vec3, *, normalize: bool) -> Vec3:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must contain three finite ENU components")
    try:
        components = tuple(values)
    except TypeError as exc:
        raise ValueError(f"{name} must contain three finite ENU components") from exc
    if len(components) != 3:
        raise ValueError(f"{name} must contain three finite ENU components")
    result = tuple(
        _finite_number(f"{name}[{index}]", value)
        for index, value in enumerate(components)
    )
    if not normalize:
        return result[0], result[1], result[2]
    magnitude = math.hypot(*result)
    if not math.isfinite(magnitude) or magnitude <= 0.0:
        raise ValueError(f"{name} must have finite nonzero length")
    return result[0] / magnitude, result[1] / magnitude, result[2] / magnitude


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


@dataclass(frozen=True)
class WallFacet:
    """One finite planar wall facet, with caller-supplied optical properties.

    Normals point out of the reflecting face. ``sun_visible_fraction`` must
    account for the Sun disk exposed at *this facet*, not at the rover site.
    ``panel_visible_fraction`` defaults to one only when the caller has not
    modeled wall-to-panel obstruction; that assumption is reported in output.
    For partially blocked facets, both fractions may be between zero and one.
    """

    center_enu_m: Vec3
    normal_enu: Vec3
    area_m2: float
    broadband_reflectance: float
    sun_visible_fraction: float
    panel_visible_fraction: Optional[float] = None


def estimate_wall_reflected_irradiance(
    *,
    panel_position_enu_m: Vec3,
    panel_normal_enu: Vec3,
    sun_direction_enu: Vec3,
    direct_normal_irradiance_w_m2: float,
    facets: Iterable[WallFacet],
) -> Dict[str, Any]:
    """Estimate wall-reflected *panel-plane* solar flux in W/m².

    The result is an opt-in environmental boundary, not a promise that all
    nearby reflecting surfaces were included. A zero with no facets means
    only that the caller supplied no reflecting geometry.
    """
    panel_position = _vector(
        "panel_position_enu_m", panel_position_enu_m, normalize=False
    )
    panel_normal = _vector("panel_normal_enu", panel_normal_enu, normalize=True)
    sun_direction = _vector("sun_direction_enu", sun_direction_enu, normalize=True)
    source_flux = _finite_number(
        "direct_normal_irradiance_w_m2", direct_normal_irradiance_w_m2
    )
    if source_flux < 0.0:
        raise ValueError("direct_normal_irradiance_w_m2 must be nonnegative")
    if isinstance(facets, (str, bytes)):
        raise ValueError("facets must be an iterable of WallFacet objects")
    try:
        facet_iterator = iter(facets)
    except TypeError as exc:
        raise ValueError("facets must be an iterable of WallFacet objects") from exc

    contributions = []
    view_factors = []
    facet_count = 0
    active_count = 0
    assumed_clear_count = 0
    for facet_count, facet in enumerate(facet_iterator, start=1):
        if facet_count > MAX_WALL_FACETS:
            raise ValueError(f"facets exceeds the {MAX_WALL_FACETS} facet limit")
        if not isinstance(facet, WallFacet):
            raise ValueError(f"facets[{facet_count - 1}] must be a WallFacet")
        name = f"facets[{facet_count - 1}]"
        center = _vector(f"{name}.center_enu_m", facet.center_enu_m, normalize=False)
        wall_normal = _vector(f"{name}.normal_enu", facet.normal_enu, normalize=True)
        area = _finite_number(f"{name}.area_m2", facet.area_m2)
        if area <= 0.0:
            raise ValueError(f"{name}.area_m2 must be positive")
        reflectance = _fraction(
            f"{name}.broadband_reflectance", facet.broadband_reflectance
        )
        sun_visible = _fraction(
            f"{name}.sun_visible_fraction", facet.sun_visible_fraction
        )
        if facet.panel_visible_fraction is None:
            panel_visible = 1.0
            assumed_clear_count += 1
        else:
            panel_visible = _fraction(
                f"{name}.panel_visible_fraction", facet.panel_visible_fraction
            )

        wall_to_panel = tuple(p - c for p, c in zip(panel_position, center))
        distance = math.hypot(*wall_to_panel)
        if not math.isfinite(distance) or distance <= 0.0:
            raise ValueError(f"{name} must have a finite positive panel distance")
        area_over_distance_squared = (area / distance) / distance
        if not math.isfinite(area_over_distance_squared):
            raise ValueError(f"{name} has unbounded area/distance geometry")
        if area_over_distance_squared > MAX_FACET_AREA_OVER_DISTANCE_SQUARED:
            raise ValueError(
                f"{name} is too large or close for centroid view-factor "
                "quadrature; subdivide it"
            )
        direction_to_panel = tuple(value / distance for value in wall_to_panel)
        cosine_wall = max(0.0, _dot(wall_normal, direction_to_panel))
        cosine_panel = max(
            0.0, -_dot(panel_normal, direction_to_panel)
        )
        cosine_sun = max(0.0, _dot(wall_normal, sun_direction))
        # This is the panel-to-wall differential view factor. The product of
        # receiver and emitter cosines prevents contributions from back faces.
        view_factor = (
            cosine_wall
            * cosine_panel
            * area_over_distance_squared
            / math.pi
            * panel_visible
        )
        view_factors.append(view_factor)
        contribution = (
            source_flux
            * sun_visible
            * reflectance
            * cosine_sun
            * view_factor
        )
        contributions.append(contribution)
        if contribution > 0.0:
            active_count += 1

    total_view_factor = math.fsum(view_factors)
    if total_view_factor > 1.0 + _VIEW_FACTOR_TOLERANCE:
        raise ValueError(
            "summed panel-to-wall view factor exceeds one; check overlapping "
            "facets, occlusion, or near-field geometry"
        )
    reflected = math.fsum(contributions)
    if not math.isfinite(reflected) or reflected > source_flux * (1.0 + 1e-10):
        raise ValueError("reflected irradiance exceeds the source-flux bound")
    return {
        "model": "single_bounce_lambertian_wall_facets_v1",
        "wall_reflected_solar_irradiance_w_m2": reflected,
        "facet_count": facet_count,
        "active_facet_count": active_count,
        "assumed_clear_wall_to_panel_facet_count": assumed_clear_count,
        "total_panel_to_wall_view_factor": total_view_factor,
        "facet_sampling_area_over_distance_squared_max": (
            MAX_FACET_AREA_OVER_DISTANCE_SQUARED
        ),
    }
