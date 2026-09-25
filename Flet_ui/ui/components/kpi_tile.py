"""計算頁頂端的大字關鍵數值卡。"""

import flet as ft

from ..theme import TOKENS, card_shadow


class KpiTile(ft.Container):
    """以小標籤、大數字與小單位呈現一個關鍵結果；數值由呼叫端格式化後提供。"""

    def __init__(self, label: str, *, col: dict[str, int] | None = None) -> None:
        """建立尚未有數值的關鍵數值卡。

參數：
    label: 指標名稱。
    col: 選用的 ResponsiveRow 欄寬設定。

回傳：
    無。"""
        self.label_control = ft.Text(label, size=TOKENS.caption + 1, color=TOKENS.text_secondary)
        self.value_control = ft.Text("—", size=TOKENS.display, weight=ft.FontWeight.W_500,
                                     font_family=TOKENS.mono_font,
                                     color=TOKENS.text_primary, selectable=True)
        self.unit_control = ft.Text("", size=TOKENS.caption + 1, color=TOKENS.text_muted)
        super().__init__(
            content=ft.Column(
                [
                    self.label_control,
                    ft.Row(
                        [self.value_control, self.unit_control],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        wrap=True,
                    ),
                ],
                spacing=TOKENS.spacing_sm,
            ),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_lg - 4, vertical=TOKENS.spacing_md + 2),
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
            shadow=card_shadow(),
            col=col or {"xs": 6},
        )

    def set_value(self, value: str, unit: str = "") -> None:
        """更新顯示的數值與單位。

參數：
    value: 已格式化的數值文字。
    unit: 單位文字。

回傳：
    無。"""
        self.value_control.value = value
        self.unit_control.value = unit
