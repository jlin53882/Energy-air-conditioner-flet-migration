"""將分析模組回傳的格式化文字投影為分組指標卡片。

分析模組目前以「名稱: 數值 單位」的文字行回傳結果。本模組只負責版面投影：
拆出分組標題與名稱／數值配對，不重新計算、不換算，也不補上模組未提供的數值。
"""

from dataclasses import dataclass, field
import re

import flet as ft

from ..theme import TOKENS
from .metric_tile import MetricTile

_SECTION_PATTERN = re.compile(r"^-{2,}\s*(?P<title>.+?)\s*-{2,}$")


@dataclass
class ResultSection:
    """一組結果指標與其原始說明文字。"""

    title: str | None
    items: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def parse_result_text(text: str) -> list[ResultSection]:
    """將分析結果文字拆為分組指標，保留原始數值字串。

參數：
    text: 分析模組回傳的多行結果文字。

回傳：
    依出現順序排列的結果分組；空白分組會被略過。"""
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


def build_result_section_controls(
    sections: list[ResultSection], *, accent: str | None = None
) -> list[ft.Control]:
    """為結果分組建立標題與指標卡片控制項。

參數：
    sections: 由 parse_result_text 產生的結果分組。
    accent: 選用的指標強調色。

回傳：
    可直接放入 Column 的 Flet 控制項清單。"""
    controls: list[ft.Control] = []
    only_one_item = sum(len(section.items) for section in sections) == 1
    for section in sections:
        if section.title:
            controls.append(
                ft.Row(
                    [
                        ft.Container(width=4, height=16, bgcolor=accent or TOKENS.primary,
                                     border_radius=ft.BorderRadius.all(2)),
                        ft.Text(section.title, size=TOKENS.body, weight=ft.FontWeight.W_600,
                                color=TOKENS.text_primary),
                    ],
                    spacing=TOKENS.spacing_sm,
                )
            )
        if section.items:
            controls.append(
                ft.ResponsiveRow(
                    [
                        MetricTile(
                            label,
                            value,
                            accent=accent,
                            emphasis=only_one_item,
                            col={"xs": 12} if only_one_item else {"xs": 12, "sm": 6, "xl": 4},
                        )
                        for label, value in section.items
                    ],
                    spacing=TOKENS.spacing_sm,
                    run_spacing=TOKENS.spacing_sm,
                )
            )
        for note in section.notes:
            controls.append(ft.Text(note, size=TOKENS.caption, color=TOKENS.text_secondary))
    return controls
