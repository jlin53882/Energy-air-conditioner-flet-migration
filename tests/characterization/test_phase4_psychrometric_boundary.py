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
        rh=0.5,
        altitude_m=0.0,
    )

    assert result["Tdb"] == pytest.approx(298.15)
    assert result["P"] > 0
    assert result["H"] > 0
    assert result["Tdp"] < result["Tdb"]


def test_psychrometric_rh_input_uses_fraction_boundary_and_si_pressure() -> None:
    """RH fraction 必須轉回 legacy model 的百分比輸入，結果壓力則回傳 Pa。

回傳：
    無。"""
    service = PsychrometricService(LegacyPsychrometricModelAdapter())
    result = service.calculate_from_tdb_rh(tdb_k=288.65, rh=0.88, altitude_m=0.0)

    assert result["RH"] == pytest.approx(0.88)
    assert result["P"] == pytest.approx(101325.0)
    assert result["Twb"] == pytest.approx(287.44, abs=0.01)
    assert result["W"] == pytest.approx(0.009662404)
    assert result["H"] == pytest.approx(40037.239511)
    assert result["V"] == pytest.approx(0.830444155)


def test_psychrometric_rh_percentage_input_is_rejected_by_strict_domain() -> None:
    """domain service 僅接受 RH fraction，percentage 由 caller adapter 負責轉換。

回傳：
    無。"""
    service = PsychrometricService(LegacyPsychrometricModelAdapter())

    with pytest.raises(ValueError, match="RH must be a fraction"):
        service.calculate_from_tdb_rh(tdb_k=288.65, rh=88.0, altitude_m=0.0)


def test_psychrometric_rh_out_of_domain_range_is_rejected() -> None:
    """RH 超出 domain fraction 範圍時必須明確失敗。

回傳：
    無。"""
    service = PsychrometricService(LegacyPsychrometricModelAdapter())

    with pytest.raises(ValueError, match="fraction between"):
        service.calculate_from_tdb_rh(tdb_k=288.65, rh=101.0, altitude_m=0.0)


def test_psychrometric_tdb_twb_path_normalizes_rh_to_fraction() -> None:
    """乾球／濕球 path 也必須將 legacy model 的 RH percentage 正規化為 fraction。

回傳：
    無。"""
    service = PsychrometricService(LegacyPsychrometricModelAdapter())

    result = service.calculate_from_tdb_twb(tdb_k=298.15, twb_k=290.15, altitude_m=0.0)

    assert result["RH"] == pytest.approx(0.4463178211755029)


def test_flet_psychrometric_adapter_matches_shared_service() -> None:
    """Flet adapter 原樣提供 shared service result。

回傳：
    無。"""
    expected = PsychrometricService(LegacyPsychrometricModelAdapter()).calculate_from_tdb_rh(298.15, 0.5, 0.0)
    actual = PsychrometricCalculator().calculate_from_tdb_rh(298.15, 0.5, 0.0)
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
