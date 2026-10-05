"""Recompute the indexed sites offline with pinned NAIF kernels; preserve UI exports."""
import hashlib
import json
from pathlib import Path

from science.config import SiteConfig, TimeRangeConfig, parse_utc, utc_iso
from science.ephemeris.spice import SpiceEphemerisProvider
from science.export import write_json


def run(workspace: Path) -> dict:
    outputs = (workspace / "outputs").resolve()
    index_bytes = (outputs / "simulation-index.json").read_bytes()
    index = json.loads(index_bytes)
    provider = SpiceEphemerisProvider(workspace / "data/kernels", auto_download=False)
    results = []
    for entry in index["sites"]:
        if not entry["data_url"].startswith("/data/"):
            raise ValueError("Unexpected site URL")
        directory = outputs if entry["id"] == "test-site-a" else outputs / "candidates"
        source = (directory / entry["data_url"].removeprefix("/data/")).resolve()
        if not source.is_relative_to(outputs):
            raise ValueError("Site export escapes output directory")
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Parent simulation checksum mismatch")
        simulation = json.loads(raw)
        s, t = simulation["site"], simulation["time_range"]
        site = SiteConfig(s["name"], s["latitude_deg"], s["longitude_deg_east"], s["observer_height_m"])
        interval = TimeRangeConfig(parse_utc(t["start_utc"]), parse_utc(t["end_utc"]), t["step_minutes"])
        bodies = {}
        for body in ("sun", "earth"):
            samples, metadata = getattr(provider, f"get_{body}_positions")(site, s["terrain_elevation_m"], interval)
            if len(samples) != len(simulation["samples"]):
                raise ValueError("Epoch count mismatch")
            errors = []
            for computed, reference in zip(samples, simulation["samples"], strict=True):
                if utc_iso(computed.timestamp) != reference["timestamp"]:
                    raise ValueError("Epoch alignment mismatch")
                ref = reference[body]
                errors.append(max(abs((computed.azimuth_deg - ref["azimuth_deg"] + 180) % 360 - 180),
                    abs(computed.elevation_deg - ref["elevation_deg"])) * 3600)
            maximum = max(errors)
            if maximum > 1.0:
                raise ValueError(f"{entry['id']} {body}: exceeds 1 arcsecond comparison gate")
            bodies[body] = {"maximum_coordinate_difference_arcsec": maximum, "metadata": metadata}
        results.append({"site_id": entry["id"], "parent_sha256": entry["sha256"], "bodies": bodies})
    return {"schema_version": "1.0.0", "status": "PASS", "flight_ready": False,
        "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
        "scope": "Kernel integrity, coverage, time round trips and existing Horizons coordinate comparison; not independent physical truth or flight certification",
        "sites": results}


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    report = run(root)
    destination = root / "outputs/spice-integrity-audit.json"
    write_json(report, destination)
    print(f"PASS: {len(report['sites'])} sites; flight_ready=false; {destination}")
