"""計算頁共用的結構化結果：關鍵數值、分組性質表與可展開的計算過程。

模組把已格式化（已換算單位）的數值填入這些資料類別，版面元件只負責呈現，
不重新計算、不換算，也不補上模組未提供的數值。本檔不依賴 Flet，
可在測試或其他通道中直接使用。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


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
