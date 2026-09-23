"""Flet 1.0 migration boundary 的 regression test。"""

from pathlib import Path
from subprocess import run
from sys import executable
from types import SimpleNamespace

import flet as ft
import flet_charts as fch
import pytest

from Flet_ui.flet_app import main as flet_main
from application.property_queries import PropertyQueryService
from Flet_ui.ui_components.analysis_modules.psy_module import PsyModule
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


def test_flet_matplotlib_backend_survives_chart_helper_import() -> None:
    """ThermoDiagramModule 載入後不得把 Flet Charts backend 覆蓋成 SVG。

回傳：
    無。"""
    result = run(
        [
            executable,
            "-c",
            "import matplotlib; import Flet_ui.ui_components.analysis_modules.thermo_diagram_module; print(matplotlib.get_backend())",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "module://flet_charts.matplotlib_backends.backend_flet_agg" in result.stdout
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


def test_property_unit_dropdown_selection_converts_and_syncs_values() -> None:
    """Property unit Dropdown 的 production selection event 必須換算並同步同 property rows。

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
    first, second = property_tab.input_rows[:2]
    for row, value in ((first, "25"), (second, "20")):
        row["prop"].value = property_tab.prop_names_map["T"]
        row["prop"].on_select(None)
        row["val"].value = value
        assert row["unit"].value == "°C"
        assert row["unit"].on_select is not None

    first["unit"].value = "°F"
    first["unit"].on_select(None)

    assert float(first["val"].value) == pytest.approx(77.0)
    assert float(second["val"].value) == pytest.approx(68.0)
    assert first["unit"].value == second["unit"].value == "°F"
    assert property_tab._last_prop_units[:2] == ["°F", "°F"]


def test_property_pressure_unit_dropdown_converts_kpa_to_bar() -> None:
    """Pressure unit selection 必須透過 production event 將 kPa 換算為 bar。

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
    row["val"].value = "100"
    assert row["unit"].value == "kPa"
    assert row["unit"].on_select is not None
    row["unit"].value = "bar"
    row["unit"].on_select(None)
    assert float(row["val"].value) == pytest.approx(1.0)
    assert property_tab._last_prop_units[0] == "bar"


def test_psychrometric_unit_dropdowns_use_selection_event_and_sync_temperature() -> None:
    """PsyModule 的乾球／濕球與海拔 unit Dropdown 必須使用 selection event。

回傳：
    無。"""
    page = DummyPage()
    analysis_tab = AnalysisTab(
        unit_converter=UnitConverter(),
        page=page,
        analyzer=HVACAnalyzer(),
        psy_calculator=PsychrometricCalculator(),
        state_calculator=ThermoStateCalculator(UnitConverter()),
    )
    module = next(item for item in analysis_tab.modules_to_load if isinstance(item, PsyModule))
    tdb = module.all_entries["psy_tdb"]
    twb = module.all_entries["psy_twb"]
    altitude = module.all_entries["psy_alt"]
    assert tdb["unit"].on_select is not None
    assert twb["unit"].on_select is not None
    assert altitude["unit"].on_select is not None

    tdb["val"].value = "25"
    twb["val"].value = "20"
    tdb["unit"].value = "°F"
    tdb["unit"].on_select(SimpleNamespace(control=tdb["unit"]))
    assert float(tdb["val"].value) == pytest.approx(77.0)
    assert float(twb["val"].value) == pytest.approx(68.0)
    assert tdb["unit"].value == twb["unit"].value == "°F"

    altitude["val"].value = "1"
    altitude["unit"].value = "ft"
    altitude["unit"].on_select(SimpleNamespace(control=altitude["unit"]))
    assert float(altitude["val"].value) == pytest.approx(3.28084, rel=1e-5)


def test_dropdown_unit_bindings_do_not_use_on_change() -> None:
    """所有 analysis unit Dropdown selection 都必須綁定 `on_select`。

回傳：
    無。"""
    root = Path(__file__).parents[1] / "Flet_ui"
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert '"unit"].on_change' not in source, path
        assert "unit_dd.on_change" not in source, path
def test_analysis_output_toggle_reformats_existing_result() -> None:
    """SI/Imperial selection event 必須重新格式化已存在的分析結果。

回傳：
    無。"""
    page = DummyPage()
    converter = UnitConverter()
    analysis_tab = AnalysisTab(
        unit_converter=converter,
        page=page,
        analyzer=HVACAnalyzer(),
        psy_calculator=PsychrometricCalculator(),
        state_calculator=ThermoStateCalculator(converter),
    )
    module = next(item for item in analysis_tab.modules_to_load if isinstance(item, PsyModule))
    analysis_tab.analysis_dd.value = "濕空氣性質 (已知乾球與相對濕度)"
    analysis_tab.on_analysis_change(None)
    module.all_entries["psy_tdb"]["val"].value = "25"
    module.all_entries["psy_rh"]["val"].value = "88"
    analysis_tab.calculate_analysis(None)
    si_result = analysis_tab.result_text.value
    analysis_tab.output_unit_toggle.selected = ["Imperial"]
    analysis_tab.output_unit_toggle.on_change(None)
    imperial_result = analysis_tab.result_text.value
    assert imperial_result != si_result
    assert "°F" in imperial_result


def test_analysis_selection_clears_cached_result_before_unit_refresh() -> None:
    """切換 analysis 後再切單位不得重算尚未執行的新 analysis。

回傳：
    無。"""
    converter = UnitConverter()
    analysis_tab = AnalysisTab(
        unit_converter=converter,
        page=DummyPage(),
        analyzer=HVACAnalyzer(),
        psy_calculator=PsychrometricCalculator(),
        state_calculator=ThermoStateCalculator(converter),
    )
    analysis_tab._has_calculated_result = True
    analysis_tab.analysis_dd.value = list(analysis_tab.analysis_map)[1]

    analysis_tab.on_analysis_change(None)

    assert analysis_tab._has_calculated_result is False


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
