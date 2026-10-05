#!/usr/bin/env python3
"""Command-line entry point for the lunar south-pole mission planner."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Sequence

from science.config import (
    PanelConfig,
    SimulationConfig,
    SiteConfig,
    TerrainConfig,
    TimeRangeConfig,
    parse_utc,
    tuple3,
)
from science.errors import SciencePipelineError
from science.export import write_csv, write_json
from science.simulation import run_simulation


WORKSPACE = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a traceable lunar-surface Sun/Earth/terrain visibility and "
            "solar-input simulation. Remote source failures are fatal; no "
            "synthetic fallback data are generated."
        )
    )
    parser.add_argument("--name", default="Test Site A")
    parser.add_argument("--lat", type=float, default=-89.9)
    parser.add_argument("--lon", type=float, default=0.0, help="East longitude")
    parser.add_argument("--observer-height-m", type=float, default=2.0)
    parser.add_argument("--start", default="2026-10-01T00:00:00Z")
    parser.add_argument("--end", default="2026-10-08T00:00:00Z")
    parser.add_argument("--step-minutes", type=int, default=10)
    parser.add_argument(
        "--terrain-source",
        default=TerrainConfig().source,
        help="NASA PGDA local-detail COG URL or compatible local GeoTIFF",
    )
    parser.add_argument(
        "--outer-terrain-source",
        default=TerrainConfig().outer_source,
        help="NASA PGDA wide-area COG URL or compatible local GeoTIFF",
    )
    parser.add_argument("--local-terrain-radius-km", type=float, default=10.0)
    parser.add_argument("--terrain-radius-km", type=float, default=200.0)
    parser.add_argument("--azimuth-step-deg", type=float, default=0.5)
    parser.add_argument("--radial-step-m", type=float, default=10.0)
    parser.add_argument("--outer-radial-step-m", type=float, default=240.0)
    parser.add_argument("--panel-area-m2", type=float, default=1.0)
    parser.add_argument("--panel-efficiency", type=float, default=0.30)
    parser.add_argument(
        "--panel-mode",
        choices=[
            "sun_tracking",
            "horizontal_fixed",
            "custom_normal",
            "fixed_tilt",
            "gimbal_limited",
        ],
        default="sun_tracking",
    )
    parser.add_argument(
        "--panel-normal-enu",
        type=float,
        nargs=3,
        metavar=("E", "N", "U"),
        default=(0.0, 0.0, 1.0),
    )
    parser.add_argument(
        "--panel-tilt-deg",
        type=float,
        default=0.0,
        help="Fixed panel tilt from horizontal; 90 degrees is vertical",
    )
    parser.add_argument(
        "--panel-azimuth-deg",
        type=float,
        default=0.0,
        help="Fixed panel outward-normal azimuth, clockwise from north",
    )
    parser.add_argument("--gimbal-tilt-min-deg", type=float, default=0.0)
    parser.add_argument("--gimbal-tilt-max-deg", type=float, default=90.0)
    parser.add_argument("--gimbal-azimuth-center-deg", type=float, default=0.0)
    parser.add_argument("--gimbal-azimuth-half-range-deg", type=float, default=180.0)
    parser.add_argument(
        "--output-json", default=str(WORKSPACE / "outputs" / "simulation.json")
    )
    parser.add_argument(
        "--output-csv", default=str(WORKSPACE / "outputs" / "simulation.csv")
    )
    parser.add_argument(
        "--publish-web-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Copy exports into apps/web/public/data for the local UI",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> SimulationConfig:
    return SimulationConfig(
        site=SiteConfig(
            name=args.name,
            latitude_deg=args.lat,
            longitude_deg_east=args.lon,
            observer_height_m=args.observer_height_m,
        ),
        time_range=TimeRangeConfig(
            start_utc=parse_utc(args.start),
            end_utc=parse_utc(args.end),
            step_minutes=args.step_minutes,
        ),
        terrain=TerrainConfig(
            source=args.terrain_source,
            outer_source=args.outer_terrain_source,
            local_radius_m=args.local_terrain_radius_km * 1000.0,
            search_radius_m=args.terrain_radius_km * 1000.0,
            azimuth_step_deg=args.azimuth_step_deg,
            radial_step_m=args.radial_step_m,
            outer_radial_step_m=args.outer_radial_step_m,
        ),
        panel=PanelConfig(
            panel_area_m2=args.panel_area_m2,
            efficiency=args.panel_efficiency,
            orientation_mode=args.panel_mode,
            custom_normal_enu=tuple3(args.panel_normal_enu),
            tilt_deg_from_horizontal=args.panel_tilt_deg,
            azimuth_deg=args.panel_azimuth_deg,
            tracking_tilt_min_deg=args.gimbal_tilt_min_deg,
            tracking_tilt_max_deg=args.gimbal_tilt_max_deg,
            tracking_azimuth_center_deg=args.gimbal_azimuth_center_deg,
            tracking_azimuth_half_range_deg=args.gimbal_azimuth_half_range_deg,
        ),
    )


def main(argv: Sequence[str] = None) -> int:  # type: ignore[assignment]
    args = build_parser().parse_args(argv)
    config = config_from_args(args)
    print("LUNAR SOUTH POLE MISSION PLANNER")
    print("No synthetic fallback data are permitted.\n")
    try:
        result = run_simulation(
            config,
            WORKSPACE,
            progress=lambda message: print(f"[science] {message}"),
        )
        json_path = Path(args.output_json).resolve()
        csv_path = Path(args.output_csv).resolve()
        write_json(result, json_path)
        write_csv(result, csv_path)
        if args.publish_web_data:
            web_data = WORKSPACE / "apps" / "web" / "public" / "data"
            web_data.mkdir(parents=True, exist_ok=True)
            shutil.copy2(json_path, web_data / "simulation.json")
            shutil.copy2(csv_path, web_data / "simulation.csv")
        _print_first_result(result)
        print(f"\nJSON: {json_path}")
        print(f"CSV:  {csv_path}")
        return 0
    except (SciencePipelineError, ValueError, OSError) as exc:
        print(f"\nSCIENCE PIPELINE FAILED: {exc}", file=sys.stderr)
        return 2


def _print_first_result(result: Dict[str, Any]) -> None:
    site = result["site"]
    sample = result["samples"][0]
    sun = sample["sun"]
    earth = sample["earth"]
    power = sample["power"]
    print("\nFIRST VERIFIED SAMPLE")
    print(f"UTC: {sample['timestamp']}")
    print("\nSITE")
    print(f"Latitude:          {site['latitude_deg']:.6f} deg")
    print(f"Longitude:         {site['longitude_deg_east']:.6f} deg E")
    print(f"Terrain elevation: {site['terrain_elevation_m']:.3f} m")
    print(f"Observer height:   {site['observer_height_m']:.3f} m AGL")
    for name, body in (("SUN", sun), ("EARTH", earth)):
        print(f"\n{name}")
        print(f"Azimuth:           {body['azimuth_deg']:.9f} deg")
        print(f"Elevation:         {body['elevation_deg']:.9f} deg")
        print(f"Terrain horizon:   {body['terrain_horizon_deg']:.9f} deg")
        print(f"Center clearance:  {body['clearance_deg']:+.9f} deg")
        print(f"Visible fraction:  {100.0 * body['visibility_fraction']:.3f}%")
        print(f"Visibility:        {body['state']}")
    print("\nPOWER")
    print(
        "Geometric sunlight: "
        f"{power['geometric_sunlight_available']}"
    )
    print(
        "Estimated electrical output: "
        f"{power['estimated_electrical_output_w']:.3f} W"
    )
    print("\nCOMMUNICATION")
    print(f"Geometric DTE:     {sample['geometric_dte_available']}")
    print(f"Earth clearance:  {earth['clearance_deg']:+.9f} deg")
    print("\nVALIDATION")
    independent = result["validation"]["independent_spice"]
    sun_error = independent["targets"]["sun"]["angular_separation_arcsec"]
    earth_error = independent["targets"]["earth"]["angular_separation_arcsec"]
    print("Operational source: NASA/JPL Horizons observer tables")
    print("Independent validator: local NASA/JPL NAIF SPICE")
    print(f"SPICE status: {independent['status']}")
    print(f"Sun max sky-vector error:   {sun_error['maximum']:.9f} arcsec")
    print(f"Earth max sky-vector error: {earth_error['maximum']:.9f} arcsec")
    print(f"Status: {result['validation']['overall_status']}")


if __name__ == "__main__":
    raise SystemExit(main())
