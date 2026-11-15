"""Telegram 物性查詢導入 Auto：與 Flet 使用同一個 resolver，同一查詢得到相同的焓、熵。"""

from __future__ import annotations

import dataclasses

import pytest

from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.thermodynamics.thermo_policy import ThermoPolicyError, resolve_thermo_policy
from domain.units.converter import CanonicalUnitConverter
from Telegram_bot.thermo_calculator import ThermoCalculator

KNOWN = [("P", 1000.0, "kPa"), ("T", 60.0, "°C")]


@pytest.fixture(scope="module")
def calculator() -> ThermoCalculator:
    """建立 Telegram 計算器。

回傳：
    ThermoCalculator。"""
    return ThermoCalculator()


@pytest.mark.parametrize(
    ("fluid", "expected"),
    [("R717", "IIR"), ("NH3", "IIR"), ("R32", "IIR"), ("R134a", "IIR"), ("Water", "DEF"), ("Air", "DEF")],
)
def test_auto_resolves_same_reference_as_flet(calculator, fluid: str, expected: str) -> None:
    """Telegram Auto 的基準與 Flet 物性頁（同一 resolver）一致。

回傳：
    無。"""
    _results, policy = calculator.calculate_properties_auto(fluid, KNOWN)
    assert policy.reference_state == expected
    assert policy.reference_state == resolve_thermo_policy(fluid).reference_state
    assert policy.is_auto_reference


def test_auto_enthalpy_matches_shared_service_with_resolved_reference(calculator) -> None:
    """焓、熵等於共用 domain 服務在解析後基準（IIR）下的值，而不是舊的 DEF。

回傳：
    無。"""
    results, policy = calculator.calculate_properties_auto("R717", KNOWN)
    service = ThermodynamicStateService(CanonicalUnitConverter())
    iir = service.calculate_properties("R717", KNOWN, reference_state=policy.reference_state)
    legacy_def = service.calculate_properties("R717", KNOWN, reference_state="DEF")
    assert results["H"] == pytest.approx(iir["H"], rel=1e-12)
    assert results["S"] == pytest.approx(iir["S"], rel=1e-12)
    assert results["H"] != pytest.approx(legacy_def["H"], rel=1e-6)
    # 壓力、溫度、密度與基準無關
    assert results["D"] == pytest.approx(legacy_def["D"], rel=1e-12)


def test_legacy_specific_volume_path_receives_resolved_reference(monkeypatch) -> None:
    """舊比容（V）路徑同樣收到解析後的基準（V 的換算語義是既有相容邊界，此處不驗證數值）。

回傳：
    無。"""
    calculator = ThermoCalculator()
    seen: list[object] = []

    def record(fluid, known_props, is_ideal_gas=False, reference_state=None):
        """記錄傳入的基準。

回傳：
    dict：空結果。"""
        seen.append(reference_state)
        return {}

    monkeypatch.setattr(calculator, "_calculate_legacy_properties", record)
    _results, policy = calculator.calculate_properties_auto("R32", [("P", 1000.0, "kPa"), ("V", 0.05, "m³/kg")])
    assert seen == [policy.reference_state] == ["IIR"]


def test_unknown_fluid_is_a_value_error(calculator) -> None:
    """無法解析的流體以 ValueError（ThermoPolicyError）回報，handler 既有的錯誤處理可接住。

回傳：
    無。"""
    with pytest.raises(ThermoPolicyError):
        calculator.calculate_properties_auto("NotAFluid", KNOWN)
    assert issubclass(ThermoPolicyError, ValueError)


def test_policy_lines_show_model_reference_and_escape_html(calculator) -> None:
    """結果文字列出模型與基準；備援說明存在時一併列出，且內容經 HTML escape。

回傳：
    無。"""
    _results, policy = calculator.calculate_properties_auto("R717", KNOWN)
    text = calculator.format_policy_lines(policy)
    assert text.splitlines()[0] == "--- 模型與基準 ---"
    assert "參考基準: IIR（Auto）" in text
    assert "備援說明" not in text

    fallback = dataclasses.replace(policy, fallback_reason="<b>不支援</b>")
    escaped = calculator.format_policy_lines(fallback)
    assert "備援說明: &lt;b&gt;不支援&lt;/b&gt;" in escaped
