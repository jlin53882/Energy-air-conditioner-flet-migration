"""Phase 6C 的 explicit analysis dispatch metadata test。"""

from __future__ import annotations

from pathlib import Path

from Flet_ui.ui_components.analysis_tab import AnalysisTab
from Flet_ui.ui_components.unit.HVACAnalyzer import HVACAnalyzer
from Flet_ui.ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from Flet_ui.ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter


class DummyPage:
    """提供建立 analysis 所需的最小 page surface。"""

    def __init__(self) -> None:
        self.overlay = []
        self.controls = []

    def update(self) -> None:
        """接受 headless update。

回傳：
    無。"""


def test_analysis_definitions_have_stable_ids_and_explicit_modes() -> None:
    """Analysis dispatch metadata 不依賴 display-label prefix。

回傳：
    無。"""
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
