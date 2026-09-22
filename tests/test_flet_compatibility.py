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
