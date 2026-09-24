"""Presentation-only 共用殼：Header + ToolSelector + Input/Result + ActionBar。

``AnalysisWorkspace`` 只負責版面組成，禁止知道任何 compressor / evaporator /
psychrometric / CoolProp / diagram 相關邏輯。呼叫端負責提供已建構好的
input 控制項與 :class:`ResultPanel`。
"""

from __future__ import annotations

import flet as ft

from .engineering_card import EngineeringCard
from .result_panel import ResultPanel
from ..theme import TOKENS


class AnalysisWorkspace(ft.Column):
    """以一致的工程排版呈現 Header、ToolSelector、Input/Result 與 ActionBar。

    Wide / Medium 版面呈現 Input | Result 並排；Narrow 版面改為單欄堆疊，
    沿用 PR #2 建立的 responsive contract（ResponsiveRow + col breakpoints）。
    """

    def __init__(
        self,
        *,
        title: str,
        subtitle: str,
        tool_selector: ft.Control,
        input_content: ft.Control,
        result_panel: ResultPanel,
        on_calculate: callable,
        show_execute_button: bool = True,
    ) -> None:
        """組合工作區版面。

        參數：
            title: 頁面標題（例如「壓縮機分析」）。
            subtitle: 頁面副標題，簡述此分析頁的用途。
            tool_selector: 已建構好的工具選取控制項（通常是 ToolSelector）。
            input_content: 已建構好的輸入表單控制項。
            result_panel: 已建構好的 ResultPanel 實例。
            on_calculate: 執行分析按鈕的點擊回呼。
            show_execute_button: 是否顯示共用的「執行分析」按鈕；部分分析
                （例如熱力圖）使用專屬按鈕，此時應設為 False 以避免
                duplicate execute 按鈕同時出現。

        回傳：
            無。
        """
        super().__init__(spacing=TOKENS.spacing_lg, expand=True, scroll=ft.ScrollMode.AUTO)
        self.header = ft.Column(
            [
                ft.Text(title, size=TOKENS.title, weight=ft.FontWeight.W_700),
                ft.Text(subtitle, size=TOKENS.body, color=ft.Colors.BLUE_GREY_600),
            ],
            spacing=TOKENS.spacing_xs,
        )
        self.tool_selector = tool_selector
        self.action_bar = ft.Container(
            content=ft.Button(
                content="執行分析",
                icon=ft.Icons.ANALYTICS_OUTLINED,
                on_click=on_calculate,
            ),
            padding=ft.Padding.only(top=TOKENS.spacing_sm, bottom=TOKENS.spacing_sm),
            alignment=ft.Alignment.CENTER,
            visible=show_execute_button,
        )
        self.input_card = EngineeringCard(
            "輸入條件",
            ft.Column([input_content, self.action_bar], spacing=TOKENS.spacing_md),
        )
        self.result_card = EngineeringCard("分析結果", result_panel)
        self.controls = [
            self.header,
            self.tool_selector,
            ft.ResponsiveRow(
                [
                    ft.Container(self.input_card, col={"xs": 12, "lg": 6}),
                    ft.Container(self.result_card, col={"xs": 12, "lg": 6}),
                ],
                spacing=TOKENS.spacing_lg,
                run_spacing=TOKENS.spacing_lg,
            ),
        ]

    def set_action_bar_visible(self, visible: bool) -> None:
        """切換共用執行按鈕的顯示，避免與模組內建按鈕重複。

        參數：
            visible: 是否顯示共用執行按鈕。

        回傳：
            無。
        """
        self.action_bar.visible = visible
