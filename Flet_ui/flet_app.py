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

# 定義主函數
def main(page: ft.Page) -> None:
    """Compose HVAC views and mount the navigation shell without changing calculations."""
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
        """Select the registered HVAC analysis within its dedicated sidebar route."""
        route = ROUTE_BY_KEY[route_key]
        if route.analysis_category:
            analysis_view.set_category(route.analysis_category)
        if route_key == "ph_chart":
            diagram_module.diagram_dd.value = "P-h"
        elif route_key == "ts_chart":
            diagram_module.diagram_dd.value = "T-s"

    def on_analysis_unit_change(event: ft.ControlEvent) -> None:
        """Route legacy analysis output toggles through the shell's shared preference."""
        selected = next(iter(event.control.selected), "SI")
        shell_ref["shell"].set_output_unit_system(selected)

    analysis_view.output_unit_toggle.on_change = on_analysis_unit_change

    def on_unit_system_change(unit_system: str) -> None:
        """Re-render outputs globally while leaving independently selected input units alone."""
        property_view.set_output_unit_system(unit_system)
        analysis_view.output_unit_toggle.selected = [unit_system]
        analysis_view.on_output_unit_change(None)

    def choose_fluid(fluid: str) -> None:
        """Apply a context-panel refrigerant shortcut to the property workspace."""
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