"""Phase 2 的 shared thermodynamic service test。"""

from __future__ import annotations

import pytest

from domain.thermodynamics.reference_state import ReferenceStateService
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter
from Flet_ui.ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from Telegram_bot.thermo_calculator import ThermoCalculator


def test_shared_service_calculates_ideal_gas_properties_headlessly() -> None:
    """domain service 計算時不依賴 Flet 或 Telegram object。

回傳：
    無。"""
    service = ThermodynamicStateService(CanonicalUnitConverter())
    result = service.calculate_properties(
        "Air",
        [("P", 101.325, "kPa"), ("T", 25.0, "°C")],
        is_ideal_gas=True,
    )

    assert result["P"] == pytest.approx(101325.0)
    assert result["T"] == pytest.approx(298.15)
    assert result["phase"] == "gas"


def test_flet_and_telegram_property_calculators_delegate_shared_service() -> None:
    """兩個 channel calculator 都提供 shared property result contract。

回傳：
    無。"""
    known_props = [("P", 101.325, "kPa"), ("T", 25.0, "°C")]
    flet = ThermoStateCalculator(CanonicalUnitConverter())
    telegram = ThermoCalculator()

    flet_result = flet.calculate_properties("Air", known_props, is_ideal_gas=True)
    telegram_result = telegram.calculate_properties("Air", known_props, is_ideal_gas=True)

    assert flet_result == telegram_result


def test_reference_state_service_serializes_and_restores_reference_state() -> None:
    """Reference-state mutation 集中於單一明確 mechanism。

回傳：
    無。"""
    service = ReferenceStateService()
    try:
        service.set("R134a", "ASHRAE")
        ashrae = service.current("R134a")
        service.set("R134a", "IIR")
        assert service.current("R134a") == "IIR"
        service.set("R134a", ashrae)
        assert service.current("R134a") == ashrae
    finally:
        service.set("R134a", "DEF")


def test_reference_state_service_rejects_invalid_code() -> None:
    """Invalid reference-state code 必須在記錄為 current 前失敗。

回傳：
    無。"""
    service = ReferenceStateService()
    with pytest.raises(ValueError, match="reference state"):
        service.set("R134a", "not-a-reference-state")
