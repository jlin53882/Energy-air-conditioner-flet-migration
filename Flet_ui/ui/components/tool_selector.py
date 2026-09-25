"""依 category 內已存在的 analysis definitions 呈現選取器，不執行計算。"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import flet as ft

from ..theme import TOKENS, chip_button_style


class ToolSelector(ft.Row):
    """以膠囊按鈕列呈現一組分析工具，只負責 key/label/selected/on_change/disabled。

    ToolSelector 不知道任何 domain 計算；它只把 caller 提供的
    ``(key, label)`` 清單轉成可點擊按鈕，並在使用者選取時回呼 ``on_change``。
    """

    def __init__(
        self,
        items: list[tuple[str, str]],
        *,
        selected: str,
        on_change: Callable[[str], None],
        disabled: bool = False,
        accent: str = TOKENS.primary,
        tooltips: Mapping[str, str] | None = None,
    ) -> None:
        """建立工具選取按鈕列。

        參數：
            items: ``(key, label)`` 組成的清單，依傳入順序呈現。
            selected: 目前選取的 key。
            on_change: 使用者選取新工具時呼叫，帶入所選 key。
            disabled: 是否停用所有按鈕（例如尚無可用工具）。
            accent: 選取狀態使用的強調色。
            tooltips: 選用的 key 對應提示文字（例如按鈕顯示短標籤時的完整名稱）。

        回傳：
            無。
        """
        self._items = list(items)
        self._on_change = on_change
        self.selected_key = selected
        self.accent = accent
        self._buttons: dict[str, ft.OutlinedButton] = {}
        for key, label in self._items:
            button = ft.OutlinedButton(
                label,
                disabled=disabled,
                tooltip=(tooltips or {}).get(key),
                on_click=(lambda _event, selected_key=key: self._handle_select(selected_key)),
            )
            self._buttons[key] = button
        super().__init__(
            controls=list(self._buttons.values()),
            spacing=TOKENS.spacing_sm,
            run_spacing=TOKENS.spacing_sm,
            wrap=True,
        )
        self._refresh_styles()

    def _handle_select(self, key: str) -> None:
        """處理按鈕點擊，更新選取狀態並轉送給呼叫端。

        參數：
            key: 使用者點擊的工具 key。

        回傳：
            無。
        """
        if key == self.selected_key:
            return
        self.selected_key = key
        self._refresh_styles()
        try:
            attached_page = self.page
        except RuntimeError:
            attached_page = None
        if attached_page:
            self.update()
        self._on_change(key)

    def set_selected(self, key: str) -> None:
        """由呼叫端（非使用者點擊）程式化切換選取狀態。

        參數：
            key: 要標示為選取的工具 key。

        回傳：
            無。
        """
        if key not in self._buttons:
            raise KeyError(f"Unknown tool key: {key}")
        self.selected_key = key
        self._refresh_styles()

    def _refresh_styles(self) -> None:
        """同步每個按鈕的樣式，讓目前選取項目在視覺上突出。

        回傳：
            無。
        """
        for key, button in self._buttons.items():
            button.style = chip_button_style(key == self.selected_key, self.accent)
