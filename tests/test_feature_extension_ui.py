"""功能延伸（空氣處理、冷凍循環、濕空氣線圖、單位換算）的 UI 整合測試。"""

from __future__ import annotations

import pytest

from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui.components.figure_panel import FigurePanel
from Flet_ui.ui_components.analysis_modules.result_formatting import ResultFormatter
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter


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


@pytest.fixture(scope="module")
def shell():
    """建構一次完整工作區供本模組測試共用。

回傳：
    AppShell。"""
    page = DummyPage()
    flet_main(page)
    return page.controls[0]


def test_result_formatter_uses_practical_units() -> None:
    """SI 風量以 m³/h、英制以 CFM 輸出，並產生可解析的分組文字。

回傳：
    無。"""
    converter = UnitConverter()
    si = ResultFormatter(converter, False).section("流量").add("風量", "VolumeFlow", 1.0, 0)
    imperial = ResultFormatter(converter, True).add("風量", "VolumeFlow", 1.0, 0)

    assert si.text() == "--- 流量 ---\n風量: 3600 m³/h"
    assert imperial.text() == "風量: 2119 ft³/min"


def test_unit_converter_supports_hvac_units() -> None:
    """溫差不做零點偏移，冷凍噸與 kcal/h 以標準換算係數往返。

回傳：
    無。"""
    converter = UnitConverter()

    assert converter.convert_to_si("DeltaT", 5.0, "°C") == pytest.approx(5.0)
    assert converter.convert_to_si("DeltaT", 9.0, "°F") == pytest.approx(5.0)
    assert converter.convert_to_si("Power", 1.0, "RT") == pytest.approx(3516.853)
    assert converter.convert_from_si("Power", 1163.0, "kcal/h") == pytest.approx(1000.0)
    assert ResultFormatter(converter, True).quantity("DeltaT", 10.0, 1) == "18.0 °F"


@pytest.mark.parametrize(
    ("analysis_key", "expected_label"),
    [
        ("psychrometrics.mixing", "混合後風量"),
        ("psychrometrics.sensible", "加熱量"),
        ("psychrometrics.cooling_coil", "顯熱比 SHR"),
        ("psychrometrics.supply_airflow", "所需送風量"),
    ],
)
def test_air_process_analyses_render_metrics_and_chart(shell, analysis_key, expected_label) -> None:
    """每個空氣處理分析以預設值計算成功，並在結果卡片顯示線圖。

參數：
    shell: 工作區外殼。
    analysis_key: 分析定義 key。
    expected_label: 結果中應出現的指標名稱。

回傳：
    無。"""
    shell.navigate("air_processes")
    view = shell.views["air_processes"]
    view._handle_tool_change(analysis_key)

    view.perform_calculation(None)

    chart_host = view.workspace.result_view.chart_host
    assert view.result_panel.status == "success", view.result_panel.message
    assert expected_label in view.adapter.result_text
    assert chart_host.visible is True
    assert isinstance(chart_host.content, FigurePanel)
    axes = chart_host.content.figure.axes[0]
    assert len(axes.lines) > 10


def test_air_process_invalid_field_names_the_field(shell) -> None:
    """無效輸入以欄名提示，且不顯示舊圖表。

回傳：
    無。"""
    shell.navigate("air_processes")
    view = shell.views["air_processes"]
    view._handle_tool_change("psychrometrics.mixing")
    view.perform_calculation(None)
    entry = view.adapter.modules[0].all_entries["mix_a_flow"]
    original = entry["val"].value
    entry["val"].value = "abc"
    try:
        view.perform_calculation(None)
    finally:
        entry["val"].value = original

    assert view.result_panel.status == "error"
    assert "風量" in view.result_panel.message
    assert view.workspace.result_view.chart_host.visible is False


def test_switching_air_process_tool_hides_previous_chart(shell) -> None:
    """切換分析後，舊結果的圖表不得沿用到尚未計算的新分析。

回傳：
    無。"""
    shell.navigate("air_processes")
    view = shell.views["air_processes"]
    view._handle_tool_change("psychrometrics.supply_airflow")
    view.perform_calculation(None)
    assert view.workspace.result_view.chart_host.visible is True

    view._handle_tool_change("psychrometrics.sensible")

    assert view.result_panel.status == "empty"
    assert view.workspace.result_view.chart_host.visible is False


def test_refrigeration_cycle_route_plots_cycle_on_ph_chart(shell) -> None:
    """冷凍循環路由以預設值求解，顯示 COP 並在 P-h 圖上畫出循環。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]

    assert view.active_key == "cycle.vapor_compression"
    view.perform_calculation(None)

    chart_host = view.workspace.result_view.chart_host
    assert view.result_panel.status == "success", view.result_panel.message
    assert "冷房 COP" in view.adapter.result_text
    assert chart_host.visible is True
    title = chart_host.content.figure.axes[0].get_title()
    assert "P-h" in title and "R32" in title


def test_superheat_tool_converts_gauge_pressure(shell) -> None:
    """錶壓力加上大氣壓力後判讀；切換為絕對壓力時隱藏大氣壓力欄位。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    view._handle_tool_change("cycle.superheat_subcooling")
    module = view.adapter.modules[0]

    view.perform_calculation(None)
    assert view.result_panel.status == "success", view.result_panel.message
    assert "過熱蒸氣" in view.adapter.result_text
    assert "1001.33 kPa" in view.adapter.result_text
    assert view.workspace.result_view.chart_host.visible is False

    module.sh_pressure_type.selected = ["Absolute"]
    module.on_pressure_type_change(None)
    assert module.all_entries["sh_atm"]["ui_row"].visible is False
    view.perform_calculation(None)
    assert "900.00 kPa" in view.adapter.result_text
    module.sh_pressure_type.selected = ["Gauge"]
    module.on_pressure_type_change(None)


def test_empty_fluid_name_is_reported_by_label(shell) -> None:
    """冷媒欄位空白時以欄名提示。

回傳：
    無。"""
    shell.navigate("refrigeration_cycle")
    view = shell.views["refrigeration_cycle"]
    view._handle_tool_change("cycle.vapor_compression")
    module = view.adapter.modules[0]
    module.text_entries["cyc_fluid"]["val"].value = " "
    try:
        view.perform_calculation(None)
    finally:
        module.text_entries["cyc_fluid"]["val"].value = "R32"

    assert view.result_panel.status == "error"
    assert "冷媒" in view.result_panel.message


def test_psychrometric_chart_route_lists_each_point(shell) -> None:
    """濕空氣線圖以預設三點計算，逐點列出性質，圖表放在指標之前。

回傳：
    無。"""
    shell.navigate("psychrometric_chart")
    view = shell.views["psychrometric_chart"]
    result_view = view.workspace.result_view

    assert view.workspace.selector_card.visible is False
    view.perform_calculation(None)

    assert view.result_panel.status == "success", view.result_panel.message
    for index in (1, 2, 3):
        assert f"--- 狀態點 {index} ---" in view.adapter.result_text
    assert result_view.chart_host.visible is True
    body = result_view.controls
    assert body.index(result_view.chart_host) < body.index(result_view.result_sections)

    shell.navigate("air_processes")
    air_view = shell.views["air_processes"]
    air_view.perform_calculation(None)
    air_body = air_view.workspace.result_view.controls
    assert air_body.index(air_view.workspace.result_view.chart_host) > air_body.index(
        air_view.workspace.result_view.result_sections
    )


def test_psychrometric_chart_validates_point_counts_and_converts_lists(shell) -> None:
    """點數不一致時提示錯誤；切換溫度單位會逐筆換算。

回傳：
    無。"""
    shell.navigate("psychrometric_chart")
    view = shell.views["psychrometric_chart"]
    module = view.adapter.modules[0]
    rh_entry = module.all_entries["pc_rh"]
    tdb_entry = module.all_entries["pc_tdb"]
    original_rh = rh_entry["val"].value
    rh_entry["val"].value = "60, 50"
    try:
        view.perform_calculation(None)
    finally:
        rh_entry["val"].value = original_rh
    assert view.result_panel.status == "error"
    assert "數量必須相同" in view.result_panel.message

    original_tdb = tdb_entry["val"].value
    tdb_entry["unit"].value = "°F"
    tdb_entry["unit"].on_select(None)
    try:
        assert tdb_entry["val"].value == "95, 78.8, 55.4"
    finally:
        tdb_entry["unit"].value = "°C"
        tdb_entry["unit"].on_select(None)
    assert tdb_entry["val"].value == original_tdb


def test_unit_converter_view_lists_every_unit(shell) -> None:
    """單位換算頁列出所選物理量的所有單位，並拒絕無效或低於絕對零度的輸入。

回傳：
    無。"""
    shell.navigate("unit_converter")
    view = shell.views["unit_converter"]
    view.quantity_dd.value = "Power"
    view._on_quantity_change(None)
    view.value_tf.value = "1"
    view.unit_dd.value = "RT"
    view.convert()

    values = {tile.label: tile.value for tile in view.results.controls}
    assert set(values) == set(UnitConverter().get_available_units("Power"))
    assert values["kW"] == "3.51685 kW"

    view.value_tf.value = "abc"
    view.convert()
    assert view.value_tf.error_text and view.results.controls == []

    view.quantity_dd.value = "T"
    view._on_quantity_change(None)
    view.value_tf.value = "-300"
    view.convert()
    assert "絕對零度" in view.value_tf.error_text
    view.value_tf.value = "1"
    view.convert()
