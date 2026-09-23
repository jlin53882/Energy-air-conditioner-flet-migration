"""呈現計算狀態與結構化指標卡片。"""

from collections.abc import Mapping

import flet as ft

from ..theme import TOKENS


class ResultPanel(ft.Container):
    """呈現計算狀態、真實指標、結果中繼資料與選用的原始輸出。"""

    SUPPORTED_STATES = frozenset({"empty", "loading", "success", "warning", "error"})

    def __init__(self) -> None:
        """初始化為明確的空狀態，直到計算成功後才呈現結果。

回傳：
    無。"""
        self.status = "empty"
        self.metrics: dict[str, str] = {}
        self.metadata: dict[str, str] = {}
        self.raw_output = ""
        self._body = ft.Column(spacing=TOKENS.spacing_md)
        super().__init__(
            content=self._body,
            padding=TOKENS.spacing_lg,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
        )
        self.set_status("empty", "尚未計算", "輸入條件後執行計算。")

    def set_status(self, status: str, title: str, message: str = "") -> None:
        """同時使用文字與圖示呈現狀態，避免只靠顏色傳達訊息。

參數：
    status: 支援的計算狀態代碼。
    title: 狀態標題。
    message: 選用的狀態補充說明。

回傳：
    無。"""
        if status not in self.SUPPORTED_STATES:
            raise ValueError(f"Unsupported result state: {status}")
        self.status = status
        icon, color = {
            "empty": (ft.Icons.INFO_OUTLINE, TOKENS.info),
            "loading": (ft.Icons.HOURGLASS_TOP, TOKENS.info),
            "success": (ft.Icons.CHECK_CIRCLE_OUTLINE, TOKENS.success),
            "warning": (ft.Icons.WARNING_AMBER_OUTLINED, TOKENS.warning),
            "error": (ft.Icons.ERROR_OUTLINE, TOKENS.error),
        }[status]
        self._body.controls = [
            ft.Row([ft.Icon(icon, color=color), ft.Text(title, size=TOKENS.section_title, weight=ft.FontWeight.W_600)]),
            ft.Text(message, size=TOKENS.body, color=ft.Colors.BLUE_GREY_700) if message else ft.Container(),
        ]

    def set_metrics(
        self,
        metrics: Mapping[str, str],
        metadata: Mapping[str, str] | None = None,
        *,
        status_detail: str | None = None,
    ) -> None:
        """只呈現計算結果 介接器 實際提供的指標與中繼資料。

參數：
    metrics: 指標名稱與格式化值的對應。
    metadata: 選用的結果來源與單位中繼資料。
    status_detail: 選用的狀態補充文字。

回傳：
    無。"""
        self.metrics = dict(metrics)
        self.metadata = dict(metadata or {})
        self.set_status("success", "計算完成", status_detail or "結果由目前計算服務提供。")
        cards = [
            ft.Container(
                content=ft.Column(
                    [ft.Text(label, size=TOKENS.caption, color=ft.Colors.BLUE_GREY_600),
                     ft.Text(value, size=TOKENS.metric, weight=ft.FontWeight.W_600, color=TOKENS.primary)],
                    spacing=TOKENS.spacing_xs,
                ),
                padding=TOKENS.spacing_md,
                bgcolor=TOKENS.surface_variant,
                border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
                col={"xs": 12, "sm": 6, "lg": 4},
            )
            for label, value in self.metrics.items()
        ]
        self._body.controls.append(ft.ResponsiveRow(cards, spacing=TOKENS.spacing_sm, run_spacing=TOKENS.spacing_sm))
        if self.metadata:
            self._body.controls.append(
                ft.Text("　·　".join(f"{key}: {value}" for key, value in self.metadata.items()),
                        size=TOKENS.caption, color=ft.Colors.BLUE_GREY_600)
            )

    def set_error(self, summary: str) -> None:
        """以簡短、面向使用者的錯誤狀態取代先前的指標。

參數：
    summary: 可供使用者理解的錯誤摘要。

回傳：
    無。"""
        self.metrics = {}
        self.metadata = {}
        self.set_status("error", "計算無法完成", summary)
