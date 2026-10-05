"""Source-pinned cell reference and audit; never silently promote to panel data."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


def load_component_spec(path: Path) -> dict:
    spec = json.loads(path.read_text())
    if spec.get("schema_version") != "1.0.0" or spec.get("automatic_promotion_to_active_model") is not False:
        raise ValueError("Unsupported or automatically promoted component specification")
    source = (path.parent / spec["source"]["path"]).resolve()
    if not source.is_relative_to(path.parent.resolve()):
        raise ValueError("Source must remain inside the specification directory")
    if hashlib.sha256(source.read_bytes()).hexdigest() != spec["source"]["sha256"]:
        raise ValueError("Component source checksum mismatch")
    for item in spec["cell_properties"].values():
        if isinstance(item["value"], bool) or not isinstance(item["value"], (int, float)) or not math.isfinite(item["value"]):
            raise ValueError("Invalid component property")
        if not item.get("basis") or item.get("page") not in (1, 2) or not item.get("unit"):
            raise ValueError("Missing property provenance")
    return spec


def cell_reference_at_temperature(spec: dict, temperature_k: float) -> dict:
    """BOL AM0 reference only, using normalized Vmp and Jmp temperature slopes.

    Normalization preserves the separately reported efficiency. Rounded table
    Vmp*Jmp does not exactly equal eta*irradiance; neither is silently corrected.
    No low-light, spectral, radiation-aging or assembly predictions are made.
    """
    low, high = spec["coefficient_temperature_range_k"]
    if isinstance(temperature_k, bool) or not isinstance(temperature_k, (int, float)) or not math.isfinite(temperature_k):
        raise ValueError("Temperature must be finite")
    if not low <= temperature_k <= high:
        raise ValueError("Temperature outside manufacturer coefficient range; extrapolation refused")
    p = {name: item["value"] for name, item in spec["cell_properties"].items()}
    delta = temperature_k - p["reference_temperature_k"]
    vratio = 1 + p["dvmp_dt_v_k"] * delta / p["vmp_v"]
    jratio = 1 + p["djmp_dt_a_m2_k"] * delta / p["jmp_a_m2"]
    eta = p["reference_efficiency"] * vratio * jratio
    return {
        "status": "CELL_REFERENCE_ONLY_UNCERTAINTY_UNSPECIFIED",
        "temperature_k": temperature_k,
        "reference_am0_efficiency": eta,
        "reference_am0_power_density_w_m2": eta * p["reference_irradiance_w_m2"],
        "relative_efficiency_slope_at_reference_per_k": p["dvmp_dt_v_k"] / p["vmp_v"] + p["djmp_dt_a_m2_k"] / p["jmp_a_m2"],
        "rounded_table_power_density_w_m2": p["vmp_v"] * p["jmp_a_m2"],
        "uncertainty": None,
        "assembly_validated": False,
    }


def audit_design(design: dict, spec: dict) -> dict:
    """Account for every active thermal/boundary input without changing it."""
    evidence = spec["cell_properties"]
    records = []
    for name, value in design["thermal_parameters"].items():
        records.append({
            "input": f"thermal_parameters.{name}", "active_value": value,
            "status": "DEFINED_GEOMETRY" if name == "collecting_area_m2" else "ASSUMED_ASSEMBLY_INPUT",
            "source": "design.json", "valid_range": None, "uncertainty": None,
            "candidate_cell_evidence": evidence.get(name),
            "promoted": False,
        })
    records.append({"input": "initial_cell_temperature_k", "active_value": design["initial_cell_temperature_k"],
                    "status": "ASSUMED_INITIAL_STATE", "source": "design.json", "valid_range": None, "uncertainty": None, "promoted": False})
    for boundary in design["boundary_cases"]:
        for name, value in boundary.items():
            if name not in {"id", "label"}:
                records.append({"input": f"boundary_cases.{boundary['id']}.{name}", "active_value": value,
                                "status": "ASSUMED_BOUNDARY", "source": "design.json", "valid_range": None,
                                "uncertainty": None, "promoted": False})
    return {"status": "NOT_READY_FOR_MEASURED_ASSEMBLY_PREDICTIONS", "flight_certified": False,
            "inputs": records, "assembly_requirements": spec["assembly_requirements"],
            "environment_requirements": spec["environment_requirements"]}
