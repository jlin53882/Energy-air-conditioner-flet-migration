"""將數值欄位與單位選擇器並置的可組合數量輸入元件。"""

import flet as ft

from ..theme import TOKENS, style_dropdown, style_text_field


class QuantityInput:
    """將數量標籤、數值欄位、單位選單與欄位驗證組合為單一元件。"""

    def __init__(
        self,
        label: str,
        property_code: str,
        *,
        value_control: ft.TextField | None = None,
        unit_control: ft.Dropdown | None = None,
        helper_text: str | None = None,
    ) -> None:
        """建立數量輸入元件；可選擇沿用呼叫端提供的相容控制項。

參數：
    label: 顯示在欄位上方的名稱。
    property_code: 對應的標準熱力性質代碼。
    value_control: 選用的數值輸入控制項。
    unit_control: 選用的單位選擇控制項。
    helper_text: 選用的欄位輔助說明。

回傳：
    無。"""
        self.label = label
        self.property_code = property_code
        self.value_control = value_control or ft.TextField(
            keyboard_type=ft.KeyboardType.NUMBER,
            height=TOKENS.input_height,
            expand=True,
        )
        self.unit_control = unit_control or ft.Dropdown(width=118, height=TOKENS.input_height)
        style_text_field(self.value_control)
        style_dropdown(self.unit_control)
        self.value_control.hint_text = self.value_control.hint_text or "輸入數值"
        self.helper_text = helper_text
        self.label_control = ft.Text(
            label, size=TOKENS.body, weight=ft.FontWeight.W_500, color=TOKENS.text_primary
        )
        self.error_control = ft.Text(
            "", size=TOKENS.caption, color=TOKENS.error, visible=False
        )
        content: list[ft.Control] = [
            self.label_control,
            ft.Row([self.value_control, self.unit_control], spacing=TOKENS.spacing_sm),
            self.error_control,
        ]
        if helper_text:
            content.append(ft.Text(helper_text, size=TOKENS.caption, color=TOKENS.text_muted))
        self.control = ft.Column(content, spacing=6, tight=True, expand=True)

    def set_error(self, message: str | None) -> None:
        """在欄位旁顯示驗證訊息，避免錯誤只出現在全域提示中。

參數：
    message: 要顯示的錯誤文字；None 代表清除錯誤。

回傳：
    無。"""
        self.value_control.error_text = message
        self.error_control.value = message or ""
        self.error_control.visible = bool(message)
        try:
            self.error_control.update()
        except RuntimeError:
            pass
