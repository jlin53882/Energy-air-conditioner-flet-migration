# flet_app_re.py (主程式 - 負責依賴注入)
#
# PR #4（Analysis Workspace Migration）之後，此檔案不再依賴共用的
# ``AnalysisTab.set_category(...)`` 做 route switching，也不再對圖表路由
# 特別判斷 ``P-h`` / ``T-s`` —— 每個 route 直接映射到各自的 dedicated view，
# diagram type 由 ``ThermoDiagramView`` 自己管理。

import flet as ft

from .ui.app_shell import AppShell
from .ui.theme import TOKENS, workspace_theme
from .ui.state import WorkspaceState
from .ui.views.home_view import HomeView
from .ui.views.compressor_view import CompressorView
from .ui.views.evaporator_view import EvaporatorView
from .ui.views.condenser_view import CondenserView
from .ui.views.psychrometrics_view import PsychrometricsView
from .ui.views.thermo_diagram_view import ThermoDiagramView
from .ui_components.analysis_modules.hvac_compressor_module import CompressorModule
from .ui_components.analysis_modules.hvac_condenser_module import CondenserModule
from .ui_components.analysis_modules.hvac_evaporator_module import EvaporatorModule
from .ui_components.analysis_modules.psy_module import PsyModule
from .ui_components.analysis_modules.thermo_diagram_module import ThermoDiagramModule
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

    # --- 每個分析分類擁有自己的既有模組實例，不再共用單一 AnalysisTab。 ---
    compressor_module = CompressorModule(
        unit_converter=unit_converter,
        page=page,
        analyzer=hvac_analyzer,
        state_calculator=state_calculator,
        property_query_service=property_query_service,
    )
    evaporator_module = EvaporatorModule(unit_converter=unit_converter, page=page, analyzer=hvac_analyzer)
    condenser_module = CondenserModule(
        unit_converter=unit_converter, page=page, analyzer=hvac_analyzer, state_calculator=state_calculator
    )
    psy_module = PsyModule(unit_converter=unit_converter, page=page, psy_calculator=psy_calculator)
    diagram_module = ThermoDiagramModule(unit_converter, page, hvac_analyzer, state_calculator)

    compressor_view = CompressorView(compressor_module, workspace_state=workspace_state)
    evaporator_view = EvaporatorView(evaporator_module, workspace_state=workspace_state)
    condenser_view = CondenserView(condenser_module, workspace_state=workspace_state)
    psychrometrics_view = PsychrometricsView(psy_module, workspace_state=workspace_state)
    diagram_view = ThermoDiagramView(diagram_module)

    shell_ref: dict[str, AppShell] = {}
    home_view = HomeView(lambda route_key: shell_ref["shell"].navigate(route_key))
    views = {
        "home": home_view,
        "thermo_properties": property_view,
        "compressor": compressor_view,
        "evaporator": evaporator_view,
        "condenser": condenser_view,
        "psychrometrics": psychrometrics_view,
        "ph_chart": diagram_view,
        "ts_chart": diagram_view,
    }

    def on_route_change(route_key: str) -> None:
        """讓熱力圖畫面依路由切換自己的 view-local mode，不再由 App root 判斷。

參數：
    route_key: 工作區內部使用的路由識別碼。

回傳：
    無。"""
        if route_key == "ph_chart":
            diagram_view.set_mode("ph")
        elif route_key == "ts_chart":
            diagram_view.set_mode("ts")

    def on_unit_system_change(unit_system: str) -> None:
        """更新全域輸出偏好並重新呈現各 dedicated view，不改寫輸入欄位單位。

參數：
    unit_system: 要套用的輸出單位系統。

回傳：
    無。"""
        property_view.set_output_unit_system(unit_system)
        for view in (compressor_view, evaporator_view, condenser_view, psychrometrics_view):
            view.set_output_unit_system(unit_system)

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
