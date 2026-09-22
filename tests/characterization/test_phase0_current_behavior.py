"""Phase 0 characterization tests for the pre-consolidation behavior.

These tests intentionally record current Flet/Telegram contracts before any
shared-domain migration.  They do not declare that every observed difference
is correct; divergence decisions belong to Phase 0.5.
"""

from __future__ import annotations

import math

import pytest

from Flet_ui.ui_components.unit.HVACAnalyzer import HVACAnalyzer
from Flet_ui.ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from Flet_ui.ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter
from Telegram_bot.thermo_calculator import ThermoCalculator


@pytest.fixture
def flet_converter() -> UnitConverter:
    """Create the current Flet unit converter used by the application."""
    return UnitConverter()


@pytest.fixture
def flet_thermo(flet_converter: UnitConverter) -> ThermoStateCalculator:
    """Create the current Flet thermodynamic calculator."""
    return ThermoStateCalculator(flet_converter)


@pytest.fixture
def telegram_thermo() -> ThermoCalculator:
    """Create the current Telegram thermodynamic calculator."""
    return ThermoCalculator()


def test_current_unit_contracts_are_recorded_for_shared_quantities(
    flet_converter: UnitConverter,
    telegram_thermo: ThermoCalculator,
) -> None:
    """Record matching pressure/temperature/enthalpy conversions pre-migration."""
    cases = (
        ("P", 1.0, "bar"),
        ("T", 25.0, "°C"),
        ("H", 250.0, "kJ/kg"),
    )

    for prop_code, value, unit in cases:
        assert flet_converter.convert_to_si(prop_code, value, unit) == pytest.approx(
            telegram_thermo._convert_to_si(prop_code, value, unit)
        )


def test_specific_volume_contract_differs_between_current_engines(
    flet_converter: UnitConverter,
    telegram_thermo: ThermoCalculator,
) -> None:
    """Record the known V contract divergence before choosing a canonical rule."""
    value = 0.5
    unit = "m³/kg"

    # Flet's converter preserves V as specific volume; Telegram's current
    # private converter returns density for the same property code.
    assert flet_converter.convert_to_si("V", value, unit) == pytest.approx(value)
    assert telegram_thermo._convert_to_si("V", value, unit) == pytest.approx(1 / value)


def test_current_ideal_gas_results_match_between_engines(
    flet_thermo: ThermoStateCalculator,
    telegram_thermo: ThermoCalculator,
) -> None:
    """Record the current ideal-gas numerical contract before consolidation."""
    known_props = [("P", 101.325, "kPa"), ("T", 25.0, "°C")]
    flet_result = flet_thermo.calculate_properties("Air", known_props, is_ideal_gas=True)
    telegram_result = telegram_thermo.calculate_properties(
        "Air", known_props, is_ideal_gas=True
    )

    for prop_code in ("P", "T", "D", "H", "U", "V"):
        assert flet_result[prop_code] == pytest.approx(telegram_result[prop_code])
    assert flet_result["phase"] == telegram_result["phase"] == "gas"


def test_current_hvac_formula_contracts_match_for_shared_cases(
    telegram_thermo: ThermoCalculator,
) -> None:
    """Record current Flet HVAC facade versus Telegram formula outputs."""
    cases = (
        (HVACAnalyzer.calculate_compressor_work, telegram_thermo.calculate_compressor_work, (0.2, 250.0, 300.0)),
        (
            HVACAnalyzer.calculate_evaporator_heat_rate,
            telegram_thermo.calculate_evaporator_heat_rate,
            (0.2, 100.0, 250.0),
        ),
        (
            HVACAnalyzer.calculate_condenser_heat_rate,
            telegram_thermo.calculate_condenser_heat_rate,
            (0.2, 300.0, 250.0),
        ),
        (
            HVACAnalyzer.calculate_compression_ratio,
            telegram_thermo.calculate_compression_ratio,
            (100.0, 500.0),
        ),
    )

    for flet_function, telegram_function, args in cases:
        assert flet_function(*args) == pytest.approx(telegram_function(*args))


def test_current_psychrometric_adapters_expose_different_output_contracts(
    telegram_thermo: ThermoCalculator,
) -> None:
    """Record Flet SI dictionary versus Telegram display-string output."""
    flet_result = PsychrometricCalculator().calculate_from_tdb_rh(
        tdb_k=298.15,
        rh=50.0,
        altitude_m=0.0,
    )
    telegram_result = telegram_thermo.calculate_psychrometric_properties(
        {"altitude": 0.0, "Tdb": 25.0, "RH": 50.0}
    )

    assert isinstance(flet_result["Tdb"], float)
    assert flet_result["Tdb"] == pytest.approx(298.15)
    assert flet_result["H"] > 0
    assert isinstance(telegram_result["乾球溫度 (Dry-Bulb Temperature)"], str)
    assert telegram_result["乾球溫度 (Dry-Bulb Temperature)"].endswith("°C")


def test_reference_state_selector_updates_current_flet_state(
    flet_thermo: ThermoStateCalculator,
) -> None:
    """Record the current mutable reference-state behavior for a pure fluid."""
    original = flet_thermo.state_service.reference_state.current("R134a") or "DEF"
    try:
        flet_thermo.set_coolprop_ref_state("R134a", "IIR")
        assert flet_thermo.state_service.reference_state.current("R134a") == "IIR"
        flet_thermo.set_coolprop_ref_state("R134a", "Default")
        assert flet_thermo.state_service.reference_state.current("R134a") == "DEF"
    finally:
        flet_thermo.set_coolprop_ref_state("R134a", original)


def test_characterization_results_are_finite_for_representative_inputs(
    flet_thermo: ThermoStateCalculator,
) -> None:
    """Guard the baseline fixture against silently recording non-finite output."""
    result = flet_thermo.calculate_properties(
        "R134a",
        [("P", 101.325, "kPa"), ("T", 25.0, "°C")],
    )
    assert all(math.isfinite(value) for key, value in result.items() if key != "phase")


def test_reference_state_sequence_returns_to_original_values(
    flet_thermo: ThermoStateCalculator,
) -> None:
    """Characterize CoolProp state mutation across sequential reference states."""
    known_props = [("P", 101.325, "kPa"), ("T", 25.0, "°C")]
    try:
        flet_thermo.set_coolprop_ref_state("R134a", "ASHRAE")
        ashrae_before = flet_thermo.calculate_properties(
            "R134a", known_props, reference_state="ASHRAE"
        )

        flet_thermo.set_coolprop_ref_state("R134a", "IIR")
        iir_result = flet_thermo.calculate_properties(
            "R134a", known_props, reference_state="IIR"
        )

        flet_thermo.set_coolprop_ref_state("R134a", "ASHRAE")
        ashrae_after = flet_thermo.calculate_properties(
            "R134a", known_props, reference_state="ASHRAE"
        )
    finally:
        flet_thermo.set_coolprop_ref_state("R134a", "DEF")

    assert iir_result["H"] != pytest.approx(ashrae_before["H"])
    assert ashrae_after["H"] == pytest.approx(ashrae_before["H"])
    assert ashrae_after["S"] == pytest.approx(ashrae_before["S"])
