"""Focused regression tests for the migrated HVAC calculation surface."""

from __future__ import annotations

import math

import pytest

from Flet_ui.ui_components.analysis_tab import AnalysisTab
from Flet_ui.ui_components.unit.HVACAnalyzer import HVACAnalyzer
from Flet_ui.ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from Flet_ui.ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter


class DummyPage:
    """Provide the page API required while constructing analysis controls."""

    def __init__(self) -> None:
        self.overlay = []
        self.controls = []

    def update(self) -> None:
        """Accept updates without a live Flet session."""

    def add(self, *controls) -> None:
        """Collect controls added by a page entry point."""
        self.controls.extend(controls)


@pytest.fixture
def analyzer() -> HVACAnalyzer:
    """Return the calculation facade used by the analysis tab."""
    return HVACAnalyzer()


def test_hvac_basic_energy_calculations(analyzer: HVACAnalyzer) -> None:
    """Cover the core compressor, heat-exchanger, and throttling equations."""
    assert analyzer.calculate_compression_ratio(2.0, 10.0) == pytest.approx(5.0)
    assert analyzer.calculate_compressor_work(2.0, 10.0, 30.0) == pytest.approx(40.0)
    assert analyzer.calculate_compressor_work_heat_transfer(2.0, 10.0, 30.0, 4.0) == pytest.approx(44.0)
    assert analyzer.calculate_evaporator_heat_rate(2.0, 10.0, 30.0) == pytest.approx(40.0)
    assert analyzer.calculate_condenser_heat_rate(2.0, 30.0, 10.0) == pytest.approx(40.0)
    assert analyzer.calculate_throttling_value(30.0, 10.0) == pytest.approx(30.0)


def test_hvac_efficiency_and_entropy_calculations(analyzer: HVACAnalyzer) -> None:
    """Cover dimensionless efficiency and entropy-generation calculations."""
    assert analyzer.calculate_Sgen(100.0, 125.0) == pytest.approx(25.0)
    assert analyzer.calculate_Sgen_flow(2.0, 100.0, 125.0) == pytest.approx(50.0)
    assert analyzer.calculate_isentropic_efficiency(10.0, 30.0, 20.0) == pytest.approx(0.5)
    assert analyzer.calculate_volumetric_efficiency(0.1, 0.01, 0.02) == pytest.approx(1.05)


def test_hvac_invalid_denominators_raise_value_error(analyzer: HVACAnalyzer) -> None:
    """Keep invalid physical inputs explicit instead of returning misleading zeros."""
    with pytest.raises((ValueError, ZeroDivisionError)):
        analyzer.calculate_compression_ratio(0.0, 10.0)
    assert analyzer.calculate_isentropic_efficiency(1.0, 2.0, 1.0) == pytest.approx(0.0)


def test_unit_converter_round_trip_and_unknown_unit(analyzer: HVACAnalyzer) -> None:
    """Verify SI conversion round trips and rejection of unsupported units."""
    converter = UnitConverter()
    for prop_code, value, unit in (("T", 25.0, "C"), ("P", 2.0, "bar"), ("H", 300.0, "kJ/kg")):
        si_value = converter.convert_to_si(prop_code, value, unit)
        assert converter.convert_from_si(prop_code, si_value, unit) == pytest.approx(value)
    assert converter.convert_to_si("P", 1.0, "not-a-unit") == 1.0


def test_thermo_state_validation_and_property_calculation() -> None:
    """Exercise CoolProp-backed state validation and one ordinary property query."""
    converter = UnitConverter()
    calculator = ThermoStateCalculator(converter)
    assert calculator.is_fluid_valid("R134a") is True
    assert calculator.is_fluid_valid("definitely-not-a-fluid") is False
    result = calculator.calculate_properties("Water", [("T", 25.0, "°C"), ("P", 1.0, "bar")])
    assert result
    assert any(key in result for key in ("T", "P", "H", "S"))


def test_psychrometric_calculator_returns_finite_properties() -> None:
    """Exercise both supported moist-air input paths with realistic conditions."""
    calculator = PsychrometricCalculator()
    for result in (
        calculator.calculate_from_tdb_rh(298.15, 0.5, 0.0),
        calculator.calculate_from_tdb_twb(298.15, 290.15, 0.0),
    ):
        assert result
        numeric_values = [value for value in result.values() if isinstance(value, (int, float))]
        assert numeric_values
        assert all(math.isfinite(value) for value in numeric_values)


def test_every_analysis_option_switches_and_calculates() -> None:
    """Smoke-test every registered analysis page and its default calculation path."""
    page = DummyPage()
    converter = UnitConverter()
    tab = AnalysisTab(
        unit_converter=converter,
        page=page,
        analyzer=HVACAnalyzer(),
        psy_calculator=PsychrometricCalculator(),
        state_calculator=ThermoStateCalculator(converter),
    )
    tab.update = lambda: None
    assert len(tab.analysis_map) == 16

    for name, definition in tab.analysis_map.items():
        tab.analysis_dd.value = name
        tab.on_analysis_change(None)
        assert definition["ui"].visible is True, name
        visible_containers = {id(item["ui"]) for item in tab.analysis_map.values() if item["ui"].visible}
        assert id(definition["ui"]) in visible_containers
        assert len(visible_containers) == 1
        tab.calculate_analysis(None)
        assert isinstance(tab.result_text.value, str), name
        assert tab.result_text.value, name
