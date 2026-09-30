"""Validated configuration models for the simulation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Sequence, Tuple

from science.errors import ConfigurationError


DEFAULT_LOCAL_TERRAIN_URL = (
    "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/"
    "LDEM_83S_10MPP_ADJ.TIF"
)
DEFAULT_OUTER_TERRAIN_URL = (
    "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/"
    "LDEM_60S_240MPP_ADJ.TIF"
)


def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp and reject ambiguous naive values."""
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ConfigurationError(f"Invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ConfigurationError(
            f"Timestamp must include a UTC offset or trailing Z: {value!r}"
        )
    return parsed.astimezone(timezone.utc)


def utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class SiteConfig:
    name: str = "Test Site A"
    latitude_deg: float = -89.9
    longitude_deg_east: float = 0.0
    observer_height_m: float = 2.0

    def validate(self) -> None:
        if not self.name.strip():
            raise ConfigurationError("Site name cannot be empty")
        if not -90.0 <= self.latitude_deg <= 90.0:
            raise ConfigurationError("Latitude must be within [-90, 90] degrees")
        if not -360.0 <= self.longitude_deg_east <= 360.0:
            raise ConfigurationError("Longitude must be within [-360, 360] degrees")
        if self.observer_height_m < 0.0:
            raise ConfigurationError("Observer height cannot be negative")


@dataclass(frozen=True)
class TimeRangeConfig:
    start_utc: datetime = field(
        default_factory=lambda: parse_utc("2026-10-01T00:00:00Z")
    )
    end_utc: datetime = field(
        default_factory=lambda: parse_utc("2026-10-08T00:00:00Z")
    )
    step_minutes: int = 10

    def validate(self) -> None:
        if self.end_utc <= self.start_utc:
            raise ConfigurationError("End time must be after start time")
        if self.step_minutes <= 0:
            raise ConfigurationError("Step minutes must be positive")
        expected_samples = (
            (self.end_utc - self.start_utc).total_seconds()
            / (self.step_minutes * 60.0)
        ) + 1.0
        if expected_samples > 10_000:
            raise ConfigurationError(
                "Horizons observer tables are limited to 10,000 output epochs; "
                f"this request would produce approximately {expected_samples:.0f}"
            )


@dataclass(frozen=True)
class TerrainConfig:
    source: str = DEFAULT_LOCAL_TERRAIN_URL
    outer_source: str = DEFAULT_OUTER_TERRAIN_URL
    local_radius_m: float = 10_000.0
    search_radius_m: float = 200_000.0
    azimuth_step_deg: float = 0.5
    radial_step_m: float = 10.0
    outer_radial_step_m: float = 240.0
    lunar_radius_m: float = 1_737_400.0

    def validate(self) -> None:
        if not self.source:
            raise ConfigurationError("Terrain source cannot be empty")
        if not self.outer_source:
            raise ConfigurationError("Outer terrain source cannot be empty")
        if not 100.0 <= self.local_radius_m <= self.search_radius_m:
            raise ConfigurationError(
                "Local terrain radius must be at least 100 m and no larger "
                "than the maximum search radius"
            )
        if not 1_000.0 <= self.search_radius_m <= 900_000.0:
            raise ConfigurationError(
                "Terrain search radius must be between 1 km and 900 km"
            )
        if not 0.05 <= self.azimuth_step_deg <= 10.0:
            raise ConfigurationError(
                "Azimuth step must be between 0.05 and 10 degrees"
            )
        count = 360.0 / self.azimuth_step_deg
        if abs(count - round(count)) > 1e-9:
            raise ConfigurationError("Azimuth step must divide 360 degrees exactly")
        if self.radial_step_m <= 0.0:
            raise ConfigurationError("Radial terrain step must be positive")
        if self.outer_radial_step_m <= 0.0:
            raise ConfigurationError("Outer radial terrain step must be positive")
        if self.lunar_radius_m <= 0.0:
            raise ConfigurationError("Lunar radius must be positive")


@dataclass(frozen=True)
class PanelConfig:
    panel_area_m2: float = 1.0
    efficiency: float = 0.30
    orientation_mode: str = "sun_tracking"
    custom_normal_enu: Tuple[float, float, float] = (0.0, 0.0, 1.0)

    def validate(self) -> None:
        if self.panel_area_m2 <= 0.0:
            raise ConfigurationError("Panel area must be positive")
        if not 0.0 < self.efficiency <= 1.0:
            raise ConfigurationError("Panel efficiency must be within (0, 1]")
        if self.orientation_mode not in {
            "sun_tracking",
            "horizontal_fixed",
            "custom_normal",
        }:
            raise ConfigurationError(
                "Panel orientation must be sun_tracking, horizontal_fixed, or "
                "custom_normal"
            )
        if len(self.custom_normal_enu) != 3:
            raise ConfigurationError("Custom panel normal must contain E, N, U")
        if sum(component * component for component in self.custom_normal_enu) <= 0:
            raise ConfigurationError("Custom panel normal cannot be the zero vector")


@dataclass(frozen=True)
class SimulationConfig:
    site: SiteConfig = field(default_factory=SiteConfig)
    time_range: TimeRangeConfig = field(default_factory=TimeRangeConfig)
    terrain: TerrainConfig = field(default_factory=TerrainConfig)
    panel: PanelConfig = field(default_factory=PanelConfig)

    def validate(self) -> None:
        self.site.validate()
        self.time_range.validate()
        self.terrain.validate()
        self.panel.validate()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "site": {
                "name": self.site.name,
                "latitude_deg": self.site.latitude_deg,
                "longitude_deg_east": self.site.longitude_deg_east,
                "observer_height_m": self.site.observer_height_m,
            },
            "time_range": {
                "start_utc": utc_iso(self.time_range.start_utc),
                "end_utc": utc_iso(self.time_range.end_utc),
                "step_minutes": self.time_range.step_minutes,
            },
            "terrain": {
                "source": self.terrain.source,
                "outer_source": self.terrain.outer_source,
                "local_radius_m": self.terrain.local_radius_m,
                "search_radius_m": self.terrain.search_radius_m,
                "azimuth_step_deg": self.terrain.azimuth_step_deg,
                "radial_step_m": self.terrain.radial_step_m,
                "outer_radial_step_m": self.terrain.outer_radial_step_m,
                "lunar_radius_m": self.terrain.lunar_radius_m,
            },
            "panel": {
                "panel_area_m2": self.panel.panel_area_m2,
                "efficiency": self.panel.efficiency,
                "orientation_mode": self.panel.orientation_mode,
                "custom_normal_enu": list(self.panel.custom_normal_enu),
            },
        }


def tuple3(values: Sequence[float]) -> Tuple[float, float, float]:
    if len(values) != 3:
        raise ConfigurationError("Expected exactly three vector components")
    return float(values[0]), float(values[1]), float(values[2])
