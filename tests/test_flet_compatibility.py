"""Flet 1.0 migration boundary 的 regression test。"""

from pathlib import Path

import flet as ft
import flet_charts as fch

from Flet_ui.flet_app import main as flet_main
from application.property_queries import PropertyQueryService
from Flet_ui.ui_components.analysis_tab import AnalysisTab
from Flet_ui.ui_components.property_tab import PropertyTab
from Flet_ui.ui_components.unit.HVACAnalyzer import HVACAnalyzer
from Flet_ui.ui_components.unit.PropertyFormatter import PropertyFormatter
from Flet_ui.ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from Flet_ui.ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter


class DummyPage:
    """提供 control construction tests 使用的最小 page surface。"""

    def __init__(self) -> None:
        self.controls = []
        self.overlay = []

    def add(self, *controls) -> None:
        """收集 application entry point 新增的 controls。

參數：
    controls (未指定型別): 函數輸入值。

回傳：
    無。"""
        self.controls.extend(controls)

    def update(self) -> None:
        """不啟動 Flet session，仍符合 page update method。

回傳：
    無。"""


def test_flet_1_api_surface_is_available() -> None:
    """確認已遷移 APIs 存在，且已移除 APIs 未被引用。

回傳：
    無。"""
    assert ft.__version__ == "1.0.0"
    assert hasattr(ft, "run")
    assert hasattr(ft, "Button")
    assert hasattr(ft, "TabBar")
    assert hasattr(ft, "TabBarView")
    assert hasattr(ft, "Border")
    assert hasattr(fch, "MatplotlibChart")
    assert hasattr(ft, "app")  # compatibility alias 仍保留，launcher 使用 ft.run
    assert not hasattr(ft, "ElevatedButton")


def test_flet_tabs_and_analysis_controls_construct() -> None:
    """不開啟 desktop session 建構兩個已遷移的 tabs。

回傳：
    無。"""
    page = DummyPage()
    converter = UnitConverter()
    state_calculator = ThermoStateCalculator(converter)

    property_tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=page,
        query_service=PropertyQueryService(state_calculator.state_service),
    )
    analysis_tab = AnalysisTab(
        unit_converter=converter,
        page=page,
        analyzer=HVACAnalyzer(),
        psy_calculator=PsychrometricCalculator(),
        state_calculator=state_calculator,
    )

    assert property_tab.controls
    assert analysis_tab.controls
    assert not property_tab.result_container.expand


def test_property_dropdown_selection_refreshes_units_through_flet_event() -> None:
    """Property Dropdown 的 `on_select` 必須更新 options、預設值與 tracking state。

回傳：
    無。"""
    page = DummyPage()
    converter = UnitConverter()
    state_calculator = ThermoStateCalculator(converter)
    property_tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=page,
        query_service=PropertyQueryService(state_calculator.state_service),
    )

    row = property_tab.input_rows[0]
    row["prop"].value = property_tab.prop_names_map["T"]
    assert row["prop"].on_select is not None
    row["prop"].on_select(None)

    option_values = [option.key for option in row["unit"].options]
    assert option_values == ["K", "°C", "°F"]
    assert row["unit"].value == "°C"
    assert property_tab._last_prop_units[0] == "°C"


def test_property_dropdown_transitions_keep_default_units() -> None:
    """T→H、H→V 與 D→V 都必須沿用 UnitConverter 的 default unit。

回傳：
    無。"""
    page = DummyPage()
    converter = UnitConverter()
    state_calculator = ThermoStateCalculator(converter)
    property_tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=page,
        query_service=PropertyQueryService(state_calculator.state_service),
    )

    row = property_tab.input_rows[0]
    for prop_code, expected_unit in (("T", "°C"), ("H", "kJ/kg"), ("V", "m³/kg")):
        row["prop"].value = property_tab.prop_names_map[prop_code]
        row["prop"].on_select(None)
        assert row["unit"].value == expected_unit
        assert property_tab._last_prop_units[0] == expected_unit

    second_row = property_tab.input_rows[1]
    second_row["prop"].value = property_tab.prop_names_map["D"]
    second_row["prop"].on_select(None)
    second_row["prop"].value = property_tab.prop_names_map["V"]
    second_row["prop"].on_select(None)
    assert second_row["unit"].value == "m³/kg"
    assert property_tab._last_prop_units[1] == "m³/kg"


def test_tab_views_wrap_content_for_flet_layout_constraints() -> None:
    """限制 tab content 範圍，讓 Flet 1 能渲染完整的可捲動 tabs。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)

    tabs = page.controls[0]
    tab_bar_view = tabs.content.controls[1]
    assert all(isinstance(control, ft.Container) for control in tab_bar_view.controls)
    assert all(control.expand for control in tab_bar_view.controls)
    assert isinstance(tab_bar_view.controls[0].content, PropertyTab)
    assert isinstance(tab_bar_view.controls[1].content, AnalysisTab)


def test_flet_text_theme_styles_use_theme_style_parameter() -> None:
    """防止 Flet 1 將 TextThemeStyle 視為 TextStyle object。

回傳：
    無。"""
    for relative_path in (
        "Flet_ui/ui_components/property_tab.py",
        "Flet_ui/ui_components/analysis_tab.py",
    ):
        source = (Path(__file__).parents[1] / relative_path).read_text(encoding="utf-8")
        assert ", style=ft.TextThemeStyle" not in source
        assert "theme_style=ft.TextThemeStyle" in source


def test_launcher_uses_flet_only_entrypoint() -> None:
    """讓支援的 launcher 使用 Flet 1.0 runtime API。

回傳：
    無。"""
    launcher = Path(__file__).parents[1] / "run.py"
    source = launcher.read_text(encoding="utf-8")
    assert "ft.run(flet_main)" in source
    assert "ft.app" not in source
    assert "start_tkinter_gui" not in source
    assert "Tkinter" not in source
    assert not (launcher.parent / "Tkinter GUI").exists()
