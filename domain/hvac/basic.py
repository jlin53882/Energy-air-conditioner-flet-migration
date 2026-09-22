"""Canonical SI HVAC equations shared by all channel adapters."""

from __future__ import annotations


def _validate_nonnegative(*values: float) -> None:
    """Reject negative physical inputs used by the basic energy equations."""
    if any(value < 0 for value in values):
        raise ValueError("mass flow and enthalpy values must be non-negative")


def calculate_compressor_work_si(
    mass_flow_kg_per_s: float,
    inlet_enthalpy_j_per_kg: float,
    outlet_enthalpy_j_per_kg: float,
) -> float:
    """Return compressor power in watts from SI quantities."""
    _validate_nonnegative(mass_flow_kg_per_s, inlet_enthalpy_j_per_kg, outlet_enthalpy_j_per_kg)
    return mass_flow_kg_per_s * (outlet_enthalpy_j_per_kg - inlet_enthalpy_j_per_kg)


def calculate_evaporator_heat_rate_si(
    mass_flow_kg_per_s: float,
    inlet_enthalpy_j_per_kg: float,
    outlet_enthalpy_j_per_kg: float,
) -> float:
    """Return evaporator heat rate in watts from SI quantities."""
    _validate_nonnegative(mass_flow_kg_per_s, inlet_enthalpy_j_per_kg, outlet_enthalpy_j_per_kg)
    if outlet_enthalpy_j_per_kg < inlet_enthalpy_j_per_kg:
        raise ValueError("outlet enthalpy must be greater than or equal to inlet enthalpy")
    return mass_flow_kg_per_s * (outlet_enthalpy_j_per_kg - inlet_enthalpy_j_per_kg)


def calculate_condenser_heat_rate_si(
    mass_flow_kg_per_s: float,
    inlet_enthalpy_j_per_kg: float,
    outlet_enthalpy_j_per_kg: float,
) -> float:
    """Return condenser heat rate in watts from SI quantities."""
    _validate_nonnegative(mass_flow_kg_per_s, inlet_enthalpy_j_per_kg, outlet_enthalpy_j_per_kg)
    if outlet_enthalpy_j_per_kg > inlet_enthalpy_j_per_kg:
        raise ValueError("inlet enthalpy must be greater than or equal to outlet enthalpy")
    return mass_flow_kg_per_s * (inlet_enthalpy_j_per_kg - outlet_enthalpy_j_per_kg)


def calculate_compression_ratio_si(
    suction_pressure_pa: float,
    discharge_pressure_pa: float,
) -> float:
    """Return the dimensionless absolute-pressure compression ratio."""
    if suction_pressure_pa <= 0 or discharge_pressure_pa <= 0:
        raise ValueError("absolute pressures must be greater than zero")
    if suction_pressure_pa > discharge_pressure_pa:
        raise ValueError("discharge pressure must be greater than or equal to suction pressure")
    return discharge_pressure_pa / suction_pressure_pa
