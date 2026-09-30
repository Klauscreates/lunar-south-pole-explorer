"""Provider abstraction for replaceable celestial geometry backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

from science.config import SiteConfig, TimeRangeConfig


@dataclass(frozen=True)
class EphemerisSample:
    timestamp: datetime
    azimuth_deg: float
    elevation_deg: float
    angular_diameter_arcsec: float
    distance_km: float
    solar_presence_code: str
    interfering_body_code: str

    @property
    def angular_radius_deg(self) -> float:
        return self.angular_diameter_arcsec / 7200.0


class EphemerisProvider(ABC):
    """Contract for topocentric lunar Sun/Earth apparent positions."""

    @abstractmethod
    def get_sun_positions(
        self,
        site: SiteConfig,
        terrain_elevation_m: float,
        time_range: TimeRangeConfig,
    ) -> Tuple[List[EphemerisSample], Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_earth_positions(
        self,
        site: SiteConfig,
        terrain_elevation_m: float,
        time_range: TimeRangeConfig,
    ) -> Tuple[List[EphemerisSample], Dict[str, Any]]:
        raise NotImplementedError

