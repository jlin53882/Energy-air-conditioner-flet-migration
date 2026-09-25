"""Flet 1.0 migration boundary 的 regression test。"""

import asyncio
import ast
from dataclasses import replace
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
from Flet_ui.ui.analysis_module_adapter import AnalysisModuleAdapter
from Flet_ui.ui.state import WorkspaceState
from Flet_ui.ui.views.thermo_diagram_view import ThermoDiagramView
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


def _control_tree_contains(root: object, target: object) -> bool:
    """深度搜尋 Flet 控制項樹，判斷目標控制項是否位於 root 之下。

參數：
    root: 搜尋起點控制項。
    target: 要尋找的控制項實例。

回傳：
    target 為 root 本身或其子孫控制項時回傳 True。"""
    if root is target:
        return True
    children = []
    content = getattr(root, "content", None)
    if content is not None and not isinstance(content, str):
        children.append(content)
    children.extend(getattr(root, "controls", None) or [])
    return any(_control_tree_contains(child, target) for child in children)


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
            # 欄名在外框之上；數值與單位選單合成同一個外框，單位位於欄位尾端。
            assert input_row.controls[0] is entry["label_control"]
            assert input_row.controls[1] is entry["field_box"]
            assert entry["field_box"].content.controls == [entry["val"], entry["unit"]]
            assert entry["val"].label is None
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


def test_property_unit_change_only_converts_selected_row() -> None:
    """單位變更只換算被選取的列，其他同性質列保持原值與單位。

    回傳：
        無。
    """
    converter = UnitConverter()
    state = WorkspaceState()
    property_tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=DummyPage(),
        query_service=PropertyQueryService(ThermoStateCalculator(converter).state_service),
        workspace_state=state,
    )
    first, second = property_tab.input_rows[:2]
    for row, value in ((first, "25"), (second, "20")):
        row["prop"].value = property_tab.prop_names_map["T"]
        row["prop"].on_select(None)
        row["val"].value = value
        assert row["unit"].value == "°C"

    first["unit"].value = "°F"
    first["unit"].on_select(None)

    assert float(first["val"].value) == pytest.approx(77.0)
    assert first["unit"].value == "°F"
    assert second["val"].value == "20"
    assert second["unit"].value == "°C"
    assert property_tab._last_prop_units[:2] == ["°F", "°C"]
    assert state.input_units["condition_0_T"] == "°F"
    assert state.input_units["condition_1_T"] == "°C"


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


def test_chart_routes_use_dedicated_diagram_view_without_shared_execute_button() -> None:
    """確認 P-h 與 T-s 圖頁使用專屬 ThermoDiagramView，且分析頁保留共用執行按鈕與結果卡。

回傳：
    無。
    """
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]

    for route_key in ("ph_chart", "ts_chart"):
        shell.navigate(route_key)
        diagram_view = shell.views[route_key]
        assert isinstance(diagram_view, ThermoDiagramView)
        # 熱力圖使用專屬繪圖按鈕，不應該再有共用的 AnalysisWorkspace 執行按鈕。
        assert not hasattr(diagram_view, "workspace")

    shell.navigate("compressor")
    compressor_view = shell.views["compressor"]
    assert compressor_view.workspace.action_bar.visible is True
    assert compressor_view.workspace.result_card.visible is True


def test_diagram_route_activation_is_owned_by_diagram_view() -> None:
    """F4 regression：flet_app.py 不再特判 ph_chart/ts_chart，改由 View 自行處理。

    確認：
    1. AppShell 的 generic route-activation 協定（``activate_route``）
       確實驅動了 ph_chart -> P-h、ts_chart -> T-s 的模式切換。
    2. flet_app.py 原始碼中不再出現 diagram-specific route dispatch
       （``route_key == "ph_chart"`` / ``ts_chart``，或 dict 形式的
       ``route_to_mode`` 對照表），確保 Composition Root 不知道 diagram
       internals；同時排除掉 ``ThermoDiagramView`` 內部合法持有這張表
       的情形（該檔案 import 路徑不同，不會被這裡掃到）。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]

    shell.navigate("ph_chart")
    diagram_view = shell.views["ph_chart"]
    assert diagram_view.mode == "ph"
    assert diagram_view.module.diagram_dd.value == "P-h"

    shell.navigate("ts_chart")
    assert diagram_view.mode == "ts"
    assert diagram_view.module.diagram_dd.value == "T-s"

    flet_app_source = (
        Path(__file__).resolve().parent.parent / "Flet_ui" / "flet_app.py"
    ).read_text(encoding="utf-8")
    # 允許 views dict 內合法出現 "ph_chart"/"ts_chart" 作為 route -> view
    # 註冊 key；要排除的是曾經存在的 diagram-mode 特判／dispatch 邏輯。
    assert 'route_key == "ph_chart"' not in flet_app_source
    assert 'route_key == "ts_chart"' not in flet_app_source
    assert "route_to_mode" not in flet_app_source
    assert "set_diagram_type(" not in flet_app_source
    assert ".set_mode(" not in flet_app_source
    assert "on_route_change" not in flet_app_source


def test_analysis_module_adapter_rejects_duplicate_keys_across_modules() -> None:
    """F5 regression：不同模組間出現重複 analysis_id 必須 fail fast，不得 silent overwrite。

回傳：
    無。"""

    class _FakeModuleA:
        def get_analysis_definitions(self) -> dict:
            return {
                "Fake A": {
                    "analysis_id": "fake.shared_key",
                    "ui": ft.Container(),
                    "calc_func": lambda use_imperial: "A",
                }
            }

    class _FakeModuleB:
        def get_analysis_definitions(self) -> dict:
            return {
                "Fake B": {
                    "analysis_id": "fake.shared_key",
                    "ui": ft.Container(),
                    "calc_func": lambda use_imperial: "B",
                }
            }

    with pytest.raises(ValueError, match="Duplicate AnalysisDefinition key"):
        AnalysisModuleAdapter([_FakeModuleA(), _FakeModuleB()])


def test_chart_route_change_clears_previous_plot_contents() -> None:
    """確認 P-h 與 T-s 路由切換會清除舊圖表、狀態點及殘留表格。

回傳：
    無。
    """
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    diagram_view = shell.views["ph_chart"]
    module = diagram_view.module

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
    assert {"thermo_properties", "compressor", "evaporator", "condenser",
            "psychrometrics", "ph_chart", "ts_chart"} <= set(shell.views)
    assert shell.route_header.controls[0].value == "狀態查詢"


def test_navigation_routes_expose_dedicated_views_and_chart_choice() -> None:
    """確認路由切換命中各自的 dedicated view，而非共用單一 AnalysisTab。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]

    workspace_content = shell.workspace.content
    shell.navigate("compressor")
    compressor_view = shell.views["compressor"]
    assert compressor_view.active_key in {key for key, _ in compressor_view.adapter.tool_items()}
    assert shell.workspace.content is workspace_content
    assert shell.views["thermo_properties"].visible is False
    assert compressor_view.visible is True
    assert compressor_view.tool_selector.controls

    shell.navigate("ph_chart")
    chart_view = shell.views["ph_chart"]
    assert chart_view.module.diagram_dd.value == "P-h"

    shell.navigate("ts_chart")
    assert chart_view.module.diagram_dd.value == "T-s"


def test_dedicated_analysis_views_are_distinct_instances() -> None:
    """禁止所有 analysis routes 又指向同一個 generic view。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]

    compressor_view = shell.views["compressor"]
    evaporator_view = shell.views["evaporator"]
    condenser_view = shell.views["condenser"]
    psychrometrics_view = shell.views["psychrometrics"]

    assert compressor_view is not evaporator_view
    assert compressor_view is not condenser_view
    assert compressor_view is not psychrometrics_view
    assert evaporator_view is not condenser_view


def test_psychrometrics_view_retains_state_across_route_navigation() -> None:
    """確認跨頁後濕空氣分析容器不重複，且切換模式狀態於路由間保留。

    回傳：
        無。
    """
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    tab = shell.views["psychrometrics"]

    for route in ("compressor", "psychrometrics", "evaporator", "condenser", "psychrometrics"):
        shell.navigate(route)
        controls = tab.input_stack.controls
        assert len(controls) == len({id(control) for control in controls})

    tool_items = tab.adapter.tool_items()
    first_key, _first_label = tool_items[0]
    second_key, second_label = tool_items[1]
    assert tab.active_key == first_key

    tab.tool_selector._handle_select(second_key)
    assert tab.active_key == second_key
    assert tab.psy_module.all_entries["psy_rh"]["ui_row"].visible is (
        "已知乾球與相對濕度" in second_label
    )

    shell.navigate("compressor")
    assert tab.active_key == second_key


def test_route_switching_retains_valid_result_and_invalidates_on_tool_switch() -> None:
    """§26/§27 regression：route 切換保留各自畫面的合法結果；同畫面內切換 tool 才清空結果。

    情境（依 final-hardening 規格 §26 Route State）：
    1. Evaporator 計算出結果 A。
    2. 導覽到 Condenser 並計算出結果 B（不同 view/adapter 的獨立狀態）。
    3. 導覽回 Evaporator：結果 A 必須原封不動保留（route-retained valid
       result），不會被 Condenser 的計算或路由切換清空。
    4. 在同一個 Psychrometrics 畫面內切換 tool：stale 的舊 tool 結果不可
       繼續顯示為新 tool 的結果（正確的 stale invalidation，對應 §27
       Tool Switch Result Contract）。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]

    shell.navigate("evaporator")
    evaporator_view = shell.views["evaporator"]
    evaporator_view.workspace.action_bar.content.on_click(SimpleNamespace())
    assert evaporator_view.adapter.result_panel.status == "success"
    evaporator_result_a = evaporator_view.adapter.result_text

    shell.navigate("condenser")
    condenser_view = shell.views["condenser"]
    condenser_view.workspace.action_bar.content.on_click(SimpleNamespace())
    assert condenser_view.adapter.result_panel.status == "success"

    shell.navigate("evaporator")
    assert evaporator_view.adapter.result_panel.status == "success"
    assert evaporator_view.adapter.result_text == evaporator_result_a

    # 切換 tool 必須清空目前畫面的舊結果（select() 已設 status="empty"）；
    # evaporator 目前只有單一 tool，因此改用可切換的 psychrometrics 驗證。
    shell.navigate("psychrometrics")
    psychrometrics_view = shell.views["psychrometrics"]
    psychrometrics_view.workspace.action_bar.content.on_click(SimpleNamespace())
    assert psychrometrics_view.adapter.result_panel.status == "success"

    tool_items = psychrometrics_view.adapter.tool_items()
    other_key = next(key for key, _ in tool_items if key != psychrometrics_view.active_key)
    psychrometrics_view.tool_selector._handle_select(other_key)

    assert psychrometrics_view.active_key == other_key
    assert psychrometrics_view.adapter.result_panel.status == "empty"


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


def test_responsive_shell_collapses_sidebar() -> None:
    """確認窄視窗會收合側邊導覽，中版改為精簡圖示列。

回傳：
    無。"""
    page = DummyPage()
    page.width = 760
    flet_main(page)
    shell = page.controls[0]

    assert isinstance(shell.content_row, ft.Stack)
    assert shell.sidebar.visible is False
    assert shell.workspace_region.padding.left == 0
    page.width = 1024
    shell._on_resize(None)
    assert shell.sidebar.visible is True
    assert shell.sidebar.width == 76
    assert shell.workspace_region.padding.left == 76
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
    property_tab.input_rows[0]["val"].on_change(SimpleNamespace(control=property_tab.input_rows[0]["val"]))
    property_tab.set_output_unit_system("SI")
    assert len(query_calls) == 1
    assert property_tab.result_panel.status == "warning"
    assert property_tab.result_panel.metrics == {}
    assert property_tab._last_si_results is None
    assert property_tab.input_rows[0]["val"].value == "-1"

    property_tab.input_rows[0]["val"].value = "1000"
    property_tab.input_rows[2]["val"].value = "1"
    property_tab.perform_calculation(None)
    assert property_tab.raw_output.value == ""
    assert property_tab.result_panel.status == "error"


def test_global_unit_toggle_propagates_to_dedicated_analysis_views() -> None:
    """確認全域單位切換會同步套用至各 dedicated analysis view 的 adapter。

    PR #4 之後 dedicated view 不再擁有各自的 output_unit_toggle；
    ``WorkspaceState.output_unit_system`` 是唯一的 source of truth，
    透過 AppShell 頂部共用的 ``unit_toggle`` 切換。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    analysis_view = shell.views["compressor"]

    shell.unit_toggle.selected = ["Imperial"]
    shell.unit_toggle.on_change(SimpleNamespace(control=shell.unit_toggle))

    assert shell.state.output_unit_system == "Imperial"
    assert shell.unit_toggle.selected == ["Imperial"]
    assert shell.views["thermo_properties"].output_unit_system == "Imperial"
    assert analysis_view.adapter.output_unit_system == "Imperial"


def test_global_output_unit_change_preserves_compressor_input_value_and_unit() -> None:
    """確認全域輸出單位切換不會竄改壓縮機大氣壓力等 input 的 value / unit。

    Global SI/Imperial 只是「結果呈現」偏好，不是 force input units；
    使用者輸入的數值與所選單位必須維持不變，除非使用者自己修改 input unit。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    compressor_view = shell.views["compressor"]
    module = compressor_view.adapter.modules[0]

    atm = module.all_entries["cr_atm_p"]
    atm["val"].value = "99.5"
    atm["unit"].value = "kPa"

    shell.unit_toggle.selected = ["Imperial"]
    shell.unit_toggle.on_change(SimpleNamespace(control=shell.unit_toggle))

    assert atm["val"].value == "99.5"
    assert atm["unit"].value == "kPa"
    assert compressor_view.adapter.output_unit_system == "Imperial"

    shell.unit_toggle.selected = ["SI"]
    shell.unit_toggle.on_change(SimpleNamespace(control=shell.unit_toggle))

    assert atm["val"].value == "99.5"
    assert atm["unit"].value == "kPa"
    assert compressor_view.adapter.output_unit_system == "SI"


def test_psychrometric_dispatch_does_not_depend_on_display_label() -> None:
    """確認濕空氣 UI 模式切換與計算 dispatch 只依賴穩定 key，不依賴顯示 label。

    F3 regression：即使把 PsychrometricsView 目前選取的 definition.label
    改成任意自訂文字（模擬未來改文案／翻譯），只要 definition.key 仍是
    ``psychrometrics.tdb_rh``，RH 欄位的可見狀態與計算路徑都必須不變。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    psychrometrics_view = shell.views["psychrometrics"]
    adapter = psychrometrics_view.adapter

    rh_key = PsyModule.MODE_TDB_RH
    twb_key = PsyModule.MODE_TDB_TWB
    assert {rh_key, twb_key} == {definition.key for definition in adapter.definitions}

    # 惡意模擬：把 adapter 內部快取的 definition 換成 label 被改掉（但 key
    # 不變）的版本，確認 dispatch 完全不受影響。
    renamed = {
        key: (
            replace(definition, label="Renamed / Translated Label")
            if key == rh_key
            else definition
        )
        for key, definition in adapter._by_key.items()
    }
    adapter._by_key = renamed
    adapter.definitions = list(renamed.values())

    psychrometrics_view._handle_tool_change(rh_key)

    assert adapter.active_key == rh_key
    module = psychrometrics_view.psy_module
    assert module.all_entries["psy_rh"]["ui_row"].visible is True
    assert module.all_entries["psy_twb"]["ui_row"].visible is False

    module.all_entries["psy_tdb"]["val"].value = "25"
    module.all_entries["psy_rh"]["val"].value = "50"
    psychrometrics_view.workspace.action_bar.content.on_click(SimpleNamespace())

    assert adapter.result_panel.status == "success"


def test_psychrometric_definitions_expose_uniform_calculate_callable() -> None:
    """F6 regression：generic factory 不需要知道 psychrometric/mode_key。

    直接對 ``definition.calculate`` 呼叫 ``calculate(False)``，不透過
    adapter 或 ``definitions_from_module()`` 做任何額外綁定，證明
    ``PsyModule`` 已經自行把 ``mode_key`` 這個 module-specific 參數吸收
    完畢，暴露出來的就是統一的 ``Callable[[bool], str]``。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    psychrometrics_view = shell.views["psychrometrics"]
    adapter = psychrometrics_view.adapter

    rh_definition = adapter._by_key[PsyModule.MODE_TDB_RH]
    twb_definition = adapter._by_key[PsyModule.MODE_TDB_TWB]

    module = psychrometrics_view.psy_module
    module.all_entries["psy_tdb"]["val"].value = "25"
    module.all_entries["psy_twb"]["val"].value = "20"
    module.all_entries["psy_rh"]["val"].value = "88"

    # RH definition 必須真的以 RH 模式計算（忽略 TWB 欄位），TWB definition
    # 必須真的以 TWB 模式計算（忽略 RH 欄位）——確認兩個 closure 真的各自
    # 綁定到不同的 mode key，不是碰巧都能算出結果就通過。
    rh_output = rh_definition.calculate(False)
    twb_output = twb_definition.calculate(False)
    assert isinstance(rh_output, str)
    assert isinstance(twb_output, str)
    assert "大氣壓力" in rh_output
    assert "大氣壓力" in twb_output
    assert rh_output != twb_output

    direct_rh = module.calculate_psy(False, mode_key=PsyModule.MODE_TDB_RH)
    direct_twb = module.calculate_psy(False, mode_key=PsyModule.MODE_TDB_TWB)
    assert rh_output == direct_rh
    assert twb_output == direct_twb


def test_analysis_definition_factory_does_not_reference_calculation_mode() -> None:
    """F6 regression：generic factory *程式碼*（非 docstring）不得判斷 calculation_mode。

    依 final-hardening 規格 §21：docstring 內為了說明背景而提及
    ``PsyModule``/``mode_key`` 是允許的相容性說明，但 *production
    generic behavior* 不得依賴這些概念。這裡用 ``ast`` 剝除所有
    docstring/字串常數只保留可執行的程式碼結構後，確認
    ``calculation_mode``、``mode_key``、``psychrometric``、
    ``PsyModule``、``isinstance`` 都不會以任何識別字或字串字面值的形式
    出現在實際執行邏輯裡。

回傳：
    無。"""
    source_path = (
        Path(__file__).parents[1] / "Flet_ui" / "ui" / "analysis_definition.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_tokens = {"calculation_mode", "mode_key", "psychrometric", "PsyModule"}

    docstring_node_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            docstring = ast.get_docstring(node, clean=False)
            if docstring is not None:
                first_stmt = node.body[0] if node.body else None
                if (
                    isinstance(first_stmt, ast.Expr)
                    and isinstance(first_stmt.value, ast.Constant)
                ):
                    docstring_node_ids.add(id(first_stmt.value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden_tokens:
            raise AssertionError(f"生產程式碼中發現禁止識別字：{node.id}")
        if isinstance(node, ast.Attribute) and node.attr in forbidden_tokens:
            raise AssertionError(f"生產程式碼中發現禁止屬性存取：{node.attr}")
        if isinstance(node, ast.keyword) and node.arg in forbidden_tokens:
            raise AssertionError(f"生產程式碼中發現禁止關鍵字參數：{node.arg}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_node_ids:
                continue
            lowered = node.value.lower()
            if any(token.lower() in lowered for token in forbidden_tokens):
                raise AssertionError(f"生產程式碼中發現禁止字串字面值：{node.value!r}")


def test_generic_adapter_only_requires_uniform_calculate_callable() -> None:
    """F6 regression：adapter 對任意假模組只要求統一 calculate 簽章。

    用一個完全與 psychrometric 無關的 fake module 建立
    ``AnalysisModuleAdapter``，確認不提供 ``calculation_mode`` 也能正常
    完成 tool-selection 與 calculate dispatch，證明 generic adapter
    contract 真的只要求 ``Callable[[bool], str]``。

回傳：
    無。"""

    class _FakeModule:
        def get_analysis_definitions(self) -> dict:
            return {
                "Fake Tool": {
                    "analysis_id": "fake.generic_tool",
                    "ui": ft.Container(),
                    "calc_func": lambda use_imperial: "fake-ok",
                }
            }

    adapter = AnalysisModuleAdapter([_FakeModule()])
    assert adapter.active_key == "fake.generic_tool"
    adapter.calculate()
    assert adapter.result_panel.status == "success"


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


def _build_property_tab_with_fake_query(monkeypatch: pytest.MonkeyPatch) -> tuple[PropertyTab, list[object]]:
    """建立隔離查詢服務的 PropertyTab，並回傳呼叫紀錄。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        PropertyTab 與查詢請求紀錄。
    """
    converter = UnitConverter()
    service = PropertyQueryService(ThermoStateCalculator(converter).state_service)
    monkeypatch.setattr(service, "is_fluid_valid", lambda _fluid: True)
    monkeypatch.setattr(service, "set_reference_state", lambda *_args: None)
    calls: list[object] = []

    def query(request: object) -> dict[str, object]:
        """回傳固定 SI 性質，供 UI 結果狀態測試使用。

        參數：
            request: PropertyQueryService 收到的計算請求。

        回傳：
            完整的假設 SI 性質結果。
        """
        calls.append(request)
        return {
            "P": 1_000_000.0, "T": 298.15, "H": 300_000.0,
            "S": 1_000.0, "D": 10.0, "V": 0.1, "U": 250_000.0,
            "Q": 0.88, "phase": "gas",
        }

    monkeypatch.setattr(service, "query", query)
    tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=DummyPage(),
        query_service=service,
    )
    tab.update = lambda: None
    tab.show_error = lambda _message: None
    tab.input_rows[0]["val"].value = "1000"
    tab.input_rows[1]["val"].value = "25"
    return tab, calls


def _calculate_property_tab(tab: PropertyTab) -> None:
    """執行一次測試用狀態查詢。

    參數：
        tab: 已設定兩個有效性質輸入的 PropertyTab。

    回傳：
        無。
    """
    tab.perform_calculation(None)
    assert tab.result_panel.status == "success"


def test_property_result_becomes_stale_after_numeric_input_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """數值輸入改變後清除舊結果，切換輸出單位也不會恢復舊成功狀態。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)

    tab.input_rows[0]["val"].value = "2000"
    tab.input_rows[0]["val"].on_change(SimpleNamespace(control=tab.input_rows[0]["val"]))
    assert tab.result_panel.status != "success"
    assert tab._has_calculated_result is False
    assert tab._last_si_results is None
    assert tab._last_result_metadata == {}
    assert tab.result_panel.metrics == {}
    assert tab.result_panel.metadata == {}
    assert tab.raw_output.value == ""

    tab.set_output_unit_system("Imperial")
    assert tab.result_panel.status != "success"
    assert len(calls) == 1


def test_property_result_becomes_stale_after_fluid_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """流體改變後不得保留前一流體計算成功的結果。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, _calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)
    tab.fluid_tf.value = "R410A"
    tab.fluid_tf.on_change(SimpleNamespace(control=tab.fluid_tf))
    assert tab.result_panel.status != "success"
    assert tab._last_si_results is None


def test_property_result_becomes_stale_after_reference_state_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """參考狀態改變後使舊結果失效，避免誤認為新政策的計算結果。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, _calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)
    tab.ref_state_dd.value = "NBP"
    tab.ref_state_dd.on_select(SimpleNamespace(control=tab.ref_state_dd))
    assert tab.result_panel.status != "success"
    assert tab._last_si_results is None


def test_output_unit_change_reformats_unchanged_cached_result_without_requery(monkeypatch: pytest.MonkeyPatch) -> None:
    """未改輸入時切換輸出系統重繪快取結果，不再次呼叫查詢服務。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)
    tab.set_output_unit_system("Imperial")
    assert tab.result_panel.status == "success"
    assert tab.result_panel.metrics["Pressure"].endswith("psia")
    assert "Btu/lbm" in tab.raw_output.value
    assert len(calls) == 1


def test_extensive_toggle_off_does_not_use_hidden_mass(monkeypatch: pytest.MonkeyPatch) -> None:
    """廣延性質選項關閉後，即使隱藏質量欄仍有值也不再計算廣延量。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, calls = _build_property_tab_with_fake_query(monkeypatch)
    tab.extensive_toggle.value = True
    tab.extensive_toggle.on_change(SimpleNamespace(control=tab.extensive_toggle))
    tab.mass_tf.value = "10"
    _calculate_property_tab(tab)
    assert "總焓 (Total Enthalpy)" in tab.raw_output.value

    tab.extensive_toggle.value = False
    tab.extensive_toggle.on_change(SimpleNamespace(control=tab.extensive_toggle))
    tab.perform_calculation(None)

    assert tab.result_panel.status == "success"
    assert "廣延性質 (Extensive Properties)" not in tab.raw_output.value
    assert len(calls) == 2


def test_extensive_result_survives_output_unit_rerender(monkeypatch: pytest.MonkeyPatch) -> None:
    """輸出單位切換保留上次成功快照中的廣延性質並換成英制單位。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, calls = _build_property_tab_with_fake_query(monkeypatch)
    tab.extensive_toggle.value = True
    tab.extensive_toggle.on_change(SimpleNamespace(control=tab.extensive_toggle))
    tab.mass_tf.value = "10"
    _calculate_property_tab(tab)
    tab.set_output_unit_system("Imperial")

    assert "廣延性質 (Extensive Properties)" in tab.raw_output.value
    assert "lbm" in tab.raw_output.value
    assert "Btu" in tab.raw_output.value
    assert len(calls) == 1


def test_workspace_state_remembers_unit_per_row() -> None:
    """相同性質在不同條件列可保存不同的獨立輸入單位。

    回傳：
        無。
    """
    state = WorkspaceState()
    state.set_input_unit("condition_0_T", "°F")
    state.set_input_unit("condition_1_T", "°C")
    assert state.input_units == {"condition_0_T": "°F", "condition_1_T": "°C"}


def test_property_unit_lock_is_released_after_conversion_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """轉換器拋出例外後釋放單位更新鎖，後續單位事件仍可執行。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    converter = UnitConverter()
    tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=DummyPage(),
        query_service=PropertyQueryService(ThermoStateCalculator(converter).state_service),
    )
    row = tab.input_rows[0]
    row["prop"].value = tab.prop_names_map["T"]
    row["prop"].on_select(None)
    row["val"].value = "25"
    original_convert = converter.convert_to_si
    attempts: list[tuple[object, ...]] = []

    def fail_once(*args: object) -> float:
        """第一次呼叫時注入轉換錯誤，之後委派原轉換器。

        參數：
            args: 原始轉換器收到的位置參數。

        回傳：
            原始轉換器的標準 SI 值。
        """
        attempts.append(args)
        if len(attempts) == 1:
            raise RuntimeError("injected conversion failure")
        return original_convert(*args)

    monkeypatch.setattr(converter, "convert_to_si", fail_once)
    row["unit"].value = "°F"
    with pytest.raises(RuntimeError, match="injected conversion failure"):
        row["unit"].on_select(SimpleNamespace(control=row["unit"]))
    assert tab._is_updating_units is False

    row["unit"].value = "°F"
    row["unit"].on_select(SimpleNamespace(control=row["unit"]))
    assert tab._is_updating_units is False
    assert float(row["val"].value) == pytest.approx(77.0)


def test_property_reset_restores_optional_ui_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """重設清除結果與錯誤，並將可選區塊還原為一致的初始狀態。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, _calls = _build_property_tab_with_fake_query(monkeypatch)
    tab.input_rows[2]["prop"].visible = True
    tab.input_rows[2]["val"].visible = True
    tab.input_rows[2]["unit"].visible = True
    tab.condition_rows[2].visible = True
    tab.extensive_toggle.value = True
    tab._toggle_extensive(SimpleNamespace(control=tab.extensive_toggle))
    tab.mass_tf.value = "10"
    _calculate_property_tab(tab)
    tab._toggle_raw_output(None)
    tab.quantity_inputs[0].set_error("欄位錯誤")
    tab.set_output_unit_system("Imperial")
    tab.result_panel.set_error("測試錯誤")
    tab.fluid_tf.value = "R410A"
    tab.ref_state_dd.value = "NBP"

    tab._reset_inputs(None)

    assert all(row["val"].value == "" for row in tab.input_rows)
    assert all(not control.visible for control in tab.input_rows[2].values())
    assert tab.condition_rows[2].visible is False
    assert tab.extensive_toggle.value is False
    assert tab.extensive_section.visible is False
    assert tab.raw_output.visible is False
    assert tab.details_button.text == "查看詳細結果"
    assert tab.result_panel.status == "empty"
    assert tab.result_panel.metrics == {}
    assert tab.result_panel.metadata == {}
    assert tab.raw_output.value == ""
    assert tab.result_text.value == ""
    assert tab.mass_tf.value == ""
    assert tab.mass_tf.error_text is None
    assert tab._has_calculated_result is False
    assert tab._last_si_results is None
    assert tab._last_total_mass_kg is None
    assert tab._last_result_metadata == {}
    assert tab.fluid_tf.value == "R410A"
    assert tab.ref_state_dd.value == "NBP"
    assert tab.output_unit_system == "Imperial"
    assert tab.input_rows[0]["val"].error_text is None
    assert tab.quantity_inputs[0].error_control.visible is False


def test_failed_recalculation_clears_previous_result_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """重新計算失敗時清除前一次成功結果的所有面板快照。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, _calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)
    assert tab.raw_output.value

    def fail_query(_request: object) -> dict[str, object]:
        """模擬查詢服務在重新計算時失敗。

        參數：
            _request: 查詢服務收到的計算請求。

        回傳：
            不會回傳；此函式會模擬領域查詢錯誤。
        """
        raise RuntimeError("injected query failure")

    monkeypatch.setattr(tab.query_service, "query", fail_query)
    tab.perform_calculation(None)

    assert tab.result_panel.status == "error"
    assert tab.result_panel.metrics == {}
    assert tab.result_panel.metadata == {}
    assert tab.raw_output.value == ""
    assert tab._has_calculated_result is False
    assert tab._last_si_results is None
    assert tab._last_total_mass_kg is None
    assert tab._last_result_metadata == {}
    assert tab._last_input_summary == ""
    assert tab._last_formatted_output == ""
    assert tab.result_text.value == ""
    assert tab.raw_output.value == ""
    assert tab.copy_result_button.disabled is True


@pytest.mark.parametrize(
    "semantic_change",
    ("property", "mode", "ideal_gas", "third_condition", "mass", "extensive"),
)

def test_all_semantic_controls_invalidate_cached_property_result(
    monkeypatch: pytest.MonkeyPatch, semantic_change: str
) -> None:
    """各計算語意控制改變後，舊結果均不得保留為目前輸入的成功結果。

    參數：
        monkeypatch: pytest 的屬性替換工具。
        semantic_change: 要模擬的語意輸入控制類型。

    回傳：
        無。
    """
    tab, _calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)

    if semantic_change == "property":
        row = tab.input_rows[0]
        row["prop"].value = tab.prop_names_map["H"]
        row["prop"].on_select(SimpleNamespace(control=row["prop"]))
    elif semantic_change == "mode":
        tab.mode_dd.value = "Water (水/水蒸氣)"
        tab.mode_dd.on_select(SimpleNamespace(control=tab.mode_dd))
    elif semantic_change == "ideal_gas":
        tab.ideal_gas_cb.value = True
        tab.ideal_gas_cb.on_change(SimpleNamespace(control=tab.ideal_gas_cb))
    elif semantic_change == "third_condition":
        tab.input_rows[2]["val"].value = "1"
        tab.input_rows[2]["val"].on_change(
            SimpleNamespace(control=tab.input_rows[2]["val"])
        )
    elif semantic_change == "mass":
        tab.mass_tf.value = "10"
        tab.mass_tf.on_change(SimpleNamespace(control=tab.mass_tf))
    elif semantic_change == "extensive":
        tab.extensive_toggle.value = True
        tab.extensive_toggle.on_change(SimpleNamespace(control=tab.extensive_toggle))

    assert tab.result_panel.status == "warning"
    assert tab._last_si_results is None


def test_property_unit_representation_change_preserves_calculated_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """輸入單位切換後保持物理量不變，不清除結果或重複查詢。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)
    row = tab.input_rows[0]
    assert row["unit"].value == "kPa"

    row["unit"].value = "MPa"
    row["unit"].on_select(SimpleNamespace(control=row["unit"]))

    assert float(row["val"].value) == pytest.approx(1.0)
    assert row["unit"].value == "MPa"
    assert tab.result_panel.status == "success"
    assert len(calls) == 1


def test_mass_unit_representation_change_preserves_extensive_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """質量顯示單位換算保留標準質量快照，並可隨輸出系統重新格式化。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, calls = _build_property_tab_with_fake_query(monkeypatch)
    tab.extensive_toggle.value = True
    tab.extensive_toggle.on_change(SimpleNamespace(control=tab.extensive_toggle))
    tab.mass_tf.value = "10"
    _calculate_property_tab(tab)

    tab.mass_unit_dd.value = "lbm"
    tab.mass_unit_dd.on_select(SimpleNamespace(control=tab.mass_unit_dd))
    assert float(tab.mass_tf.value) == pytest.approx(22.0462, rel=1e-5)
    assert tab.result_panel.status == "success"
    assert tab._last_total_mass_kg == pytest.approx(10.0)

    tab.set_output_unit_system("Imperial")
    assert "總質量 (Mass): 22.0462 lbm" in tab.raw_output.value
    assert "Btu" in tab.raw_output.value
    assert len(calls) == 1


def test_property_summary_and_detail_track_output_unit_without_requery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """輸出單位重繪更新摘要與詳細資料，但保留輸入快照且不重查詢。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)
    si_summary = tab.result_text.value
    input_summary = tab._last_input_summary
    si_output = tab._last_formatted_output

    assert "計算模式" in si_summary
    assert "R32" in si_summary
    assert "參考狀態" in si_summary
    assert "已知:" in si_summary
    assert "1000 kPa" in si_summary
    assert "25 °C" in si_summary
    assert "輸出單位: SI" in si_summary
    assert si_output not in si_summary
    assert si_output in tab._compose_result_text()
    assert "kJ/kg" in si_output
    assert tab.raw_output.value == si_output
    assert len(calls) == 1

    tab.set_output_unit_system("Imperial")
    imperial_summary = tab.result_text.value
    imperial_output = tab._last_formatted_output

    assert tab._last_input_summary == input_summary
    assert "計算模式" in imperial_summary
    assert "R32" in imperial_summary
    assert "參考狀態" in imperial_summary
    assert "已知:" in imperial_summary
    assert "1000 kPa" in imperial_summary
    assert "25 °C" in imperial_summary
    assert "輸出單位: Imperial" in imperial_summary
    assert imperial_output not in imperial_summary
    assert "psia" in imperial_output
    assert "Btu/lbm" in imperial_output
    assert tab.raw_output.value == imperial_output
    assert imperial_output in tab._compose_result_text()
    assert len(calls) == 1


def test_property_raw_output_is_not_the_same_control_as_result_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """詳細文字控制項不得與輸入摘要控制項共用同一個 Flet 物件。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, _calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)

    assert tab.raw_output is not tab.result_text
    assert not hasattr(tab.result_panel, "raw_output")
    assert _control_tree_contains(tab.results_card, tab.result_text)
    assert _control_tree_contains(tab.controls[0], tab.results_card)
    assert not _control_tree_contains(tab.result_panel, tab.result_text)
    assert tab.raw_output.visible is False
    assert tab.result_text.visible is True
    assert tab.raw_output.value == tab._last_formatted_output
    assert tab.result_text.value != tab._compose_result_text()
    assert tab._last_formatted_output not in tab.result_text.value


def test_property_summary_does_not_duplicate_raw_detail_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """常駐摘要只列輸入與輸出單位，不重複完整格式化詳細結果。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, _calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)

    assert tab.result_text.visible is True
    assert tab.raw_output.visible is False
    assert "計算模式" in tab.result_text.value
    assert "R32" in tab.result_text.value
    assert "參考狀態" in tab.result_text.value
    assert "已知:" in tab.result_text.value
    assert "輸出單位: SI" in tab.result_text.value
    assert tab._last_formatted_output not in tab.result_text.value
    assert tab.result_text.value != tab._compose_result_text()
    assert tab.raw_output.value == tab._last_formatted_output


def test_property_detail_toggle_only_reveals_raw_formatted_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """詳細按鈕只展開 formatter 輸出，不改變簡潔摘要。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, _calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)
    summary = tab.result_text.value

    assert tab.raw_output.visible is False
    tab._toggle_raw_output(None)
    assert tab.raw_output.visible is True
    assert tab.raw_output.value == tab._last_formatted_output
    assert tab.result_text.value == summary

    tab._toggle_raw_output(None)
    assert tab.raw_output.visible is False
    assert tab.result_text.value == summary


def test_property_copy_result_contract_is_stable_across_unit_rerender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """複製內容由有效快照組成，切換輸出單位只改格式而不改摘要結構。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)
    copied: list[str] = []

    class ClipboardCapture:
        """收集測試中複製的文字，不存取作業系統剪貼簿。"""

        async def set(self, value: str) -> None:
            """記錄剪貼簿服務收到的內容。

            參數：
                value: 要複製的完整結果文字。

            回傳：
                無。
            """
            copied.append(value)

    monkeypatch.setattr(ft, "Clipboard", ClipboardCapture)
    assert tab._last_formatted_output not in tab.result_text.value
    assert tab._last_formatted_output in tab._compose_result_text()
    assert tab.result_text.value != tab._compose_result_text()
    asyncio.run(tab._copy_result(None))
    si_copy = copied[-1]
    assert tab._last_formatted_output in si_copy

    tab.set_output_unit_system("Imperial")
    assert tab._last_formatted_output not in tab.result_text.value
    assert tab._last_formatted_output in tab._compose_result_text()
    assert tab.result_text.value != tab._compose_result_text()
    asyncio.run(tab._copy_result(None))
    imperial_copy = copied[-1]
    assert tab._last_formatted_output in imperial_copy

    for result in (si_copy, imperial_copy):
        assert "計算模式" in result
        assert "R32" in result
        assert "已知:" in result
        assert "1000 kPa" in result
        assert "25 °C" in result
    assert "kJ/kg" in si_copy
    assert "Btu/lbm" in imperial_copy
    assert si_copy != imperial_copy
    assert len(calls) == 1


def test_property_results_follow_summary_detail_copy_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """驗證成功、詳情、單位重繪、輸入失效、重算與重設的完整呈現生命週期。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, calls = _build_property_tab_with_fake_query(monkeypatch)
    copied: list[str] = []

    class ClipboardCapture:
        """保留測試中的完整複製表示。"""

        async def set(self, value: str) -> None:
            """記錄剪貼簿收到的完整結果。

            參數：
                value: 完整複製表示。

            回傳：
                無。
            """
            copied.append(value)

    monkeypatch.setattr(ft, "Clipboard", ClipboardCapture)
    _calculate_property_tab(tab)
    assert len(calls) == 1
    assert tab.result_panel.metrics["Pressure"].endswith("kPa")
    assert tab.result_text.visible is True
    assert tab.raw_output.visible is False
    assert tab.details_button.disabled is False
    assert tab.copy_result_button.disabled is False
    assert tab._last_formatted_output not in tab.result_text.value

    summary = tab.result_text.value
    tab._toggle_raw_output(None)
    assert tab.raw_output.visible is True
    assert tab.raw_output.value == tab._last_formatted_output
    assert tab.result_text.value == summary
    asyncio.run(tab._copy_result(None))
    assert tab._last_formatted_output in copied[-1]

    tab.set_output_unit_system("Imperial")
    assert len(calls) == 1
    assert tab.result_panel.metrics["Pressure"].endswith("psia")
    assert "輸出單位: Imperial" in tab.result_text.value
    assert "psia" in tab.raw_output.value
    assert "Btu/lbm" in tab.raw_output.value
    asyncio.run(tab._copy_result(None))
    assert tab._last_formatted_output in copied[-1]

    tab.input_rows[0]["val"].value = "2000"
    tab.input_rows[0]["val"].on_change(SimpleNamespace(control=tab.input_rows[0]["val"]))
    assert tab.result_panel.status == "warning"
    assert tab._last_si_results is None
    assert tab._last_input_summary == ""
    assert tab._last_formatted_output == ""
    assert tab.result_text.value == ""
    assert tab.result_text.visible is False
    assert tab.raw_output.value == ""
    assert tab.raw_output.visible is False
    assert tab.details_button.disabled is True
    assert tab.copy_result_button.disabled is True

    _calculate_property_tab(tab)
    assert len(calls) == 2
    assert tab.result_panel.status == "success"
    tab._reset_inputs(None)
    assert tab.result_panel.status == "empty"
    assert tab.result_panel.metrics == {}
    assert tab.result_text.value == ""
    assert tab.result_text.visible is False
    assert tab.raw_output.value == ""
    assert tab.raw_output.visible is False
    assert tab._last_input_summary == ""
    assert tab._last_formatted_output == ""
    assert tab.copy_result_button.disabled is True
    assert tab.details_button.disabled is True


def test_property_stale_result_clears_copy_and_detail_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """語意輸入改變後不得再複製或展開前一筆成功結果。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, _calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)
    previous_summary = tab.result_text.value
    previous_detail = tab.raw_output.value
    tab._toggle_raw_output(None)
    assert tab.raw_output.visible is True

    tab.input_rows[0]["val"].value = "2000"
    tab.input_rows[0]["val"].on_change(SimpleNamespace(control=tab.input_rows[0]["val"]))

    copied: list[str] = []

    class ClipboardCapture:
        """收集是否錯誤複製了已失效的結果。"""

        async def set(self, value: str) -> None:
            """記錄剪貼簿服務收到的內容。

            參數：
                value: 要複製的文字。

            回傳：
                無。
            """
            copied.append(value)

    monkeypatch.setattr(ft, "Clipboard", ClipboardCapture)
    asyncio.run(tab._copy_result(None))

    assert copied == []
    assert tab._has_calculated_result is False
    assert tab.copy_result_button.disabled is True
    assert tab.raw_output.value == ""
    assert tab.raw_output.visible is False
    assert tab.result_text.value == ""
    assert tab.result_text.visible is False
    assert tab._last_input_summary == ""
    assert tab._last_formatted_output == ""
    assert previous_summary
    assert previous_detail


def test_property_reset_clears_presentation_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """重設清除摘要、格式化輸出、詳細文字與可複製快照。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, _calls = _build_property_tab_with_fake_query(monkeypatch)
    _calculate_property_tab(tab)
    tab._toggle_raw_output(None)
    assert tab._last_input_summary
    assert tab._last_formatted_output

    tab._reset_inputs(None)

    assert tab._last_input_summary == ""
    assert tab._last_formatted_output == ""
    assert tab.result_text.value == ""
    assert tab.result_text.visible is False
    assert tab.raw_output.value == ""
    assert tab.raw_output.visible is False
    assert tab.copy_result_button.disabled is True
    assert tab.details_button.disabled is True
    assert tab.result_panel.status == "empty"
    assert tab.result_panel.metrics == {}
    assert tab.result_panel.metadata == {}
    assert tab._has_calculated_result is False


def test_mass_unit_conversion_failure_rolls_back_without_partial_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """預期的質量換算錯誤會回復單位，保留原值與有效計算快照。

    參數：
        monkeypatch: pytest 的屬性替換工具。

    回傳：
        無。
    """
    tab, calls = _build_property_tab_with_fake_query(monkeypatch)
    tab.extensive_toggle.value = True
    tab.extensive_toggle.on_change(SimpleNamespace(control=tab.extensive_toggle))
    tab.mass_tf.value = "10"
    tab._on_mass_input_change(SimpleNamespace(control=tab.mass_tf))
    _calculate_property_tab(tab)
    assert tab.mass_unit_dd.value == "kg"
    assert tab._last_total_mass_kg == pytest.approx(10.0)

    def fail_mass_conversion(property_code: str, value: float, unit: str) -> float:
        """模擬質量顯示單位轉換發生可預期的領域錯誤。

        參數：
            property_code: 轉換的性質代碼。
            value: 原始質量值。
            unit: 原始顯示單位。

        回傳：
            不會回傳；此函式會注入轉換錯誤。
        """
        if property_code == "Mass" and unit == "kg":
            raise ValueError("injected mass conversion failure")
        return UnitConverter().convert_to_si(property_code, value, unit)

    monkeypatch.setattr(tab.unit_converter, "convert_to_si", fail_mass_conversion)
    tab.mass_unit_dd.value = "lbm"
    tab.mass_unit_dd.on_select(SimpleNamespace(control=tab.mass_unit_dd))

    assert tab.mass_unit_dd.value == "kg"
    assert tab._last_mass_unit == "kg"
    assert tab.mass_tf.value == "10"
    assert tab.mass_tf.error_text
    assert tab._last_total_mass_kg == pytest.approx(10.0)
    assert tab._has_calculated_result is True
    assert tab.result_panel.status == "success"
    assert len(calls) == 1


def test_mass_unit_unexpected_error_is_logged_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """非預期的質量轉換錯誤會記錄例外、回復欄位並保留錯誤傳播。

    參數：
        monkeypatch: pytest 的屬性替換工具。
        caplog: pytest 的日誌擷取工具。

    回傳：
        無。
    """
    tab, _calls = _build_property_tab_with_fake_query(monkeypatch)
    tab.update = lambda: None
    tab.mass_tf.value = "10"

    def fail_unexpectedly(_property_code: str, _value: float, _unit: str) -> float:
        """注入非預期程式錯誤，確認事件處理器不會無聲吞掉。

        參數：
            _property_code: 要轉換的性質代碼。
            _value: 原始質量值。
            _unit: 原始顯示單位。

        回傳：
            不會回傳；此函式會注入程式錯誤。
        """
        raise RuntimeError("injected programmer error")

    monkeypatch.setattr(tab.unit_converter, "convert_to_si", fail_unexpectedly)
    tab.mass_unit_dd.value = "lbm"

    with pytest.raises(RuntimeError, match="injected programmer error"):
        tab.mass_unit_dd.on_select(SimpleNamespace(control=tab.mass_unit_dd))

    assert tab.mass_unit_dd.value == "kg"
    assert tab._last_mass_unit == "kg"
    assert tab.mass_tf.value == "10"
    assert "非預期錯誤" in tab.mass_tf.error_text
    assert any(
        "Unexpected error while converting the extensive-property mass unit" in record.message
        for record in caplog.records
    )
