"""Presentation-only 共用計算頁版型：左側輸入卡、右側結果區。

``AnalysisWorkspace`` 只負責版面組成，禁止知道任何 compressor / evaporator /
psychrometric / CoolProp / diagram 相關邏輯。呼叫端負責提供已建構好的
工具選單、input 控制項與 :class:`ResultPanel`，以及目前分析的標題、說明與
公式文字。

版面：
- 左欄「輸入條件」卡：分析項目選單、分析說明與公式、模組輸入、全寬「計算」按鈕。
- 右欄結果區（:class:`AnalysisResultView`）：關鍵數值列、圖表＋完整性質表、
  可展開的計算過程。
窄視窗時兩欄上下堆疊（ResponsiveRow + col breakpoints）。
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from ..structured_result import StructuredResult
from ..theme import TOKENS, primary_button_style
from .analysis_result_view import AnalysisResultView
from .result_panel import ResultPanel

# 輸入欄固定佔較窄的欄寬，讓結果區有足夠空間並排圖表與性質表。
INPUT_COLUMN = {"xs": 12, "md": 5, "lg": 4, "xl": 3}
RESULT_COLUMN = {"xs": 12, "md": 7, "lg": 8, "xl": 9}


class AnalysisWorkspace(ft.Column):
    """以一致的工程排版呈現輸入卡與結果區。

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
    ) -> None:
        """組合工作區版面。

        參數：
            title: 頁面標題（例如「壓縮機分析」）。
            subtitle: 頁面副標題，簡述此分析頁的用途。
            tool_selector: 已建構好的工具選取控制項（通常是 ToolSelector）。
            input_content: 已建構好的輸入表單控制項。
            result_panel: 已建構好的 ResultPanel 實例。
            on_calculate: 計算按鈕的點擊回呼。
            show_execute_button: 是否顯示共用的「計算」按鈕；部分分析使用
                專屬按鈕時應設為 False，避免重複的執行按鈕。
            show_tool_selector: 是否顯示工具選單；只有單一工具時可隱藏。

        回傳：
            無。
        """
        super().__init__(spacing=TOKENS.spacing_md, expand=True, scroll=ft.ScrollMode.AUTO)
        self.header = ft.Column(
            [
                ft.Text(title, size=TOKENS.title, weight=ft.FontWeight.W_700),
                ft.Text(subtitle, size=TOKENS.body, color=TOKENS.text_secondary),
            ],
            spacing=TOKENS.spacing_xs,
            visible=False,
        )
        self.tool_selector = tool_selector
        self.tool_selector.visible = show_tool_selector

        # 分析名稱、說明與公式提示
        self.analysis_title = ft.Text("", size=TOKENS.body + 1, weight=ft.FontWeight.W_600,
                                      color=TOKENS.text_primary)
        self.analysis_summary = ft.Text("", size=TOKENS.caption, color=TOKENS.text_muted)
        self.formula_text = ft.Text("", size=TOKENS.caption + 1, font_family=TOKENS.mono_font,
                                    color=TOKENS.text_secondary, selectable=True)
        self.formula_box = ft.Container(
            content=self.formula_text,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor=TOKENS.surface_variant,
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
        )
        self.analysis_info = ft.Column(
            [self.analysis_title, self.analysis_summary, self.formula_box],
            spacing=6,
        )
        # action_bar.content 必須是計算按鈕本身，呼叫端與測試依此觸發計算。
        self.action_bar = ft.Container(
            content=ft.Button(
                content="計算",
                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                on_click=on_calculate,
                style=primary_button_style(),
                expand=True,
                height=TOKENS.button_height + 4,
                tooltip="Ctrl + Enter",
            ),
            visible=show_execute_button,
            padding=ft.Padding.only(top=TOKENS.spacing_sm),
        )
        self.input_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("輸入條件", size=TOKENS.body + 2, weight=ft.FontWeight.W_700,
                            color=TOKENS.text_primary),
                    self.tool_selector,
                    self.analysis_info,
                    ft.Divider(height=1, color=TOKENS.border),
                    input_content,
                    self.action_bar,
                ],
                spacing=TOKENS.spacing_md,
                # 讓計算按鈕與輸入欄同寬。
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=TOKENS.spacing_lg,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
        )

        self.result_view = AnalysisResultView(result_panel)
        # result_card 指向整個結果區，方便呼叫端與測試判斷結果區是否可見。
        self.result_card = self.result_view
        self.input_column = ft.Container(self.input_card, col=dict(INPUT_COLUMN))
        self.result_column = ft.Container(self.result_view, col=dict(RESULT_COLUMN))
        self.controls = [
            self.header,
            ft.ResponsiveRow(
                [self.input_column, self.result_column],
                spacing=TOKENS.spacing_md + 4,
                run_spacing=TOKENS.spacing_md,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ]

    def show_analysis(self, label: str, summary: str = "", formula: str = "") -> None:
        """更新輸入卡片中的分析名稱、說明與公式提示。

        參數：
            label: 分析名稱。
            summary: 選用的簡短說明。
            formula: 選用的公式提示。

        回傳：
            無。
        """
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
        structured: StructuredResult | None = None,
    ) -> None:
        """以目前 ResultPanel 狀態重新呈現結果區。

        參數：
            result_text: 模組回傳的原始結果文字；尚未計算時為 None。
            chart: 選用的結果圖表。
            structured: 選用的結構化結果。

        回傳：
            無。
        """
        self.result_view.show(result_text, chart=chart, structured=structured)

    def set_action_bar_visible(self, visible: bool) -> None:
        """切換共用計算按鈕的顯示，避免與模組內建按鈕重複。

        參數：
            visible: 是否顯示共用計算按鈕。

        回傳：
            無。
        """
        self.action_bar.visible = visible
