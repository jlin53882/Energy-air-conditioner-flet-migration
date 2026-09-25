"""工作區狀態失效矩陣（docs/state-invalidation.md）的整合回歸測試。

每個測試都以真正的 ``Flet_ui.flet_app.main`` 建構完整工作區，驗證跨頁、單位切換、
錶壓／絕對壓、Reference State 與圖表生命週期的行為。
"""

from __future__ import annotations

from types import SimpleNamespace

import matplotlib.pyplot as plt
import pytest

from domain.refrigeration.condenser_exergy import analyze_condenser_exergy
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units import CanonicalUnitConverter
from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui_components.unit.UnitConverter import GAUGE_PRESSURE, UnitConverter


class DummyPage:
    """提供建構完整工作區所需的最小 page 介面。"""

    def __init__(self) -> None:
        """初始化控制項與 overlay 容器。

回傳：
    無。"""
        self.controls = []
        self.overlay = []

    def add(self, *controls) -> None:
        """收集進入點新增的控制項。

參數：
    controls: 要加入頁面的控制項。

回傳：
    無。"""
        self.controls.extend(controls)

    def update(self) -> None:
        """在沒有 Flet session 時接受更新呼叫。

回傳：
    無。"""


@pytest.fixture
def shell():
    """為每個測試建構獨立的完整工作區，避免測試之間共用輸入與結果狀態。

回傳：
    AppShell。"""
    page = DummyPage()
    flet_main(page)
    app_shell = page.controls[0]
    property_view = app_shell.views["thermo_properties"]
    # 物性查詢頁在未掛載時直接呼叫 update()／SnackBar；測試只關心狀態。
    property_view.update = lambda: None
    property_view.show_error = lambda _message: None
    yield app_shell
    plt.close("all")


def _switch_unit_system(shell, unit_system: str) -> None:
    """透過頂列的單位切換控制項改變全域輸出單位。

參數：
    shell: 工作區外殼。
    unit_system: "SI" 或 "Imperial"。

回傳：
    無。"""
    shell.unit_toggle.selected = [unit_system]
    shell.unit_toggle.on_change(SimpleNamespace(control=shell.unit_toggle))


def _calculate_property(shell, *, fluid: str = "R32", reference_state: str = "ASHRAE") -> float:
    """在物性查詢頁以 1000 kPa、0 °C 查詢狀態，回傳 SI 比焓。

參數：
    shell: 工作區外殼。
    fluid: 流體名稱。
    reference_state: 參考狀態代碼。

回傳：
    比焓（J/kg）。"""
    shell.navigate("thermo_properties")
    view = shell.views["thermo_properties"]
    if view.fluid_tf.value != fluid:
        view.fluid_tf.value = fluid
        view.on_fluid_change(None)
    if view.ref_state_dd.value != reference_state:
        view.ref_state_dd.value = reference_state
        view.on_ref_state_change(None)
    view.input_rows[0]["val"].value = "1000"
    view.input_rows[1]["val"].value = "0"
    view.perform_calculation(None)
    assert view.result_panel.status == "success", view.result_panel.message
    return float(view._last_si_results["H"])


def _entry_state(module, keys: list[str]) -> dict[str, tuple[str, str]]:
    """擷取輸入列目前的數值與單位。

參數：
    module: 分析模組。
    keys: 輸入列識別鍵。

回傳：
    識別鍵對應 (數值, 單位) 的字典。"""
    return {key: (module.all_entries[key]["val"].value, module.all_entries[key]["unit"].value) for key in keys}


def _plotted_line_count(figure) -> int:
    """回傳 figure 第一個座標軸上的線條數；沒有座標軸時為 0。

參數：
    figure: Matplotlib figure。

回傳：
    線條數。"""
    return len(figure.axes[0].lines) if figure.axes else 0


# ======================================================
# 1. 跨頁 A → B → A
# ======================================================
@pytest.mark.parametrize(
    ("route_key", "analysis_key"),
    [
        ("refrigeration_cycle", "cycle.vapor_compression"),
        ("refrigeration_cycle", "cycle.superheat_subcooling"),
        ("condenser", "condenser.exergy"),
        ("air_processes", "psychrometrics.cooling_coil"),
        ("psychrometric_chart", "psychrometric_chart.plot"),
    ],
)
def test_navigation_round_trip_keeps_inputs_result_and_chart(shell, route_key, analysis_key) -> None:
    """切到其他頁面再回來時，輸入、結果文字與圖表都保留。

參數：
    shell: 工作區外殼。
    route_key: 要測試的路由。
    analysis_key: 該路由內的分析項目。

回傳：
    無。"""
    shell.navigate(route_key)
    view = shell.views[route_key]
    view._handle_tool_change(analysis_key)
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    assert view.result_panel.status == "success", view.result_panel.message
    inputs_before = _entry_state(module, list(module.all_entries))
    result_before = view.adapter.result_text
    chart_visible_before = view.workspace.result_view.chart_column.visible

    shell.navigate("home")
    shell.navigate("thermo_properties")
    shell.navigate(route_key)

    assert view.active_key == analysis_key
    assert _entry_state(module, list(module.all_entries)) == inputs_before
    assert view.result_panel.status == "success"
    assert view.adapter.result_text == result_before
    assert view.workspace.result_view.chart_column.visible is chart_visible_before


def test_property_result_survives_navigation_round_trip(shell) -> None:
    """物性查詢結果在切到分析頁再回來後仍保留，且不需重新查詢。

回傳：
    無。"""
    enthalpy = _calculate_property(shell)
    view = shell.views["thermo_properties"]
    metrics_before = dict(view.result_panel.metrics)

    shell.navigate("refrigeration_cycle")
    shell.views["refrigeration_cycle"].perform_calculation(None)
    shell.navigate("thermo_properties")

    assert view.result_panel.status == "success"
    assert view._last_si_results["H"] == pytest.approx(enthalpy)
    assert view.result_panel.metrics == metrics_before


def test_thermo_diagram_keeps_plot_when_reentering_same_route(shell) -> None:
    """P-h 圖畫好後切到其他頁面再回到 P-h，已繪製的圖不被清除。

回傳：
    無。"""
    shell.navigate("ph_chart")
    module = shell.views["ph_chart"].module
    module.perform_plot(None)
    assert "成功" in module.result_text.value
    lines_before = _plotted_line_count(module.chart.figure)
    title_before = module.chart.figure.axes[0].get_title()
    assert lines_before > 0 and "P-h" in title_before

    shell.navigate("home")
    shell.navigate("ph_chart")

    assert _plotted_line_count(module.chart.figure) == lines_before
    assert module.chart.figure.axes[0].get_title() == title_before
    assert "成功" in module.result_text.value


def test_thermo_diagram_clears_plot_when_switching_diagram_type(shell) -> None:
    """P-h 與 T-s 路由互切時清除舊圖，但保留輸入。

回傳：
    無。"""
    shell.navigate("ph_chart")
    module = shell.views["ph_chart"].module
    module.perform_plot(None)
    inputs_before = _entry_state(module, ["td_T", "td_P"])

    shell.navigate("ts_chart")

    assert module.diagram_dd.value == "T-s"
    assert _plotted_line_count(module.chart.figure) == 0
    assert "成功" not in module.result_text.value
    assert _entry_state(module, ["td_T", "td_P"]) == inputs_before


# ======================================================
# 2. SI / Imperial
# ======================================================
def test_unit_switch_keeps_inputs_and_round_trips_result(shell) -> None:
    """切換輸出單位只改結果呈現；切回原單位時結果與原本完全相同。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    si_result = view.adapter.result_text
    inputs_before = _entry_state(module, list(module.all_entries))

    _switch_unit_system(shell, "Imperial")
    assert view.result_panel.status == "success"
    assert "°F" in view.adapter.result_text and "psia" in view.adapter.result_text
    assert _entry_state(module, list(module.all_entries)) == inputs_before

    _switch_unit_system(shell, "SI")
    assert view.adapter.result_text == si_result
    assert _entry_state(module, list(module.all_entries)) == inputs_before


@pytest.mark.parametrize("edited_value", ["10", "abc"])
def test_unit_switch_does_not_recalculate_with_edited_inputs(shell, edited_value) -> None:
    """計算後修改輸入但未重新計算，切換單位不得以未送出的輸入重算，結果改為失效。

參數：
    shell: 工作區外殼。
    edited_value: 使用者修改後尚未送出的蒸發溫度。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    module.all_entries["cyc_te"]["val"].value = edited_value

    _switch_unit_system(shell, "Imperial")

    assert view.result_panel.status == "warning"
    assert "輸入已變更" in view.result_panel.message
    assert view.adapter.result_text is None
    assert view.workspace.result_view.chart_column.visible is False
    assert module.all_entries["cyc_te"]["val"].value == edited_value

    # 以目前輸入重新計算後恢復正常。
    module.all_entries["cyc_te"]["val"].value = "10"
    view.perform_calculation(None)
    assert view.result_panel.status == "success"
    assert "°F" in view.adapter.result_text


def test_unit_switch_recalculates_all_views_with_unchanged_inputs(shell) -> None:
    """未修改輸入的其他分析頁在切換單位後仍以新單位顯示成功結果。

回傳：
    無。"""
    for route_key in ("condenser", "air_processes", "psychrometrics"):
        shell.navigate(route_key)
        shell.views[route_key].perform_calculation(None)
        assert shell.views[route_key].result_panel.status == "success"

    _switch_unit_system(shell, "Imperial")

    for route_key in ("condenser", "air_processes", "psychrometrics"):
        view = shell.views[route_key]
        assert view.result_panel.status == "success", (route_key, view.result_panel.message)
        assert "輸出 Imperial" in view.result_panel.message


# ======================================================
# 3. Gauge / Absolute
# ======================================================
def _compression_ratio_module(shell):
    """切到壓縮比分析並回傳 (view, module)。

參數：
    shell: 工作區外殼。

回傳：
    (CompressorView, CompressorModule)。"""
    shell.navigate("compressor")
    view = shell.views["compressor"]
    view._handle_tool_change("compressor.compression_ratio")
    return view, view.adapter.modules[0]


def _set_compression_ratio_mode(module, mode: str) -> None:
    """切換壓縮比頁的壓力類型。

參數：
    module: 壓縮機模組。
    mode: "Gauge" 或 "Absolute"。

回傳：
    無。"""
    module.cr_pressure_type_toggle.selected = [mode]
    module.on_pressure_type_change(None)


def test_compression_ratio_gauge_toggle_preserves_physical_pressure(shell) -> None:
    """壓縮比頁切換錶壓／絕對壓時換算數值，實際壓力與壓縮比不變。

回傳：
    無。"""
    view, module = _compression_ratio_module(shell)
    module.all_entries["cr_pe"]["val"].value = "0.3"
    module.all_entries["cr_pc"]["val"].value = "1.2"
    view.perform_calculation(None)
    assert "4.0000" in view.adapter.result_text

    _set_compression_ratio_mode(module, "Gauge")

    pe = module.all_entries["cr_pe"]
    assert pe["prop_code"] == GAUGE_PRESSURE
    assert pe["unit"].value == "MPag"
    assert {option.key for option in pe["unit"].options} == {"Pag", "kPag", "MPag", "barg", "psig"}
    assert float(pe["val"].value) == pytest.approx(0.3 - 0.101325)
    view.perform_calculation(None)
    assert "4.0000" in view.adapter.result_text

    _set_compression_ratio_mode(module, "Absolute")

    assert pe["prop_code"] == "P"
    assert pe["unit"].value == "MPa"
    assert float(pe["val"].value) == pytest.approx(0.3)
    view.perform_calculation(None)
    assert "4.0000" in view.adapter.result_text


def test_compression_ratio_gauge_toggle_rejects_invalid_atmospheric_pressure(shell) -> None:
    """大氣壓力無法解析時維持原模式並提示，不把原數值直接改當另一種基準。

回傳：
    無。"""
    _view, module = _compression_ratio_module(shell)
    module.all_entries["cr_pe"]["val"].value = "0.3"
    module.all_entries["cr_atm_p"]["val"].value = "abc"

    _set_compression_ratio_mode(module, "Gauge")

    assert module.cr_pressure_type_toggle.selected == ["Absolute"]
    assert module.all_entries["cr_pe"]["prop_code"] == "P"
    assert module.all_entries["cr_pe"]["val"].value == "0.3"
    assert module.all_entries["cr_atm_p"]["val"].error_text


def test_gauge_reading_is_kept_when_atmospheric_pressure_changes(shell) -> None:
    """錶壓模式下修改大氣壓力時保留錶壓讀值，計算時以新大氣壓力換算絕對壓。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    view._handle_tool_change("cycle.superheat_subcooling")
    module = view.adapter.modules[0]

    module.all_entries["sh_atm"]["val"].value = "95"
    view.perform_calculation(None)

    assert module.all_entries["sh_p"]["val"].value == "900"
    assert module.all_entries["sh_p"]["unit"].value == "kPag"
    assert "995.00 kPa" in view.adapter.result_text


def test_gauge_pressure_is_consistent_across_navigation_and_unit_switch(shell) -> None:
    """錶壓輸入在跨頁與切換單位後不被改寫，結果的實際絕對壓力一致。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    view._handle_tool_change("cycle.superheat_subcooling")
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    assert "1001.33 kPa" in view.adapter.result_text

    shell.navigate("compressor")
    _switch_unit_system(shell, "Imperial")
    shell.navigate("refrigeration_cycle")

    assert module.all_entries["sh_p"]["val"].value == "900"
    assert module.all_entries["sh_p"]["unit"].value == "kPag"
    expected_psia = UnitConverter().convert_from_si("P", 1_001_325.0, "psia")
    assert f"{expected_psia:.2f} psia" in view.adapter.result_text


# ======================================================
# 4. Reference State
# ======================================================
def test_property_reference_state_does_not_leak_into_refrigeration_cycle(shell) -> None:
    """物性查詢頁把 R32 改為 IIR 後，冷凍循環結果不變；循環計算也不改變物性查詢頁的 policy。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    cycle_view = shell.views["refrigeration_cycle"]
    cycle_view.perform_calculation(None)
    baseline_cycle = cycle_view.adapter.result_text

    ashrae_h = _calculate_property(shell, reference_state="ASHRAE")
    iir_h = _calculate_property(shell, reference_state="IIR")
    assert iir_h != pytest.approx(ashrae_h)

    shell.navigate("refrigeration_cycle")
    cycle_view.perform_calculation(None)
    assert cycle_view.adapter.result_text == baseline_cycle

    assert _calculate_property(shell, reference_state="IIR") == pytest.approx(iir_h)


def test_property_reference_state_round_trip_across_fluids(shell) -> None:
    """R32 / R134a 與 ASHRAE / IIR 來回切換後，回到原設定的結果與原本相同。

回傳：
    無。"""
    r32_ashrae = _calculate_property(shell, fluid="R32", reference_state="ASHRAE")
    r32_iir = _calculate_property(shell, fluid="R32", reference_state="IIR")
    r134a_iir = _calculate_property(shell, fluid="R134a", reference_state="IIR")
    r134a_ashrae = _calculate_property(shell, fluid="R134a", reference_state="ASHRAE")

    assert _calculate_property(shell, fluid="R32", reference_state="IIR") == pytest.approx(r32_iir)
    assert _calculate_property(shell, fluid="R32", reference_state="ASHRAE") == pytest.approx(r32_ashrae)
    assert _calculate_property(shell, fluid="R134a", reference_state="IIR") == pytest.approx(r134a_iir)
    assert _calculate_property(shell, fluid="R134a", reference_state="ASHRAE") == pytest.approx(r134a_ashrae)
    assert r134a_ashrae != pytest.approx(r32_ashrae)


def test_property_reference_state_change_invalidates_result(shell) -> None:
    """物性查詢頁切換 Reference State 後，舊結果立即失效。

回傳：
    無。"""
    _calculate_property(shell, reference_state="ASHRAE")
    view = shell.views["thermo_properties"]

    view.ref_state_dd.value = "IIR"
    view.on_ref_state_change(None)

    assert view.result_panel.status == "warning"
    assert view._last_si_results is None


def test_thermo_diagram_reference_state_does_not_change_property_query(shell) -> None:
    """熱力圖以 IIR 繪製 R32 後，物性查詢頁的 ASHRAE 結果不變。

回傳：
    無。"""
    baseline = _calculate_property(shell, fluid="R32", reference_state="ASHRAE")

    shell.navigate("ph_chart")
    module = shell.views["ph_chart"].module
    module.fluid_tf.value = "R32"
    module.ref_state_dd.value = "IIR"
    module.perform_plot(None)
    assert "成功" in module.result_text.value

    assert _calculate_property(shell, fluid="R32", reference_state="ASHRAE") == pytest.approx(baseline)


@pytest.mark.parametrize("fluid", ["R134a", "R32"])
def test_condenser_exergy_balance_is_reference_state_invariant(fluid) -> None:
    """冷凝器 Exergy 只取狀態差值，ASHRAE / IIR / NBP 下的平衡結果相同。

參數：
    fluid: 冷媒名稱。

回傳：
    無。"""
    provider = ThermodynamicStateService(CanonicalUnitConverter())
    results = {
        policy: analyze_condenser_exergy(
            provider, fluid, 1_500_000.0, 343.15, 303.15, 0.05, 298.15,
            boundary_temperature_k=303.15, reference_state=policy,
        )
        for policy in ("ASHRAE", "IIR", "NBP")
    }
    baseline = results["ASHRAE"]
    assert results["IIR"].inlet.enthalpy_j_kg != pytest.approx(baseline.inlet.enthalpy_j_kg)
    for policy in ("IIR", "NBP"):
        balance = results[policy].balance
        assert balance.heat_rejection_w == pytest.approx(baseline.balance.heat_rejection_w, rel=1e-9)
        assert balance.exergy_decrease_w == pytest.approx(baseline.balance.exergy_decrease_w, rel=1e-9)
        assert balance.exergy_destruction_w == pytest.approx(baseline.balance.exergy_destruction_w, rel=1e-9)
        assert balance.exergy_efficiency == pytest.approx(baseline.balance.exergy_efficiency, rel=1e-9)


# ======================================================
# 5. 圖表生命週期
# ======================================================
def test_cycle_chart_redraw_reuses_figure_without_accumulating(shell) -> None:
    """冷凍循環重算多次時沿用同一個 figure，線條數不累積，也不建立新 figure。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    panel = view.adapter.modules[0].chart_panel
    view.perform_calculation(None)
    figure = panel.figure
    line_count = _plotted_line_count(figure)
    figure_numbers = set(plt.get_fignums())

    for _ in range(3):
        view.perform_calculation(None)

    assert panel.figure is figure
    assert len(figure.axes) == 1
    assert _plotted_line_count(figure) == line_count
    assert set(plt.get_fignums()) == figure_numbers


def test_cycle_chart_hidden_on_failure_and_redrawn_for_new_fluid(shell) -> None:
    """計算失敗時隱藏舊循環圖；改用其他冷媒成功後重畫為新冷媒的圖。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    assert "R32" in module.chart_panel.figure.axes[0].get_title()

    module.all_entries["cyc_te"]["val"].value = "60"
    view.perform_calculation(None)
    assert view.result_panel.status == "error"
    assert view.workspace.result_view.chart_column.visible is False

    module.all_entries["cyc_te"]["val"].value = "5"
    module.text_entries["cyc_fluid"]["val"].value = "R134a"
    view.perform_calculation(None)
    assert view.result_panel.status == "success"
    assert view.workspace.result_view.chart_column.visible is True
    title = module.chart_panel.figure.axes[0].get_title()
    assert "R134a" in title and "R32" not in title


def test_thermo_diagram_redraw_does_not_accumulate(shell) -> None:
    """熱力圖重複繪製時沿用同一個 figure，線條數不累積。

回傳：
    無。"""
    shell.navigate("ph_chart")
    module = shell.views["ph_chart"].module
    module.perform_plot(None)
    figure = module.chart.figure
    line_count = _plotted_line_count(figure)
    figure_numbers = set(plt.get_fignums())

    for _ in range(3):
        module.perform_plot(None)

    assert module.chart.figure is figure
    assert len(figure.axes) == 1
    assert _plotted_line_count(figure) == line_count
    assert set(plt.get_fignums()) == figure_numbers


@pytest.mark.parametrize(
    ("route_key", "analysis_key"),
    [
        ("psychrometric_chart", "psychrometric_chart.plot"),
        ("air_processes", "psychrometrics.mixing"),
    ],
)
def test_psychrometric_chart_redraw_does_not_duplicate_series(shell, route_key, analysis_key) -> None:
    """濕空氣線圖重算多次時資料序列與標註點數量不累積。

參數：
    shell: 工作區外殼。
    route_key: 要測試的路由。
    analysis_key: 該路由內的分析項目。

回傳：
    無。"""
    shell.navigate(route_key)
    view = shell.views[route_key]
    view._handle_tool_change(analysis_key)
    view.perform_calculation(None)
    panel = view.workspace.result_view.chart_host.content
    series_count = len(panel.chart.data_series)
    marker_count = len(panel.markers)
    guide_count = len(panel.guides)

    for _ in range(3):
        view.perform_calculation(None)

    assert view.workspace.result_view.chart_host.content is panel
    assert len(panel.chart.data_series) == series_count
    assert len(panel.markers) == marker_count
    assert len(panel.guides) == guide_count
