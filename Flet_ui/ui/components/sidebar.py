"""依工程工作流程分組並使用語意路由鍵的淺色側邊導覽，可收合為圖示列。"""

import flet as ft
from collections.abc import Callable

from ..navigation import ROUTES, WorkspaceRoute
from ..theme import TOKENS


class Sidebar(ft.Container):
    """依工程流程分組，提供可到達的工作區路由。"""

    def __init__(self, on_select: Callable[[str], None], selected_key: str) -> None:
        """建立含圖示與標籤的導覽項目，選取時回傳穩定路由鍵。

參數：
    on_select: 使用者選取路由時呼叫的回呼函式。
    selected_key: 初始選取的穩定路由鍵。

回傳：
    無。"""
        self.on_select = on_select
        self.selected_key = selected_key
        self.compact = False
        self.items: dict[str, ft.Container] = {}
        self._icons: dict[str, ft.Icon] = {}
        self._labels: dict[str, ft.Text] = {}
        self._indicators: dict[str, ft.Container] = {}
        self.section_labels: list[ft.Control] = []
        groups: dict[str, list[WorkspaceRoute]] = {}
        for route in ROUTES:
            groups.setdefault(route.section, []).append(route)
        section_controls: list[ft.Control] = []
        for section, routes in groups.items():
            section_label = ft.Container(
                content=ft.Text(
                    section,
                    size=TOKENS.overline,
                    color=TOKENS.nav_text_muted,
                    weight=ft.FontWeight.W_600,
                ),
                padding=ft.Padding.only(left=TOKENS.spacing_sm + 4, top=TOKENS.spacing_md, bottom=2),
            )
            self.section_labels.append(section_label)
            section_controls.append(section_label)
            for route in routes:
                item = self._route_item(route)
                self.items[route.key] = item
                section_controls.append(item)
        self.footer = ft.Container(
            content=ft.Column(
                [
                    ft.Text("計算引擎", size=TOKENS.overline, color=TOKENS.nav_text_muted,
                            weight=ft.FontWeight.W_600),
                    ft.Text("CoolProp · ASHRAE 濕空氣模型", size=TOKENS.caption,
                            color=TOKENS.nav_text),
                ],
                spacing=2,
                tight=True,
            ),
            padding=TOKENS.spacing_md,
            margin=ft.Margin.only(top=TOKENS.spacing_md),
            bgcolor=TOKENS.surface_variant,
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
        )
        super().__init__(
            width=TOKENS.sidebar_width,
            content=ft.Column(
                [
                    ft.Column(section_controls, spacing=2, scroll=ft.ScrollMode.AUTO, expand=True),
                    self.footer,
                ],
                spacing=0,
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_sm + 4, vertical=TOKENS.spacing_sm),
            bgcolor=TOKENS.nav_background,
            border=ft.Border.only(right=ft.BorderSide(1, TOKENS.border)),
        )
        self.set_selected(selected_key)

    def set_compact(self, compact: bool) -> None:
        """窄版導覽列空間不足時隱藏文字標籤、分類標題與頁尾資訊。

參數：
    compact: True 表示採用精簡圖示列。

回傳：
    無。"""
        self.compact = compact
        for label in self.section_labels:
            label.visible = not compact
        self.footer.visible = not compact
        self.padding = ft.Padding.symmetric(
            horizontal=TOKENS.spacing_sm if compact else TOKENS.spacing_sm + 4,
            vertical=TOKENS.spacing_sm,
        )
        for key, item in self.items.items():
            self._labels[key].visible = not compact
            self._indicators[key].visible = not compact
            item.content.alignment = (
                ft.MainAxisAlignment.CENTER if compact else ft.MainAxisAlignment.START
            )
            item.padding = (
                ft.Padding.symmetric(vertical=12)
                if compact
                else ft.Padding.symmetric(horizontal=TOKENS.spacing_sm + 4, vertical=10)
            )

    def set_selected(self, route_key: str) -> None:
        """更新目前路由的醒目提示，其餘項目回到一般樣式。

參數：
    route_key: 目前選取的穩定路由鍵。

回傳：
    無。"""
        self.selected_key = route_key
        for key, item in self.items.items():
            selected = key == route_key
            self._icons[key].color = TOKENS.nav_accent if selected else TOKENS.nav_text_muted
            self._labels[key].color = TOKENS.nav_accent if selected else TOKENS.nav_text
            self._labels[key].weight = ft.FontWeight.W_600 if selected else ft.FontWeight.W_400
            self._indicators[key].bgcolor = TOKENS.nav_accent if selected else ft.Colors.TRANSPARENT
            item.bgcolor = TOKENS.nav_selected if selected else None

    def _route_item(self, route: WorkspaceRoute) -> ft.Container:
        """建立單一路由控制項，回呼函式傳遞穩定鍵而非顯示標籤。

參數：
    route: 要呈現的工作區路由定義。

回傳：
    對應路由的 Flet 容器控制項。"""
        icon = ft.Icon(getattr(ft.Icons, route.icon), size=20)
        label = ft.Text(route.label, size=TOKENS.body, expand=True)
        indicator = ft.Container(width=6, height=6, border_radius=ft.BorderRadius.all(3))
        self._icons[route.key] = icon
        self._labels[route.key] = label
        self._indicators[route.key] = indicator
        return ft.Container(
            content=ft.Row(
                [icon, label, indicator],
                spacing=TOKENS.spacing_sm + 4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_sm + 4, vertical=10),
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
            on_click=lambda _event, key=route.key: self.on_select(key),
            tooltip=route.label,
            ink=True,
        )
