#!/usr/bin/env python3
"""Precompute and publish the NASA-reference-point simulation array.

No entry is published as validated unless the live/cached NASA/JPL Horizons
table, local SPICE cross-check, and two-scale LOLA horizon all pass. Existing
science files are never fabricated to fill gaps. The compact index points to
complete, retained 1,009-epoch results and hashes the served JSON bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence

from science.candidates import EVALUATED_SITES, EvaluatedSite
from science.comms import classify_comms_potential
from science.config import SimulationConfig, SiteConfig, utc_iso
from science.errors import SciencePipelineError
from science.export import write_csv, write_json
from science.simulation import run_simulation


WORKSPACE = Path(__file__).resolve().parent
SCHEMA_VERSION = "1.3.0"


def paths_for(site: EvaluatedSite) -> tuple[Path, Path, str]:
    if site.id == "test-site-a":
        return (
            WORKSPACE / "outputs" / "simulation.json",
            WORKSPACE / "outputs" / "simulation.csv",
            "simulation.json",
        )
    return (
        WORKSPACE / "outputs" / "candidates" / f"{site.id}.json",
        WORKSPACE / "outputs" / "candidates" / f"{site.id}.csv",
        f"{site.id}.json",
    )


def validate_result(result: Dict[str, Any], site: EvaluatedSite) -> None:
    """Fail closed on stale, mislabeled, incomplete, or unvalidated exports."""
    if result.get("schema_version") != SCHEMA_VERSION:
        raise SciencePipelineError(f"{site.id}: stale simulation schema")
    actual = result.get("site", {})
    if (
        actual.get("name") != site.name
        or actual.get("latitude_deg") != site.latitude_deg
        or actual.get("longitude_deg_east") != site.longitude_deg_east
    ):
        raise SciencePipelineError(f"{site.id}: site coordinates/name mismatch")
    samples = result.get("samples", [])
    if len(samples) != 1009 or result.get("time_range", {}).get("sample_count") != 1009:
        raise SciencePipelineError(f"{site.id}: incomplete epoch matrix")
    if len(result.get("horizon", {}).get("profile", [])) != 720:
        raise SciencePipelineError(f"{site.id}: incomplete 0.5-degree horizon")
    mask = result.get("horizon_mask", {}).get("profile", [])
    if len(mask) != 360 or any(
        entry.get("azimuth_deg") != azimuth
        for azimuth, entry in enumerate(mask)
    ):
        raise SciencePipelineError(f"{site.id}: incomplete 1-degree horizon mask")
    validation = result.get("validation", {})
    if (
        validation.get("overall_status") != "PASS"
        or validation.get("independent_spice", {}).get("status") != "PASS"
    ):
        raise SciencePipelineError(f"{site.id}: science validation did not pass")
    if result.get("provenance_contract", {}).get("validator_used_for_operational_samples") is not False:
        raise SciencePipelineError(f"{site.id}: invalid Horizons/SPICE provenance")
    if result.get("provenance_contract", {}).get("operational_ephemeris") != "NASA/JPL Horizons":
        raise SciencePipelineError(f"{site.id}: unrecognized operational ephemeris")
    if result.get("data_sources", {}).get("spice_validation", {}).get("role") != "independent_validator_only":
        raise SciencePipelineError(f"{site.id}: unrecognized SPICE validator role")
    expected_scenarios = {
        "ideal_tracking", "fixed_vertical_north", "fixed_tilt_80_north", "limited_gimbal"
    }
    if set(result.get("panel_scenarios", {})) != expected_scenarios or any(
        set(sample.get("power_scenarios", {})) != expected_scenarios
        for sample in samples
    ):
        raise SciencePipelineError(f"{site.id}: incomplete panel scenario matrix")
    try:
        comms_consistent = all(
            sample.get("comms_potential") == classify_comms_potential(sample["earth"])
            for sample in samples
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SciencePipelineError(f"{site.id}: invalid communications matrix") from exc
    if not comms_consistent:
        raise SciencePipelineError(f"{site.id}: inconsistent communications matrix")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)


def run_array(selected_ids: set[str] | None = None) -> Dict[str, Any]:
    web_data = WORKSPACE / "apps" / "web" / "public" / "data"
    web_data.mkdir(parents=True, exist_ok=True)
    results: Dict[str, Dict[str, Any]] = {}
    for site in EVALUATED_SITES:
        if selected_ids is not None and site.id not in selected_ids:
            continue
        print(f"\n[{site.id}] NASA/LOLA + Horizons + local SPICE", flush=True)
        config = SimulationConfig(
            site=SiteConfig(
                name=site.name,
                latitude_deg=site.latitude_deg,
                longitude_deg_east=site.longitude_deg_east,
            )
        )
        result = run_simulation(
            config, WORKSPACE,
            progress=lambda message: print(f"[{site.id}] {message}", flush=True),
        )
        validate_result(result, site)
        json_path, csv_path, _ = paths_for(site)
        write_json(result, json_path)
        write_csv(result, csv_path)
        results[site.id] = result

    # Verify *every* site before writing an index. A partial run can resume
    # later, but never advertises a missing or stale site as available.
    entries = []
    for site in EVALUATED_SITES:
        json_path, csv_path, web_name = paths_for(site)
        if not json_path.is_file() or not csv_path.is_file():
            raise SciencePipelineError(f"{site.id}: export is missing")
        result = results.get(site.id)
        if result is None:
            result = json.loads(json_path.read_text(encoding="utf-8"))
        validate_result(result, site)
        served_path = web_data / web_name
        _copy_atomic(json_path, served_path)
        if site.id == "test-site-a":
            _copy_atomic(csv_path, web_data / "simulation.csv")
        entries.append({
            "id": site.id,
            "name": site.name,
            "latitude_deg": site.latitude_deg,
            "longitude_deg_east": site.longitude_deg_east,
            "kind": site.kind,
            "region_status": site.region_status,
            "coordinate_source_url": site.coordinate_source_url,
            "data_url": f"/data/{web_name}",
            "sha256": _sha256(served_path),
            "summary": {
                "sunlight_percentage": result["windows"]["solar"]["illumination_percentage"],
                "earth_visible_percentage": result["windows"]["earth"]["earth_visible_percentage"],
            },
        })
    first = results.get("test-site-a")
    if first is None:
        first = json.loads(paths_for(EVALUATED_SITES[0])[0].read_text(encoding="utf-8"))
    index = {
        "schema_version": "1.0.0",
        "generated_utc": utc_iso(datetime.now(timezone.utc)),
        "time_range": first["time_range"],
        "coordinate_note": (
            "NASA Data Book points are centers of original DEM polygons, not "
            "certified touchdown sites. Connecting Ridge is a historical 2022 "
            "candidate; the other three are in NASA's 2024 nine-region cohort."
        ),
        "sites": entries,
    }
    write_json(index, WORKSPACE / "outputs" / "simulation-index.json")
    _copy_atomic(WORKSPACE / "outputs" / "simulation-index.json", web_data / "simulation-index.json")
    return index


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site", action="append", choices=[site.id for site in EVALUATED_SITES],
        help="Run only this site (repeatable); publish index only when all five validated exports exist",
    )
    args = parser.parse_args(argv)
    try:
        index = run_array(set(args.site) if args.site else None)
    except (SciencePipelineError, OSError, ValueError) as exc:
        print(f"Candidate array failed closed: {exc}", file=sys.stderr)
        return 2
    print(f"Published {len(index['sites'])} validated site series.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
