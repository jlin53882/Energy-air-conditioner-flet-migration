"""連結至目前確實可用工程工具的首頁。"""

import flet as ft
from collections.abc import Callable

from ..components.engineering_card import EngineeringCard
from ..navigation import ROUTES
from ..theme import TOKENS


class HomeView(ft.Column):
    """提供前往目前確實已實作工程工具的首頁捷徑。"""

    def __init__(self, on_navigate: Callable[[str], None]) -> None:
        """使用與側邊導覽相同的穩定路由清單建立首頁捷徑。

參數：
    on_navigate: 點選捷徑時執行的路由切換 回呼函式。

回傳：
    無。"""
        cards = []
        for route in ROUTES:
            if route.key == "home":
                continue
            cards.append(ft.Container(
                content=ft.Row([
                    ft.Icon(getattr(ft.Icons, route.icon), color=TOKENS.primary),
                    ft.Text(route.label, weight=ft.FontWeight.W_600, expand=True),
                    ft.Icon(ft.Icons.ARROW_FORWARD, size=16),
                ]),
                padding=TOKENS.spacing_md,
                bgcolor=TOKENS.surface,
                border=ft.Border.all(1, TOKENS.border),
                border_radius=ft.BorderRadius.all(TOKENS.radius_md),
                on_click=lambda _event, key=route.key: on_navigate(key),
                tooltip=f"開啟{route.label}",
                col={"xs": 12, "sm": 6, "lg": 4},
            ))
        super().__init__([
            EngineeringCard("快速開始", ft.ResponsiveRow(cards, spacing=TOKENS.spacing_md,
                                                           run_spacing=TOKENS.spacing_md),
                            "以下捷徑只連至目前已實作的計算功能。"),
            EngineeringCard("工作區導覽", ft.Text(
                "熱力性質查詢、HVAC 設備分析、濕空氣計算與熱力圖分別位於側邊導覽。",
                color=ft.Colors.BLUE_GREY_700,
            )),
        ], spacing=TOKENS.spacing_md, expand=True, scroll=ft.ScrollMode.AUTO)
