"""Phase 1 的 canonical unit contract test。"""

from __future__ import annotations

import pytest

from domain.units.converter import CanonicalUnitConverter
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter
from Telegram_bot.thermo_calculator import ThermoCalculator


@pytest.fixture
def canonical_converter() -> CanonicalUnitConverter:
    """建立受測的 canonical unit converter。

回傳：
    CanonicalUnitConverter：函數計算或處理後的結果。"""
    return CanonicalUnitConverter()


def test_canonical_converter_round_trips_core_quantities(
    canonical_converter: CanonicalUnitConverter,
) -> None:
    """核心 physical quantities 透過明確 SI transforms 往返轉換。

參數：
    canonical_converter (CanonicalUnitConverter): 函數輸入值。

回傳：
    無。"""
    cases = (
        ("P", 1.2, "bar"),
        ("T", 25.0, "°C"),
        ("H", 250.0, "kJ/kg"),
        ("S", 1.1, "kJ/(kg.K)"),
        ("D", 1.5, "lbm/ft³"),
        ("U", 300.0, "Btu/lbm"),
    )

    for prop_code, value, unit_code in cases:
        si_value = canonical_converter.convert_to_si(prop_code, value, unit_code)
        assert canonical_converter.convert_from_si(prop_code, si_value, unit_code) == pytest.approx(value)


def test_canonical_converter_uses_specific_volume_semantics(
    canonical_converter: CanonicalUnitConverter,
) -> None:
    """V 在 domain boundary 表示 specific volume，而不是 density。

參數：
    canonical_converter (CanonicalUnitConverter): 函數輸入值。

回傳：
    無。"""
    assert canonical_converter.convert_to_si("V", 0.5, "m³/kg") == pytest.approx(0.5)
    assert canonical_converter.convert_to_si("V", 16.0185, "ft³/lbm") == pytest.approx(
        16.0185 * 0.062428
    )
    assert canonical_converter.convert_from_si("V", 1.0, "ft³/lbm") == pytest.approx(
        1.0 / 0.062428
    )


def test_flet_converter_delegates_core_quantities_to_canonical_contract() -> None:
    """既有 Flet facade 公開 canonical core transforms。

回傳：
    無。"""
    converter = UnitConverter()
    canonical = CanonicalUnitConverter()

    for prop_code, value, unit_code in (("P", 1.2, "bar"), ("T", 25.0, "°C"), ("H", 250.0, "kJ/kg"), ("V", 16.0185, "ft³/lbm")):
        assert converter.convert_to_si(prop_code, value, unit_code) == pytest.approx(
            canonical.convert_to_si(prop_code, value, unit_code)
        )


def test_telegram_converter_delegates_core_quantities_to_canonical_contract() -> None:
    """Telegram calculator 使用相同的 core conversion semantics。

回傳：
    無。"""
    converter = ThermoCalculator()
    canonical = CanonicalUnitConverter()

    for prop_code, value, unit_code in (("P", 1.2, "bar"), ("T", 25.0, "°C"), ("H", 250.0, "kJ/kg")):
        assert converter._convert_to_si(prop_code, value, unit_code) == pytest.approx(
            canonical.convert_to_si(prop_code, value, unit_code)
        )
        assert converter._convert_from_si(
            prop_code,
            canonical.convert_to_si(prop_code, value, unit_code),
            unit_code,
        ) == pytest.approx(value)


def test_flet_converter_rejects_unknown_specific_volume_units() -> None:
    """Flet V conversion 必須使用 canonical explicit-error contract。

回傳：
    無。"""
    converter = UnitConverter()
    with pytest.raises(ValueError, match="Unknown unit"):
        converter.convert_to_si("V", 1.0, "not-a-unit")
    with pytest.raises(ValueError, match="Unknown unit"):
        converter.convert_from_si("V", 1.0, "not-a-unit")


def test_canonical_converter_rejects_unknown_units() -> None:
    """未知 core units 必須明確失敗，而不是默默改變 semantics。

回傳：
    無。"""
    with pytest.raises(ValueError, match="Unknown unit"):
        CanonicalUnitConverter().convert_to_si("P", 1.0, "not-a-pressure-unit")
