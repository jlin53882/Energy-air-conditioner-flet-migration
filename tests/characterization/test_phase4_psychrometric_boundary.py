"""Phase 4 的 single psychrometric boundary test。"""

from __future__ import annotations

import pytest

from domain.psychrometrics.service import PsychrometricService
from Flet_ui.ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from Telegram_bot.thermo_calculator import ThermoCalculator
from infrastructure.psychrometrics import LegacyPsychrometricModelAdapter


def test_shared_psychrometric_service_returns_si_numeric_result() -> None:
    """shared adapter 隱藏排除 model 的 tuple contract。

回傳：
    無。"""
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
    """Flet adapter 原樣提供 shared service result。

回傳：
    無。"""
    expected = PsychrometricService(LegacyPsychrometricModelAdapter()).calculate_from_tdb_rh(298.15, 50.0, 0.0)
    actual = PsychrometricCalculator().calculate_from_tdb_rh(298.15, 50.0, 0.0)
    assert actual == expected


def test_telegram_psychrometric_adapter_preserves_display_contract() -> None:
    """Telegram 保留 display string，但數值來源改由 service 提供。

回傳：
    無。"""
    result = ThermoCalculator().calculate_psychrometric_properties(
        {"altitude": 0.0, "Tdb": 25.0, "RH": 50.0}
    )
    assert result["乾球溫度 (Dry-Bulb Temperature)"] == "25.00 °C"
    assert result["相對濕度 (Relative Humidity)"] == "50.00 %"
    assert result["濕空氣之焓值 (Enthalpy)"].endswith("kJ/kg")
