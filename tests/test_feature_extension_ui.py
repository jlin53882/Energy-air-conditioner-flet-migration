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
