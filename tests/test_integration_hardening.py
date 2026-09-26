"""工作區狀態失效矩陣（docs/state-invalidation.md）的整合回歸測試。

每個測試都以真正的 ``Flet_ui.flet_app.main`` 建構完整工作區，驗證跨頁、單位切換、
錶壓／絕對壓、Reference State 與圖表生命週期的行為。
"""

from __future__ import annotations

from types import SimpleNamespace

import flet as ft
import matplotlib.pyplot as plt
import pytest

from domain.refrigeration.condenser_exergy import analyze_condenser_exergy
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units import CanonicalUnitConverter
from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui.analysis_module_adapter import AnalysisModuleAdapter, iter_controls
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
        ("superheat_subcooling", "refrigerant.superheat_subcooling"),
        ("saturation", "refrigerant.saturation"),
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


def _edit(control, value: str) -> None:
    """模擬使用者在輸入控制項中修改內容並觸發 Flet 事件。

參數：
    control: TextField 或 Dropdown。
    value: 新的內容。

回傳：
    無。"""
    control.value = value
    handler = control.on_select if isinstance(control, ft.Dropdown) else control.on_change
    handler(SimpleNamespace(control=control))


@pytest.mark.parametrize("edited_value", ["10", "abc"])
def test_editing_analysis_input_invalidates_result(shell, edited_value) -> None:
    """分析頁修改輸入後結果立即失效；之後切換單位也不得以未送出的輸入重算。

參數：
    shell: 工作區外殼。
    edited_value: 使用者修改後尚未送出的蒸發溫度。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    module = view.adapter.modules[0]
    view.perform_calculation(None)

    _edit(module.all_entries["cyc_te"]["val"], edited_value)

    assert view.result_panel.status == "warning"
    assert view.result_panel.title == "輸入已變更"
    assert view.adapter.result_text is None
    assert view.workspace.result_view.chart_column.visible is False

    _switch_unit_system(shell, "Imperial")
    assert view.result_panel.status == "warning"
    assert view.adapter.result_text is None
    assert module.all_entries["cyc_te"]["val"].value == edited_value

    # 以目前輸入重新計算後恢復正常。
    module.all_entries["cyc_te"]["val"].value = "10"
    view.perform_calculation(None)
    assert view.result_panel.status == "success"
    assert "°F" in view.adapter.result_text


def test_editing_input_on_every_analysis_view_invalidates_result(shell) -> None:
    """每個分析頁的文字輸入修改後都使結果失效，並在結果區隱藏圖表。

回傳：
    無。"""
    for route_key in ("compressor", "evaporator", "condenser", "refrigeration_cycle", "saturation",
                      "superheat_subcooling",
                      "psychrometrics", "air_processes", "psychrometric_chart"):
        shell.navigate(route_key)
        view = shell.views[route_key]
        view.perform_calculation(None)
        if view.result_panel.status != "success":
            continue
        field = next(
            control for control in iter_controls(view.adapter.active_definition.input_view)
            if isinstance(control, ft.TextField) and control.visible
        )
        _edit(field, field.value or "1")
        assert view.result_panel.status == "warning", route_key
        assert view.workspace.result_view.chart_column.visible is False, route_key


def test_unit_dropdown_and_pressure_basis_do_not_invalidate_result(shell) -> None:
    """切換欄位單位或錶壓／絕對壓只改表示方式，實際數值不變，結果保留。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    _edit(module.all_entries["cyc_te"]["unit"], "°F")
    assert view.result_panel.status == "success"
    assert float(module.all_entries["cyc_te"]["val"].value) == pytest.approx(41.0)

    shell.navigate("superheat_subcooling")
    view = shell.views["superheat_subcooling"]
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    module.sh_pressure_type.selected = ["Absolute"]
    module.sh_pressure_type.on_change(SimpleNamespace(control=module.sh_pressure_type))
    assert view.result_panel.status == "success"
    assert module.all_entries["sh_p"]["unit"].value == "kPa"


def test_reference_state_selector_change_invalidates_result(shell) -> None:
    """分析頁自己的 Reference State 選單屬於計算輸入，修改後結果失效。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    module = view.adapter.modules[0]
    view.perform_calculation(None)

    _edit(module.cyc_ref_state, "IIR")

    assert view.result_panel.status == "warning"


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
    shell.navigate("superheat_subcooling")
    view = shell.views["superheat_subcooling"]
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
    shell.navigate("superheat_subcooling")
    view = shell.views["superheat_subcooling"]
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    assert "1001.33 kPa" in view.adapter.result_text

    shell.navigate("compressor")
    _switch_unit_system(shell, "Imperial")
    shell.navigate("superheat_subcooling")

    assert module.all_entries["sh_p"]["val"].value == "900"
    assert module.all_entries["sh_p"]["unit"].value == "kPag"
    expected_psia = UnitConverter().convert_from_si("P", 1_001_325.0, "psia")
    assert f"{expected_psia:.2f} psia" in view.adapter.result_text


def _superheat_module(shell):
    """切到過熱度／過冷度判讀並回傳 (view, module)。

參數：
    shell: 工作區外殼。

回傳：
    (SuperheatSubcoolingView, SuperheatSubcoolingModule)。"""
    shell.navigate("superheat_subcooling")
    view = shell.views["superheat_subcooling"]
    return view, view.adapter.modules[0]


def test_altitude_sets_atmospheric_pressure_and_keeps_gauge_reading(shell) -> None:
    """填入海拔時自動計算大氣壓力，錶壓讀值不變；清空海拔時恢復 101.325 kPa。

回傳：
    無。"""
    view, module = _superheat_module(shell)
    atmosphere = module.all_entries["sh_atm"]["val"]
    assert atmosphere.value == "101.325"

    _edit(module.all_entries["sh_alt"]["val"], "1000")

    assert float(atmosphere.value) == pytest.approx(89.8745, rel=1e-5)
    assert module.all_entries["sh_p"]["val"].value == "900"
    view.perform_calculation(None)
    assert "989.87 kPa" in view.adapter.result_text

    _edit(module.all_entries["sh_alt"]["val"], "")

    assert float(atmosphere.value) == pytest.approx(101.325)
    view.perform_calculation(None)
    assert "1001.33 kPa" in view.adapter.result_text


def test_invalid_altitude_keeps_atmospheric_pressure_and_names_error(shell) -> None:
    """海拔無效時提示錯誤，不改動大氣壓力欄位。

回傳：
    無。"""
    _view, module = _superheat_module(shell)
    atmosphere = module.all_entries["sh_atm"]["val"]
    atmosphere.value = "100"

    _edit(module.all_entries["sh_alt"]["val"], "abc")

    assert module.all_entries["sh_alt"]["val"].error_text
    assert atmosphere.value == "100"


@pytest.mark.parametrize(
    ("route_key", "analysis_key", "toggle_name", "altitude_key", "atm_key"),
    [
        ("superheat_subcooling", "refrigerant.superheat_subcooling", "sh_pressure_type", "sh_alt", "sh_atm"),
        ("saturation", "refrigerant.saturation", "sat_pressure_type", "sat_alt", "sat_atm"),
        ("compressor", "compressor.compression_ratio", "cr_pressure_type_toggle", "cr_alt", "cr_atm_p"),
        ("condenser", "condenser.exergy", "cx_pressure_type", "cx_alt", "cx_atm"),
    ],
)
def test_altitude_and_atmosphere_rows_follow_pressure_basis(
    shell, route_key, analysis_key, toggle_name, altitude_key, atm_key
) -> None:
    """海拔與大氣壓力欄位只在錶壓模式顯示。

參數：
    shell: 工作區外殼。
    route_key: 要測試的路由。
    analysis_key: 分析項目。
    toggle_name: 壓力類型切換按鈕的屬性名稱。
    altitude_key: 海拔輸入列識別鍵。
    atm_key: 大氣壓力輸入列識別鍵。

回傳：
    無。"""
    shell.navigate(route_key)
    view = shell.views[route_key]
    view._handle_tool_change(analysis_key)
    module = view.adapter.modules[0]
    toggle = getattr(module, toggle_name)

    for mode in ("Gauge", "Absolute", "Gauge"):
        toggle.selected = [mode]
        toggle.on_change(SimpleNamespace(control=toggle))
        assert module.all_entries[altitude_key]["ui_row"].visible is (mode == "Gauge")
        assert module.all_entries[atm_key]["ui_row"].visible is (mode == "Gauge")


def test_condenser_exergy_gauge_toggle_preserves_physical_pressure(shell) -> None:
    """冷凝器 Exergy 頁切換錶壓後實際壓力不變，計算結果與絕對壓力模式相同。

回傳：
    無。"""
    shell.navigate("condenser")
    view = shell.views["condenser"]
    view._handle_tool_change("condenser.exergy")
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    absolute_result = view.adapter.result_text
    assert "冷凝壓力（絕對）: 1000.00 kPa" in absolute_result

    module.cx_pressure_type.selected = ["Gauge"]
    module.cx_pressure_type.on_change(SimpleNamespace(control=module.cx_pressure_type))

    pressure = module.all_entries["cx_p"]
    assert pressure["prop_code"] == GAUGE_PRESSURE and pressure["unit"].value == "kPag"
    assert float(pressure["val"].value) == pytest.approx(1000 - 101.325)
    assert view.result_panel.status == "success"
    view.perform_calculation(None)
    assert view.adapter.result_text == absolute_result


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


def _result_line(result_text: str, label: str) -> str:
    """回傳結果文字中以指定名稱開頭的那一行。

參數：
    result_text: 模組輸出的格式化文字。
    label: 結果名稱。

回傳：
    該行文字。"""
    return next(line for line in result_text.splitlines() if line.startswith(label))


def test_refrigeration_cycle_uses_its_own_reference_state(shell) -> None:
    """冷凍循環以自己頁面的 Reference State 回報焓值；COP 等狀態差值不受影響。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    ashrae = view.adapter.result_text

    module.cyc_ref_state.value = "IIR"
    view.perform_calculation(None)
    iir = view.adapter.result_text

    enthalpy_section = "--- 狀態點比焓 ---"
    assert iir.split(enthalpy_section)[1] != ashrae.split(enthalpy_section)[1]
    assert _result_line(iir, "冷房 COP") == _result_line(ashrae, "冷房 COP")
    assert _result_line(iir, "壓縮功 w") == _result_line(ashrae, "壓縮功 w")


def test_condenser_exergy_uses_its_own_reference_state(shell) -> None:
    """冷凝器 Exergy 以自己頁面的 Reference State 回報焓、熵；Exergy 平衡不受影響。

回傳：
    無。"""
    shell.navigate("condenser")
    view = shell.views["condenser"]
    view._handle_tool_change("condenser.exergy")
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    ashrae = view.adapter.result_text

    module.cx_ref_state.value = "IIR"
    view.perform_calculation(None)
    iir = view.adapter.result_text

    assert _result_line(iir, "入口比焓 h1") != _result_line(ashrae, "入口比焓 h1")
    for label in ("Exergy 破壞率 X_dest", "Exergy 效率 η", "放熱量 Q_H", "熵產生率 S_gen"):
        assert _result_line(iir, label) == _result_line(ashrae, label), label


def test_compressor_example_results_do_not_depend_on_reference_state(shell, monkeypatch) -> None:
    """壓縮機綜合範例只輸出狀態差值，不同 policy 下結果相同，因此不提供選單。

參數：
    shell: 工作區外殼。
    monkeypatch: pytest 的屬性替換工具。

回傳：
    無。"""
    shell.navigate("compressor")
    view = shell.views["compressor"]
    view._handle_tool_change("compressor.combined_example")
    module = view.adapter.modules[0]
    results = {}
    for policy in ("ASHRAE", "IIR", "NBP"):
        monkeypatch.setattr(module, "_reference_state_for", lambda _fluid, policy=policy: policy)
        view.perform_calculation(None)
        assert view.result_panel.status == "success", view.result_panel.message
        results[policy] = view.adapter.result_text
    assert results["IIR"] == results["ASHRAE"]
    assert results["NBP"] == results["ASHRAE"]


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


# ======================================================
# 6. 輸出單位切換的不變量（過渡期限制）
# ======================================================
def test_output_unit_round_trip_keeps_canonical_cycle_result(shell, monkeypatch) -> None:
    """SI → Imperial → SI 時交給冷凍服務的 canonical 輸入與工程結果都不變，輸入欄位也不變。

    切換輸出單位目前仍會重新計算（見 docs/state-invalidation.md §3.1 的過渡期限制）；
    本測試確認重新計算不改變工程意義：request 相同，COP、壓縮比、壓縮功、冷凍效果與
    質量流率相同，只有顯示單位不同。

參數：
    shell: 工作區外殼。
    monkeypatch: pytest 的屬性替換工具。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    module = view.adapter.modules[0]
    service = module.refrigeration
    solved = []
    original_solve = service.solve_cycle

    def recording_solve(request):
        result = original_solve(request)
        solved.append((request, result))
        return result

    monkeypatch.setattr(service, "solve_cycle", recording_solve)
    view.perform_calculation(None)
    inputs_before = _entry_state(module, list(module.all_entries))
    fluid_before = module.text_entries["cyc_fluid"]["val"].value

    for unit_system in ("Imperial", "SI"):
        _switch_unit_system(shell, unit_system)
        assert view.result_panel.status == "success", view.result_panel.message

    assert len(solved) == 3
    baseline_request, baseline = solved[0]
    # 每次狀態查詢都會設定並還原 CoolProp reference state，重複求解在 ~1e-9 相對誤差內
    # 可能不是逐位元相同（見 docs/state-invalidation.md §3.1）；1e-7 遠小於顯示精度。
    tolerance = 1e-7
    for request, result in solved[1:]:
        assert request == baseline_request
        assert result.cop_cooling == pytest.approx(baseline.cop_cooling, rel=tolerance)
        assert result.pressure_ratio == pytest.approx(baseline.pressure_ratio, rel=tolerance)
        assert result.compressor_work_j_kg == pytest.approx(baseline.compressor_work_j_kg, rel=tolerance)
        assert result.refrigerating_effect_j_kg == pytest.approx(baseline.refrigerating_effect_j_kg, rel=tolerance)
        assert result.mass_flow_kg_s == pytest.approx(baseline.mass_flow_kg_s, rel=tolerance)
    assert _entry_state(module, list(module.all_entries)) == inputs_before
    assert module.text_entries["cyc_fluid"]["val"].value == fluid_before


# ======================================================
# 7. 錶壓／絕對壓切換的無效輸入
# ======================================================
@pytest.mark.parametrize("raw_value", ["", "abc", "nan", "inf", "-inf"])
def test_compression_ratio_pressure_basis_with_invalid_input(shell, monkeypatch, raw_value) -> None:
    """無效的壓力輸入切換錶壓／絕對壓時不當掉、不部分切換、不偽造換算，計算時以欄名報錯。

參數：
    shell: 工作區外殼。
    monkeypatch: pytest 的屬性替換工具。
    raw_value: 入口壓力欄位中的無效內容。

回傳：
    無。"""
    view, module = _compression_ratio_module(shell)
    pe = module.all_entries["cr_pe"]
    pc = module.all_entries["cr_pc"]
    pe["val"].value = "0.3"
    pc["val"].value = "1.2"
    view.perform_calculation(None)
    assert view.result_panel.status == "success"
    pe["val"].value = raw_value
    requests = []
    original_calculate = module.compression_ratio_service.calculate
    monkeypatch.setattr(
        module.compression_ratio_service, "calculate",
        lambda request: requests.append(request) or original_calculate(request),
    )

    expected = {
        "Gauge": (GAUGE_PRESSURE, "MPag", 1.2 - 0.101325),
        "Absolute": ("P", "MPa", 1.2),
    }
    for mode in ("Gauge", "Absolute", "Gauge"):
        _set_compression_ratio_mode(module, mode)
        prop_code, unit, pc_value = expected[mode]
        assert module.cr_pressure_type_toggle.selected == [mode]
        for entry in (pe, pc):
            assert entry["prop_code"] == prop_code
            assert entry["unit"].value == unit
        assert pe["val"].value == raw_value
        assert float(pc["val"].value) == pytest.approx(pc_value)

    view.perform_calculation(None)

    assert view.result_panel.status == "error"
    assert "入口壓力 (Inlet Pressure)" in view.result_panel.message
    assert view.adapter.result_text is None
    assert requests == []


@pytest.mark.parametrize(
    ("route_key", "analysis_key", "toggle_name", "pressure_key", "label"),
    [
        ("superheat_subcooling", "refrigerant.superheat_subcooling", "sh_pressure_type", "sh_p", "量測壓力"),
        ("saturation", "refrigerant.saturation", "sat_pressure_type", "sat_p", "飽和壓力"),
        ("condenser", "condenser.exergy", "cx_pressure_type", "cx_p", "冷凝壓力"),
    ],
)
@pytest.mark.parametrize("raw_value", ["abc", "nan"])
def test_pressure_basis_with_invalid_input_on_other_pages(
    shell, route_key, analysis_key, toggle_name, pressure_key, label, raw_value
) -> None:
    """過熱度判讀與冷凝器 Exergy 的無效壓力輸入切換後保留原文字，計算時以欄名報錯。

參數：
    shell: 工作區外殼。
    route_key: 要測試的路由。
    analysis_key: 分析項目。
    toggle_name: 壓力類型切換按鈕的屬性名稱。
    pressure_key: 壓力輸入列識別鍵。
    label: 壓力欄位名稱。
    raw_value: 無效內容。

回傳：
    無。"""
    shell.navigate(route_key)
    view = shell.views[route_key]
    view._handle_tool_change(analysis_key)
    module = view.adapter.modules[0]
    toggle = getattr(module, toggle_name)
    entry = module.all_entries[pressure_key]
    entry["val"].value = raw_value

    for mode in ("Gauge", "Absolute", "Gauge", "Absolute"):
        toggle.selected = [mode]
        toggle.on_change(SimpleNamespace(control=toggle))
        assert toggle.selected == [mode]
        assert entry["prop_code"] == (GAUGE_PRESSURE if mode == "Gauge" else "P")
        assert entry["val"].value == raw_value

    view.perform_calculation(None)
    assert view.result_panel.status == "error"
    assert label in view.result_panel.message


# ======================================================
# 8. 語意輸入／只改表示方式的輸入契約
# ======================================================
class _ContractModule:
    """含各種支援輸入類型的最小分析模組，用來驗證 adapter 的失效契約。"""

    def __init__(self) -> None:
        """建立每種語意輸入、一個單位選單與一個只改表示方式的切換按鈕。

回傳：
    無。"""
        self.unit = ft.Dropdown(options=[ft.dropdown.Option("kPa"), ft.dropdown.Option("MPa")], value="kPa")
        self.presentation_toggle = ft.SegmentedButton(
            segments=[ft.Segment(value="Gauge", label=ft.Text("Gauge")),
                      ft.Segment(value="Absolute", label=ft.Text("Absolute"))],
            selected=["Absolute"],
        )
        self.semantic = {
            "TextField": (ft.TextField(value="1"), "on_change"),
            "Dropdown": (ft.Dropdown(options=[ft.dropdown.Option("a"), ft.dropdown.Option("b")], value="a"), "on_select"),
            "Checkbox": (ft.Checkbox(value=False), "on_change"),
            "Switch": (ft.Switch(value=False), "on_change"),
            "RadioGroup": (ft.RadioGroup(content=ft.Column([ft.Radio(value="a"), ft.Radio(value="b")]), value="a"), "on_change"),
            "SegmentedButton": (ft.SegmentedButton(
                segments=[ft.Segment(value="x", label=ft.Text("x")), ft.Segment(value="y", label=ft.Text("y"))],
                selected=["x"],
            ), "on_change"),
        }
        self.all_entries = {"value": {"unit": self.unit}}
        self.presentation_only_controls = [self.presentation_toggle]
        controls = [control for control, _event in self.semantic.values()]
        self.ui = ft.Container(content=ft.Column([*controls, ft.Row([self.unit]), self.presentation_toggle]))

    def get_analysis_definitions(self) -> dict:
        """回報單一分析。

回傳：
    分析定義字典。"""
        return {"契約分析": {"analysis_id": "contract.analysis", "ui": self.ui, "calc_func": lambda _imperial: "結果: 1"}}


def _fire(control, event_name: str) -> None:
    """以 Flet 會使用的事件名稱觸發控制項事件。

參數：
    control: 控制項。
    event_name: 事件屬性名稱。

回傳：
    無。"""
    getattr(control, event_name)(SimpleNamespace(control=control))


@pytest.mark.parametrize("control_type", ["TextField", "Dropdown", "Checkbox", "Switch", "RadioGroup", "SegmentedButton"])
def test_every_supported_semantic_input_type_invalidates_result(control_type) -> None:
    """每種支援的語意輸入被使用者修改時，既有成功結果都會失效，原有事件處理器也會執行。

參數：
    control_type: 輸入控制項類型名稱。

回傳：
    無。"""
    module = _ContractModule()
    control, event_name = module.semantic[control_type]
    original_calls = []
    setattr(control, event_name, lambda event: original_calls.append(event))
    adapter = AnalysisModuleAdapter([module])
    adapter.calculate()
    assert adapter.result_panel.status == "success"

    _fire(control, event_name)

    assert adapter.result_panel.status == "warning"
    assert adapter.result_text is None
    assert len(original_calls) == 1


def test_unit_dropdown_and_presentation_only_controls_keep_result() -> None:
    """單位選單與登記為 presentation_only_controls 的控制項變更後，成功結果保留。

回傳：
    無。"""
    module = _ContractModule()
    adapter = AnalysisModuleAdapter([module])
    adapter.calculate()

    for control, event_name in ((module.unit, "on_select"), (module.presentation_toggle, "on_change")):
        handler = getattr(control, event_name)
        if handler is not None:
            handler(SimpleNamespace(control=control))

    assert adapter.result_panel.status == "success"
    assert adapter.result_text == "結果: 1"


# 會改變數值、但 AnalysisModuleAdapter 尚未支援失效處理的 Flet 輸入類型。
_UNSUPPORTED_VALUE_INPUT_TYPES = tuple(
    control_type
    for control_type in (
        getattr(ft, name, None)
        for name in (
            "Slider", "RangeSlider", "CupertinoSwitch", "CupertinoCheckbox", "CupertinoSlider",
            "CupertinoSegmentedButton", "CupertinoSlidingSegmentedButton", "AutoComplete", "SearchBar",
        )
    )
    if isinstance(control_type, type)
)


def test_production_analysis_inputs_only_use_supported_input_types(shell) -> None:
    """正式分析頁的輸入只使用 adapter 支援失效處理的控制項類型。

    新增其他類型（例如 Slider）時，必須同步擴充 ``_SEMANTIC_INPUT_EVENTS`` 與本檔的回歸測試，
    否則使用者修改它時結果不會失效。

參數：
    shell: 工作區外殼。

回傳：
    無。"""
    unsupported = [
        (route_key, definition.key, type(control).__name__)
        for route_key, view in shell.views.items()
        if hasattr(view, "adapter")
        for definition in view.adapter.definitions
        for control in iter_controls(definition.input_view)
        if isinstance(control, _UNSUPPORTED_VALUE_INPUT_TYPES)
    ]
    assert unsupported == []
