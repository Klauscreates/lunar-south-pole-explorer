"""Offline lunar-topocentric ephemerides from pinned NASA/JPL NAIF kernels.

The provider uses CSPICE ``azlcpo`` for a constant-position lunar observer.
It deliberately names the DE440 Mean-Earth frame instead of relying on the
Moon's mutable default body-frame association. Azimuth increases clockwise
from local north through east, and elevation is positive toward local up.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from science.config import SiteConfig, TimeRangeConfig, utc_iso
from science.ephemeris.base import EphemerisProvider, EphemerisSample
from science.ephemeris.kernels import (
    KernelError,
    KernelRepository,
    VerifiedKernel,
)
from science.errors import EphemerisError

try:
    import spiceypy as _default_spice
    from spiceypy.utils.exceptions import SpiceyError as _SpiceyError
except ImportError:  # Keep the Horizons provider importable with a bad install.
    _default_spice = None

    class _SpiceyError(Exception):
        pass


_SPICE_POOL_LOCK = threading.RLock()
_TARGETS = {
    "SUN": {"id": 10, "display_name": "Sun"},
    "EARTH": {"id": 399, "display_name": "Earth"},
}


class KernelCoverageError(EphemerisError):
    """The pinned kernels do not cover the complete requested interval."""


class SpiceEphemerisProvider(EphemerisProvider):
    """Compute apparent Sun/Earth geometry at a fixed lunar surface site.

    CSPICE maintains a process-global kernel pool. Calls through this provider
    are serialized, run with only the locked kernel set, and restore directly
    loaded kernels or meta-kernels that were present before the calculation.
    Applications making independent raw CSPICE calls concurrently should use a
    dedicated worker process to obtain full process isolation.
    """

    def __init__(
        self,
        kernel_dir: Path,
        *,
        auto_download: bool = True,
        aberration_correction: str = "CN+S",
        repository: KernelRepository | None = None,
        spice_module: Any = None,
    ) -> None:
        self._spice = spice_module or _default_spice
        if self._spice is None:
            raise EphemerisError(
                "SpiceyPy is required for the local SPICE provider. Install the "
                "project environment with `uv pip install -e '.[dev]'`."
            )
        if aberration_correction != "CN+S":
            raise ValueError(
                "The validated local apparent-ephemeris mode is locked to "
                "converged Newtonian light-time plus stellar aberration (CN+S)"
            )
        self.repository = repository or KernelRepository(
            kernel_dir,
            auto_download=auto_download,
        )
        self.aberration_correction = aberration_correction

    def get_sun_positions(
        self,
        site: SiteConfig,
        terrain_elevation_m: float,
        time_range: TimeRangeConfig,
    ) -> tuple[list[EphemerisSample], dict[str, Any]]:
        return self._get_positions("SUN", site, terrain_elevation_m, time_range)

    def get_earth_positions(
        self,
        site: SiteConfig,
        terrain_elevation_m: float,
        time_range: TimeRangeConfig,
    ) -> tuple[list[EphemerisSample], dict[str, Any]]:
        return self._get_positions("EARTH", site, terrain_elevation_m, time_range)

    def _get_positions(
        self,
        target: str,
        site: SiteConfig,
        terrain_elevation_m: float,
        time_range: TimeRangeConfig,
    ) -> tuple[list[EphemerisSample], dict[str, Any]]:
        target_key = target.upper()
        if target_key not in _TARGETS:
            raise ValueError(f"Unsupported SPICE target: {target!r}")
        self._validate_inputs(site, terrain_elevation_m, time_range)
        timestamps = _sample_timestamps(time_range)
        altitude_km = (
            float(terrain_elevation_m) + float(site.observer_height_m)
        ) / 1000.0

        try:
            kernels = self.repository.resolve()
            with _isolated_kernel_pool(self._spice, kernels):
                result = self._compute_loaded(
                    target_key,
                    site,
                    float(terrain_elevation_m),
                    altitude_km,
                    time_range,
                    timestamps,
                    kernels,
                )
        except KernelError:
            raise
        except _SpiceyError as exc:
            raise EphemerisError(
                f"CSPICE failed for {target_key} at site {site.name!r} over "
                f"{utc_iso(time_range.start_utc)} to "
                f"{utc_iso(time_range.end_utc)}: {exc}"
            ) from exc
        except (ArithmeticError, OverflowError, ValueError) as exc:
            raise EphemerisError(
                f"Invalid SPICE geometry for {target_key} at site {site.name!r}: {exc}"
            ) from exc
        return result

    def _compute_loaded(
        self,
        target: str,
        site: SiteConfig,
        terrain_elevation_m: float,
        altitude_km: float,
        time_range: TimeRangeConfig,
        timestamps: Sequence[datetime],
        kernels: Sequence[VerifiedKernel],
    ) -> tuple[list[EphemerisSample], dict[str, Any]]:
        spice = self._spice
        manifest = self.repository.manifest
        frame = manifest.reference_frame_name
        frame_id = int(spice.namfrm(frame))
        if frame_id != manifest.reference_frame_id:
            raise EphemerisError(
                f"Locked lunar frame {frame!r} resolved to ID {frame_id}; "
                f"expected {manifest.reference_frame_id}"
            )
        frame_info = tuple(spice.frinfo(frame_id))
        if len(frame_info) < 3:
            raise EphemerisError(f"CSPICE returned incomplete frame data for {frame}")
        center_id, frame_class, class_id = map(int, frame_info[:3])
        if (center_id, frame_class, class_id) != (
            manifest.reference_frame_center_id,
            4,
            manifest.reference_frame_id,
        ):
            raise EphemerisError(
                f"Unexpected frame specification for {frame}: center={center_id}, "
                f"class={frame_class}, class_id={class_id}"
            )

        start_et = float(spice.str2et(_spice_utc_string(time_range.start_utc)))
        end_et = float(spice.str2et(_spice_utc_string(time_range.end_utc)))
        coverage = self._validate_coverage(target, start_et, end_et, kernels)

        # Explicit endpoint transforms catch frame-chain errors in addition to
        # the binary-PCK interval check.
        spice.pxform(frame, "J2000", start_et)
        spice.pxform(frame, "J2000", end_et)

        moon_radii = _body_radii(spice, "MOON")
        if not all(
            math.isclose(
                radius,
                1737.4,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            for radius in moon_radii
        ):
            raise EphemerisError(
                "The validated lunar coordinate convention requires the "
                "pck00011 1737.4 km spherical Moon reference surface; loaded "
                f"radii are {moon_radii!r} km"
            )
        equatorial_radius_km = moon_radii[0]
        flattening = (moon_radii[0] - moon_radii[2]) / moon_radii[0]
        observer_position_km = spice.georec(
            math.radians(site.longitude_deg_east),
            math.radians(site.latitude_deg),
            altitude_km,
            equatorial_radius_km,
            flattening,
        )
        observer_radius_km = math.sqrt(
            sum(float(component) ** 2 for component in observer_position_km)
        )
        if not all(math.isfinite(float(value)) for value in observer_position_km):
            raise EphemerisError("CSPICE produced a non-finite observer position")

        target_radii = _body_radii(spice, target)
        angular_radius_km = max(target_radii[0], target_radii[1])
        target_info = _TARGETS[target]
        samples: list[EphemerisSample] = []
        light_times_seconds: list[float] = []
        time_audit: list[dict[str, Any]] = []
        for timestamp in timestamps:
            et = float(spice.str2et(_spice_utc_string(timestamp)))
            # Use CSPICE's LSK-driven time subsystem, not a fixed UTC offset.
            # This is its TT/TDB approximation, not a lunar proper-time model.
            tt = float(spice.unitim(et, "TDB", "TDT"))
            recovered_et = float(spice.unitim(tt, "TDT", "TDB"))
            roundtrip_error = abs(recovered_et - et)
            if not all(math.isfinite(v) for v in (et, tt, recovered_et)) or roundtrip_error > 1e-6:
                raise EphemerisError("CSPICE TT/TDB time conversion failed the 1 microsecond round-trip check")
            time_audit.append({
                "utc": utc_iso(timestamp), "tdb_seconds_past_j2000": et,
                "tt_seconds_past_j2000": tt, "tdb_minus_tt_seconds": et - tt,
                "roundtrip_error_seconds": roundtrip_error,
            })
            az_state, light_time = spice.azlcpo(
                "ELLIPSOID",
                target,
                et,
                self.aberration_correction,
                False,  # clockwise: North -> East -> South -> West
                True,  # elevation positive toward local +Up
                observer_position_km,
                "MOON",
                frame,
            )
            distance_km = float(az_state[0])
            azimuth_deg = math.degrees(float(az_state[1])) % 360.0
            elevation_deg = math.degrees(float(az_state[2]))
            angular_diameter_arcsec = _angular_diameter_arcsec(
                angular_radius_km,
                distance_km,
            )
            values = (
                distance_km,
                azimuth_deg,
                elevation_deg,
                angular_diameter_arcsec,
                float(light_time),
            )
            if not all(math.isfinite(value) for value in values):
                raise EphemerisError(
                    f"CSPICE returned a non-finite {target} sample at "
                    f"{utc_iso(timestamp)}"
                )
            if not (-90.0 <= elevation_deg <= 90.0):
                raise EphemerisError(
                    f"CSPICE elevation is out of range at {utc_iso(timestamp)}: "
                    f"{elevation_deg}"
                )
            samples.append(
                EphemerisSample(
                    timestamp=timestamp,
                    azimuth_deg=azimuth_deg,
                    elevation_deg=elevation_deg,
                    angular_diameter_arcsec=angular_diameter_arcsec,
                    distance_km=distance_km,
                    solar_presence_code="",
                    interfering_body_code="",
                )
            )
            light_times_seconds.append(float(light_time))

        if len(samples) != len(timestamps):
            raise EphemerisError(
                f"SPICE returned {len(samples)} {target} samples; expected "
                f"{len(timestamps)}"
            )

        metadata: dict[str, Any] = {
            "provider": "NASA/JPL NAIF SPICE (local via SpiceyPy)",
            "target_id": str(target_info["id"]),
            "target_name": target_info["display_name"],
            "ephemeris_source": "JPL DE440 (de440s.bsp)",
            "center_body": "Moon (301)",
            "center_frame": frame,
            "coordinate_type": "planetodetic on the loaded lunar sphere",
            "site_coordinates_used": {
                "longitude_deg_east": site.longitude_deg_east,
                "latitude_deg": site.latitude_deg,
                "terrain_elevation_m": terrain_elevation_m,
                "observer_height_m": site.observer_height_m,
                "altitude_above_reference_sphere_km": altitude_km,
                "observer_position_in_frame_km": [
                    float(value) for value in observer_position_km
                ],
                "observer_radius_km": observer_radius_km,
            },
            "local_topocentric_convention": {
                "method": "CSPICE azlcpo ELLIPSOID surface normal",
                "up": "outward normal to the 1737.4 km reference sphere",
                "north": "tangent toward the lunar north pole",
                "east": "positive-east tangent",
                "azimuth": "clockwise from north, degrees in [0, 360)",
                "elevation": "degrees above the local tangent plane",
            },
            "apparent_state": {
                "aberration_correction": self.aberration_correction,
                "reception_case": True,
                "light_time_seconds_min": min(light_times_seconds),
                "light_time_seconds_max": max(light_times_seconds),
                "relativistic_light_deflection": (
                    "not modeled by CSPICE azlcpo; retained as a stated "
                    "difference from Horizons apparent observer tables"
                ),
            },
            "time_conversion_audit": {
                "method": "CSPICE str2et UTC to TDB; unitim TDB to TDT (TT)",
                "model": "LSK DELTET periodic TT/TDB approximation; not exact lunar proper time",
                "roundtrip_tolerance_seconds": 1e-6,
                "samples": time_audit,
            },
            "qualification": {
                "flight_ready": False,
                "kernel_integrity": "size and SHA-256 pinned; interval coverage checked",
                "lunar_orientation": "DE440 binary PCK plus explicit Mean-Earth frame; not error-free truth",
                "antenna_phase_center": "UNKNOWN: generic site observer, no calibrated hardware offset applied",
                "relativistic_light_propagation": "NOT_IMPLEMENTED: no Shapiro delay or relativistic light deflection",
                "relativistic_stellar_aberration": "NOT_IMPLEMENTED: CN+S uses Newtonian stellar aberration",
                "lunar_proper_time": "NOT_IMPLEMENTED",
                "binding_authority": "SpiceyPy is third-party; CSPICE and locked kernels are NASA/JPL NAIF products",
            },
            "angular_diameter": {
                "definition": (
                    "two times asin(equatorial_radius/apparent_range), using "
                    "BODY target radii from pck00011.tpc"
                ),
                "target_equatorial_radius_km": angular_radius_km,
                "target_radii_km": list(target_radii),
            },
            "requested_interval": {
                "start_utc": utc_iso(time_range.start_utc),
                "end_utc": utc_iso(time_range.end_utc),
                "start_et_seconds_past_j2000": start_et,
                "end_et_seconds_past_j2000": end_et,
                "step_minutes": time_range.step_minutes,
                "sample_count": len(samples),
            },
            "kernel_coverage": coverage,
            "kernel_manifest": {
                "manifest_id": manifest.manifest_id,
                "manifest_path": str(manifest.path),
                "manifest_sha256": manifest.sha256,
                "source_authority": manifest.source_authority,
                "kernels": [kernel.as_provenance() for kernel in kernels],
            },
            "software": {
                "spiceypy": _installed_version("spiceypy"),
                "cspice_toolkit": str(spice.tkvrsn("TOOLKIT")),
            },
        }
        return samples, metadata

    def _validate_coverage(
        self,
        target: str,
        start_et: float,
        end_et: float,
        kernels: Sequence[VerifiedKernel],
    ) -> dict[str, Any]:
        spice = self._spice
        verified_by_name = {kernel.spec.filename: kernel for kernel in kernels}
        spk_spec = self.repository.manifest.spec_by_kind("SPK")
        pck_spec = self.repository.manifest.spec_by_kind("PCK-BINARY")
        try:
            spk_path = verified_by_name[spk_spec.filename].path
            pck_path = verified_by_name[pck_spec.filename].path
        except KeyError as exc:
            raise EphemerisError(
                "The resolved kernel set does not match its lock manifest"
            ) from exc
        target_id = int(_TARGETS[target]["id"])
        spk_records: dict[str, list[dict[str, Any]]] = {}
        for body_name, body_id in ((target, target_id), ("MOON", 301)):
            intervals = _window_intervals(spice, spice.spkcov(str(spk_path), body_id))
            _require_coverage(
                intervals,
                start_et,
                end_et,
                f"{spk_path.name} body {body_name} ({body_id})",
            )
            spk_records[f"{body_name}:{body_id}"] = _coverage_records(spice, intervals)

        pck_frame_id = self.repository.manifest.binary_pck_frame_id
        pck_intervals = _window_intervals(
            spice,
            spice.pckcov(str(pck_path), pck_frame_id),
        )
        _require_coverage(
            pck_intervals,
            start_et,
            end_et,
            f"{pck_path.name} frame {pck_frame_id}",
        )
        return {
            "requested_interval_fully_covered": True,
            "spk": spk_records,
            "binary_pck": {
                "frame_id": pck_frame_id,
                "intervals": _coverage_records(spice, pck_intervals),
            },
        }

    @staticmethod
    def _validate_inputs(
        site: SiteConfig,
        terrain_elevation_m: float,
        time_range: TimeRangeConfig,
    ) -> None:
        site.validate()
        time_range.validate()
        if not math.isfinite(float(terrain_elevation_m)):
            raise EphemerisError("Terrain elevation must be finite")
        if site.latitude_deg <= -90.0 or site.latitude_deg >= 90.0:
            raise EphemerisError(
                "Azimuth is undefined at the exact lunar poles; use a site "
                "strictly inside (-90, 90) degrees latitude"
            )
        for name, timestamp in (
            ("start", time_range.start_utc),
            ("end", time_range.end_utc),
        ):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise EphemerisError(f"Time-range {name} timestamp must be UTC-aware")


def _sample_timestamps(time_range: TimeRangeConfig) -> tuple[datetime, ...]:
    step_seconds = time_range.step_minutes * 60
    total_seconds = (time_range.end_utc - time_range.start_utc).total_seconds()
    count = int(total_seconds // step_seconds) + 1
    return tuple(
        time_range.start_utc + timedelta(seconds=index * step_seconds)
        for index in range(count)
    )


def _spice_utc_string(timestamp: datetime) -> str:
    value = timestamp.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M:%S.%f UTC")


def _body_radii(spice: Any, body: str) -> tuple[float, float, float]:
    dimension, values = spice.bodvrd(body, "RADII", 3)
    radii = tuple(float(value) for value in values)
    if (
        int(dimension) != 3
        or len(radii) != 3
        or not all(math.isfinite(value) and value > 0.0 for value in radii)
    ):
        raise EphemerisError(f"Invalid {body} radii from the loaded text PCK")
    return radii  # type: ignore[return-value]


def _angular_diameter_arcsec(radius_km: float, distance_km: float) -> float:
    if distance_km <= radius_km or radius_km <= 0.0:
        raise EphemerisError(
            f"Cannot compute angular diameter for radius={radius_km} km and "
            f"range={distance_km} km"
        )
    return math.degrees(2.0 * math.asin(radius_km / distance_km)) * 3600.0


def _window_intervals(spice: Any, window: Any) -> list[tuple[float, float]]:
    return [
        tuple(float(value) for value in spice.wnfetd(window, index))
        for index in range(int(spice.wncard(window)))
    ]


def _require_coverage(
    intervals: Sequence[tuple[float, float]],
    start_et: float,
    end_et: float,
    label: str,
) -> None:
    tolerance_seconds = 1e-6
    if any(
        lower - tolerance_seconds <= start_et and end_et <= upper + tolerance_seconds
        for lower, upper in intervals
    ):
        return
    raise KernelCoverageError(
        f"{label} does not continuously cover requested ET interval "
        f"[{start_et:.6f}, {end_et:.6f}]; available intervals: {intervals}"
    )


def _coverage_records(
    spice: Any,
    intervals: Sequence[tuple[float, float]],
) -> list[dict[str, Any]]:
    return [
        {
            "start_et_seconds_past_j2000": lower,
            "end_et_seconds_past_j2000": upper,
            "start_tdb_calendar": str(spice.etcal(lower)),
            "end_tdb_calendar": str(spice.etcal(upper)),
        }
        for lower, upper in intervals
    ]


def _installed_version(distribution: str) -> str:
    try:
        return importlib_metadata.version(distribution)
    except importlib_metadata.PackageNotFoundError:
        return "unknown"


def _kernel_pool_roots(spice: Any) -> list[str]:
    roots: list[str] = []
    for index in range(int(spice.ktotal("ALL"))):
        record = tuple(spice.kdata(index, "ALL"))
        if len(record) < 3:
            continue
        filename, _kind, source = map(str, record[:3])
        if not source and filename not in roots:
            roots.append(filename)
    return roots


@contextmanager
def _isolated_kernel_pool(
    spice: Any,
    kernels: Sequence[VerifiedKernel],
) -> Iterator[None]:
    """Load only the pinned set, then restore the caller's root kernels."""
    with _SPICE_POOL_LOCK:
        previous_roots = _kernel_pool_roots(spice)
        spice.kclear()
        try:
            for kernel in kernels:
                spice.furnsh(str(kernel.path))
            loaded_count = int(spice.ktotal("ALL"))
            if loaded_count != len(kernels):
                raise EphemerisError(
                    f"Loaded SPICE kernel count is {loaded_count}; expected "
                    f"{len(kernels)} from the lock manifest"
                )
            yield
        finally:
            spice.kclear()
            for root in previous_roots:
                spice.furnsh(root)
