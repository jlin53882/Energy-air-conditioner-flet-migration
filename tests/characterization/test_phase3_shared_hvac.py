"""Phase 3 tests for shared SI HVAC equations."""

from __future__ import annotations

import pytest

from domain.hvac.basic import (
    calculate_compression_ratio_si,
    calculate_compressor_work_si,
    calculate_condenser_heat_rate_si,
    calculate_evaporator_heat_rate_si,
)
from Flet_ui.ui_components.unit.HVACAnalyzer import HVACAnalyzer
from Telegram_bot.thermo_calculator import ThermoCalculator


def test_shared_hvac_equations_use_si_energy_units() -> None:
    """J/kg inputs produce W outputs in the domain boundary."""
    assert calculate_compressor_work_si(0.2, 250_000.0, 300_000.0) == pytest.approx(10_000.0)
    assert calculate_evaporator_heat_rate_si(0.2, 100_000.0, 250_000.0) == pytest.approx(30_000.0)
    assert calculate_condenser_heat_rate_si(0.2, 300_000.0, 250_000.0) == pytest.approx(10_000.0)
    assert calculate_compression_ratio_si(100_000.0, 500_000.0) == pytest.approx(5.0)


def test_shared_hvac_equations_preserve_existing_channel_outputs() -> None:
    """Flet and Telegram compatibility callers retain their current kW API."""
    telegram = ThermoCalculator()
    cases = (
        (HVACAnalyzer.calculate_compressor_work, telegram.calculate_compressor_work, (0.2, 250.0, 300.0)),
        (HVACAnalyzer.calculate_evaporator_heat_rate, telegram.calculate_evaporator_heat_rate, (0.2, 100.0, 250.0)),
        (HVACAnalyzer.calculate_condenser_heat_rate, telegram.calculate_condenser_heat_rate, (0.2, 300.0, 250.0)),
        (HVACAnalyzer.calculate_compression_ratio, telegram.calculate_compression_ratio, (100.0, 500.0)),
    )
    for flet_function, telegram_function, args in cases:
        assert flet_function(*args) == pytest.approx(telegram_function(*args))


def test_shared_hvac_equations_reject_invalid_boundaries() -> None:
    """Negative flow/enthalpy and non-positive absolute pressure fail."""
    with pytest.raises(ValueError):
        calculate_compressor_work_si(-0.1, 250_000.0, 300_000.0)
    with pytest.raises(ValueError):
        calculate_evaporator_heat_rate_si(0.2, 300_000.0, 250_000.0)
    with pytest.raises(ValueError):
        calculate_condenser_heat_rate_si(0.2, 250_000.0, 300_000.0)
    with pytest.raises(ValueError):
        calculate_compression_ratio_si(0.0, 500_000.0)
