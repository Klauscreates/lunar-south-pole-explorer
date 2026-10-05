"""NASA/JPL Horizons observer-table provider with raw-response caching."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import certifi

from science.config import SiteConfig, TimeRangeConfig, utc_iso
from science.ephemeris.base import EphemerisProvider, EphemerisSample
from science.errors import EphemerisError


HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
HORIZONS_DOC_URL = "https://ssd-api.jpl.nasa.gov/doc/horizons.html"
_SOURCE_RE = re.compile(r"Target body name:.*?\{source:\s*([^}]+)\}")
_CENTER_FRAME_RE = re.compile(r"Center pole/equ\s*:\s*([^\{\n]+)")


class HorizonsEphemerisProvider(EphemerisProvider):
    """Retrieve apparent, airless lunar-topocentric observer quantities.

    Azimuth is the Horizons convention: clockwise from local north through
    east. Elevation is relative to the plane perpendicular to the lunar
    reference-surface local zenith. The site's altitude sent to Horizons is
    the LOLA terrain elevation plus observer height, in kilometres.
    """

    def __init__(self, cache_dir: Path, timeout_seconds: float = 60.0) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds

    def get_sun_positions(
        self,
        site: SiteConfig,
        terrain_elevation_m: float,
        time_range: TimeRangeConfig,
    ) -> Tuple[List[EphemerisSample], Dict[str, Any]]:
        return self._get("10", "Sun", site, terrain_elevation_m, time_range)

    def get_earth_positions(
        self,
        site: SiteConfig,
        terrain_elevation_m: float,
        time_range: TimeRangeConfig,
    ) -> Tuple[List[EphemerisSample], Dict[str, Any]]:
        return self._get("399", "Earth", site, terrain_elevation_m, time_range)

    def _get(
        self,
        target_id: str,
        target_name: str,
        site: SiteConfig,
        terrain_elevation_m: float,
        time_range: TimeRangeConfig,
    ) -> Tuple[List[EphemerisSample], Dict[str, Any]]:
        altitude_km = (terrain_elevation_m + site.observer_height_m) / 1000.0
        params = self._build_params(
            target_id, site, altitude_km, time_range
        )
        canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / (
            f"horizons_{target_name.lower()}_{request_hash[:20]}.json"
        )
        cache_hit = cache_path.exists()

        if cache_hit:
            try:
                envelope = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EphemerisError(
                    f"Horizons cache is unreadable: {cache_path}"
                ) from exc
        else:
            envelope = self._fetch(params)
            envelope["request"] = {
                "endpoint": HORIZONS_API_URL,
                "parameters": params,
                "canonical_sha256": request_hash,
                "retrieved_utc": utc_iso(datetime.now(timezone.utc)),
            }
            temporary = cache_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8"
            )
            temporary.replace(cache_path)

        response = envelope.get("response")
        if not isinstance(response, dict):
            raise EphemerisError(f"Invalid Horizons cache envelope: {cache_path}")
        if response.get("error"):
            raise EphemerisError(f"Horizons returned an error: {response['error']}")
        raw_result = response.get("result")
        if not isinstance(raw_result, str):
            raise EphemerisError("Horizons response did not contain a text result")

        samples = parse_horizons_observer_table(raw_result)
        expected = int(
            (time_range.end_utc - time_range.start_utc).total_seconds()
            // (time_range.step_minutes * 60)
        ) + 1
        if len(samples) != expected:
            raise EphemerisError(
                f"Horizons returned {len(samples)} rows for {target_name}; "
                f"expected {expected}"
            )

        metadata: Dict[str, Any] = {
            "provider": "NASA/JPL Horizons",
            "provider_url": HORIZONS_API_URL,
            "documentation_url": HORIZONS_DOC_URL,
            "api_signature": response.get("signature", {}),
            "target_id": target_id,
            "target_name": target_name,
            "ephemeris_source": _capture(_SOURCE_RE, raw_result),
            "center_body": "Moon (301)",
            "center_frame": _capture(_CENTER_FRAME_RE, raw_result),
            "coordinate_type": "GEODETIC",
            "site_coordinates_sent": {
                "longitude_deg_east": site.longitude_deg_east,
                "latitude_deg": site.latitude_deg,
                "altitude_above_reference_sphere_km": altitude_km,
            },
            "observer_quantities": [
                "airless apparent azimuth/elevation",
                "angular diameter",
                "observer-target apparent range",
            ],
            "request_parameters": params,
            "request_sha256": request_hash,
            "raw_cache_path": str(cache_path.resolve()),
            "raw_cache_sha256": _sha256_file(cache_path),
            "cache_hit": cache_hit,
            "retrieved_utc": envelope.get("request", {}).get("retrieved_utc"),
        }
        return samples, metadata

    @staticmethod
    def _build_params(
        target_id: str,
        site: SiteConfig,
        altitude_km: float,
        time_range: TimeRangeConfig,
    ) -> Dict[str, str]:
        start = time_range.start_utc.strftime("%Y-%m-%d %H:%M:%S")
        stop = time_range.end_utc.strftime("%Y-%m-%d %H:%M:%S")
        return {
            "format": "json",
            "COMMAND": f"'{target_id}'",
            "OBJ_DATA": "'NO'",
            "MAKE_EPHEM": "'YES'",
            "EPHEM_TYPE": "'OBSERVER'",
            "CENTER": "'coord@301'",
            "COORD_TYPE": "'GEODETIC'",
            "SITE_COORD": (
                f"'{site.longitude_deg_east:.12g},"
                f"{site.latitude_deg:.12g},{altitude_km:.12g}'"
            ),
            "START_TIME": f"'{start}'",
            "STOP_TIME": f"'{stop}'",
            "STEP_SIZE": f"'{time_range.step_minutes}m'",
            "QUANTITIES": "'4,13,20'",
            "TIME_TYPE": "'UT'",
            "TIME_DIGITS": "'SECONDS'",
            "CAL_FORMAT": "'CAL'",
            "CAL_TYPE": "'GREGORIAN'",
            "ANG_FORMAT": "'DEG'",
            "APPARENT": "'AIRLESS'",
            "RANGE_UNITS": "'KM'",
            "SUPPRESS_RANGE_RATE": "'YES'",
            "ELEV_CUT": "'-90'",
            "SKIP_DAYLT": "'NO'",
            "CSV_FORMAT": "'YES'",
            "EXTRA_PREC": "'YES'",
        }

    def _fetch(self, params: Dict[str, str]) -> Dict[str, Any]:
        url = HORIZONS_API_URL + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "LunarMissionPlanner/0.1 scientific-prototype",
            },
        )
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self.timeout_seconds,
                    context=ssl.create_default_context(cafile=certifi.where()),
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return {"response": payload}
            except (
                urllib.error.URLError,
                TimeoutError,
                json.JSONDecodeError,
            ) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise EphemerisError(
            f"NASA/JPL Horizons request failed after 3 attempts: {last_error}"
        ) from last_error


def parse_horizons_observer_table(raw_result: str) -> List[EphemerisSample]:
    """Parse the exact CSV schema requested by this provider.

    The raw Horizons response is retained separately for provenance. Parsing
    fails closed when a row is malformed or a numeric field is unavailable.
    """
    start_marker = raw_result.find("$$SOE")
    end_marker = raw_result.find("$$EOE")
    if start_marker < 0 or end_marker < 0 or end_marker <= start_marker:
        raise EphemerisError("Horizons response lacks a valid $$SOE/$$EOE table")
    table = raw_result[start_marker + len("$$SOE") : end_marker].strip()
    reader = csv.reader(io.StringIO(table), skipinitialspace=True)
    samples: List[EphemerisSample] = []
    for row_number, row in enumerate(reader, start=1):
        if not row or not any(cell.strip() for cell in row):
            continue
        trimmed = [cell.strip() for cell in row]
        if len(trimmed) < 7:
            raise EphemerisError(
                f"Malformed Horizons row {row_number}: expected 7 fields, "
                f"received {len(trimmed)}"
            )
        try:
            timestamp = datetime.strptime(
                trimmed[0], "%Y-%b-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
            numeric = [float(value) for value in trimmed[3:7]]
        except (ValueError, TypeError) as exc:
            raise EphemerisError(
                f"Invalid Horizons row {row_number}: {trimmed!r}"
            ) from exc
        samples.append(
            EphemerisSample(
                timestamp=timestamp,
                azimuth_deg=numeric[0] % 360.0,
                elevation_deg=numeric[1],
                angular_diameter_arcsec=numeric[2],
                distance_km=numeric[3],
                solar_presence_code=trimmed[1],
                interfering_body_code=trimmed[2],
            )
        )
    if not samples:
        raise EphemerisError("Horizons observer table contains no data rows")
    return samples


def _capture(pattern: re.Pattern, text: str) -> Optional[str]:
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
