"""Phase 6C tests for explicit analysis dispatch metadata."""

from __future__ import annotations

from pathlib import Path

from Flet_ui.ui_components.analysis_tab import AnalysisTab
from Flet_ui.ui_components.unit.HVACAnalyzer import HVACAnalyzer
from Flet_ui.ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from Flet_ui.ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter


class DummyPage:
    """Provide the minimal page surface needed for analysis construction."""

    def __init__(self) -> None:
        self.overlay = []
        self.controls = []

    def update(self) -> None:
        """Accept headless updates."""


def test_analysis_definitions_have_stable_ids_and_explicit_modes() -> None:
    """Analysis dispatch metadata is independent of display-label prefixes."""
    tab = AnalysisTab(
        unit_converter=UnitConverter(),
        page=DummyPage(),
        analyzer=HVACAnalyzer(),
        psy_calculator=PsychrometricCalculator(),
        state_calculator=ThermoStateCalculator(UnitConverter()),
    )
    definitions = list(tab.analysis_map.values())
    assert all(definition["analysis_id"] for definition in definitions)
    assert all(definition["calculation_mode"] in {"standard", "psychrometric"} for definition in definitions)

    source = (Path(__file__).parents[2] / "Flet_ui/ui_components/analysis_tab.py").read_text(
        encoding="utf-8"
    )
    assert 'startswith("濕空氣性質")' not in source
