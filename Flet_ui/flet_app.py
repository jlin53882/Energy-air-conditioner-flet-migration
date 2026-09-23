# flet_app_re.py (主程式 - 負責依賴注入)

import flet as ft

from .ui.app_shell import AppShell
from .ui.navigation import ROUTE_BY_KEY
from .ui.theme import TOKENS, workspace_theme
from .ui.state import WorkspaceState
from .ui.views.home_view import HomeView
from .ui_components.analysis_modules.thermo_diagram_module import ThermoDiagramModule
from .ui_components.analysis_tab import AnalysisTab
from .ui_components.property_tab import PropertyTab
from .ui_components.unit.HVACAnalyzer import HVACAnalyzer
from .ui_components.unit.PropertyFormatter import PropertyFormatter
from .ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from .ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from .ui_components.unit.UnitConverter import UnitConverter
from application.property_queries import PropertyQueryService


def main(page: ft.Page) -> None:
    """組合 HVAC 工作區畫面並掛載導覽外殼，不改動既有計算邏輯。

參數：
    page: Flet 提供的應用程式頁面。

回傳：
    無。"""
    page.title = "HVAC & Thermodynamics Engineering Workspace"
    page.window_width = 1440
    page.window_height = 960
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = workspace_theme()
    page.bgcolor = TOKENS.background

    unit_converter = UnitConverter()
    workspace_state = WorkspaceState()
    state_calculator = ThermoStateCalculator(unit_converter)
    formatter = PropertyFormatter(unit_converter)
    property_query_service = PropertyQueryService(state_calculator.state_service)
    hvac_analyzer = HVACAnalyzer()
    psy_calculator = PsychrometricCalculator()

    property_view = PropertyTab(
        unit_converter=unit_converter,
        formatter=formatter,
        page=page,
        query_service=property_query_service,
        workspace_state=workspace_state,
    )
    analysis_view = AnalysisTab(
        unit_converter=unit_converter,
        page=page,
        analyzer=hvac_analyzer,
        psy_calculator=psy_calculator,
        state_calculator=state_calculator,
        property_query_service=property_query_service,
    )
    diagram_module = next(
        module for module in analysis_view.modules_to_load
        if isinstance(module, ThermoDiagramModule)
    )
    shell_ref: dict[str, AppShell] = {}
    home_view = HomeView(lambda route_key: shell_ref["shell"].navigate(route_key))
    views = {
        "home": home_view,
        "thermo_properties": property_view,
        "compressor": analysis_view,
        "evaporator": analysis_view,
        "condenser": analysis_view,
        "psychrometrics": analysis_view,
        "ph_chart": analysis_view,
        "ts_chart": analysis_view,
    }

    def on_route_change(route_key: str) -> None:
        """依穩定路由鍵切換 HVAC 分析類別或圖表，並清除圖表舊內容。

參數：
    route_key: 工作區內部使用的路由識別碼。

回傳：
    無。"""
        route = ROUTE_BY_KEY[route_key]
        if route.analysis_category:
            analysis_view.set_category(route.analysis_category)
        if route_key == "ph_chart":
            diagram_module.set_diagram_type("P-h")
        elif route_key == "ts_chart":
            diagram_module.set_diagram_type("T-s")

    def on_analysis_unit_change(event: ft.ControlEvent) -> None:
        """將分析頁舊有的輸出單位切換同步到全域偏好。

參數：
    event: 含有目前選取單位系統的 Flet 控制事件。

回傳：
    無。"""
        selected = next(iter(event.control.selected), "SI")
        shell_ref["shell"].set_output_unit_system(selected)

    analysis_view.output_unit_toggle.on_change = on_analysis_unit_change

    def on_unit_system_change(unit_system: str) -> None:
        """更新全域輸出偏好並重新呈現輸出，不改寫各輸入欄位單位。

參數：
    unit_system: 要套用的輸出單位系統。

回傳：
    無。"""
        property_view.set_output_unit_system(unit_system)
        analysis_view.output_unit_toggle.selected = [unit_system]
        analysis_view.on_output_unit_change(None)

    def choose_fluid(fluid: str) -> None:
        """將常用冷媒捷徑套用至熱力性質工作區。

參數：
    fluid: 要選取的流體名稱。

回傳：
    無。"""
        shell_ref["shell"].navigate("thermo_properties")
        property_view.fluid_tf.value = fluid
        property_view.on_fluid_change(None)

    shell = AppShell(
        page,
        views,
        on_route_change=on_route_change,
        on_unit_system_change=on_unit_system_change,
        on_fluid_shortcut=choose_fluid,
        state=workspace_state,
    )
    shell_ref["shell"] = shell
    page.add(shell)
    page.update()


if __name__ == "__main__":
    ft.run(main)