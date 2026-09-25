"""連結至目前確實可用工程工具的首頁。"""

import flet as ft
from collections.abc import Callable, Mapping

from ..components.engineering_card import EngineeringCard
from ..navigation import ROUTES, WorkspaceRoute
from ..theme import TOKENS

# 常用冷媒捷徑：點選後以該流體開啟狀態查詢；不代表 CoolProp 的完整支援清單。
FLUID_SHORTCUTS = ("R32", "R410A", "R134a", "R290", "R600a", "R22")

WORKFLOW_STEPS = (
    ("thermo_properties", "1", "查詢狀態點", "以兩個獨立性質取得焓、熵、比容等狀態值。"),
    ("compressor", "2", "分析設備", "將狀態值帶入壓縮機、蒸發器或冷凝器分析。"),
    ("ph_chart", "3", "繪製熱力圖", "在 P-h／T-s 圖上檢查循環與壓縮過程。"),
)


class HomeView(ft.Column):
    """提供前往目前確實已實作工程工具的首頁捷徑。"""

    def __init__(
        self,
        on_navigate: Callable[[str], None],
        analysis_counts: Mapping[str, int] | None = None,
        total_analyses: int | None = None,
        on_fluid: Callable[[str], None] | None = None,
    ) -> None:
        """使用與側邊導覽相同的穩定路由清單建立首頁捷徑。

參數：
    on_navigate: 點選捷徑時執行的路由切換回呼函式。
    analysis_counts: 選用的路由鍵對應已註冊分析項目數量；只顯示呼叫端實際提供的數字。
    total_analyses: 選用的分析註冊表項目總數；未提供時不顯示此統計。
    on_fluid: 選用的常用冷媒捷徑回呼函式；未提供時不顯示冷媒捷徑。

回傳：
    無。"""
        self.on_navigate = on_navigate
        self.analysis_counts = dict(analysis_counts or {})
        self.total_analyses = total_analyses
        self.on_fluid = on_fluid
        self.tool_cards: dict[str, ft.Container] = {}
        tool_routes = [route for route in ROUTES if route.key != "home"]
        for route in tool_routes:
            self.tool_cards[route.key] = self._tool_card(route)
        tools = EngineeringCard(
            "工程工具",
            ft.ResponsiveRow(list(self.tool_cards.values()), spacing=TOKENS.spacing_md,
                             run_spacing=TOKENS.spacing_md),
            "以下捷徑只連至目前已實作的計算功能。",
            icon=ft.Icons.APPS_OUTLINED,
        )

        super().__init__(
            [
                self._hero(len(tool_routes)),
                tools,
                self._workflow_card(),
            ]
            + ([self._fluid_card()] if on_fluid else []),
            spacing=TOKENS.spacing_lg,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def _hero(self, tool_count: int) -> ft.Container:
        """建立首頁頂端的歡迎橫幅與主要行動按鈕。

參數：
    tool_count: 目前可到達的工具路由數量。

回傳：
    橫幅容器。"""
        stats = [self._hero_stat(str(tool_count), "項工程工具")]
        if self.total_analyses:
            stats.append(self._hero_stat(str(self.total_analyses), "種已註冊分析"))
        stats.append(self._hero_stat("SI / IP", "輸出單位即時切換"))
        self.start_button = ft.Button(
            "開始狀態查詢",
            icon=ft.Icons.ARROW_FORWARD,
            on_click=lambda _event: self.on_navigate("thermo_properties"),
            style=ft.ButtonStyle(
                color=TOKENS.primary,
                bgcolor=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=TOKENS.radius_sm),
                padding=ft.Padding.symmetric(horizontal=20, vertical=14),
            ),
        )
        self.chart_button = ft.OutlinedButton(
            "繪製 P-h 圖",
            icon=ft.Icons.SHOW_CHART,
            on_click=lambda _event: self.on_navigate("ph_chart"),
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                side=ft.BorderSide(1, ft.Colors.with_opacity(0.6, ft.Colors.WHITE)),
                shape=ft.RoundedRectangleBorder(radius=TOKENS.radius_sm),
                padding=ft.Padding.symmetric(horizontal=20, vertical=14),
            ),
        )
        return ft.Container(
            content=ft.ResponsiveRow(
                [
                    ft.Column(
                        [
                            ft.Container(
                                content=ft.Text("HVAC ENGINEERING WORKSPACE", size=TOKENS.overline,
                                                weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.WHITE),
                                border_radius=ft.BorderRadius.all(TOKENS.radius_pill),
                            ),
                            ft.Text("熱力學與冷凍空調工程計算", size=TOKENS.display,
                                    weight=ft.FontWeight.W_700, color=ft.Colors.WHITE),
                            ft.Text(
                                "從冷媒狀態查詢、設備能量分析、濕空氣計算到熱力圖繪製，"
                                "所有結果皆由既有 CoolProp 與 HVAC 計算服務提供。",
                                size=TOKENS.body + 1,
                                color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE),
                            ),
                            ft.Row([self.start_button, self.chart_button], spacing=TOKENS.spacing_sm,
                                   wrap=True, run_spacing=TOKENS.spacing_sm),
                        ],
                        spacing=TOKENS.spacing_md,
                        col={"xs": 12, "lg": 8},
                    ),
                    ft.Column(
                        stats,
                        spacing=TOKENS.spacing_sm,
                        col={"xs": 12, "lg": 4},
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                ],
                spacing=TOKENS.spacing_lg,
                run_spacing=TOKENS.spacing_lg,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=TOKENS.spacing_xl,
            border_radius=ft.BorderRadius.all(TOKENS.radius_lg),
            bgcolor=TOKENS.primary,
        )

    @staticmethod
    def _hero_stat(value: str, label: str) -> ft.Container:
        """建立橫幅右側的數據摘要。

參數：
    value: 數據主值。
    label: 數據說明。

回傳：
    數據摘要容器。"""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(value, size=TOKENS.title, weight=ft.FontWeight.W_700,
                            color=ft.Colors.WHITE),
                    ft.Text(label, size=TOKENS.caption, color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE),
                            expand=True),
                ],
                spacing=TOKENS.spacing_sm + 4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_md, vertical=12),
            bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.WHITE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.16, ft.Colors.WHITE)),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
        )

    def _tool_card(self, route: WorkspaceRoute) -> ft.Container:
        """建立單一工具卡片，點選時以穩定路由鍵導覽。

參數：
    route: 工具對應的路由定義。

回傳：
    工具卡片容器。"""
        accent, soft = TOKENS.primary, TOKENS.primary_soft
        footer: list[ft.Control] = []
        count = self.analysis_counts.get(route.key)
        if count and count > 1:
            footer.append(
                ft.Container(
                    content=ft.Text(f"{count} 種分析", size=TOKENS.overline,
                                    weight=ft.FontWeight.W_600, color=accent),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    bgcolor=soft,
                    border_radius=ft.BorderRadius.all(TOKENS.radius_pill),
                )
            )
        footer.append(ft.Container(expand=True))
        footer.append(
            ft.Row(
                [
                    ft.Text("開啟", size=TOKENS.caption, weight=ft.FontWeight.W_600, color=accent),
                    ft.Icon(ft.Icons.ARROW_FORWARD, size=14, color=accent),
                ],
                spacing=4,
                tight=True,
            )
        )
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(getattr(ft.Icons, route.icon), color=accent, size=22),
                                width=42,
                                height=42,
                                alignment=ft.Alignment.CENTER,
                                bgcolor=soft,
                                border_radius=ft.BorderRadius.all(TOKENS.radius_md),
                            ),
                            ft.Container(expand=True),
                            ft.Container(
                                content=ft.Text(route.section, size=TOKENS.overline,
                                                weight=ft.FontWeight.W_600, color=accent),
                                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                                border=ft.Border.all(1, ft.Colors.with_opacity(0.35, accent)),
                                border_radius=ft.BorderRadius.all(TOKENS.radius_pill),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.Text(route.label, size=TOKENS.section_title - 1, weight=ft.FontWeight.W_600,
                            color=TOKENS.text_primary),
                    ft.Text(route.description, size=TOKENS.caption + 1, color=TOKENS.text_secondary,
                            max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Row(footer, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ],
                spacing=TOKENS.spacing_sm + 2,
            ),
            padding=TOKENS.spacing_lg - 4,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
            on_click=lambda _event, key=route.key: self.on_navigate(key),
            tooltip=f"開啟{route.label}",
            ink=True,
            col={"xs": 12, "sm": 6, "xl": 4},
        )

    def _workflow_card(self) -> EngineeringCard:
        """建立建議工作流程卡片，每一步都連到實際存在的路由。

回傳：
    工作流程卡片。"""
        steps = []
        for route_key, number, title, description in WORKFLOW_STEPS:
            steps.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(number, weight=ft.FontWeight.W_700,
                                                color=ft.Colors.WHITE),
                                width=32,
                                height=32,
                                alignment=ft.Alignment.CENTER,
                                bgcolor=TOKENS.primary,
                                border_radius=ft.BorderRadius.all(TOKENS.radius_pill),
                            ),
                            ft.Column(
                                [
                                    ft.Text(title, weight=ft.FontWeight.W_600,
                                            color=TOKENS.text_primary),
                                    ft.Text(description, size=TOKENS.caption,
                                            color=TOKENS.text_secondary),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ],
                        spacing=TOKENS.spacing_sm + 4,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    padding=TOKENS.spacing_md,
                    bgcolor=TOKENS.surface_variant,
                    border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
                    on_click=lambda _event, key=route_key: self.on_navigate(key),
                    ink=True,
                    col={"xs": 12, "md": 4},
                )
            )
        return EngineeringCard(
            "建議工作流程",
            ft.ResponsiveRow(steps, spacing=TOKENS.spacing_sm, run_spacing=TOKENS.spacing_sm),
            "典型的冷凍循環分析步驟；每一步都可直接開啟對應工具。",
            icon=ft.Icons.ROUTE_OUTLINED,
        )

    def _fluid_card(self) -> EngineeringCard:
        """建立常用冷媒捷徑卡片，點選後以該流體開啟狀態查詢。

回傳：
    冷媒捷徑卡片。"""
        self.fluid_buttons = [
            ft.OutlinedButton(
                fluid,
                on_click=lambda _event, value=fluid: self.on_fluid(value),
                tooltip=f"以 {fluid} 開啟狀態查詢",
                style=ft.ButtonStyle(
                    color=TOKENS.primary,
                    side=ft.BorderSide(1, TOKENS.border_strong),
                    shape=ft.RoundedRectangleBorder(radius=TOKENS.radius_sm),
                    text_style=ft.TextStyle(font_family=TOKENS.mono_font, weight=ft.FontWeight.W_600),
                ),
            )
            for fluid in FLUID_SHORTCUTS
        ]
        return EngineeringCard(
            "常用冷媒",
            ft.Row(self.fluid_buttons, spacing=TOKENS.spacing_sm, run_spacing=TOKENS.spacing_sm, wrap=True),
            "點選即以該流體開啟狀態查詢；不代表 CoolProp 的完整支援清單。",
            icon=ft.Icons.PROPANE_TANK_OUTLINED,
        )
