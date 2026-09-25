"""以分組、右對齊數值呈現性質清單的表格元件。"""

from collections.abc import Sequence

import flet as ft

from ..structured_result import PropertyGroup, PropertyRow
from ..theme import TOKENS

__all__ = ["PropertyGroup", "PropertyRow", "PropertyTable"]


class PropertyTable(ft.Column):
    """依分組呈現性質；數值靠右對齊，方便上下比較。"""

    def __init__(self) -> None:
        """建立空表格。

回傳：
    無。"""
        super().__init__(spacing=TOKENS.spacing_sm)
        self.groups: list[PropertyGroup] = []

    def set_groups(self, groups: Sequence[PropertyGroup]) -> None:
        """以新的分組內容重建表格。

參數：
    groups: 要顯示的性質分組。

回傳：
    無。"""
        self.groups = list(groups)
        controls: list[ft.Control] = []
        for group in self.groups:
            controls.append(
                ft.Container(
                    content=ft.Text(group.title, size=TOKENS.caption, weight=ft.FontWeight.W_600,
                                    color=TOKENS.text_muted),
                    padding=ft.Padding.only(top=TOKENS.spacing_xs),
                )
            )
            for row in group.rows:
                controls.append(self._row(row, group.highlighted))
        self.controls = controls

    @staticmethod
    def _row(row: PropertyRow, highlighted: bool) -> ft.Container:
        """建立單一表格列。

參數：
    row: 列內容。
    highlighted: 是否使用淡底色。

回傳：
    表格列容器。"""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(row.label, size=TOKENS.body, color=TOKENS.text_primary, expand=True),
                    ft.Text(row.value, size=TOKENS.body + 1, weight=ft.FontWeight.W_500,
                            color=TOKENS.text_primary, text_align=ft.TextAlign.RIGHT, selectable=True),
                    ft.Container(
                        content=ft.Text(row.unit, size=TOKENS.caption, color=TOKENS.text_muted),
                        width=72,
                    ),
                ],
                spacing=TOKENS.spacing_sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=9),
            bgcolor=TOKENS.surface_variant if highlighted else None,
            border=None if highlighted else ft.Border.only(bottom=ft.BorderSide(1, TOKENS.border)),
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm) if highlighted else None,
        )
