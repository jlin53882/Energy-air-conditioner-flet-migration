"""壓縮機、冷凝器、蒸發器分析的欄位錯誤提示，以及壓縮機㶲效率兩種算法的一致性。"""

from __future__ import annotations

import pytest

from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui_components.unit.hvac_calculations.compressor import (
    calculate_compressor_exergetic_efficiency_loss,
    calculate_compressor_exergetic_efficiency_ratio,
    calculate_compressor_reversible_work,
    calculate_compressor_work,
)


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
def shell():
    """建構一次完整工作區供本模組測試共用。

回傳：
    AppShell。"""
    page = DummyPage()
    flet_main(page)
    return page.controls[0]


@pytest.fixture(scope="module")
def compressor_view(shell):
    """回傳壓縮機分析頁。

回傳：
    CompressorView。"""
    return shell.views["compressor"]


def _run(view, analysis_key: str, entry_key: str, raw_value: str) -> tuple[str, str]:
    """把一個欄位改成指定文字後計算，回傳狀態與訊息，並還原欄位。

參數：
    view: 分析頁。
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
            assert "請輸入「入口壓力 (Inlet Pressure)」" in compressor_view.result_panel.message
        else:
            assert compressor_view.result_panel.status == "success", definition.key


@pytest.mark.parametrize(
    ("view_key", "analysis_key", "entry_key", "label"),
    [
        ("condenser", "condenser.heat_rate", "qc_h1", "入口焓值 (Inlet Enthalpy, h1)"),
        ("evaporator", "evaporator.heat_rate", "qe_m_dot", "質量流率 (Mass Flow Rate)"),
    ],
)
def test_condenser_and_evaporator_fields_name_the_field(shell, view_key, analysis_key, entry_key, label) -> None:
    """冷凝器與蒸發器的空白或無效欄位同樣以欄名提示；預設輸入仍能計算。

回傳：
    無。"""
    view = shell.views[view_key]
    status, message = _run(view, analysis_key, entry_key, "")
    assert status == "error"
    assert f"請輸入「{label}」" in message
    status, message = _run(view, analysis_key, entry_key, "abc")
    assert status == "error"
    assert f"「{label}」請輸入有效數值（目前為「abc」）" in message
    view.perform_calculation(None)
    assert view.result_panel.status == "success"


@pytest.mark.parametrize(
    ("mass_flow", "h1", "h2", "s1", "s2", "t0"),
    [
        (0.1, 400.0, 450.0, 1.70, 1.80, 298.15),
        (0.35, 410.0, 452.0, 1.75, 1.78, 293.15),
        (2.0, 250.0, 290.0, 1.10, 1.16, 303.15),
    ],
)
def test_exergy_efficiency_ratio_uses_reversible_work(mass_flow, h1, h2, s1, s2, t0) -> None:
    """可逆功法直接以 W_rev / W_in 計算，結果與損失法相同，且不受死狀態焓熵影響。

回傳：
    無。"""
    expected = (calculate_compressor_reversible_work(mass_flow, h1, h2, s1, s2, t0)
                / calculate_compressor_work(mass_flow, h1, h2))
    ratio = calculate_compressor_exergetic_efficiency_ratio(mass_flow, h1, h2, s1, s2, t0, 400.0, 1.7)
    loss = calculate_compressor_exergetic_efficiency_loss(mass_flow, h1, h2, s1, s2, t0, 400.0, 1.7)
    assert ratio == pytest.approx(expected)
    assert ratio == pytest.approx(loss)
    assert calculate_compressor_exergetic_efficiency_ratio(
        mass_flow, h1, h2, s1, s2, t0, 120.0, 0.4
    ) == pytest.approx(ratio)


def test_exergy_efficiency_ratio_rejects_invalid_work() -> None:
    """輸入功不為正或可逆功為負時明確報錯。

回傳：
    無。"""
    with pytest.raises(ValueError, match="Win"):
        calculate_compressor_exergetic_efficiency_ratio(0.1, 450.0, 400.0, 1.7, 1.8, 298.15, 400.0, 1.7)
    with pytest.raises(ValueError, match="Wrev"):
        calculate_compressor_exergetic_efficiency_ratio(0.1, 400.0, 410.0, 1.7, 1.8, 298.15, 400.0, 1.7)
