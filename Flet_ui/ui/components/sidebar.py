"""依工程工作流程分組並使用語意路由鍵的側邊導覽。"""

import flet as ft
from collections.abc import Callable

from ..navigation import ROUTES, WorkspaceRoute
from ..theme import TOKENS


class Sidebar(ft.Container):
    """依工程流程分組，提供可到達的工作區路由。"""

    def __init__(self, on_select: Callable[[str], None], selected_key: str) -> None:
        """建立含圖示與標籤的導覽項目，選取時回傳穩定路由鍵。

參數：
    on_select: 使用者選取路由時呼叫的 回呼函式。
    selected_key: 初始選取的穩定路由鍵。

回傳：
    無。"""
        self.on_select = on_select
        self.selected_key = selected_key
        self.items: dict[str, ft.Control] = {}
        self.section_labels: list[ft.Text] = []
        groups: dict[str, list[WorkspaceRoute]] = {}
        for route in ROUTES:
            groups.setdefault(route.section, []).append(route)
        section_controls: list[ft.Control] = []
        for section, routes in groups.items():
            section_label = ft.Text(section, size=TOKENS.caption, color=ft.Colors.BLUE_GREY_600,
                                    weight=ft.FontWeight.W_600)
            self.section_labels.append(section_label)
            section_controls.append(section_label)
            for route in routes:
                item = self._route_item(route)
                self.items[route.key] = item
                section_controls.append(item)
        super().__init__(
            width=TOKENS.sidebar_width,
            content=ft.Column(section_controls, spacing=TOKENS.spacing_sm, scroll=ft.ScrollMode.AUTO),
            padding=TOKENS.spacing_md,
            bgcolor=TOKENS.surface,
            border=ft.Border.only(right=ft.BorderSide(1, TOKENS.border)),
        )

    def set_compact(self, compact: bool) -> None:
        """窄版導覽列空間不足時隱藏文字標籤與分類標題。

參數：
    compact: True 表示採用精簡圖示列。

回傳：
    無。"""
        for label in self.section_labels:
            label.visible = not compact
        for item in self.items.values():
            _, label = item.content.controls
            label.visible = not compact
            item.content.alignment = (
                ft.MainAxisAlignment.CENTER if compact else ft.MainAxisAlignment.START
            )

    def _route_item(self, route: WorkspaceRoute) -> ft.Control:
        """建立單一路由控制項，回呼函式 傳遞穩定鍵而非顯示標籤。

參數：
    route: 要呈現的工作區路由定義。

回傳：
    對應路由的 Flet 容器控制項。"""
        selected = route.key == self.selected_key
        icon = getattr(ft.Icons, route.icon)
        return ft.Container(
            content=ft.Row([ft.Icon(icon, size=18, color=TOKENS.primary if selected else ft.Colors.BLUE_GREY_600),
                            ft.Text(route.label, size=TOKENS.body, weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_400)],
                           spacing=TOKENS.spacing_sm),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_md, vertical=TOKENS.spacing_sm),
            bgcolor="#E7EFF8" if selected else None,
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
            on_click=lambda _event, key=route.key: self.on_select(key),
            tooltip=route.label,
        )
