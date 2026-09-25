"""呈現計算狀態與結構化指標卡片。"""

from collections.abc import Mapping

import flet as ft

from ..theme import TOKENS
from .metric_tile import MetricTile
from .status_badge import status_style

# 指標鍵值維持計算轉接器使用的英文識別字；此表只決定畫面標籤與圖示。
METRIC_PRESENTATION: dict[str, tuple[str, ft.IconData]] = {
    "Temperature": ("溫度 T", ft.Icons.THERMOSTAT_OUTLINED),
    "Pressure": ("壓力 P", ft.Icons.SPEED_OUTLINED),
    "Enthalpy": ("比焓 h", ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED),
    "Entropy": ("比熵 s", ft.Icons.SCATTER_PLOT_OUTLINED),
    "Density": ("密度 ρ", ft.Icons.GRAIN_OUTLINED),
    "Specific Volume": ("比容 v", ft.Icons.VIEW_IN_AR_OUTLINED),
    "Quality": ("乾度 x", ft.Icons.WATER_DROP_OUTLINED),
}

METADATA_LABELS: dict[str, str] = {
    "Fluid": "物質",
    "Engine": "引擎",
    "Reference": "參考狀態",
    "Input units": "輸入單位",
    "Output": "輸出",
}


class ResultPanel(ft.Container):
    """呈現計算狀態、結構化指標與結果中繼資料。"""

    SUPPORTED_STATES = frozenset({"empty", "loading", "success", "warning", "error"})

    def __init__(self) -> None:
        """初始化為明確的空狀態，直到計算成功後才呈現結果。

回傳：
    無。"""
        self.status = "empty"
        self.title = ""
        self.message = ""
        self.metrics: dict[str, str] = {}
        self.metadata: dict[str, str] = {}
        self._body = ft.Column(spacing=TOKENS.spacing_md)
        super().__init__(content=self._body)
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
        self.title = title
        self.message = message
        icon, color, soft, _label = status_style(status)
        indicator: ft.Control
        if status == "loading":
            indicator = ft.ProgressRing(width=18, height=18, stroke_width=2.5, color=color)
        else:
            indicator = ft.Icon(icon, color=color, size=20)
        self._body.controls = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=indicator,
                            width=36,
                            height=36,
                            alignment=ft.Alignment.CENTER,
                            bgcolor=ft.Colors.WHITE,
                            border_radius=ft.BorderRadius.all(TOKENS.radius_pill),
                        ),
                        ft.Column(
                            [
                                ft.Text(title, size=TOKENS.body + 1, weight=ft.FontWeight.W_600,
                                        color=TOKENS.text_primary),
                                ft.Text(message, size=TOKENS.caption, color=TOKENS.text_secondary,
                                        visible=bool(message)),
                            ],
                            spacing=2,
                            tight=True,
                            expand=True,
                        ),
                    ],
                    spacing=TOKENS.spacing_sm + 4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                bgcolor=soft,
                border=ft.Border.all(1, ft.Colors.with_opacity(0.25, color)),
                border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
            )
        ]

    def set_metrics(
        self,
        metrics: Mapping[str, str],
        metadata: Mapping[str, str] | None = None,
        *,
        status_detail: str | None = None,
    ) -> None:
        """只呈現計算結果轉接器實際提供的指標與中繼資料。

參數：
    metrics: 指標名稱與格式化值的對應。
    metadata: 選用的結果來源與單位中繼資料。
    status_detail: 選用的狀態補充文字。

回傳：
    無。"""
        self.metrics = dict(metrics)
        self.metadata = dict(metadata or {})
        self.set_status("success", "計算完成", status_detail or "結果由目前計算服務提供。")
        tiles = []
        for index, (key, value) in enumerate(self.metrics.items()):
            label, icon = METRIC_PRESENTATION.get(key, (key, ft.Icons.DATA_USAGE))
            tiles.append(
                MetricTile(
                    label,
                    value,
                    icon=icon,
                    accent=TOKENS.primary if index < 2 else TOKENS.accent,
                    col={"xs": 12, "sm": 6},
                )
            )
        self._body.controls.append(
            ft.ResponsiveRow(tiles, spacing=TOKENS.spacing_sm, run_spacing=TOKENS.spacing_sm)
        )
        if self.metadata:
            self._body.controls.append(
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(
                                f"{METADATA_LABELS.get(key, key)}：{value}",
                                size=TOKENS.caption,
                                color=TOKENS.text_secondary,
                            ),
                            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                            bgcolor=TOKENS.surface_muted,
                            border_radius=ft.BorderRadius.all(TOKENS.radius_pill),
                        )
                        for key, value in self.metadata.items()
                    ],
                    spacing=TOKENS.spacing_xs + 2,
                    run_spacing=TOKENS.spacing_xs + 2,
                    wrap=True,
                )
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
