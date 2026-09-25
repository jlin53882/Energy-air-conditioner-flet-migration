"""Presentation-only 共用殼：ToolSelector 卡片 + Input/Result 卡片 + ActionBar。

``AnalysisWorkspace`` 只負責版面組成，禁止知道任何 compressor / evaporator /
psychrometric / CoolProp / diagram 相關邏輯。呼叫端負責提供已建構好的
input 控制項與 :class:`ResultPanel`，以及目前分析的標題、說明與公式文字。
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from ..theme import TOKENS, card_shadow, primary_button_style
from .analysis_result_view import AnalysisResultView
from .result_panel import ResultPanel


def _card(content: ft.Control, *, padding: int = TOKENS.spacing_lg) -> ft.Container:
    """建立工作區共用的白色圓角卡片。

    參數：
        content: 卡片內容。
        padding: 卡片內距。

    回傳：
        卡片容器。
    """
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=TOKENS.surface,
        border=ft.Border.all(1, TOKENS.border),
        border_radius=ft.BorderRadius.all(TOKENS.radius_md),
        shadow=card_shadow(),
    )


class AnalysisWorkspace(ft.Column):
    """以一致的工程排版呈現 ToolSelector、Input/Result 卡片與 ActionBar。

    Wide / Medium 版面呈現 Input | Result 並排；Narrow 版面改為單欄堆疊，
    沿用 PR #2 建立的 responsive contract（ResponsiveRow + col breakpoints）。
    頁面標題與說明由 AppShell 的 route header 呈現，因此 ``header`` 只保留
    給沒有外殼的嵌入情境，預設不顯示。
    """

    def __init__(
        self,
        *,
        title: str,
        subtitle: str,
        tool_selector: ft.Control,
        input_content: ft.Control,
        result_panel: ResultPanel,
        on_calculate: Callable[[ft.ControlEvent | None], None],
        show_execute_button: bool = True,
        show_tool_selector: bool = True,
        accent: str = TOKENS.primary,
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
            show_tool_selector: 是否顯示工具選取卡片；只有單一工具時可隱藏。
            accent: 此分類使用的強調色。

        回傳：
            無。
        """
        super().__init__(spacing=TOKENS.spacing_md, expand=True, scroll=ft.ScrollMode.AUTO)
        self.accent = accent
        self.header = ft.Column(
            [
                ft.Text(title, size=TOKENS.title, weight=ft.FontWeight.W_700),
                ft.Text(subtitle, size=TOKENS.body, color=TOKENS.text_secondary),
            ],
            spacing=TOKENS.spacing_xs,
            visible=False,
        )
        self.tool_selector = tool_selector
        self.active_tool_label = ft.Text(
            "", color=accent, weight=ft.FontWeight.W_600, size=TOKENS.caption + 1
        )
        self.selector_card = _card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("分析項目", size=TOKENS.caption, weight=ft.FontWeight.W_600,
                                    color=TOKENS.text_muted),
                            ft.Container(expand=True),
                            self.active_tool_label,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    tool_selector,
                ],
                spacing=TOKENS.spacing_sm + 2,
            ),
            padding=TOKENS.spacing_md,
        )
        self.selector_card.visible = show_tool_selector

        # 輸入卡片：分析標題、說明、公式、模組輸入與執行列
        self.analysis_title = ft.Text("", size=TOKENS.section_title, weight=ft.FontWeight.W_600,
                                      color=TOKENS.text_primary)
        self.analysis_summary = ft.Text("", size=TOKENS.caption, color=TOKENS.text_muted)
        self.formula_text = ft.Text("", size=TOKENS.body, font_family="Courier New",
                                    color=TOKENS.text_primary, selectable=True)
        self.formula_box = ft.Container(
            content=ft.Row(
                [ft.Icon(ft.Icons.FUNCTIONS, size=16, color=TOKENS.text_muted), self.formula_text],
                spacing=TOKENS.spacing_sm,
                wrap=True,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            bgcolor=TOKENS.surface_variant,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
        )
        input_header = ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.FUNCTIONS, size=18, color=accent),
                            width=34, height=34, alignment=ft.Alignment.CENTER,
                            bgcolor=ft.Colors.with_opacity(0.12, accent),
                            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
                        ),
                        ft.Column([self.analysis_title, self.analysis_summary], spacing=2,
                                  tight=True, expand=True),
                    ],
                    spacing=TOKENS.spacing_sm + 4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.formula_box,
                ft.Divider(height=1, color=TOKENS.border),
            ],
            spacing=TOKENS.spacing_md,
        )
        # action_bar.content 必須是執行按鈕本身，呼叫端與測試依此觸發計算。
        self.action_bar = ft.Container(
            content=ft.Button(
                content="執行分析",
                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                on_click=on_calculate,
                style=primary_button_style(),
            ),
            visible=show_execute_button,
        )
        self.action_hint = ft.Row(
            [
                ft.Icon(ft.Icons.KEYBOARD_OUTLINED, size=14, color=TOKENS.text_muted),
                ft.Text("Ctrl + Enter 執行", size=TOKENS.caption, color=TOKENS.text_muted),
            ],
            spacing=6,
            visible=show_execute_button,
        )
        action_row = ft.Container(
            content=ft.Row(
                [self.action_hint, ft.Container(expand=True), self.action_bar],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(top=TOKENS.spacing_sm),
        )
        self.input_card = _card(
            ft.Column([input_header, input_content, action_row], spacing=TOKENS.spacing_md)
        )

        # 結果卡片
        self.result_view = AnalysisResultView(result_panel)
        self.result_card = _card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(ft.Icons.INSIGHTS_OUTLINED, size=18, color=TOKENS.accent),
                                width=34, height=34, alignment=ft.Alignment.CENTER,
                                bgcolor=TOKENS.accent_soft,
                                border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
                            ),
                            ft.Column(
                                [
                                    ft.Text("分析結果", size=TOKENS.section_title,
                                            weight=ft.FontWeight.W_600, color=TOKENS.text_primary),
                                    ft.Text("切換頂端輸出單位會以相同輸入重新格式化。",
                                            size=TOKENS.caption, color=TOKENS.text_muted),
                                ],
                                spacing=2,
                                tight=True,
                                expand=True,
                            ),
                        ],
                        spacing=TOKENS.spacing_sm + 4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.result_view,
                ],
                spacing=TOKENS.spacing_md,
            )
        )
        self.input_column = ft.Column([self.input_card], col={"xs": 12, "lg": 6})
        self.result_column = ft.Column([self.result_card], col={"xs": 12, "lg": 6})
        self.controls = [
            self.header,
            self.selector_card,
            ft.ResponsiveRow(
                [self.input_column, self.result_column],
                spacing=TOKENS.spacing_md,
                run_spacing=TOKENS.spacing_md,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ]

    def show_analysis(self, label: str, summary: str = "", formula: str = "") -> None:
        """更新輸入卡片頂端的分析名稱、說明與公式提示。

        參數：
            label: 分析名稱。
            summary: 選用的簡短說明。
            formula: 選用的公式提示。

        回傳：
            無。
        """
        self.active_tool_label.value = f"目前：{label}"
        self.analysis_title.value = label
        self.analysis_summary.value = summary
        self.analysis_summary.visible = bool(summary)
        self.formula_text.value = formula
        self.formula_box.visible = bool(formula)

    def show_result(
        self,
        result_text: str | None,
        *,
        chart: ft.Control | None = None,
        chart_first: bool = False,
    ) -> None:
        """以目前 ResultPanel 狀態重新呈現結果區。

        參數：
            result_text: 模組回傳的原始結果文字；尚未計算時為 None。
            chart: 選用的結果圖表。
            chart_first: True 表示圖表放在指標卡片之前。

        回傳：
            無。
        """
        self.result_view.show(result_text, accent=self.accent, chart=chart, chart_first=chart_first)

    def set_action_bar_visible(self, visible: bool) -> None:
        """切換共用執行按鈕的顯示，避免與模組內建按鈕重複。

        參數：
            visible: 是否顯示共用執行按鈕。

        回傳：
            無。
        """
        self.action_bar.visible = visible
        self.action_hint.visible = visible
