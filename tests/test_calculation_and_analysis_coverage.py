"""已遷移 HVAC calculation surface 的 focused regression tests。"""

from __future__ import annotations

import logging
import math

import pytest

from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui_components.analysis_modules.psy_module import PsyModule
from Flet_ui.ui_components.unit.HVACAnalyzer import HVACAnalyzer
from Flet_ui.ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from Flet_ui.ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter


class DummyPage:
    """提供建構 analysis controls 時所需的 page API。"""

    def __init__(self) -> None:
        self.overlay = []
        self.controls = []

    def update(self) -> None:
        """在沒有 live Flet session 的情況下接受 updates。

回傳：
    無。"""

    def add(self, *controls) -> None:
        """收集 page entry point 新增的 controls。

參數：
    controls (未指定型別): 函數輸入值。

回傳：
    無。"""
        self.controls.extend(controls)


@pytest.fixture
def analyzer() -> HVACAnalyzer:
    """回傳 analysis tab 使用的 calculation facade。

回傳：
    HVACAnalyzer：函數計算或處理後的結果。"""
    return HVACAnalyzer()


def test_hvac_basic_energy_calculations(analyzer: HVACAnalyzer) -> None:
    """涵蓋核心 compressor、heat-exchanger 與 throttling equations。

參數：
    analyzer (HVACAnalyzer): 函數輸入值。

回傳：
    無。"""
    assert analyzer.calculate_compression_ratio(2.0, 10.0) == pytest.approx(5.0)
    assert analyzer.calculate_compressor_work(2.0, 10.0, 30.0) == pytest.approx(40.0)
    assert analyzer.calculate_compressor_work_heat_transfer(2.0, 10.0, 30.0, 4.0) == pytest.approx(44.0)
    assert analyzer.calculate_evaporator_heat_rate(2.0, 10.0, 30.0) == pytest.approx(40.0)
    assert analyzer.calculate_condenser_heat_rate(2.0, 30.0, 10.0) == pytest.approx(40.0)
    assert analyzer.calculate_throttling_value(30.0, 10.0) == pytest.approx(30.0)


def test_hvac_efficiency_and_entropy_calculations(analyzer: HVACAnalyzer) -> None:
    """涵蓋 dimensionless efficiency 與 entropy-generation calculations。

參數：
    analyzer (HVACAnalyzer): 函數輸入值。

回傳：
    無。"""
    assert analyzer.calculate_Sgen(100.0, 125.0) == pytest.approx(25.0)
    assert analyzer.calculate_Sgen_flow(2.0, 100.0, 125.0) == pytest.approx(50.0)
    assert analyzer.calculate_isentropic_efficiency(10.0, 30.0, 20.0) == pytest.approx(0.5)
    assert analyzer.calculate_volumetric_efficiency(0.1, 0.01, 0.02) == pytest.approx(1.05)


def test_hvac_invalid_denominators_raise_value_error(analyzer: HVACAnalyzer) -> None:
    """明確處理無效 physical inputs，而不是回傳誤導性的零值。

參數：
    analyzer (HVACAnalyzer): 函數輸入值。

回傳：
    無。"""
    with pytest.raises((ValueError, ZeroDivisionError)):
        analyzer.calculate_compression_ratio(0.0, 10.0)
    assert analyzer.calculate_isentropic_efficiency(1.0, 2.0, 1.0) == pytest.approx(0.0)


def test_unit_converter_round_trip_and_unknown_unit(analyzer: HVACAnalyzer) -> None:
    """驗證 SI conversion 往返結果，以及拒絕不支援的 units。

參數：
    analyzer (HVACAnalyzer): 函數輸入值。

回傳：
    無。"""
    converter = UnitConverter()
    for prop_code, value, unit in (("T", 25.0, "C"), ("P", 2.0, "bar"), ("H", 300.0, "kJ/kg")):
        si_value = converter.convert_to_si(prop_code, value, unit)
        assert converter.convert_from_si(prop_code, si_value, unit) == pytest.approx(value)
    with pytest.raises(ValueError):
        converter.convert_to_si("P", 1.0, "not-a-unit")


def test_relative_humidity_percentage_round_trip() -> None:
    """RH 的 display percentage 與 canonical fraction 必須雙向正確轉換。

回傳：
    無。"""
    converter = UnitConverter()
    for display_value, canonical_value in ((0.0, 0.0), (50.0, 0.5), (88.0, 0.88), (100.0, 1.0)):
        assert converter.convert_to_si("RH", display_value, "%") == pytest.approx(canonical_value)
        assert converter.convert_from_si("RH", canonical_value, "%") == pytest.approx(display_value)


def test_thermo_state_validation_and_property_calculation() -> None:
    """執行 CoolProp-backed state validation 與一次一般 property query。

回傳：
    無。"""
    converter = UnitConverter()
    calculator = ThermoStateCalculator(converter)
    assert calculator.is_fluid_valid("R134a") is True
    assert calculator.is_fluid_valid("definitely-not-a-fluid") is False
    result = calculator.calculate_properties("Water", [("T", 25.0, "°C"), ("P", 1.0, "bar")])
    assert result
    assert any(key in result for key in ("T", "P", "H", "S"))


def test_psychrometric_calculator_returns_finite_properties() -> None:
    """以 realistic conditions 執行兩條受支援的 moist-air input paths。

回傳：
    無。"""
    calculator = PsychrometricCalculator()
    for result in (
        calculator.calculate_from_tdb_rh(298.15, 0.5, 0.0),
        calculator.calculate_from_tdb_twb(298.15, 290.15, 0.0),
    ):
        assert result
        numeric_values = [value for value in result.values() if isinstance(value, (int, float))]
        assert numeric_values
        assert all(math.isfinite(value) for value in numeric_values)


def test_psychrometric_relative_humidity_renders_percentage() -> None:
    """Canonical RH fraction 0.88 必須在實際 PsyModule output path 顯示為 88%。

回傳：
    無。"""
    module = PsyModule(UnitConverter(), DummyPage(), PsychrometricCalculator())
    mode = PsyModule.MODE_TDB_RH
    module.configure_ui_for_mode(mode)
    module.all_entries["psy_rh"]["val"].value = "88"

    output = module.calculate_psy(use_imperial=False, mode_key=mode)

    assert "88.00 %" in output
    assert "0.88 %" not in output


def test_psychrometric_ui_matches_trusted_model_contract() -> None:
    """Flet RH UI 輸入 15.5°C／88% 必須得到 trusted model 對應的 SI 結果。

回傳：
    無。"""
    module = PsyModule(UnitConverter(), DummyPage(), PsychrometricCalculator())
    mode = PsyModule.MODE_TDB_RH
    module.configure_ui_for_mode(mode)
    module.all_entries["psy_tdb"]["val"].value = "15.5"
    module.all_entries["psy_rh"]["val"].value = "88"

    output = module.calculate_psy(use_imperial=False, mode_key=mode)

    assert "大氣壓力 (Atmospheric Pressure)" in output
    assert "101325.0000 Pa" in output
    assert "計算濕球溫度 (Calculated Wet-Bulb Temp)" in output
    assert "14.29 °C" in output
    assert "0.009662 kg/kg" in output
    assert "40.0372 kJ/kg" in output
def test_every_analysis_option_switches_and_calculates(caplog: pytest.LogCaptureFixture) -> None:
    """Smoke-test 每個 dedicated view 已註冊的分析項目與其預設計算路徑。

    每個分析切換後只顯示自己的輸入區；以預設值計算時只能得到成功結果或以欄名
    提示的輸入錯誤，不得出現未預期的例外。

參數：
    caplog: pytest 的 log 擷取工具。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    analysis_views = {
        route_key: view for route_key, view in shell.views.items() if hasattr(view, "adapter")
    }
    total = 0
    with caplog.at_level(logging.ERROR, logger="Flet_ui.ui.analysis_module_adapter"):
        for route_key, view in analysis_views.items():
            shell.navigate(route_key)
            for definition in view.adapter.definitions:
                total += 1
                view._handle_tool_change(definition.key)
                assert definition.input_view.visible is True, definition.key
                visible_inputs = {
                    id(item.input_view) for item in view.adapter.definitions if item.input_view.visible
                }
                assert visible_inputs == {id(definition.input_view)}, definition.key
                view.perform_calculation(None)
                assert view.result_panel.status in {"success", "error"}, definition.key
                if view.result_panel.status == "success":
                    assert view.adapter.result_text, definition.key
    assert not caplog.records, [record.getMessage() for record in caplog.records]
    assert total == sum(len(view.adapter.definitions) for view in analysis_views.values())

    diagram_module = shell.views["ph_chart"].module
    assert "成功" in diagram_module.calculate_thermo_diagram(use_imperial=False)
