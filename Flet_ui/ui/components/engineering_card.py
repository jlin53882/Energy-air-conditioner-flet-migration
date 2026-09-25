"""維持工程工作區卡片層級一致的共用容器。"""

import flet as ft

from ..theme import TOKENS, card_shadow


class EngineeringCard(ft.Container):
    """呈現具有一致工作區表面樣式與標題層級的工程內容卡片。"""

    def __init__(
        self,
        title: str,
        content: ft.Control,
        subtitle: str | None = None,
        *,
        icon: ft.IconData | None = None,
        accent: str | None = None,
        actions: list[ft.Control] | None = None,
        padding: int | None = None,
    ) -> None:
        """建立共用卡片容器，但不接管內容本身的業務邏輯。

參數：
    title: 卡片標題。
    content: 要放入卡片的 Flet 控制項。
    subtitle: 選用的補充說明。
    icon: 選用的標題圖示，會以淡色圓角底座呈現。
    accent: 選用的圖示強調色；未提供時使用主要品牌色。
    actions: 選用的標題列右側操作控制項。
    padding: 選用的卡片內距；未提供時使用標準內距。

回傳：
    無。"""
        accent_color = accent or TOKENS.primary
        self.title_control = ft.Text(
            title,
            size=TOKENS.section_title,
            weight=ft.FontWeight.W_600,
            color=TOKENS.text_primary,
        )
        self.subtitle_control = ft.Text(
            subtitle or "",
            size=TOKENS.caption,
            color=TOKENS.text_muted,
            visible=bool(subtitle),
        )
        heading: list[ft.Control] = []
        if icon is not None:
            heading.append(
                ft.Container(
                    content=ft.Icon(icon, size=18, color=accent_color),
                    width=34,
                    height=34,
                    alignment=ft.Alignment.CENTER,
                    bgcolor=ft.Colors.with_opacity(0.12, accent_color),
                    border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
                )
            )
        heading.append(
            ft.Column(
                [self.title_control, self.subtitle_control],
                spacing=2,
                tight=True,
                expand=True,
            )
        )
        if actions:
            heading.extend(actions)
        self.header = ft.Row(
            heading,
            spacing=TOKENS.spacing_sm + 4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.body = content
        super().__init__(
            content=ft.Column([self.header, content], spacing=TOKENS.spacing_md),
            padding=TOKENS.spacing_lg if padding is None else padding,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
            shadow=card_shadow(),
        )
