"""結果性質表：長說明文字改為上下排列並換行，數值列維持左右排列。"""

from __future__ import annotations

import flet as ft

from Flet_ui.ui.components.property_table import PropertyRow, PropertyTable, is_long_text
from domain.thermodynamics.thermo_policy import resolve_thermo_policy
from Flet_ui.ui_components.analysis_modules.thermo_state_presentation import policy_rows


def test_numeric_rows_keep_label_value_unit_layout() -> None:
    """有單位或短文字的列維持「名稱｜數值｜單位」左右排列。

回傳：
    無。"""
    for row in (PropertyRow("溫度", "-25.00", "°C"), PropertyRow("參考基準", "IIR（Auto）")):
        assert not is_long_text(row)
        container = PropertyTable._row(row, highlighted=False)
        assert isinstance(container.content, ft.Row)


def test_long_text_rows_stack_and_wrap() -> None:
    """決策原因等長說明文字改為名稱在上、內容在下，內容可換行且不再擠壓名稱。

回傳：
    無。"""
    rows = {row.label: row for row in policy_rows(resolve_thermo_policy("R717"))}
    reason = rows["決策原因"]
    assert is_long_text(reason)
    container = PropertyTable._row(reason, highlighted=False)
    column = container.content
    assert isinstance(column, ft.Column)
    label, value = column.controls
    assert (label.value, value.value) == ("決策原因", reason.value)
    assert column.horizontal_alignment == ft.CrossAxisAlignment.STRETCH
    assert not label.expand and not value.expand
