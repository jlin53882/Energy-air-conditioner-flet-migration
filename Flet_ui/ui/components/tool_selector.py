"""依 category 內已存在的 analysis definitions 呈現選取器，不執行計算。"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from ..theme import TOKENS, style_dropdown


class ToolSelector(ft.Column):
    """以帶標籤的下拉選單呈現一組分析工具，只負責 key/label/selected/on_change/disabled。

    ToolSelector 不知道任何 domain 計算；它只把 caller 提供的
    ``(key, label)`` 清單轉成選項，並在使用者選取時回呼 ``on_change``。
    選項的 ``key`` 就是分析定義 key，顯示文字可以自由調整。
    """

    def __init__(
        self,
        items: list[tuple[str, str]],
        *,
        selected: str,
        on_change: Callable[[str], None],
        disabled: bool = False,
        label: str = "分析項目",
    ) -> None:
        """建立工具選取下拉選單。

        參數：
            items: ``(key, label)`` 組成的清單，依傳入順序呈現。
            selected: 目前選取的 key。
            on_change: 使用者選取新工具時呼叫，帶入所選 key。
            disabled: 是否停用選單（例如只有一項工具）。
            label: 選單上方的欄位名稱。

        回傳：
            無。
        """
        self._items = list(items)
        self._keys = {key for key, _label in self._items}
        self._on_change = on_change
        self.selected_key = selected
        self.label_control = ft.Text(label, size=TOKENS.body, weight=ft.FontWeight.W_500,
                                     color=TOKENS.text_secondary)
        self.dropdown = style_dropdown(ft.Dropdown(
            value=selected,
            options=[ft.dropdown.Option(key=key, text=text) for key, text in self._items],
            disabled=disabled,
            expand=True,
            on_select=self._on_dropdown_select,
        ))
        super().__init__(controls=[self.label_control, self.dropdown], spacing=6)

    def _on_dropdown_select(self, event: ft.ControlEvent) -> None:
        """把下拉選單的選取事件轉為 key 選取。

        參數：
            event: Flet 選取事件。

        回傳：
            無。
        """
        self._handle_select(self.dropdown.value)

    def _handle_select(self, key: str) -> None:
        """處理使用者選取，更新選取狀態並轉送給呼叫端。

        參數：
            key: 使用者選取的工具 key。

        回傳：
            無。
        """
        if key == self.selected_key:
            return
        self.selected_key = key
        self.dropdown.value = key
        try:
            attached_page = self.page
        except RuntimeError:
            attached_page = None
        if attached_page:
            self.update()
        self._on_change(key)

    def set_selected(self, key: str) -> None:
        """由呼叫端（非使用者選取）程式化切換選取狀態。

        參數：
            key: 要標示為選取的工具 key。

        回傳：
            無。
        """
        if key not in self._keys:
            raise KeyError(f"Unknown tool key: {key}")
        self.selected_key = key
        self.dropdown.value = key
