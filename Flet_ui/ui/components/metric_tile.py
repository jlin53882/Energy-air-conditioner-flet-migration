"""呈現單一計算結果數值的共用指標卡片。"""

import flet as ft

from ..theme import TOKENS


def split_value_and_unit(text: str) -> tuple[str, str]:
    """將「數值 單位」格式的結果文字拆成數值與單位，供排版使用。

只拆分第一段可解析為數字的內容，不改寫或重新計算數值；無法辨識時整段視為數值。

參數：
    text: 計算轉接器提供的格式化結果文字。

回傳：
    由數值文字與單位文字組成的二元組。"""
    stripped = text.strip()
    head, _, tail = stripped.partition(" ")
    try:
        float(head)
    except ValueError:
        return stripped, ""
    return head, tail.strip()


class MetricTile(ft.Container):
    """以標籤、主數值及單位呈現一筆已格式化的結果。"""

    def __init__(
        self,
        label: str,
        value: str,
        *,
        icon: ft.IconData | None = None,
        accent: str | None = None,
        emphasis: bool = False,
        col: dict[str, int] | None = None,
    ) -> None:
        """建立指標卡片；數值必須來自計算轉接器，元件本身不合成資料。

參數：
    label: 指標名稱。
    value: 已格式化的結果文字，可包含單位。
    icon: 選用的指標圖示。
    accent: 選用的強調色。
    emphasis: 是否以較大字級呈現主要指標。
    col: 選用的 ResponsiveRow 欄寬設定。

回傳：
    無。"""
        accent_color = accent or TOKENS.primary
        number, unit = split_value_and_unit(value)
        self.label = label
        self.value = value
        label_row: list[ft.Control] = []
        if icon is not None:
            label_row.append(ft.Icon(icon, size=14, color=accent_color))
        label_row.append(
            ft.Text(
                label,
                size=TOKENS.caption,
                color=TOKENS.text_secondary,
                weight=ft.FontWeight.W_500,
                expand=True,
                max_lines=2,
            )
        )
        value_controls: list[ft.Control] = [
            ft.Text(
                number,
                size=TOKENS.metric_large if emphasis else TOKENS.metric,
                weight=ft.FontWeight.W_700,
                color=TOKENS.text_primary,
                selectable=True,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                tooltip=value,
            )
        ]
        if unit:
            value_controls.append(
                ft.Text(unit, size=TOKENS.caption, color=TOKENS.text_muted, weight=ft.FontWeight.W_500)
            )
        super().__init__(
            content=ft.Column(
                [
                    ft.Row(label_row, spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Column(value_controls, spacing=0, tight=True),
                ],
                spacing=TOKENS.spacing_xs + 2,
            ),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_md, vertical=14),
            bgcolor=TOKENS.surface_variant,
            border=ft.Border.only(left=ft.BorderSide(3, accent_color)),
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
            col=col or {"xs": 12, "sm": 6, "xl": 4},
        )
