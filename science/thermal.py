"""Opt-in, single-node photovoltaic thermal/electrical model.

This module does not estimate lunar wall albedo, IR backload, spacecraft
temperatures, or hardware properties. Callers must supply those measured or
independently modeled quantities, with provenance outside this module. Wall
reflected solar and lunar IR irradiances are already incident on the panel
face, including their own view factors and any relevant spacecraft blockage;
the direct-beam visibility/pointing/occlusion factors are *not* applied to
them again. The effective radiation sink must exclude lunar IR represented
by ``lunar_ir_irradiance_w_m2`` to avoid double counting.

The single lumped cell node obeys

    C dT/dt = alpha_s (P_direct + P_reflected) - P_electrical
              + epsilon_ir A_cell F_lunar_ir
              - epsilon_ir sigma A_radiating (T**4 - T_sink**4)
              + G_mount (T_mount - T).

Both direct and reflected solar input use the same reference PV conversion
efficiency. This two-band approximation is not a spectral response, detailed
thermal network, electronics, battery, or flight-certification model. The
energy-flow terms follow NASA's spacecraft thermal-balance description:
https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Any, Dict


STEFAN_BOLTZMANN_W_M2_K4 = 5.670374419e-8
_MAX_MODEL_TEMPERATURE_K = 10_000.0
_MAX_INTEGRATION_STEP_S = 300.0
_MAX_INTEGRATION_SUBSTEPS = 10_000
_TEMPERATURE_SOLVE_ITERATIONS = 128


def _finite_number(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _finite_result(name: str, value: float) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} exceeds the finite range of this model")
    return value


def _temperature(name: str, value: float) -> float:
    number = _finite_number(name, value)
    if not 0.0 < number <= _MAX_MODEL_TEMPERATURE_K:
        raise ValueError(
            f"{name} must be within (0, {_MAX_MODEL_TEMPERATURE_K:g}] K"
        )
    return number


@dataclass(frozen=True)
class PanelThermalParameters:
    """Required, hardware-specific parameters for one thermally lumped panel.

    ``efficiency_temperature_coefficient_per_k`` is the *relative* linear
    coefficient around ``reference_temperature_k`` (normally negative).
    Efficiency is clamped to [0, solar_absorptivity] outside its linear
    operating region so the panel cannot export more electrical energy than
    it absorbs in the modeled solar band. This clamp is a numerical safety
    bound, not a claim about degraded hardware survivability.
    """

    collecting_area_m2: float
    radiating_area_m2: float
    heat_capacity_j_k: float
    solar_absorptivity: float
    ir_emissivity: float
    reference_efficiency: float
    reference_temperature_k: float
    efficiency_temperature_coefficient_per_k: float
    mount_conductance_w_k: float

    def validate(self) -> None:
        positive = (
            "collecting_area_m2",
            "radiating_area_m2",
            "heat_capacity_j_k",
        )
        for name in positive:
            if _finite_number(name, getattr(self, name)) <= 0.0:
                raise ValueError(f"{name} must be positive")
        alpha = _finite_number("solar_absorptivity", self.solar_absorptivity)
        epsilon = _finite_number("ir_emissivity", self.ir_emissivity)
        if not 0.0 < alpha <= 1.0:
            raise ValueError("solar_absorptivity must be within (0, 1]")
        if not 0.0 < epsilon <= 1.0:
            raise ValueError("ir_emissivity must be within (0, 1]")
        efficiency = _finite_number("reference_efficiency", self.reference_efficiency)
        if not 0.0 <= efficiency <= alpha:
            raise ValueError(
                "reference_efficiency must be within [0, solar_absorptivity]"
            )
        _temperature("reference_temperature_k", self.reference_temperature_k)
        coefficient = _finite_number(
            "efficiency_temperature_coefficient_per_k",
            self.efficiency_temperature_coefficient_per_k,
        )
        if not -1.0 <= coefficient <= 0.0:
            raise ValueError(
                "efficiency_temperature_coefficient_per_k must be "
                "within [-1, 0]"
            )
        if _finite_number(
            "mount_conductance_w_k", self.mount_conductance_w_k
        ) < 0.0:
            raise ValueError("mount_conductance_w_k must be nonnegative")


@dataclass(frozen=True)
class PanelEnvironment:
    """Resolved fluxes and thermal boundary conditions for one time interval.

    The direct-beam factors multiply ``direct_normal_irradiance_w_m2``.
    ``wall_reflected_solar_irradiance_w_m2`` and
    ``lunar_ir_irradiance_w_m2`` must be independently provided *panel-plane*
    incident fluxes, not guessed from a global albedo scalar. The radiation
    sink represents other effective background views and must not include
    the same lunar IR backload a second time. All fields are mandatory.
    """

    direct_normal_irradiance_w_m2: float
    terrain_visible_fraction: float
    incidence_cosine: float
    structural_unobstructed_fraction: float
    wall_reflected_solar_irradiance_w_m2: float
    lunar_ir_irradiance_w_m2: float
    mount_temperature_k: float
    radiation_sink_temperature_k: float

    def validate(self) -> None:
        for name in (
            "direct_normal_irradiance_w_m2",
            "wall_reflected_solar_irradiance_w_m2",
            "lunar_ir_irradiance_w_m2",
        ):
            if _finite_number(name, getattr(self, name)) < 0.0:
                raise ValueError(f"{name} must be nonnegative")
        for name in (
            "terrain_visible_fraction",
            "incidence_cosine",
            "structural_unobstructed_fraction",
        ):
            value = _finite_number(name, getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1]")
        _temperature("mount_temperature_k", self.mount_temperature_k)
        _temperature("radiation_sink_temperature_k", self.radiation_sink_temperature_k)


def _efficiency(temperature_k: float, parameters: PanelThermalParameters) -> float:
    linear = parameters.reference_efficiency * (
        1.0
        + parameters.efficiency_temperature_coefficient_per_k
        * (temperature_k - parameters.reference_temperature_k)
    )
    return min(parameters.solar_absorptivity, max(0.0, linear))


def _evaluate_validated(
    temperature_k: float,
    parameters: PanelThermalParameters,
    environment: PanelEnvironment,
) -> Dict[str, Any]:
    area = parameters.collecting_area_m2
    direct = _finite_result(
        "direct_solar_incident_power_w",
        environment.direct_normal_irradiance_w_m2
        * environment.terrain_visible_fraction
        * environment.incidence_cosine
        * environment.structural_unobstructed_fraction
        * area,
    )
    reflected = _finite_result(
        "wall_reflected_incident_power_w",
        environment.wall_reflected_solar_irradiance_w_m2 * area,
    )
    solar = _finite_result("solar_incident_power_w", direct + reflected)
    efficiency = _efficiency(temperature_k, parameters)
    direct_electrical = _finite_result(
        "direct_solar_electrical_power_w", direct * efficiency
    )
    reflected_electrical = _finite_result(
        "wall_reflected_electrical_power_w", reflected * efficiency
    )
    electrical = _finite_result(
        "electrical_output_w", direct_electrical + reflected_electrical
    )
    absorbed_solar = _finite_result(
        "absorbed_solar_power_w", parameters.solar_absorptivity * solar
    )
    solar_heat = _finite_result(
        "solar_heat_power_w", absorbed_solar - electrical
    )
    absorbed_ir = _finite_result(
        "absorbed_lunar_ir_power_w",
        parameters.ir_emissivity * environment.lunar_ir_irradiance_w_m2 * area,
    )
    radiative_loss = _finite_result(
        "radiative_loss_power_w",
        parameters.ir_emissivity
        * STEFAN_BOLTZMANN_W_M2_K4
        * parameters.radiating_area_m2
        * (temperature_k**4 - environment.radiation_sink_temperature_k**4),
    )
    conductive_exchange = _finite_result(
        "conductive_exchange_power_w",
        parameters.mount_conductance_w_k
        * (environment.mount_temperature_k - temperature_k),
    )
    net = _finite_result(
        "net_thermal_power_w",
        solar_heat + absorbed_ir - radiative_loss + conductive_exchange,
    )
    return {
        "model": "single_node_pv_thermal_v1",
        "cell_temperature_k": temperature_k,
        "temperature_derated_efficiency": efficiency,
        "direct_solar_incident_power_w": direct,
        "wall_reflected_incident_power_w": reflected,
        "solar_incident_power_w": solar,
        "absorbed_solar_power_w": absorbed_solar,
        "direct_solar_electrical_power_w": direct_electrical,
        "wall_reflected_electrical_power_w": reflected_electrical,
        "electrical_output_w": electrical,
        "solar_heat_power_w": solar_heat,
        "absorbed_lunar_ir_power_w": absorbed_ir,
        "radiative_loss_power_w": radiative_loss,
        "conductive_exchange_power_w": conductive_exchange,
        "net_thermal_power_w": net,
    }


def evaluate_panel_thermal_electrical(
    temperature_k: float,
    parameters: PanelThermalParameters,
    environment: PanelEnvironment,
) -> Dict[str, Any]:
    """Evaluate instantaneous electrical output and thermal flows at a cell T."""
    parameters.validate()
    environment.validate()
    temperature = _temperature("temperature_k", temperature_k)
    return _evaluate_validated(temperature, parameters, environment)


def _solve_backward_euler_step(
    previous_temperature_k: float,
    step_s: float,
    parameters: PanelThermalParameters,
    environment: PanelEnvironment,
) -> tuple[float, Dict[str, Any]]:
    capacity = parameters.heat_capacity_j_k

    def residual(temperature_k: float) -> float:
        flows = _evaluate_validated(temperature_k, parameters, environment)
        return _finite_result(
            "thermal_energy_residual_j",
            capacity * (temperature_k - previous_temperature_k)
            - step_s * flows["net_thermal_power_w"],
        )

    lower = 0.0  # Mathematical bracket only; a returned cell T must remain >0 K.
    upper = _MAX_MODEL_TEMPERATURE_K
    if residual(lower) >= 0.0 or residual(upper) <= 0.0:
        raise ValueError(
            "Thermal state has no positive solution within the supported "
            f"(0, {_MAX_MODEL_TEMPERATURE_K:g}] K model range"
        )
    # With the adaptive feedback limit below, the backward-Euler residual is
    # strictly increasing, so bisection yields the unique continuous root.
    # Iterate to adjacent representable floats, not a loose relative-T width:
    # near thermal equilibrium, a 1e-10 K temperature error multiplied by a
    # large heat capacity can appear as a false energy-closure failure.
    for _ in range(_TEMPERATURE_SOLVE_ITERATIONS):
        middle = (lower + upper) / 2.0
        if middle <= lower or middle >= upper:
            break
        if residual(middle) > 0.0:
            upper = middle
        else:
            lower = middle
    # Pick the representable endpoint with the smaller energy residual. The
    # arithmetic mean can round to either side without evaluating its closure.
    temperature = min((lower, upper), key=lambda candidate: abs(residual(candidate)))
    if temperature <= 0.0:
        raise ValueError("Thermal solver reached a nonphysical cell temperature")
    return temperature, _evaluate_validated(temperature, parameters, environment)


def advance_panel_thermal_electrical(
    previous_temperature_k: float,
    dt_s: float,
    parameters: PanelThermalParameters,
    environment: PanelEnvironment,
) -> Dict[str, Any]:
    """Advance one panel across an interval with constant boundary inputs.

    The caller supplies the actual elapsed UTC seconds and a boundary state
    valid for this interval. Inputs are held piecewise constant within it.
    Backward Euler is used in bounded substeps. The substep limit also keeps
    the PV-efficiency positive thermal feedback below half the cell heat
    capacity per step, ensuring a unique bracketed implicit solution. The
    resulting energy-closure residual is reported, not silently discarded.
    """
    parameters.validate()
    environment.validate()
    previous = _temperature("previous_temperature_k", previous_temperature_k)
    interval = _finite_number("dt_s", dt_s)
    if interval < 0.0:
        raise ValueError("dt_s must be nonnegative")
    if interval > _MAX_INTEGRATION_STEP_S * _MAX_INTEGRATION_SUBSTEPS:
        raise ValueError(
            "dt_s exceeds the supported interval; provide shorter UTC intervals"
        )
    if interval == 0.0:
        return {
            **_evaluate_validated(previous, parameters, environment),
            "previous_cell_temperature_k": previous,
            "interval_s": 0.0,
            "integration_method": "backward_euler_bisection",
            "integration_substeps": 0,
            "thermal_storage_change_j": 0.0,
            "integrated_net_thermal_energy_j": 0.0,
            "energy_balance_residual_j": 0.0,
        }

    area = parameters.collecting_area_m2
    incoming = _finite_result(
        "solar_incident_power_w",
        area
        * (
            environment.direct_normal_irradiance_w_m2
            * environment.terrain_visible_fraction
            * environment.incidence_cosine
            * environment.structural_unobstructed_fraction
            + environment.wall_reflected_solar_irradiance_w_m2
        ),
    )
    positive_feedback_w_k = _finite_result(
        "efficiency_thermal_feedback_w_k",
        parameters.reference_efficiency
        * abs(parameters.efficiency_temperature_coefficient_per_k)
        * incoming,
    )
    time_steps = math.ceil(interval / _MAX_INTEGRATION_STEP_S)
    feedback_ratio = _finite_result(
        "efficiency_thermal_feedback_step_ratio",
        2.0 * interval * positive_feedback_w_k / parameters.heat_capacity_j_k,
    )
    if feedback_ratio > _MAX_INTEGRATION_SUBSTEPS:
        raise ValueError(
            "PV thermal feedback requires too many substeps; "
            "provide shorter UTC intervals or validated higher heat capacity"
        )
    feedback_steps = math.ceil(feedback_ratio)
    substeps = max(1, time_steps, feedback_steps)
    if substeps > _MAX_INTEGRATION_SUBSTEPS:
        raise ValueError(
            "Requested interval requires too many thermal substeps; "
            "provide shorter timestamp intervals or a validated higher heat capacity"
        )
    step_s = interval / substeps
    current = previous
    integrated_net = 0.0
    for _ in range(substeps):
        current, flows = _solve_backward_euler_step(
            current, step_s, parameters, environment
        )
        integrated_net = _finite_result(
            "integrated_net_thermal_energy_j",
            integrated_net + step_s * flows["net_thermal_power_w"],
        )
    stored = _finite_result(
        "thermal_storage_change_j", parameters.heat_capacity_j_k * (current - previous)
    )
    closure = _finite_result("energy_balance_residual_j", stored - integrated_net)
    allowed_error = max(1e-6, 1e-8 * max(abs(stored), abs(integrated_net)))
    if abs(closure) > allowed_error:
        raise ValueError("Thermal integrator failed its energy-closure tolerance")
    return {
        **flows,
        "previous_cell_temperature_k": previous,
        "interval_s": interval,
        "integration_method": "backward_euler_bisection",
        "integration_substeps": substeps,
        "thermal_storage_change_j": stored,
        "integrated_net_thermal_energy_j": integrated_net,
        "energy_balance_residual_j": closure,
    }
