"""Regression tests for the Flet 1.0 migration boundary."""

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
    """Provide the minimal page surface used by control construction tests."""

    def __init__(self) -> None:
        self.controls = []
        self.overlay = []

    def add(self, *controls) -> None:
        """Collect controls added by the application entry point."""
        self.controls.extend(controls)

    def update(self) -> None:
        """Match the page update method without starting a Flet session."""


def test_flet_1_api_surface_is_available() -> None:
    """Ensure the migrated APIs exist and removed APIs are not referenced."""
    assert ft.__version__ == "1.0.0"
    assert hasattr(ft, "run")
    assert hasattr(ft, "Button")
    assert hasattr(ft, "TabBar")
    assert hasattr(ft, "TabBarView")
    assert hasattr(ft, "Border")
    assert hasattr(fch, "MatplotlibChart")
    assert hasattr(ft, "app")  # compatibility alias remains, launcher uses ft.run
    assert not hasattr(ft, "ElevatedButton")


def test_flet_tabs_and_analysis_controls_construct() -> None:
    """Construct both migrated tabs without opening a desktop session."""
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
    """Keep tab content bounded so Flet 1 renders the complete scrollable tabs."""
    page = DummyPage()
    flet_main(page)

    tabs = page.controls[0]
    tab_bar_view = tabs.content.controls[1]
    assert all(isinstance(control, ft.Container) for control in tab_bar_view.controls)
    assert all(control.expand for control in tab_bar_view.controls)
    assert isinstance(tab_bar_view.controls[0].content, PropertyTab)
    assert isinstance(tab_bar_view.controls[1].content, AnalysisTab)


def test_flet_text_theme_styles_use_theme_style_parameter() -> None:
    """Prevent Flet 1 from treating TextThemeStyle as a TextStyle object."""
    for relative_path in (
        "Flet_ui/ui_components/property_tab.py",
        "Flet_ui/ui_components/analysis_tab.py",
    ):
        source = (Path(__file__).parents[1] / relative_path).read_text(encoding="utf-8")
        assert ", style=ft.TextThemeStyle" not in source
        assert "theme_style=ft.TextThemeStyle" in source


def test_launcher_uses_flet_only_entrypoint() -> None:
    """Keep the supported launcher on the Flet 1.0 runtime API."""
    launcher = Path(__file__).parents[1] / "run.py"
    source = launcher.read_text(encoding="utf-8")
    assert "ft.run(flet_main)" in source
    assert "ft.app" not in source
    assert "start_tkinter_gui" not in source
    assert "Tkinter" not in source
    assert not (launcher.parent / "Tkinter GUI").exists()
