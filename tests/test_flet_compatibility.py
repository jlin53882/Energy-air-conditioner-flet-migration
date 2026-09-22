"""Regression tests for the Flet 1.0 migration boundary."""

from pathlib import Path

import flet as ft
import flet_charts as fch

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
        self.overlay = []

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
        state_calculator=state_calculator,
        formatter=PropertyFormatter(converter),
        page=page,
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


def test_launcher_uses_flet_only_entrypoint() -> None:
    """Keep the supported launcher on the Flet 1.0 runtime API."""
    launcher = Path(__file__).parents[1] / "run.py"
    source = launcher.read_text(encoding="utf-8")
    assert "ft.run(flet_main)" in source
    assert "ft.app" not in source
    assert "start_tkinter_gui" not in source
    assert "Tkinter" not in source
    assert not (launcher.parent / "Tkinter GUI").exists()
