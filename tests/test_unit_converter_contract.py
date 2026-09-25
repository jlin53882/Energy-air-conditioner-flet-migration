"""通道層 UnitConverter 的換算契約：未知性質／單位明確報錯，常用冷凍空調單位可往返換算。"""

from __future__ import annotations

import pytest

from Flet_ui.ui_components.unit.UnitConverter import GAUGE_PRESSURE, UnitConverter


@pytest.fixture(scope="module")
def converter() -> UnitConverter:
    """建立共用的單位轉換器。

回傳：
    UnitConverter。"""
    return UnitConverter()


@pytest.mark.parametrize(
    ("direction", "prop_code", "unit_code"),
    [
        ("to_si", "VolumeFlow", "m3/h"),
        ("from_si", "Power", "KW_BAD"),
        ("to_si", "DeltaT", "degC"),
        ("from_si", "MassFlow", "kg/h"),
        ("to_si", GAUGE_PRESSURE, "psia"),
        ("to_si", "P", "psig"),
    ],
)
def test_unknown_unit_is_rejected_instead_of_identity(converter, direction, prop_code, unit_code) -> None:
    """未註冊的單位引發 ValueError，不會把數值原樣當成 SI 值。

參數：
    converter: 單位轉換器。
    direction: "to_si" 或 "from_si"。
    prop_code: 性質代碼。
    unit_code: 未註冊的單位。

回傳：
    無。"""
    convert = converter.convert_to_si if direction == "to_si" else converter.convert_from_si
    with pytest.raises(ValueError, match="Unknown unit"):
        convert(prop_code, 3600.0, unit_code)


@pytest.mark.parametrize("direction", ["to_si", "from_si"])
def test_unknown_property_is_rejected_instead_of_identity(converter, direction) -> None:
    """未註冊的性質引發 ValueError（例如拼錯的性質代碼）。

參數：
    converter: 單位轉換器。
    direction: "to_si" 或 "from_si"。

回傳：
    無。"""
    convert = converter.convert_to_si if direction == "to_si" else converter.convert_from_si
    for prop_code in ("UnknownPhysicalQuantity", "SpecVolume"):
        with pytest.raises(ValueError, match="Unknown property"):
            convert(prop_code, 1.0, "m³/kg")


def test_every_listed_unit_converts_both_ways(converter) -> None:
    """下拉選單列出的每個單位都能雙向換算並回到原值。

回傳：
    無。"""
    for prop_code in converter.conversion_map:
        for unit in converter.get_available_units(prop_code):
            value_si = converter.convert_to_si(prop_code, 12.5, unit)
            assert converter.convert_from_si(prop_code, value_si, unit) == pytest.approx(12.5), (prop_code, unit)


def test_temperature_difference_has_no_zero_offset(converter) -> None:
    """ΔT：1 K = 1 °C 差 = 1.8 °F 差，不套用絕對溫度的零點偏移。

回傳：
    無。"""
    assert converter.convert_from_si("DeltaT", 1.0, "°C") == pytest.approx(1.0)
    assert converter.convert_from_si("DeltaT", 1.0, "°F") == pytest.approx(1.8)
    assert converter.convert_to_si("DeltaT", 1.8, "°F") == pytest.approx(1.0)
    # 對照：絕對溫度 1 K 換成 °F 會有零點偏移，溫差不可如此換算。
    assert converter.convert_from_si("T", 1.0, "°F") == pytest.approx(-457.87)


@pytest.mark.parametrize(("unit", "watts"), [("RT", 3516.853), ("kcal/h", 1.163), ("kW", 1000.0)])
def test_refrigeration_capacity_units(converter, unit, watts) -> None:
    """冷凍能力單位：1 RT（US 冷凍噸）≈ 3516.853 W、1 kcal/h ≈ 1.163 W，並可往返換算。

參數：
    converter: 單位轉換器。
    unit: 能力單位。
    watts: 1 單位對應的瓦特數。

回傳：
    無。"""
    assert converter.convert_to_si("Power", 1.0, unit) == pytest.approx(watts)
    assert converter.convert_from_si("Power", watts, unit) == pytest.approx(1.0)
    assert converter.convert_from_si("Power", converter.convert_to_si("Power", 37.5, unit), unit) == pytest.approx(37.5)


@pytest.mark.parametrize(
    ("unit", "per_m3_s"),
    [("m³/s", 1.0), ("m³/min", 60.0), ("m³/h", 3600.0), ("L/s", 1000.0), ("ft³/min", 2118.88)],
)
def test_volume_flow_units(converter, unit, per_m3_s) -> None:
    """風量單位：1 m³/s 對應各單位的數值，並可往返換算。

參數：
    converter: 單位轉換器。
    unit: 風量單位。
    per_m3_s: 1 m³/s 以該單位表示的數值。

回傳：
    無。"""
    assert converter.convert_from_si("VolumeFlow", 1.0, unit) == pytest.approx(per_m3_s, rel=1e-5)
    assert converter.convert_to_si("VolumeFlow", per_m3_s, unit) == pytest.approx(1.0, rel=1e-5)


def test_gauge_pressure_units_are_differences_on_the_absolute_scale(converter) -> None:
    """錶壓單位與同尺度絕對單位使用相同換算因子，本身不含大氣壓力。

回傳：
    無。"""
    assert converter.convert_to_si(GAUGE_PRESSURE, 900.0, "kPag") == pytest.approx(900_000.0)
    assert converter.convert_to_si(GAUGE_PRESSURE, 100.0, "psig") == pytest.approx(
        converter.convert_to_si("P", 100.0, "psia")
    )
    assert converter.gauge_to_absolute_pa(900_000.0, 101_325.0) == pytest.approx(1_001_325.0)


def test_volumetric_efficiency_specific_volumes_use_registered_units() -> None:
    """容積效率的比容欄位使用已註冊的比容單位，混用單位時仍得到相同結果。

    這兩個欄位原本使用未註冊的性質代碼，單位清單是空的，換算時直接把數值
    當成 SI 值；只有兩欄剛好同單位時比值才正確。

回傳：
    無。"""
    from Flet_ui.flet_app import main as flet_main

    class DummyPage:
        """提供建構工作區所需的最小 page 介面。"""

        def __init__(self) -> None:
            """初始化控制項與 overlay。

回傳：
    無。"""
            self.controls = []
            self.overlay = []

        def add(self, *controls) -> None:
            """收集控制項。

參數：
    controls: 要加入的控制項。

回傳：
    無。"""
            self.controls.extend(controls)

        def update(self) -> None:
            """接受更新呼叫。

回傳：
    無。"""

    page = DummyPage()
    flet_main(page)
    module = page.controls[0].views["compressor"].adapter.modules[0]
    v1, v2 = module.all_entries["ve_v1"], module.all_entries["ve_v2"]
    assert v1["prop_code"] == v2["prop_code"] == "V"
    assert "ft³/lbm" in [option.key for option in v1["unit"].options]

    v1["val"].value, v1["unit"].value = "0.05", "m³/kg"
    v2["val"].value, v2["unit"].value = "0.005", "m³/kg"
    same_units = module.calculate_vol_eff(False)
    v1["val"].value, v1["unit"].value = f"{0.05 / 0.062428:.10g}", "ft³/lbm"
    mixed_units = module.calculate_vol_eff(False)

    assert mixed_units == same_units
