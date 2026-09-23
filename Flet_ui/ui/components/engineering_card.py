"""維持工程工作區卡片層級一致的共用容器。"""

import flet as ft

from ..theme import TOKENS


class EngineeringCard(ft.Container):
    """呈現具有一致工作區表面樣式與標題層級的工程內容卡片。"""

    def __init__(self, title: str, content: ft.Control, subtitle: str | None = None):
        """建立共用卡片容器，但不接管內容本身的業務邏輯。

參數：
    title: 卡片標題。
    content: 要放入卡片的 Flet 控制項。
    subtitle: 選用的補充說明。

回傳：
    無。"""
        children: list[ft.Control] = [ft.Text(title, size=TOKENS.section_title, weight=ft.FontWeight.W_600)]
        if subtitle:
            children.append(ft.Text(subtitle, size=TOKENS.caption, color=ft.Colors.BLUE_GREY_600))
        children.append(content)
        super().__init__(
            content=ft.Column(children, spacing=TOKENS.spacing_md),
            padding=TOKENS.spacing_lg,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
        )
