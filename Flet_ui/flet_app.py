# flet_app_re.py (主程式 - 負責依賴注入)
#
# PR #4（Analysis Workspace Migration）之後，此檔案不再依賴共用的
# ``AnalysisTab.set_category(...)`` 做 route switching，也不知道
# ``ph_chart`` / ``ts_chart`` 與 ``P-h`` / ``T-s`` 的對應關係 —— 每個
# route 直接映射到各自的 dedicated view；圖表 route 的啟用邏輯由
# ``ThermoDiagramView.activate_route()``（AppShell 的 generic route
# activation 協定）自行處理。

import flet as ft

from .ui.app_shell import AppShell
from .ui.theme import MONO_FONT_URL, TOKENS, workspace_theme
from .ui.state import WorkspaceState
from .ui.views.home_view import HomeView
from .ui.views.compressor_view import CompressorView
from .ui.views.evaporator_view import EvaporatorView
from .ui.views.condenser_view import CondenserView
from .ui.views.refrigeration_cycle_view import RefrigerationCycleView
from .ui.views.psychrometrics_view import PsychrometricsView
from .ui.views.air_process_view import AirProcessView
from .ui.views.psychrometric_chart_view import PsychrometricChartView
from .ui.views.thermo_diagram_view import ThermoDiagramView
from .ui.views.unit_converter_view import UnitConverterView
from .ui_components.analysis_modules.hvac_compressor_module import CompressorModule
from .ui_components.analysis_modules.hvac_condenser_module import CondenserModule
from .ui_components.analysis_modules.hvac_evaporator_module import EvaporatorModule
from .ui_components.analysis_modules.psy_module import PsyModule
from .ui_components.analysis_modules.psy_process_module import PsyProcessModule
from .ui_components.analysis_modules.psychrometric_chart_module import PsychrometricChartModule
from .ui_components.analysis_modules.refrigeration_cycle_module import RefrigerationCycleModule
from .ui_components.analysis_modules.thermo_diagram_module import ThermoDiagramModule
from .ui_components.property_tab import PropertyTab
from .ui_components.unit.HVACAnalyzer import HVACAnalyzer
from .ui_components.unit.PropertyFormatter import PropertyFormatter
from .ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from .ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from .ui_components.unit.UnitConverter import UnitConverter
from application.air_processes import AirProcessService
from application.property_queries import PropertyQueryService
from application.refrigeration import RefrigerationService


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
    page.fonts = {TOKENS.mono_font: MONO_FONT_URL}

    unit_converter = UnitConverter()
    workspace_state = WorkspaceState()
    state_calculator = ThermoStateCalculator(unit_converter)
    formatter = PropertyFormatter(unit_converter)
    property_query_service = PropertyQueryService(state_calculator.state_service)
    hvac_analyzer = HVACAnalyzer()
    psy_calculator = PsychrometricCalculator()
    # 錶壓換算的「海拔 → 大氣壓力」全系統共用濕空氣服務的同一個公式。
    pressure_from_altitude = psy_calculator.service.calculate_pressure_from_altitude

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
        pressure_from_altitude=pressure_from_altitude,
    )
    evaporator_module = EvaporatorModule(unit_converter=unit_converter, page=page, analyzer=hvac_analyzer)
    # 冷凝器㶲分析與冷凍循環共用同一個 application service。
    refrigeration_service = RefrigerationService(state_calculator.state_service)
    condenser_module = CondenserModule(
        unit_converter=unit_converter,
        page=page,
        analyzer=hvac_analyzer,
        state_calculator=state_calculator,
        refrigeration_service=refrigeration_service,
        pressure_from_altitude=pressure_from_altitude,
    )
    cycle_module = RefrigerationCycleModule(
        unit_converter=unit_converter,
        page=page,
        refrigeration_service=refrigeration_service,
        pressure_from_altitude=pressure_from_altitude,
    )
    psy_module = PsyModule(unit_converter=unit_converter, page=page, psy_calculator=psy_calculator)
    # 空氣處理與濕空氣線圖共用同一個 application service。
    air_process_service = AirProcessService(psy_calculator.service)
    air_process_module = PsyProcessModule(
        unit_converter=unit_converter, page=page, air_process_service=air_process_service
    )
    psychrometric_chart_module = PsychrometricChartModule(
        unit_converter=unit_converter, page=page, air_process_service=air_process_service
    )
    diagram_module = ThermoDiagramModule(unit_converter, page, hvac_analyzer, state_calculator)

    compressor_view = CompressorView(compressor_module, workspace_state=workspace_state)
    evaporator_view = EvaporatorView(evaporator_module, workspace_state=workspace_state)
    condenser_view = CondenserView(condenser_module, workspace_state=workspace_state)
    cycle_view = RefrigerationCycleView(cycle_module, workspace_state=workspace_state)
    psychrometrics_view = PsychrometricsView(psy_module, workspace_state=workspace_state)
    air_process_view = AirProcessView(air_process_module, workspace_state=workspace_state)
    psychrometric_chart_view = PsychrometricChartView(
        psychrometric_chart_module, workspace_state=workspace_state
    )
    diagram_view = ThermoDiagramView(diagram_module)

    analysis_views = {
        "compressor": compressor_view,
        "evaporator": evaporator_view,
        "condenser": condenser_view,
        "refrigeration_cycle": cycle_view,
        "psychrometrics": psychrometrics_view,
        "air_processes": air_process_view,
        "psychrometric_chart": psychrometric_chart_view,
    }
    # 首頁統計只使用各 dedicated view 實際註冊的分析定義數量。
    analysis_counts = {key: len(view.adapter.definitions) for key, view in analysis_views.items()}
    shell_ref: dict[str, AppShell] = {}

    def choose_fluid(fluid: str) -> None:
        """將常用冷媒捷徑套用至熱力性質工作區。

參數：
    fluid: 要選取的流體名稱。

回傳：
    無。"""
        shell_ref["shell"].navigate("thermo_properties")
        property_view.fluid_tf.value = fluid
        property_view.on_fluid_change(None)

    home_view = HomeView(
        lambda route_key: shell_ref["shell"].navigate(route_key),
        analysis_counts=analysis_counts,
        total_analyses=sum(analysis_counts.values()),
        on_fluid=choose_fluid,
    )
    views = {
        "home": home_view,
        "thermo_properties": property_view,
        "compressor": compressor_view,
        "evaporator": evaporator_view,
        "condenser": condenser_view,
        "refrigeration_cycle": cycle_view,
        "psychrometrics": psychrometrics_view,
        "air_processes": air_process_view,
        "ph_chart": diagram_view,
        "ts_chart": diagram_view,
        "psychrometric_chart": psychrometric_chart_view,
        "unit_converter": UnitConverterView(unit_converter),
    }

    def on_unit_system_change(unit_system: str) -> None:
        """更新全域輸出偏好並重新呈現各 dedicated view，不改寫輸入欄位單位。

參數：
    unit_system: 要套用的輸出單位系統。

回傳：
    無。"""
        property_view.set_output_unit_system(unit_system)
        for view in analysis_views.values():
            view.set_output_unit_system(unit_system)

    shell = AppShell(
        page,
        views,
        on_unit_system_change=on_unit_system_change,
        state=workspace_state,
    )
    shell_ref["shell"] = shell
    page.add(shell)
    page.update()


if __name__ == "__main__":
    ft.run(main)
