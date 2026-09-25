"""分析結果卡片的內容：狀態列、分組指標、原始文字與複製動作。

本元件只負責呈現呼叫端提供的結果文字；狀態由 :class:`ResultPanel`
（通常由 ``AnalysisModuleAdapter`` 擁有）決定，這裡不執行任何計算。
"""

from __future__ import annotations

import flet as ft

from ..theme import TOKENS, secondary_button_style
from .result_panel import ResultPanel
from .result_sections import build_result_section_controls, parse_result_text


class AnalysisResultView(ft.Column):
    """將模組回傳的格式化文字投影為狀態、分組指標與可切換的原始文字。"""

    def __init__(self, result_panel: ResultPanel) -> None:
        """組合結果區塊。

        參數：
            result_panel: 顯示計算狀態的 ResultPanel。

        回傳：
            無。
        """
        self.result_panel = result_panel
        self.result_sections = ft.Column(spacing=TOKENS.spacing_sm + 4)
        # 分析定義提供的結果圖表（例如 FigurePanel），只在成功計算後顯示。
        self.chart_host = ft.Container(visible=False)
        self.raw_text = ft.Text("", font_family="Courier New", selectable=True,
                                color=TOKENS.text_primary, size=TOKENS.caption + 1)
        self.raw_box = ft.Container(
            content=self.raw_text,
            padding=TOKENS.spacing_sm + 4,
            bgcolor=TOKENS.surface_muted,
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
            visible=False,
        )
        self.details_button = ft.TextButton(
            "顯示原始文字", icon=ft.Icons.NOTES, on_click=self._toggle_raw, disabled=True
        )
        self.copy_button = ft.OutlinedButton(
            "複製結果", icon=ft.Icons.CONTENT_COPY, on_click=self._copy, disabled=True,
            style=secondary_button_style(),
        )
        self.actions_row = ft.Row(
            [self.details_button, ft.Container(expand=True), self.copy_button],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        super().__init__(
            [self.result_panel, self.result_sections, self.chart_host, self.actions_row, self.raw_box],
            spacing=TOKENS.spacing_sm + 4,
        )

    def show(
        self,
        result_text: str | None,
        *,
        accent: str,
        chart: ft.Control | None = None,
        chart_first: bool = False,
    ) -> None:
        """依目前狀態呈現結果；只有成功狀態才會投影指標與圖表。

        參數：
            result_text: 模組回傳的原始結果文字；尚未計算時為 None。
            accent: 指標卡片使用的強調色。
            chart: 選用的結果圖表；成功時顯示並要求重繪。
            chart_first: True 表示圖表放在指標卡片之前。

        回傳：
            無。
        """
        has_text = bool(result_text)
        succeeded = has_text and self.result_panel.status == "success"
        self.raw_text.value = result_text or ""
        self.result_sections.controls = (
            build_result_section_controls(parse_result_text(result_text), accent=accent)
            if succeeded
            else []
        )
        self._show_chart(chart if succeeded else None, chart_first)
        self.details_button.disabled = not has_text
        self.copy_button.disabled = not succeeded
        if not has_text:
            self.raw_box.visible = False
        self.details_button.text = "隱藏原始文字" if self.raw_box.visible else "顯示原始文字"

    def _show_chart(self, chart: ft.Control | None, chart_first: bool) -> None:
        """放入或隱藏結果圖表；圖表提供 refresh() 時要求重繪。

        參數：
            chart: 要顯示的圖表；None 表示隱藏。
            chart_first: True 表示圖表放在指標卡片之前。

        回傳：
            無。
        """
        self.chart_host.content = chart
        self.chart_host.visible = chart is not None
        self.controls.remove(self.chart_host)
        anchor = self.result_panel if chart_first else self.result_sections
        self.controls.insert(self.controls.index(anchor) + 1, self.chart_host)
        refresh = getattr(chart, "refresh", None)
        if callable(refresh):
            refresh()

    def _toggle_raw(self, _event: ft.ControlEvent | None) -> None:
        """顯示或隱藏模組回傳的原始結果文字。

        參數：
            _event: Flet 點擊事件；此處不需讀取事件內容。

        回傳：
            無。
        """
        self.raw_box.visible = not self.raw_box.visible
        self.details_button.text = "隱藏原始文字" if self.raw_box.visible else "顯示原始文字"
        try:
            attached_page = self.page
        except RuntimeError:
            attached_page = None
        if attached_page:
            self.update()

    async def _copy(self, _event: ft.ControlEvent | None) -> None:
        """透過 Flet 剪貼簿服務複製目前的結果文字。

        參數：
            _event: Flet 點擊事件；此處不需讀取事件內容。

        回傳：
            無。
        """
        if self.raw_text.value:
            await ft.Clipboard().set(self.raw_text.value)
