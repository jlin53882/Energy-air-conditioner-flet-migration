"""壓縮機分析：空白或無效欄位以欄名提示。"""

from __future__ import annotations

import pytest

from Flet_ui.flet_app import main as flet_main


class DummyPage:
    """提供建構工作區時所需的 page API。"""

    def __init__(self) -> None:
        self.overlay = []
        self.controls = []
        self.width = 1440

    def update(self) -> None:
        """在沒有 live Flet session 的情況下接受 updates。

回傳：
    無。"""

    def add(self, *controls) -> None:
        """收集 page entry point 新增的 controls。

參數：
    controls: 新增的控制項。

回傳：
    無。"""
        self.controls.extend(controls)


@pytest.fixture(scope="module")
def compressor_view():
    """建構一次完整工作區並回傳壓縮機分析頁。

回傳：
    CompressorView。"""
    page = DummyPage()
    flet_main(page)
    return page.controls[0].views["compressor"]


def _run(view, analysis_key: str, entry_key: str, raw_value: str) -> tuple[str, str]:
    """把一個欄位改成指定文字後計算，回傳狀態與訊息，並還原欄位。

參數：
    view: 壓縮機分析頁。
    analysis_key: 分析項目 key。
    entry_key: 要修改的輸入欄位 key。
    raw_value: 欄位文字。

回傳：
    (狀態, 訊息)。"""
    view._handle_tool_change(analysis_key)
    module = view.adapter.modules[0]
    field = module.all_entries[entry_key]["val"]
    original = field.value
    field.value = raw_value
    try:
        view.perform_calculation(None)
        return view.result_panel.status, view.result_panel.message
    finally:
        field.value = original


def test_blank_compressor_field_names_the_field(compressor_view) -> None:
    """空白欄位以欄名提示，不再顯示 Python 的轉換錯誤。

回傳：
    無。"""
    status, message = _run(compressor_view, "compressor.work", "win_h1", "  ")
    assert status == "error"
    assert "請輸入「入口焓值 (Inlet Enthalpy)」" in message
    assert "could not convert" not in message


def test_non_numeric_compressor_field_shows_the_bad_value(compressor_view) -> None:
    """非數字輸入指出欄位與目前的內容；無限大也會被拒絕。

回傳：
    無。"""
    status, message = _run(compressor_view, "compressor.exergy_efficiency_ratio", "eer_m_dot", "0.1O")
    assert status == "error"
    assert "「質量流率 (Mass Flow Rate)」請輸入有效數值（目前為「0.1O」）" in message

    status, message = _run(compressor_view, "compressor.work", "win_h2", "inf")
    assert status == "error"
    assert "必須是有限數字" in message


def test_every_compressor_analysis_still_calculates_with_defaults(compressor_view) -> None:
    """預設輸入下每個壓縮機分析仍能完成計算；壓縮比的壓力欄位預設空白，會提示先輸入。

回傳：
    無。"""
    for definition in compressor_view.adapter.definitions:
        compressor_view._handle_tool_change(definition.key)
        compressor_view.perform_calculation(None)
        if definition.key == "compressor.compression_ratio":
            assert compressor_view.result_panel.status == "error"
            assert "請輸入「入口壓力 (Inlet Pressor)」" in compressor_view.result_panel.message
        else:
            assert compressor_view.result_panel.status == "success", definition.key
