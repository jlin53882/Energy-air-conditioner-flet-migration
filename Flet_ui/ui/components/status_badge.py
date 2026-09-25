"""以圖示、文字與色彩同時表達計算狀態的共用標籤。"""

import flet as ft

from ..theme import TOKENS

STATUS_STYLES: dict[str, tuple[ft.IconData, str, str, str]] = {
    "empty": (ft.Icons.INFO_OUTLINE, TOKENS.info, TOKENS.info_soft, "待計算"),
    "loading": (ft.Icons.HOURGLASS_TOP, TOKENS.info, TOKENS.info_soft, "計算中"),
    "success": (ft.Icons.CHECK_CIRCLE_OUTLINE, TOKENS.success, TOKENS.success_soft, "完成"),
    "warning": (ft.Icons.WARNING_AMBER_OUTLINED, TOKENS.warning, TOKENS.warning_soft, "注意"),
    "error": (ft.Icons.ERROR_OUTLINE, TOKENS.error, TOKENS.error_soft, "錯誤"),
}


def status_style(status: str) -> tuple[ft.IconData, str, str, str]:
    """回傳狀態對應的圖示、前景色、背景色與預設短標籤。

參數：
    status: empty、loading、success、warning 或 error。

回傳：
    由圖示、前景色、背景色與短標籤組成的四元組。

引發：
    ValueError: 狀態代碼未定義時。"""
    if status not in STATUS_STYLES:
        raise ValueError(f"Unsupported status: {status}")
    return STATUS_STYLES[status]


class StatusBadge(ft.Container):
    """顯示計算狀態的膠囊標籤，不只依賴顏色傳遞意義。"""

    def __init__(self, status: str = "empty", label: str | None = None) -> None:
        """建立狀態標籤並立即套用指定狀態。

參數：
    status: 初始狀態代碼。
    label: 選用的自訂文字；未提供時使用狀態預設文字。

回傳：
    無。"""
        self.icon_control = ft.Icon(ft.Icons.INFO_OUTLINE, size=14)
        self.label_control = ft.Text("", size=TOKENS.caption, weight=ft.FontWeight.W_600)
        super().__init__(
            content=ft.Row(
                [self.icon_control, self.label_control],
                spacing=4,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=ft.BorderRadius.all(TOKENS.radius_pill),
        )
        self.set_status(status, label)

    def set_status(self, status: str, label: str | None = None) -> None:
        """更新標籤的狀態、圖示與文字。

參數：
    status: 新的狀態代碼。
    label: 選用的自訂文字。

回傳：
    無。"""
        icon, color, soft, default_label = status_style(status)
        self.status = status
        self.icon_control.icon = icon
        self.icon_control.color = color
        self.label_control.value = label or default_label
        self.label_control.color = color
        self.bgcolor = soft
