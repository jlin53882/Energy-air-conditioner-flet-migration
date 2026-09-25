"""計算頁共用的結構化結果：關鍵數值、分組性質表與可展開的計算過程。

模組把已格式化（已換算單位）的數值填入這些資料類別，版面元件只負責呈現，
不重新計算、不換算，也不補上模組未提供的數值。本檔不依賴 Flet，
可在測試或其他通道中直接使用。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

_SECTION_PATTERN = re.compile(r"^-{2,}\s*(?P<title>.+?)\s*-{2,}$")
# 關鍵數值列最多四張，與參考版面一致。
MAX_KEY_METRICS = 4


@dataclass(frozen=True)
class ResultMetric:
    """頁面頂端以大字呈現的一個關鍵數值。"""

    label: str
    value: str
    unit: str = ""


@dataclass(frozen=True)
class PropertyRow:
    """性質表中的一列：名稱、已格式化數值與單位。"""

    label: str
    value: str
    unit: str = ""


@dataclass(frozen=True)
class PropertyGroup:
    """一組性質；highlighted 為真時以淡底色標示（例如輸入值）。"""

    title: str
    rows: Sequence[PropertyRow]
    highlighted: bool = False


@dataclass(frozen=True)
class StructuredResult:
    """一次成功計算的結構化呈現內容。

    Attributes:
        key_metrics: 最重要的數個結果，建議不超過四個。
        groups: 完整性質表的分組。
        process_groups: 收在「顯示計算過程」中的中間值。
        chart_title: 結果圖表卡片的標題（分析提供圖表時使用）。
        chart_legend: 選用的圖例文字，顯示在圖表卡片標題列右側。
    """

    key_metrics: Sequence[ResultMetric] = field(default_factory=tuple)
    groups: Sequence[PropertyGroup] = field(default_factory=tuple)
    process_groups: Sequence[PropertyGroup] = field(default_factory=tuple)
    chart_title: str = "圖表"
    chart_legend: str = ""


@dataclass
class ResultSection:
    """結果文字中的一組「名稱: 數值」項目與無法配對的說明文字。"""

    title: str | None
    items: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def parse_result_text(text: str | None) -> list[ResultSection]:
    """將分析模組回傳的「名稱: 數值 單位」文字拆為分組，保留原始數值字串。

    ``--- 標題 ---`` 會成為分組標題；無法配對的文字保留為說明。

    參數：
        text: 分析模組回傳的多行結果文字。

    回傳：
        依出現順序排列的結果分組；空白分組會被略過。
    """
    sections: list[ResultSection] = [ResultSection(None)]
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = _SECTION_PATTERN.match(line)
        if heading:
            sections.append(ResultSection(heading.group("title")))
            continue
        label, separator, value = line.partition(": ")
        if separator and label.strip() and value.strip():
            sections[-1].items.append((label.strip(), value.strip()))
        else:
            sections[-1].notes.append(line)
    return [section for section in sections if section.items or section.notes]


def split_value_and_unit(text: str) -> tuple[str, str]:
    """將「數值 單位」格式的結果文字拆成數值與單位，供排版使用。

    只拆分第一段可解析為數字的內容，不改寫或重新計算數值；無法辨識時整段視為數值。

    參數：
        text: 計算轉接器提供的格式化結果文字。

    回傳：
        由數值文字與單位文字組成的二元組。
    """
    stripped = text.strip()
    head, _, tail = stripped.partition(" ")
    try:
        float(head)
    except ValueError:
        return stripped, ""
    return head, tail.strip()


def structured_from_text(
    text: str | None,
    *,
    key_labels: Sequence[str] = (),
    chart_title: str = "圖表",
) -> StructuredResult:
    """把模組回傳的格式化文字轉成結構化結果，只重新排版、不改寫數值。

    關鍵數值依 ``key_labels`` 指定的結果名稱挑選（依指定順序，找不到的名稱
    略過）；未指定時取前幾個結果。所有結果都會列在完整性質表中；只有當每
    個結果都已是關鍵數值時才省略性質表，避免重複。

    參數：
        text: 分析模組回傳的多行結果文字。
        key_labels: 要提升為關鍵數值的結果名稱。
        chart_title: 分析提供圖表時使用的圖表卡片標題。

    回傳：
        StructuredResult。
    """
    sections = parse_result_text(text)
    items = [item for section in sections for item in section.items]
    if key_labels:
        # 多個分組可能出現同名結果（例如多個狀態點），以第一次出現者為準。
        by_label: dict[str, str] = {}
        for label, value in items:
            by_label.setdefault(label, value)
        chosen = [(label, by_label[label]) for label in key_labels if label in by_label]
    else:
        chosen = items
    key_metrics = tuple(
        ResultMetric(label, *split_value_and_unit(value)) for label, value in chosen[:MAX_KEY_METRICS]
    )
    groups = tuple(
        PropertyGroup(
            section.title or "結果",
            tuple(PropertyRow(label, *split_value_and_unit(value)) for label, value in section.items)
            + tuple(PropertyRow(note, "") for note in section.notes),
        )
        for section in sections
    )
    if len(key_metrics) == len(items) and not any(section.notes for section in sections):
        groups = ()
    return StructuredResult(key_metrics=key_metrics, groups=groups, chart_title=chart_title)
