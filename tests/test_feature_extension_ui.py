"""功能延伸（空氣處理、冷凍循環、濕空氣線圖、單位換算）的 UI 整合測試。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui.components.psychrometric_chart_panel import PsychrometricChartPanel
from Flet_ui.ui_components.analysis_modules.psy_module import PsyModule
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

    result_view = view.workspace.result_view
    chart_host = result_view.chart_host
    assert view.result_panel.status == "success", view.result_panel.message
    assert expected_label in view.adapter.result_text
    assert result_view.chart_column.visible is True
    panel = chart_host.content
    assert isinstance(panel, PsychrometricChartPanel)
    assert panel.chart_box.visible is True
    # 飽和線、等 RH 線、等焓線與過程線都是原生折線圖的資料序列。
    assert len(panel.chart.data_series) > 10
    assert panel.markers


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
    assert view.workspace.result_view.chart_column.visible is False


def test_switching_air_process_tool_hides_previous_chart(shell) -> None:
    """切換分析後，舊結果的圖表不得沿用到尚未計算的新分析。

回傳：
    無。"""
    shell.navigate("air_processes")
    view = shell.views["air_processes"]
    view._handle_tool_change("psychrometrics.supply_airflow")
    view.perform_calculation(None)
    assert view.workspace.result_view.chart_column.visible is True

    view._handle_tool_change("psychrometrics.sensible")

    assert view.result_panel.status == "empty"
    assert view.workspace.result_view.chart_column.visible is False


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
    assert view.workspace.result_view.chart_column.visible is True
    title = chart_host.content.figure.axes[0].get_title()
    assert "P-h" in title and "R32" in title


def test_superheat_tool_converts_gauge_pressure(shell) -> None:
    """錶壓力加上大氣壓力後判讀；切換為絕對壓力時隱藏大氣壓力欄位，實際壓力不變。

回傳：
    無。"""
    shell.navigate("superheat_subcooling")
    view = shell.views["superheat_subcooling"]
    module = view.adapter.modules[0]

    view.perform_calculation(None)
    assert view.result_panel.status == "success", view.result_panel.message
    assert "過熱蒸氣" in view.adapter.result_text
    assert "1001.33 kPa" in view.adapter.result_text
    assert view.workspace.result_view.chart_column.visible is False

    module.sh_pressure_type.selected = ["Absolute"]
    module.on_pressure_type_change(None)
    assert module.all_entries["sh_atm"]["ui_row"].visible is False
    assert module.all_entries["sh_p"]["unit"].value == "kPa"
    view.perform_calculation(None)
    # 切換模式時數值換算為同一個實際壓力：900 kPag → 1001.325 kPa。
    assert "1001.33 kPa" in view.adapter.result_text

    view.set_output_unit_system("Imperial")
    assert "145.23 psia" in view.adapter.result_text
    view.set_output_unit_system("SI")

    module.sh_pressure_type.selected = ["Gauge"]
    module.on_pressure_type_change(None)
    assert module.all_entries["sh_p"]["unit"].value == "kPag"
    assert float(module.all_entries["sh_p"]["val"].value) == pytest.approx(900.0)


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

    assert view.tool_selector.visible is False
    view.perform_calculation(None)

    assert view.result_panel.status == "success", view.result_panel.message
    for index in (1, 2, 3):
        assert f"--- 狀態點 {index} ---" in view.adapter.result_text
    assert result_view.chart_column.visible is True


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


def test_psychrometric_property_modes_use_structured_result_view(shell) -> None:
    """濕空氣性質模式以關鍵數值、焓濕圖與性質表取代通用指標卡片。

回傳：
    無。"""
    shell.navigate("psychrometrics")
    tab = shell.views["psychrometrics"]
    view = tab.workspace.result_view
    tab._handle_tool_change(PsyModule.MODE_TDB_TWB)
    tab.perform_calculation(None)

    assert tab.result_panel.status == "success"
    assert view.status_card.visible is False
    kpis = {tile.label_control.value: tile for tile in view.kpi_row.controls}
    assert list(kpis) == ["相對濕度 RH", "露點溫度 Tdp", "焓值 h", "濕度比 W"]
    assert kpis["相對濕度 RH"].value_control.value == "63.5"
    assert kpis["露點溫度 Tdp"].value_control.value == "17.59"
    assert view.chart_title.value == "焓濕圖"
    assert view.chart_column.visible is True
    assert view.table_column.col == {"xs": 12, "xl": 5}
    inputs, results = view.property_table.groups
    assert [row.label for row in inputs.rows][:2] == ["乾球溫度", "濕球溫度"]
    assert inputs.highlighted is True
    assert "相對濕度" in [row.label for row in results.rows]
    panel = tab.psy_module.result_builder.chart_panel
    assert [marker.label for marker in panel.markers] == ["25.0 °C / 63.5%"]
    assert [guide.end.label for guide in panel.guides] == ["Twb 20.0", "Tdp 17.6"]
    guide_series = [series for series in panel.chart.data_series if series.dash_pattern == [4, 3]]
    assert len(guide_series) == 2
    assert guide_series[1].points[1].y == pytest.approx(guide_series[1].points[0].y)
    # 讀值直接標在圖上：模擬圖表回報尺寸後，狀態點、輔助線與曲線標籤都應放置且互不重疊。
    assert panel.label_layer.controls == []
    panel._on_chart_resize(SimpleNamespace(width=420, height=360))
    assert panel.placed_labels[:3] == ["25.0 °C / 63.5%", "Twb 20.0", "Tdp 17.6"]
    assert "100%" in panel.placed_labels
    assert len(panel.label_layer.controls) == len(panel.placed_labels)
    marker_x, marker_y = panel.to_screen(25.0, panel.markers[0].humidity_ratio * 1000)
    assert 0 < marker_x < 420 - 34 - 22 and 0 < marker_y < 360 - 24 - 22

    assert view.process_card.visible is True
    assert view.process_body.visible is False
    view.toggle_process(None)
    assert view.process_body.visible is True
    view.toggle_process(None)

    tab._handle_tool_change(PsyModule.MODE_TDB_RH)
    assert view.kpi_row.visible is False
    assert view.status_card.visible is True
    tab.perform_calculation(None)
    inputs, results = view.property_table.groups
    assert inputs.rows[1].label == "相對濕度"
    assert "濕球溫度" in [row.label for row in results.rows]


def test_psychrometric_result_view_follows_output_units(shell) -> None:
    """切換英制後關鍵數值與性質表改用英制單位。

回傳：
    無。"""
    shell.navigate("psychrometrics")
    tab = shell.views["psychrometrics"]
    tab._handle_tool_change(PsyModule.MODE_TDB_TWB)
    view = tab.workspace.result_view
    tab.perform_calculation(None)
    try:
        tab.set_output_unit_system("Imperial")
        kpis = {tile.label_control.value: tile for tile in view.kpi_row.controls}
        assert kpis["露點溫度 Tdp"].unit_control.value == "°F"
        assert kpis["濕度比 W"].unit_control.value == "gr/lbm"
    finally:
        tab.set_output_unit_system("SI")


def test_altitude_field_shows_atmospheric_pressure_hint(shell) -> None:
    """海拔輸入即時顯示大氣壓力，無效輸入時顯示提示而不拋錯。

回傳：
    無。"""
    module = shell.views["psychrometrics"].psy_module
    field = module.all_entries["psy_alt"]["val"]
    try:
        field.value = "1000"
        module.update_pressure_hint(None)
        assert module.pressure_hint.value == "→ 大氣壓力 89.875 kPa"
        field.value = "abc"
        module.update_pressure_hint(None)
        assert "有效海拔" in module.pressure_hint.value
    finally:
        field.value = "0"
        module.update_pressure_hint(None)
    assert module.pressure_hint.value == "→ 大氣壓力 101.325 kPa"


def test_chart_axes_expand_for_hot_humid_states() -> None:
    """焓濕圖預設 0–35 °C／30 g/kg，狀態點超出時自動放大。

回傳：
    無。"""
    from Flet_ui.ui_components.analysis_modules.psy_result_view import chart_axes_for

    assert chart_axes_for({"Tdb": 298.15, "Tdp": 290.74, "W": 0.0126}) == ((0.0, 35.0), 0.030)
    (low, high), w_max = chart_axes_for({"Tdb": 318.15, "Tdp": 305.0, "W": 0.030})
    assert high == 50.0 and w_max == pytest.approx(0.045)


def test_wide_sidebar_collapses_to_icon_rail_and_back() -> None:
    """寬版可把側欄收合為圖示列並讓工作區變寬；中版固定為圖示列。

回傳：
    無。"""
    page = DummyPage()
    page.width = 1440
    flet_main(page)
    shell = page.controls[0]

    assert shell.sidebar.width == 256
    assert shell.menu_button.visible is True
    shell._toggle_sidebar(None)
    assert shell.sidebar_collapsed is True
    assert shell.sidebar.compact is True
    assert shell.sidebar.width == 76
    assert shell.workspace_region.padding.left == 76
    assert shell.brand_text.visible is False

    page.width = 1024
    shell._on_resize(None)
    assert shell.menu_button.visible is False
    shell._toggle_sidebar(None)
    assert shell.sidebar_collapsed is True

    page.width = 1440
    shell._on_resize(None)
    shell._toggle_sidebar(None)
    assert shell.sidebar.width == 256
    assert shell.workspace_region.padding.left == 256


def test_home_refrigerant_shortcut_opens_property_query(shell, monkeypatch) -> None:
    """首頁的常用冷媒捷徑以該流體開啟狀態查詢。

參數：
    shell: 工作區外殼。
    monkeypatch: pytest monkeypatch；狀態查詢畫面未掛載到真實頁面，略過其重繪。

回傳：
    無。"""
    monkeypatch.setattr(shell.views["thermo_properties"], "update", lambda: None)
    home = shell.views["home"]
    button = next(item for item in home.fluid_buttons if item.content == "R134a")

    button.on_click(SimpleNamespace())

    assert shell.state.route_key == "thermo_properties"
    assert shell.views["thermo_properties"].fluid_tf.value == "R134a"
    shell.navigate("home")


def test_every_analysis_view_uses_the_shared_calculation_layout(shell) -> None:
    """所有分析頁共用左側輸入卡＋右側結果區的欄寬。

回傳：
    無。"""
    from Flet_ui.ui.components.analysis_workspace import INPUT_COLUMN, RESULT_COLUMN

    for key, view in shell.views.items():
        if not hasattr(view, "workspace"):
            continue
        assert view.workspace.input_column.col == INPUT_COLUMN, key
        assert view.workspace.result_column.col == RESULT_COLUMN, key
    assert shell.views["psychrometrics"].tool_selector.label_control.value == "已知參數組合"


def test_psychrometric_chart_keeps_important_labels_when_they_collide(shell) -> None:
    """狀態點與濕球／露點標籤互相碰撞時改放候選位置，仍全部顯示；曲線數值可略過。

回傳：
    無。"""
    from chart.psychrometric import ChartGuide, ChartMarker, build_psychrometric_chart_data

    service = shell.views["psychrometrics"].psy_module.psy_calculator.service
    data = build_psychrometric_chart_data(service, 0.0, dry_bulb_range_c=(-10.0, 50.0),
                                          humidity_ratio_max=0.030)
    panel = PsychrometricChartPanel(height=300)
    p1, p2 = ChartMarker("P1", 25.0, 0.01000), ChartMarker("P2", 25.1, 0.01005)
    panel.draw(data, markers=[p1, p2])
    panel._on_chart_resize(SimpleNamespace(width=420, height=360))
    # 兩點幾乎重合，第二個標籤原本的位置一定與第一個重疊。
    assert "P1" in panel.placed_labels and "P2" in panel.placed_labels
    first, second = panel.label_layer.controls[:2]
    assert (first.left, first.top) != (second.left, second.top)

    # 候選位置都用完時，必要標籤仍放在第一個候選位置，不會消失。
    crowded = [ChartMarker(f"S{index}", 25.0, 0.010) for index in range(6)]
    guides = [ChartGuide(p1, ChartMarker("Twb 20.0", 20.0, 0.010)),
              ChartGuide(p1, ChartMarker("Tdp 17.6", 20.0, 0.010))]
    panel.draw(data, markers=crowded, guides=guides)
    assert panel.placed_labels[:8] == [f"S{index}" for index in range(6)] + ["Twb 20.0", "Tdp 17.6"]

    # 次要的曲線數值在窄圖上可以略過一部分，但必要標籤仍在。
    panel.draw(data, markers=[p1, p2])
    panel._on_chart_resize(SimpleNamespace(width=180, height=160))
    secondary = [curve.label for curve in data.relative_humidity_lines]
    assert "P1" in panel.placed_labels and "P2" in panel.placed_labels
    assert not set(secondary) <= set(panel.placed_labels)


def test_native_psychrometric_chart_axes_follow_the_data_range(shell) -> None:
    """原生線圖的座標範圍與刻度跟著線圖資料；未繪圖前只顯示提示。

回傳：
    無。"""
    from chart.psychrometric import ChartMarker, build_psychrometric_chart_data

    panel = PsychrometricChartPanel(height=300)
    assert panel.placeholder.visible is True
    assert panel.chart_box.visible is False

    service = shell.views["psychrometrics"].psy_module.psy_calculator.service
    data = build_psychrometric_chart_data(service, 0.0, dry_bulb_range_c=(-10.0, 50.0),
                                          humidity_ratio_max=0.030)
    panel.draw(data, markers=[ChartMarker("P", 30.0, 0.012)])

    assert panel.chart_box.visible is True
    assert (panel.chart.min_x, panel.chart.max_x) == (-10.0, 50.0)
    assert panel.chart.max_y == pytest.approx(30.0)
    assert [label.value for label in panel.chart.bottom_axis.labels] == [-10, 0, 10, 20, 30, 40, 50]
    assert [label.value for label in panel.chart.right_axis.labels] == [0, 5, 10, 15, 20, 25, 30]
    # 圖表不回應滑鼠（避免游標經過時在每條背景線上標點）；標註點座標直接列在圖例。
    assert panel.chart.interactive is False
    assert panel.legend.controls[0].controls[1].value == "P  30.0 °C · 12.00 g/kg"
    # 曲線以直線段連接計算取樣點，不做 Bézier 平滑。
    assert not any(series.curved for series in panel.chart.data_series)
