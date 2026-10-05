"""Opt-in spacecraft geometry and thermal analysis over verified site epochs.

This layer deliberately does not substitute an illustrative rover for a flight
vehicle or infer lunar-wall optical flux from LOLA heights. A configured run
requires checksum-pinned CAD, measured/derived hardware properties, an
attitude, and an epoch-aligned thermal-environment profile. Its output is an
engineering screening calculation, not a certified flight prediction.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import fields
from pathlib import Path
from typing import Any

from science.config import parse_utc
from science.errors import ConfigurationError
from science.power import direct_solar_irradiance_w_m2
from science.spacecraft import (
    RaycastBudget,
    evaluate_spacecraft_geometry,
    load_spacecraft_geometry,
)
from science.thermal import (
    PanelEnvironment,
    PanelThermalParameters,
    advance_panel_thermal_electrical,
    evaluate_panel_thermal_electrical,
)
from science.visibility import disk_visible_fraction


MAX_CONFIG_BYTES = 1_000_000
MAX_ENVIRONMENT_BYTES = 64_000_000
MAX_SIMULATION_BYTES = 128_000_000
MAX_RAYCAST_WORK_UNITS = 50_000_000
_THERMAL_FIELDS = {field.name for field in fields(PanelThermalParameters)}
_ENVIRONMENT_FIELDS = {
    "wall_reflected_solar_irradiance_w_m2",
    "lunar_ir_irradiance_w_m2",
    "mount_temperature_k",
    "radiation_sink_temperature_k",
}


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant {value} is prohibited")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path, limit: int) -> tuple[dict[str, Any], str]:
    try:
        if path.stat().st_size > limit:
            raise ConfigurationError(f"Input exceeds {limit} bytes: {path}")
        data = path.read_bytes()
        if len(data) > limit:
            raise ConfigurationError(f"Input exceeds {limit} bytes: {path}")
        parsed = json.loads(
            data,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ConfigurationError(f"Cannot parse input {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ConfigurationError(f"Input must be a JSON object: {path}")
    return parsed, hashlib.sha256(data).hexdigest()


def _keys(value: Any, required: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != required:
        raise ConfigurationError(f"{label} requires exactly {sorted(required)}")
    return value


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{label} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ConfigurationError(f"{label} must be a finite number") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise ConfigurationError(f"{label} must be finite{' and positive' if positive else ''}")
    return number


def _source(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ConfigurationError(f"{label} must be a nonempty source identifier")
    return value


def _pinned_path(reference: Any, root: Path, label: str) -> tuple[Path, str]:
    item = _keys(reference, {"path", "sha256"}, label)
    relative = item["path"]
    digest = item["sha256"]
    if (
        not isinstance(relative, str)
        or not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise ConfigurationError(f"{label}.path must be relative within the hardware directory")
    if not isinstance(digest, str) or len(digest) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in digest
    ):
        raise ConfigurationError(f"{label}.sha256 must be a SHA-256 digest")
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ConfigurationError(f"{label}.path escapes the hardware directory")
    return path, digest.lower()


def _verified_json_reference(
    reference: Any, root: Path, label: str, limit: int
) -> tuple[dict[str, Any], str, Path]:
    path, expected_sha = _pinned_path(reference, root, label)
    data, actual_sha = _read_json(path, limit)
    if actual_sha != expected_sha:
        raise ConfigurationError(f"{label} SHA-256 does not match hardware configuration")
    return data, actual_sha, path


def _validate_simulation(simulation: dict[str, Any]) -> list[dict[str, Any]]:
    validation = simulation.get("validation")
    contract = simulation.get("provenance_contract")
    if (
        simulation.get("schema_version") != "1.3.0"
        or not isinstance(validation, dict)
        or validation.get("overall_status") != "PASS"
        or not isinstance(validation.get("independent_spice"), dict)
        or validation["independent_spice"].get("status") != "PASS"
        or not isinstance(contract, dict)
        or contract.get("operational_ephemeris") != "NASA/JPL Horizons"
        or contract.get("validator_used_for_operational_samples") is not False
    ):
        raise ConfigurationError(
            "Input simulation lacks the required Horizons/SPICE v1.3 validation contract"
        )
    samples = simulation.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ConfigurationError("Input simulation has no epochs")
    previous_time = None
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ConfigurationError(f"Simulation epoch {index} is invalid")
        try:
            timestamp = parse_utc(sample["timestamp"])
            sun = sample["sun"]
            earth = sample["earth"]
            _finite(sun["azimuth_deg"], "Sun azimuth")
            _finite(sun["elevation_deg"], "Sun elevation")
            _finite(sun["distance_km"], "Sun distance", positive=True)
            _finite(sun["terrain_horizon_deg"], "Sun terrain skyline")
            _finite(sun["clearance_deg"], "Sun terrain clearance")
            sun_radius = _finite(sun["angular_radius_deg"], "Sun angular radius", positive=True)
            sun_fraction = _finite(sun["visibility_fraction"], "Sun disk visibility")
            baseline_flux = _finite(
                sample["power"]["direct_irradiance_w_m2"], "baseline solar flux"
            )
            _finite(earth["azimuth_deg"], "Earth azimuth")
            _finite(earth["elevation_deg"], "Earth elevation")
            _finite(earth["terrain_horizon_deg"], "Earth terrain skyline")
            _finite(earth["clearance_deg"], "Earth terrain clearance")
            earth_radius = _finite(earth["angular_radius_deg"], "Earth angular radius", positive=True)
            earth_fraction = _finite(earth["visibility_fraction"], "Earth disk visibility")
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"Simulation epoch {index} lacks valid geometry") from exc
        if not (0 <= sun_fraction <= 1 and 0 <= earth_fraction <= 1):
            raise ConfigurationError(f"Simulation epoch {index} has invalid disk visibility")
        for body_name, body, radius, fraction in (
            ("Sun", sun, sun_radius, sun_fraction),
            ("Earth", earth, earth_radius, earth_fraction),
        ):
            if not math.isclose(
                body["elevation_deg"] - body["terrain_horizon_deg"],
                body["clearance_deg"],
                rel_tol=0.0,
                abs_tol=5e-8,
            ):
                raise ConfigurationError(
                    f"Simulation epoch {index} {body_name} skyline clearance is inconsistent"
                )
            if not math.isclose(
                disk_visible_fraction(body["clearance_deg"], radius),
                fraction,
                rel_tol=0.0,
                abs_tol=2e-8,
            ):
                raise ConfigurationError(
                    f"Simulation epoch {index} {body_name} disk fraction is inconsistent"
                )
        if not math.isclose(
            baseline_flux,
            direct_solar_irradiance_w_m2(sun["distance_km"]),
            rel_tol=0.0,
            abs_tol=2e-6,
        ):
            raise ConfigurationError(
                f"Simulation epoch {index} solar flux disagrees with power.py range scaling"
            )
        if previous_time is not None and timestamp <= previous_time:
            raise ConfigurationError("Simulation timestamps must increase strictly")
        previous_time = timestamp
    return samples


def analyze_spacecraft_files(
    simulation_path: Path, hardware_path: Path, *, output_path: Path | None = None
) -> dict[str, Any]:
    """Run the configured static-pose spacecraft screening model.

    The environmental record at epoch *i* is held over [i, i+1) when
    integrating the cell temperature, matching the mission timeline's
    left-closed convention. Power at each epoch uses its current boundary.
    """
    simulation_path = Path(simulation_path).resolve(strict=True)
    hardware_path = Path(hardware_path).resolve(strict=True)
    simulation, simulation_sha = _read_json(simulation_path, MAX_SIMULATION_BYTES)
    samples = _validate_simulation(simulation)
    hardware, hardware_sha = _read_json(hardware_path, MAX_CONFIG_BYTES)
    _keys(
        hardware,
        {"schema_version", "geometry_manifest", "attitude_deg", "panels", "environment_profile"},
        "hardware configuration",
    )
    if hardware["schema_version"] != "1.0.0":
        raise ConfigurationError("Unsupported hardware configuration schema")
    root = hardware_path.parent
    geometry_data, geometry_sha, geometry_path = _verified_json_reference(
        hardware["geometry_manifest"], root, "geometry_manifest", MAX_CONFIG_BYTES
    )
    geometry = load_spacecraft_geometry(geometry_path, allowed_root=root)
    if geometry.manifest_sha256 != geometry_sha:
        raise ConfigurationError("Geometry manifest changed while loading")
    attitude = _keys(
        hardware["attitude_deg"], {"yaw", "pitch", "roll", "source"}, "attitude_deg"
    )
    yaw = _finite(attitude["yaw"], "yaw")
    pitch = _finite(attitude["pitch"], "pitch")
    roll = _finite(attitude["roll"], "roll")
    attitude_source = _source(attitude["source"], "attitude source")

    panel_config = hardware["panels"]
    panel_ids = {panel.id for panel in geometry.panels}
    if not isinstance(panel_config, dict) or not panel_ids or set(panel_config) != panel_ids:
        raise ConfigurationError("Hardware thermal panels must match every CAD panel ID")
    parameters: dict[str, PanelThermalParameters] = {}
    temperatures: dict[str, float] = {}
    for panel in geometry.panels:
        item = _keys(
            panel_config[panel.id],
            {"thermal_parameters", "initial_cell_temperature_k"},
            f"panels.{panel.id}",
        )
        params_data = _keys(
            item["thermal_parameters"], _THERMAL_FIELDS,
            f"panels.{panel.id}.thermal_parameters",
        )
        params = PanelThermalParameters(**params_data)
        params.validate()
        if not math.isclose(params.collecting_area_m2, panel.area_m2, rel_tol=1e-9, abs_tol=1e-12):
            raise ConfigurationError(f"{panel.id}: CAD active area and thermal collecting area differ")
        initial = _finite(item["initial_cell_temperature_k"], f"{panel.id} initial cell T", positive=True)
        parameters[panel.id] = params
        temperatures[panel.id] = initial

    environment, environment_sha, environment_path = _verified_json_reference(
        hardware["environment_profile"], root, "environment_profile", MAX_ENVIRONMENT_BYTES
    )
    if output_path is not None:
        output = Path(output_path).resolve()
        mesh_path = (geometry_path.parent / geometry_data["mesh"]["path"]).resolve(strict=True)
        protected_inputs = {
            simulation_path, hardware_path, geometry_path, mesh_path, environment_path
        }
        if output in protected_inputs:
            raise ConfigurationError("Analysis output must not replace any input artifact")
    _keys(environment, {"schema_version", "provenance", "samples"}, "environment profile")
    if environment["schema_version"] != "1.0.0":
        raise ConfigurationError("Unsupported thermal environment schema")
    provenance = _keys(
        environment["provenance"], {"source", "revision", "method"},
        "environment provenance",
    )
    for key, value in provenance.items():
        _source(value, f"environment provenance.{key}")
    environment_samples = environment["samples"]
    if not isinstance(environment_samples, list) or len(environment_samples) != len(samples):
        raise ConfigurationError("Thermal environment must cover every simulation epoch")

    results = []
    raycast_budget = RaycastBudget(MAX_RAYCAST_WORK_UNITS)
    previous_environments: dict[str, PanelEnvironment] = {}
    previous_time = None
    for index, (sample, boundary) in enumerate(zip(samples, environment_samples)):
        boundary = _keys(boundary, {"timestamp", "panels"}, f"environment epoch {index}")
        if boundary["timestamp"] != sample["timestamp"]:
            raise ConfigurationError(f"Thermal environment timestamp mismatch at epoch {index}")
        timestamp = parse_utc(sample["timestamp"])
        boundary_panels = boundary["panels"]
        if not isinstance(boundary_panels, dict) or set(boundary_panels) != panel_ids:
            raise ConfigurationError(f"Thermal boundary panel IDs differ at epoch {index}")

        sun = sample["sun"]
        earth = sample["earth"]
        geometry_result = evaluate_spacecraft_geometry(
            geometry,
            sun_azimuth_deg=sun["azimuth_deg"],
            sun_elevation_deg=sun["elevation_deg"],
            earth_azimuth_deg=earth["azimuth_deg"],
            earth_elevation_deg=earth["elevation_deg"],
            yaw_deg=yaw,
            pitch_deg=pitch,
            roll_deg=roll,
            include_samples=False,
            budget=raycast_budget,
        )
        geometry_panels = {panel["id"]: panel for panel in geometry_result["panels"]}
        panel_results = []
        for panel_id in sorted(panel_ids):
            flux = _keys(
                boundary_panels[panel_id], _ENVIRONMENT_FIELDS,
                f"environment epoch {index} panel {panel_id}",
            )
            geom_panel = geometry_panels[panel_id]
            panel_environment = PanelEnvironment(
                direct_normal_irradiance_w_m2=sample["power"]["direct_irradiance_w_m2"],
                terrain_visible_fraction=sun["visibility_fraction"],
                incidence_cosine=geom_panel["incidence_cosine"],
                structural_unobstructed_fraction=geom_panel["unoccluded_sample_fraction"],
                wall_reflected_solar_irradiance_w_m2=flux["wall_reflected_solar_irradiance_w_m2"],
                lunar_ir_irradiance_w_m2=flux["lunar_ir_irradiance_w_m2"],
                mount_temperature_k=flux["mount_temperature_k"],
                radiation_sink_temperature_k=flux["radiation_sink_temperature_k"],
            )
            panel_environment.validate()
            interval = None
            if previous_time is not None:
                interval = advance_panel_thermal_electrical(
                    temperatures[panel_id],
                    (timestamp - previous_time).total_seconds(),
                    parameters[panel_id],
                    previous_environments[panel_id],
                )
                temperatures[panel_id] = interval["cell_temperature_k"]
            thermal = evaluate_panel_thermal_electrical(
                temperatures[panel_id], parameters[panel_id], panel_environment
            )
            panel_results.append({
                "id": panel_id,
                "geometry": geom_panel,
                "thermal_boundary": flux,
                "thermal_electrical": thermal,
                "integration_from_previous_epoch": None if interval is None else {
                    "elapsed_s": (timestamp - previous_time).total_seconds(),
                    "integration_substeps": interval["integration_substeps"],
                    "energy_balance_residual_j": interval["energy_balance_residual_j"],
                },
            })
            previous_environments[panel_id] = panel_environment
        previous_time = timestamp
        center_terrain_clear = earth["clearance_deg"] > 0.0
        antenna_results = [
            {
                **antenna,
                "earth_center_terrain_clear": center_terrain_clear,
                "earth_center_geometric_los_clear": center_terrain_clear and antenna["self_los_clear"],
            }
            for antenna in geometry_result["antennas"]
        ]
        results.append({
            "timestamp": sample["timestamp"],
            "attitude_deg": geometry_result["attitude_deg"],
            "sun_terrain_visible_fraction": sun["visibility_fraction"],
            "earth_disk_visible_fraction": earth["visibility_fraction"],
            "panels": panel_results,
            "antennas": antenna_results,
            "total_electrical_output_w": sum(
                panel["thermal_electrical"]["electrical_output_w"] for panel in panel_results
            ),
        })

    return {
        "schema_version": "1.0.0",
        "analysis_status": "CONFIGURED_UNVALIDATED",
        "flight_certified": False,
        "input_contract_validation": "PASS",
        "source_claims_independently_verified": False,
        "parent_validation_record": {
            "reported_overall_status": "PASS",
            "reported_independent_spice_status": "PASS",
            "independently_rerun_by_this_layer": False,
            "source_authenticity_independently_verified": False,
        },
        "model_contract": {
            "geometry": "rigid_mesh_center_rays_weighted_panel_samples_v1",
            "thermal_electrical": "single_node_pv_thermal_v1",
            "wall_reflection": "externally_supplied_panel_plane_flux",
            "attitude": "static_body_to_enu_for_all_epochs",
            "time_integration": "left_closed_environment_boundary",
        },
        "scope": (
            "Finite-sample rigid-mesh Sun/Earth-center rays and one-node panel thermal-electrical "
            "screening at a fixed site; no RF link budget, articulations, terrain wall-flux "
            "solver, detailed EPS, thermal-vac correlation, or flight certification"
        ),
        "model_id": geometry.model_id,
        "site": simulation.get("site"),
        "input_sha256": {
            "simulation": simulation_sha,
            "hardware_configuration": hardware_sha,
            "geometry_manifest": geometry.manifest_sha256,
            "mesh": geometry.mesh_sha256,
            "thermal_environment": environment_sha,
        },
        "source_provenance": {
            "geometry": dict(geometry.provenance),
            "attitude": attitude_source,
            "thermal_environment": provenance,
            "parent_declared_operational_ephemeris": simulation["provenance_contract"]["operational_ephemeris"],
            "parent_declared_independent_ephemeris_validator": "local NAIF SPICE",
        },
        "sample_count": len(results),
        "raycast_work_units": {
            "used": raycast_budget.used_work_units,
            "limit": raycast_budget.max_work_units,
            "unit": "BVH node visit or triangle intersection test",
        },
        "samples": results,
    }
