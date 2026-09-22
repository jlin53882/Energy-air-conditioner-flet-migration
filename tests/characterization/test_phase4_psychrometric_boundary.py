"""Phase 4 tests for the single psychrometric boundary."""

from __future__ import annotations

import pytest

from domain.psychrometrics.service import PsychrometricService
from Flet_ui.ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from Telegram_bot.thermo_calculator import ThermoCalculator
from infrastructure.psychrometrics import LegacyPsychrometricModelAdapter


def test_shared_psychrometric_service_returns_si_numeric_result() -> None:
    """The shared adapter hides the excluded model tuple contract."""
    result = PsychrometricService(LegacyPsychrometricModelAdapter()).calculate_from_tdb_rh(
        tdb_k=298.15,
        rh=50.0,
        altitude_m=0.0,
    )

    assert result["Tdb"] == pytest.approx(298.15)
    assert result["P"] > 0
    assert result["H"] > 0
    assert result["Tdp"] < result["Tdb"]


def test_flet_psychrometric_adapter_matches_shared_service() -> None:
    """The Flet adapter exposes the shared service result unchanged."""
    expected = PsychrometricService(LegacyPsychrometricModelAdapter()).calculate_from_tdb_rh(298.15, 50.0, 0.0)
    actual = PsychrometricCalculator().calculate_from_tdb_rh(298.15, 50.0, 0.0)
    assert actual == expected


def test_telegram_psychrometric_adapter_preserves_display_contract() -> None:
    """Telegram keeps display strings while sourcing values from the service."""
    result = ThermoCalculator().calculate_psychrometric_properties(
        {"altitude": 0.0, "Tdb": 25.0, "RH": 50.0}
    )
    assert result["乾球溫度 (Dry-Bulb Temperature)"] == "25.00 °C"
    assert result["相對濕度 (Relative Humidity)"] == "50.00 %"
    assert result["濕空氣之焓值 (Enthalpy)"].endswith("kJ/kg")
