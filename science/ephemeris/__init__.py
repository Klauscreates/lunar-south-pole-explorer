"""Ephemeris provider implementations."""

from typing import TYPE_CHECKING, Any

from science.ephemeris.base import EphemerisProvider, EphemerisSample
from science.ephemeris.horizons import HorizonsEphemerisProvider

if TYPE_CHECKING:
    from science.ephemeris.spice import SpiceEphemerisProvider

__all__ = [
    "EphemerisProvider",
    "EphemerisSample",
    "HorizonsEphemerisProvider",
    "SpiceEphemerisProvider",
]


def __getattr__(name: str) -> Any:
    """Load the optional native SPICE binding only when it is requested."""
    if name == "SpiceEphemerisProvider":
        from science.ephemeris.spice import SpiceEphemerisProvider

        return SpiceEphemerisProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
