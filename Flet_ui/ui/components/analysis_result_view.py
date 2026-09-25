"""計算頁右側的結果區：關鍵數值列、圖表與完整性質表、可展開的計算過程。

版面參考工程計算工具常見的「關鍵數值＋圖表＋完整性質」排法。本元件只呈現
呼叫端提供的 :class:`StructuredResult` 與原始文字；狀態由 :class:`ResultPanel`
（通常由 ``AnalysisModuleAdapter`` 擁有）決定，這裡不執行任何計算。
"""

from __future__ import annotations

import flet as ft

from ..structured_result import StructuredResult
from ..theme import TOKENS, secondary_button_style
from .kpi_tile import KpiTile
from .property_table import PropertyTable
from .result_panel import ResultPanel


def result_card(title: str, content: ft.Control, trailing: ft.Control | None = None) -> ft.Container:
    """建立結果區使用的白底卡片（標題列＋內容）。

    參數：
        title: 卡片標題。
        content: 卡片內容。
        trailing: 選用的標題列右側控制項。

    回傳：
        卡片容器。
    """
    title_text = ft.Text(title, size=TOKENS.body + 1, weight=ft.FontWeight.W_600,
                         color=TOKENS.text_primary, expand=True)
    header = ft.Row([title_text] + ([trailing] if trailing is not None else []),
                    vertical_alignment=ft.CrossAxisAlignment.CENTER)
    return ft.Container(
        content=ft.Column([header, content], spacing=TOKENS.spacing_sm + 4),
        padding=TOKENS.spacing_lg - 4,
        bgcolor=TOKENS.surface,
        border=ft.Border.all(1, TOKENS.border),
        border_radius=ft.BorderRadius.all(TOKENS.radius_md),
    )


# 關鍵數值卡固定為一列四張的寬度，數量較少時靠左排列，不拉寬卡片。
KPI_COLUMN = {"xs": 6, "md": 3}


class AnalysisResultView(ft.Column):
    """依結果狀態切換空白提示、結構化結果與錯誤訊息。"""

    def __init__(self, result_panel: ResultPanel) -> None:
        """組合結果區塊。

        參數：
            result_panel: 顯示計算狀態的 ResultPanel。

        回傳：
            無。
        """
        self.result_panel = result_panel
        self.status_card = ft.Container(
            content=result_panel,
            padding=TOKENS.spacing_md,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
        )
        self.kpi_row = ft.ResponsiveRow(spacing=TOKENS.spacing_md - 4, run_spacing=TOKENS.spacing_md - 4)

        self.property_table = PropertyTable()
        self.table_card = result_card("完整性質", self.property_table)
        # 分析定義提供的結果圖表（例如 FigurePanel），只在成功計算後顯示。
        self.chart_host = ft.Container()
        self.chart_legend = ft.Row(spacing=6, tight=True)
        self.chart_card = result_card("圖表", self.chart_host, self.chart_legend)
        self.chart_title = self.chart_card.content.controls[0].controls[0]
        self.chart_column = ft.Container(self.chart_card, col={"xs": 12, "xl": 7})
        self.table_column = ft.Container(self.table_card, col={"xs": 12, "xl": 5})
        self.body_row = ft.ResponsiveRow(
            [self.chart_column, self.table_column],
            spacing=TOKENS.spacing_md,
            run_spacing=TOKENS.spacing_md,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        self.process_table = PropertyTable()
        self.process_body = ft.Container(content=self.process_table, visible=False)
        self.process_icon = ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=TOKENS.text_secondary)
        self.process_caption = ft.Text("", size=TOKENS.caption, color=TOKENS.text_muted)
        self.process_card = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row(
                            [
                                self.process_icon,
                                ft.Text("顯示計算過程", size=TOKENS.body, weight=ft.FontWeight.W_600,
                                        color=TOKENS.text_primary),
                                self.process_caption,
                            ],
                            spacing=TOKENS.spacing_sm,
                        ),
                        on_click=self.toggle_process,
                        ink=True,
                        padding=ft.Padding.symmetric(vertical=4),
                    ),
                    self.process_body,
                ],
                spacing=TOKENS.spacing_sm,
            ),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_lg - 4, vertical=TOKENS.spacing_sm + 4),
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
        )

        self.raw_text = ft.Text("", font_family="Courier New", selectable=True,
                                color=TOKENS.text_primary, size=TOKENS.caption + 1)
        self.raw_box = ft.Container(
            content=self.raw_text,
            padding=TOKENS.spacing_sm + 4,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
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
            [
                self.status_card,
                self.kpi_row,
                self.body_row,
                self.process_card,
                self.actions_row,
                self.raw_box,
            ],
            spacing=TOKENS.spacing_md,
        )
        self.show(None)

    def show(
        self,
        result_text: str | None,
        *,
        chart: ft.Control | None = None,
        structured: StructuredResult | None = None,
    ) -> None:
        """依目前狀態呈現結果；只有成功狀態才會顯示數值與圖表。

        參數：
            result_text: 模組回傳的原始結果文字；尚未計算時為 None。
            chart: 選用的結果圖表；成功時顯示並要求重繪。
            structured: 成功時要呈現的結構化結果。

        回傳：
            無。
        """
        has_text = bool(result_text)
        succeeded = has_text and self.result_panel.status == "success"
        self.raw_text.value = result_text or ""
        # 成功時由數值本身說明結果，狀態列只在尚未計算或失敗時出現。
        self.status_card.visible = not succeeded

        self._show_structured(structured if succeeded else None, chart if succeeded else None)

        self.details_button.disabled = not has_text
        self.copy_button.disabled = not succeeded
        self.actions_row.visible = has_text
        if not has_text:
            self.raw_box.visible = False
        self.details_button.text = "隱藏原始文字" if self.raw_box.visible else "顯示原始文字"

    def _show_structured(self, structured: StructuredResult | None, chart: ft.Control | None) -> None:
        """呈現關鍵數值、圖表／性質表與計算過程；未提供的部分會隱藏。

        參數：
            structured: 結構化結果；None 表示不顯示結構化區塊。
            chart: 選用的結果圖表。

        回傳：
            無。
        """
        metrics = list(structured.key_metrics) if structured else []
        self.kpi_row.controls = []
        for metric in metrics:
            tile = KpiTile(metric.label, col=dict(KPI_COLUMN))
            tile.set_value(metric.value, metric.unit)
            self.kpi_row.controls.append(tile)
        self.kpi_row.visible = bool(metrics)

        groups = list(structured.groups) if structured else []
        self.property_table.set_groups(groups)
        self.table_column.visible = bool(groups)

        self._show_chart(chart, structured)
        # 沒有圖表時性質表佔滿整列；兩者並存時寬螢幕左右並排。
        self.table_column.col = {"xs": 12, "xl": 5} if self.chart_column.visible else {"xs": 12}
        self.body_row.visible = self.chart_column.visible or self.table_column.visible

        process_groups = list(structured.process_groups) if structured else []
        self.process_table.set_groups(process_groups)
        self.process_caption.value = "、".join(group.title for group in process_groups)
        self.process_card.visible = bool(process_groups)

    def _show_chart(self, chart: ft.Control | None, structured: StructuredResult | None) -> None:
        """放入或隱藏結果圖表；圖表提供 refresh() 時要求重繪。

        參數：
            chart: 要顯示的圖表；None 表示隱藏。
            structured: 提供圖表標題與圖例的結構化結果。

        回傳：
            無。
        """
        self.chart_host.content = chart
        self.chart_column.visible = chart is not None
        self.chart_title.value = structured.chart_title if structured else "圖表"
        legend = structured.chart_legend if structured else ""
        self.chart_legend.controls = (
            [
                ft.Container(width=8, height=8, bgcolor=TOKENS.error, border_radius=ft.BorderRadius.all(4)),
                ft.Text(legend, size=TOKENS.caption, color=TOKENS.text_secondary),
            ]
            if legend
            else []
        )
        refresh = getattr(chart, "refresh", None)
        if callable(refresh):
            refresh()

    def toggle_process(self, _event: ft.ControlEvent | None) -> None:
        """展開或收合計算過程。

        參數：
            _event: Flet 點擊事件；此處不需讀取內容。

        回傳：
            無。
        """
        self.process_body.visible = not self.process_body.visible
        self.process_icon.icon = ft.Icons.EXPAND_MORE if self.process_body.visible else ft.Icons.CHEVRON_RIGHT
        self._safe_update()

    def _toggle_raw(self, _event: ft.ControlEvent | None) -> None:
        """顯示或隱藏模組回傳的原始結果文字。

        參數：
            _event: Flet 點擊事件；此處不需讀取事件內容。

        回傳：
            無。
        """
        self.raw_box.visible = not self.raw_box.visible
        self.details_button.text = "隱藏原始文字" if self.raw_box.visible else "顯示原始文字"
        self._safe_update()

    def _safe_update(self) -> None:
        """只在控制項已掛載到頁面時更新畫面。

        回傳：
            無。
        """
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
