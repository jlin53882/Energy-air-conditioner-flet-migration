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
from Flet_ui.ui_components.analysis_modules import thermo_diagram_module
from Flet_ui.ui_components.analysis_modules.thermo_diagram_module import ThermoDiagramModule
from Flet_ui.ui_components.analysis_tab import AnalysisTab
from Flet_ui.ui.state import WorkspaceState
from Flet_ui.ui_components.property_tab import PropertyTab
from Flet_ui.ui_components.unit.HVACAnalyzer import HVACAnalyzer
from Flet_ui.ui_components.unit.PropertyFormatter import PropertyFormatter
from Flet_ui.ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from Flet_ui.ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter


class DummyPage:
    """提供 control construction tests 使用的最小 page surface。"""

    def __init__(self) -> None:
        """初始化最小頁面替身，供 UI 控制項建構測試使用。

回傳：
    無。"""
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


def test_thermo_diagram_external_label_tracks_unit_selection() -> None:
    """熱力圖輸入單位切換時，框外欄位標籤必須同步更新。

回傳：
    無。
"""
    module = ThermoDiagramModule(UnitConverter(), None, None, None)
    entry = module.all_entries["td_P"]
    entry["val"].value = "0.16"
    entry["unit"].value = "kPa"
    entry["unit"].on_select(SimpleNamespace(control=entry["unit"]))

    assert entry["val"].value == "160"
    assert entry["label_control"].value == "壓力 P (kPa)"

    entry["unit"].value = "MPa"
    entry["unit"].on_select(SimpleNamespace(control=entry["unit"]))
    assert float(entry["val"].value) == pytest.approx(0.16)
    assert entry["label_control"].value == "壓力 P (MPa)"


def test_thermo_diagram_uses_consistent_pressure_units_and_refreshes_existing_chart(monkeypatch) -> None:
    """熱力圖輸入單位與座標設定一致，繪圖後刷新既有 chart control。

回傳：
    無。"""
    module = ThermoDiagramModule(UnitConverter(), None, None, None)
    assert module.all_entries["td_P"]["unit"].value == "MPa"

    module.input_pair_dd.value = "T-P"
    initial_chart = module.chart.figure
    monkeypatch.setattr(thermo_diagram_module, "check_coolprop_fluid", lambda _: (True, ""))
    monkeypatch.setattr(
        thermo_diagram_module,
        "generate_thermo_diagram",
        lambda **kwargs: kwargs["figure"],
    )

    result = module.calculate_thermo_diagram(use_imperial=False)

    assert result == "成功繪製 R134a 的 P-h 圖 (2 個點)。"
    assert module.chart.figure is initial_chart
    assert module.chart_container.content is module.chart


def test_flet_tabs_and_analysis_controls_construct() -> None:
    """不啟動桌面工作階段，直接建構已遷移的兩個分頁。

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
    assert property_tab.result_panel.status == "empty"
    assert property_tab.scroll is None
    assert property_tab.controls[-1] is property_tab.action_bar
    assert property_tab.controls[0].scroll == ft.ScrollMode.AUTO


def test_shared_analysis_input_labels_are_outside_field_borders() -> None:
    """三個分析頁的欄位標籤獨立於輸入框，單位切換不改動欄位名稱。

回傳：
    無。
"""
    converter = UnitConverter()
    analysis_tab = AnalysisTab(
        unit_converter=converter,
        page=DummyPage(),
        analyzer=HVACAnalyzer(),
        psy_calculator=PsychrometricCalculator(),
        state_calculator=ThermoStateCalculator(converter),
    )
    modules = {type(module).__name__: module for module in analysis_tab.modules_to_load}
    cases = {
        "CompressorModule": ("cr_pe", "cr_pc"),
        "EvaporatorModule": ("qe_h1", "qe_h2", "qe_m_dot"),
        "CondenserModule": ("qc_h1", "qc_h2", "qc_m_dot"),
    }

    for module_name, entry_keys in cases.items():
        for key in entry_keys:
            entry = modules[module_name].all_entries[key]
            input_row = entry["ui_row"]
            assert entry["label_control"] in input_row.controls[0].controls
            assert entry["val"] in input_row.controls[0].controls
            assert entry["val"].label is None
            assert entry["unit_label_control"] in input_row.controls[1].controls
            assert entry["unit"] in input_row.controls[1].controls
            assert entry["unit"].label is None

    for module_name, key in (
        ("CompressorModule", "cr_pe"),
        ("EvaporatorModule", "qe_h1"),
        ("CondenserModule", "qc_h1"),
    ):
        entry = modules[module_name].all_entries[key]
        original_label = entry["label_control"].value
        current_unit = entry["unit"].value
        new_unit = next(
            option.key for option in entry["unit"].options if option.key != current_unit
        )
        entry["unit"].value = new_unit
        entry["unit"].on_select(SimpleNamespace(control=entry["unit"]))
        assert entry["unit"].value == new_unit
        assert entry["label_control"].value == original_label


def test_property_dropdown_selection_refreshes_units_through_flet_event() -> None:
    """透過 Flet 選取事件驗證性質變更會更新單位選項、預設值與追蹤狀態。

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
    row["val"].value = "950"
    row["prop"].value = property_tab.prop_names_map["T"]
    assert row["prop"].on_select is not None
    row["prop"].on_select(None)

    option_values = [option.key for option in row["unit"].options]
    assert option_values == ["K", "°C", "°F"]
    assert row["unit"].value == "°C"
    assert row["val"].value == ""
    assert property_tab.quantity_inputs[0].label == "Temperature (溫度)"
    assert property_tab.quantity_inputs[0].label_control.value == "Temperature (溫度)"
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


def test_analysis_hides_generic_execute_button_for_thermodiagram() -> None:
    """熱力圖使用專屬繪圖按鈕，不顯示共用的執行分析按鈕。

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

    assert analysis_tab.calc_button_container.visible is True
    analysis_tab.analysis_dd.value = "熱力圖繪製"
    analysis_tab.on_analysis_change(None)

    heatmap = next(item for item in analysis_tab.modules_to_load if isinstance(item, ThermoDiagramModule))
    assert analysis_tab.calc_button_container.visible is False
    assert heatmap.plot_btn.visible is True

    analysis_tab.analysis_dd.value = next(name for name in analysis_tab.analysis_map if name != "熱力圖繪製")
    analysis_tab.on_analysis_change(None)
    assert analysis_tab.calc_button_container.visible is True


def test_chart_routes_hide_the_legacy_analysis_result_panel() -> None:
    """確認 P-h 與 T-s 圖頁隱藏舊共用結果面板，其他分析仍保留面板。

回傳：
    無。
    """
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]

    for route_key in ("ph_chart", "ts_chart"):
        shell.navigate(route_key)
        analysis_tab = shell.views[route_key]
        assert analysis_tab.result_container.visible is False
        assert analysis_tab.controls[-2].visible is False

    shell.navigate("compressor")
    analysis_tab = shell.views["compressor"]
    assert analysis_tab.result_container.visible is True
    assert analysis_tab.controls[-2].visible is True


def test_chart_route_change_clears_previous_plot_contents() -> None:
    """確認 P-h 與 T-s 路由切換會清除舊圖表、狀態點及殘留表格。

回傳：
    無。
    """
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    module = next(
        item for item in shell.views["ph_chart"].modules_to_load
        if isinstance(item, ThermoDiagramModule)
    )

    for source_route, target_route, target_diagram in (
        ("ph_chart", "ts_chart", "T-s"),
        ("ts_chart", "ph_chart", "P-h"),
    ):
        shell.navigate(source_route)
        figure = module.chart.figure
        axes = figure.axes[0]
        axes.plot([0, 1], [0, 1])
        axes.table(cellText=[["舊資料"]], colLabels=["舊表格"])
        module.result_text.value = "前一張圖表的結果"

        shell.navigate(target_route)

        assert module.diagram_dd.value == target_diagram
        assert module.chart.figure is figure
        assert len(figure.axes) == 1
        assert len(figure.axes[0].lines) == 0
        assert len(figure.axes[0].tables) == 0
        assert any(text.get_text() == "尚未繪製" for text in figure.axes[0].texts)
        assert module.result_text.value == "請輸入參數並點擊繪圖。"


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


def test_app_shell_replaces_top_level_tabs_and_exposes_implemented_routes() -> None:
    """確認 Flet 入口掛載工作區外殼，並提供現有工具的獨立導覽路由。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)

    shell = page.controls[0]
    assert isinstance(shell, ft.Column)
    assert shell.sidebar is not None
    assert shell.top_bar is not None
    assert shell.workspace is not None
    assert shell.context_panel is not None
    assert {"thermo_properties", "compressor", "evaporator", "condenser",
            "psychrometrics", "ph_chart", "ts_chart"} <= set(shell.views)
    assert shell.route_header.controls[0].value == "狀態查詢"


def test_navigation_routes_update_analysis_category_and_chart_choice() -> None:
    """確認路由切換選取既有分析分類與圖表，而非依顯示文字建立假功能。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]

    workspace_content = shell.workspace.content
    shell.navigate("compressor")
    assert shell.views["compressor"].active_category == "compressor"
    assert shell.views["compressor"].analysis_dd.value in shell.views["compressor"]._active_analysis_names
    assert shell.workspace.content is workspace_content
    assert shell.views["thermo_properties"].visible is False
    assert shell.views["compressor"].visible is True
    assert shell.views["compressor"].module_nav.controls

    shell.navigate("ph_chart")
    chart_module = next(
        module for module in shell.views["ph_chart"].modules_to_load
        if isinstance(module, ThermoDiagramModule)
    )
    assert chart_module.diagram_dd.value == "P-h"

    shell.navigate("ts_chart")
    assert chart_module.diagram_dd.value == "T-s"


def test_analysis_navigation_deduplicates_panels_and_identifies_selected_mode() -> None:
    """確認跨頁後分析容器不重複，並清楚顯示濕空氣模式選取狀態。

    回傳：
        無。
    """
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    tab = shell.views["psychrometrics"]

    for route in ("compressor", "psychrometrics", "evaporator", "condenser", "psychrometrics"):
        shell.navigate(route)
        controls = tab.controls_stack.controls
        assert len(controls) == len({id(control) for control in controls})
        assert sum(bool(control.visible) for control in controls) == 1

    first_mode = tab._active_analysis_names[0]
    second_mode = tab._active_analysis_names[1]
    assert tab.analysis_mode_status.visible is True
    assert first_mode in tab.analysis_mode_status.value
    buttons = tab.module_nav.controls
    assert buttons[0].style.bgcolor != buttons[1].style.bgcolor

    tab.module_nav.controls[1].on_click(SimpleNamespace())
    assert second_mode in tab.analysis_mode_status.value
    assert tab.module_nav.controls[0].style.bgcolor != tab.module_nav.controls[1].style.bgcolor

    shell.navigate("compressor")
    assert tab.analysis_mode_status.visible is False


def test_property_query_hides_unsupported_third_condition_and_aligns_controls() -> None:
    """確認未支援的第三條件入口隱藏，且性質與數值欄控制項等高對齊。

    回傳：
        無。
    """
    converter = UnitConverter()
    property_tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=DummyPage(),
        query_service=PropertyQueryService(ThermoStateCalculator(converter).state_service),
    )

    assert not hasattr(property_tab, "add_condition_button")
    assert all(not control.visible for control in property_tab.input_rows[2].values())
    assert property_tab.condition_rows[2].visible is False
    for row in property_tab.input_rows:
        assert row["prop"].label is None
        assert row["prop"].height == row["val"].height == row["unit"].height


def test_responsive_shell_collapses_sidebar_and_context_panel() -> None:
    """確認窄視窗會收合側邊導覽並隱藏選用情境面板。

回傳：
    無。"""
    page = DummyPage()
    page.width = 760
    flet_main(page)
    shell = page.controls[0]

    assert isinstance(shell.content_row, ft.Stack)
    assert shell.sidebar.visible is False
    assert shell.context_panel.visible is False
    assert shell.workspace_region.padding.left == 0
    page.width = 1024
    shell._on_resize(None)
    assert shell.sidebar.visible is True
    assert shell.sidebar.width == 76
    assert shell.workspace_region.padding.left == 76
    assert shell.context_panel.visible is False
    page.width = 760
    shell._on_resize(None)
    shell._toggle_sidebar(None)
    assert shell.sidebar.visible is True
    shell._on_keyboard_event(SimpleNamespace(key="Escape", ctrl=False))
    assert shell.sidebar.visible is False


def test_global_output_unit_switch_renders_new_metrics_without_mutating_inputs(monkeypatch) -> None:
    """確認輸出單位偏好能重新呈現指標，同時保留各欄位原輸入單位。

參數：
    monkeypatch: pytest 提供的替換工具，用於隔離熱力性質查詢服務。

回傳：
    無。"""
    converter = UnitConverter()
    service = PropertyQueryService(ThermoStateCalculator(converter).state_service)
    property_tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=DummyPage(),
        query_service=service,
    )
    property_tab.update = lambda: None
    property_tab.show_error = lambda _message: None
    property_tab.input_rows[0]["val"].value = "1000"
    property_tab.input_rows[1]["val"].value = "0"
    query_calls = []

    def fake_query(request):
        """以固定的 SI 性質值替代查詢服務，隔離輸出單位重繪測試。

參數：
    request: 傳入查詢服務的熱力性質請求。

回傳：
    模擬查詢結果中的 SI 性質值。"""
        query_calls.append(request)
        return {
            "P": 1_000_000.0,
            "T": 273.15,
            "H": 300_000.0,
            "S": 1_000.0,
            "D": 10.0,
            "V": 0.1,
            "Q": 0.88,
            "phase": "gas",
        }

    monkeypatch.setattr(service, "query", fake_query)

    property_tab.perform_calculation(None)
    si_pressure = property_tab.result_panel.metrics["Pressure"]
    original_units = [row["unit"].value for row in property_tab.input_rows[:2]]
    property_tab.set_output_unit_system("Imperial")

    assert si_pressure.endswith("kPa")
    assert property_tab.result_panel.metrics["Pressure"].endswith("psia")
    assert property_tab.result_panel.metrics["Quality"] == "0.8800"
    assert [row["unit"].value for row in property_tab.input_rows[:2]] == original_units
    assert property_tab.raw_output.value

    property_tab.input_rows[0]["val"].value = "-1"
    property_tab.set_output_unit_system("SI")
    assert len(query_calls) == 1
    assert property_tab.result_panel.status == "success"
    assert property_tab.result_panel.metrics["Pressure"].endswith("kPa")
    assert property_tab.input_rows[0]["val"].value == "-1"

    property_tab.input_rows[0]["val"].value = "1000"
    property_tab.input_rows[2]["val"].value = "1"
    property_tab.perform_calculation(None)
    assert property_tab.raw_output.value == ""
    assert property_tab.result_panel.status == "error"


def test_analysis_local_unit_toggle_updates_the_global_preference() -> None:
    """確認分析頁沿用的單位切換會同步更新全域偏好。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    analysis_view = shell.views["compressor"]
    analysis_view.output_unit_toggle.selected = ["Imperial"]
    analysis_view.output_unit_toggle.on_change(
        SimpleNamespace(control=analysis_view.output_unit_toggle)
    )

    assert shell.state.output_unit_system == "Imperial"
    assert shell.unit_toggle.selected == ["Imperial"]
    assert shell.views["thermo_properties"].output_unit_system == "Imperial"


def test_workspace_state_remembers_input_units_by_row_and_property() -> None:
    """確認工作區依輸入列與性質分別保存單位，不與輸出偏好混用。

回傳：
    無。"""
    converter = UnitConverter()
    state = WorkspaceState(input_units={"condition_0_T": "°F"})
    tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=DummyPage(),
        query_service=PropertyQueryService(ThermoStateCalculator(converter).state_service),
        workspace_state=state,
    )

    assert tab.input_rows[0]["unit"].value == "kPa"
    tab.input_rows[0]["prop"].value = tab.prop_names_map["T"]
    tab.input_rows[0]["prop"].on_select(None)
    assert tab.input_rows[0]["unit"].value == "°F"
    assert tab.input_rows[0]["val"].value == ""
    tab.set_output_unit_system("Imperial")
    assert state.output_unit_system == "Imperial"
    assert state.input_units["condition_0_T"] == "°F"


def test_reference_state_selector_uses_short_executable_codes_with_helper_copy() -> None:
    """確認參考狀態選單使用簡短代碼，並就近提供完整說明。

回傳：
    無。"""
    converter = UnitConverter()
    tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=DummyPage(),
        query_service=PropertyQueryService(ThermoStateCalculator(converter).state_service),
    )

    assert tab.ref_state_dd.value == "ASHRAE"
    assert {option.key for option in tab.ref_state_dd.options} == {"ASHRAE", "IIR", "NBP", "Default"}
    tab.ref_state_dd.value = "NBP"
    tab.on_ref_state_change(None)
    assert "Normal boiling point" in tab.reference_state_helper.value


def test_property_query_validation_errors_are_attached_to_the_offending_field() -> None:
    """確認無效壓力會在呼叫熱力服務前顯示於對應欄位旁。

回傳：
    無。"""
    converter = UnitConverter()
    state_calculator = ThermoStateCalculator(converter)
    tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=DummyPage(),
        query_service=PropertyQueryService(state_calculator.state_service),
    )
    tab.update = lambda: None
    tab.input_rows[0]["val"].value = "-1"
    tab.input_rows[1]["val"].value = "12"

    tab.perform_calculation(None)

    assert "大於 0" in tab.input_rows[0]["val"].error_text
    assert tab.quantity_inputs[0].error_control.visible is True
    assert "大於 0" in tab.quantity_inputs[0].error_control.value
    assert tab.input_rows[1]["val"].error_text is None
    assert tab.result_panel.status == "error"

    tab._reset_inputs(None)

    assert tab.input_rows[0]["val"].error_text is None
    assert tab.quantity_inputs[0].error_control.visible is False
    assert tab.quantity_inputs[0].error_control.value == ""
    assert tab.result_panel.status == "empty"


def test_relative_humidity_and_quality_validation_remain_distinct() -> None:
    """確認 RH 百分比與無單位乾度採用不同的欄位驗證範圍。

回傳：
    無。"""
    converter = UnitConverter()
    state_calculator = ThermoStateCalculator(converter)
    tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=DummyPage(),
        query_service=PropertyQueryService(state_calculator.state_service),
    )

    assert tab._validate_known_input("RH", "88", "%") == (88.0, None)
    assert tab._validate_known_input("Q", "0.88", "-") == (0.88, None)
    assert "0–100%" in tab._validate_known_input("RH", "120", "%")[1]
    assert "0–1" in tab._validate_known_input("Q", "1.2", "-")[1]


def test_flet_text_theme_styles_use_theme_style_parameter() -> None:
    """防止 Flet 1 將 TextThemeStyle 當成文字樣式物件使用。

回傳：
    無。"""
    for relative_path in (
        "Flet_ui/ui_components/property_tab.py",
        "Flet_ui/ui_components/analysis_tab.py",
    ):
        source = (Path(__file__).parents[1] / relative_path).read_text(encoding="utf-8")
        assert ", style=ft.TextThemeStyle" not in source


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
