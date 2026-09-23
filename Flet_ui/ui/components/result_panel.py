"""Structured result states and metric cards for engineering calculations."""

from collections.abc import Mapping

import flet as ft

from ..theme import TOKENS


class ResultPanel(ft.Container):
    """Render calculation status, truthful metrics, metadata, and optional raw output."""

    SUPPORTED_STATES = frozenset({"empty", "loading", "success", "warning", "error"})

    def __init__(self) -> None:
        """Start in an explicit empty state until a calculation succeeds."""
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
        """Show a named state with text and icon so color is never the only signal."""
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
        """Present only values supplied by the calculation result adapter."""
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
        """Replace prior metrics with a concise user-facing error state."""
        self.metrics = {}
        self.metadata = {}
        self.set_status("error", "計算無法完成", summary)
