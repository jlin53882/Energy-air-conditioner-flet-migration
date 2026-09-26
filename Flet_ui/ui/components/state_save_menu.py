"""「儲存到狀態庫」選單：把目前成功計算的狀態點保存到 State Library。

選單只列出呼叫端提供的狀態點（來自 domain 回傳的 ``ThermoStatePoint``／``AirStatePoint``），
不從格式化文字反推數值。沒有連接 State Library 或沒有可保存的狀態點時整列隱藏。
"""

from __future__ import annotations

from collections.abc import Sequence

import flet as ft

from application.state_library import StateLibraryService
from domain.state_library import SavedPoint, default_state_name

from ..theme import TOKENS

SAVE_ALL_LABEL = "全部儲存"


class StateSaveMenu(ft.Row):
    """儲存狀態點的選單與結果提示。"""

    def __init__(self) -> None:
        """建立隱藏的選單列。

回傳：
    無。"""
        self.service: StateLibraryService | None = None
        self.points: tuple[SavedPoint, ...] = ()
        self.menu = ft.PopupMenuButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.BOOKMARK_ADD_OUTLINED, size=18, color=TOKENS.primary),
                 ft.Text("儲存狀態點", size=TOKENS.body, color=TOKENS.primary)],
                spacing=6, tight=True,
            ),
            tooltip="儲存到狀態庫",
            items=[],
        )
        self.feedback = ft.Text("", size=TOKENS.caption, color=TOKENS.text_secondary)
        super().__init__(
            [self.menu, self.feedback],
            spacing=TOKENS.spacing_sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            visible=False,
        )

    def attach(self, service: StateLibraryService) -> None:
        """連接 State Library。

參數：
    service: State Library 服務。

回傳：
    無。"""
        self.service = service

    def show_points(self, points: Sequence[SavedPoint]) -> None:
        """依可保存的狀態點更新選單；沒有狀態點或沒有連接狀態庫時隱藏。

參數：
    points: 目前成功計算結果的狀態點。

回傳：
    無。"""
        self.points = tuple(points)
        self.feedback.value = ""
        items = [
            ft.PopupMenuItem(
                content=ft.Text(default_state_name(point)),
                on_click=lambda _event, point=point: self.save((point,)),
            )
            for point in self.points
        ]
        if len(self.points) > 1:
            items.append(ft.PopupMenuItem(content=ft.Text(SAVE_ALL_LABEL),
                                          on_click=lambda _event: self.save(self.points)))
        self.menu.items = items
        self.visible = self.service is not None and bool(self.points)

    def hide(self) -> None:
        """隱藏選單並清除狀態點與提示。

回傳：
    無。"""
        self.show_points(())

    def save(self, points: Sequence[SavedPoint]) -> None:
        """保存狀態點並顯示結果提示；失敗時顯示原因，不引發例外。

參數：
    points: 要保存的狀態點。

回傳：
    無。"""
        if self.service is None:
            return
        saved: list[str] = []
        try:
            for point in points:
                saved.append(self.service.save(point).name)
        except ValueError as exc:
            self.feedback.value = f"儲存失敗：{exc}"
            self.feedback.color = TOKENS.error
        else:
            self.feedback.value = f"已儲存到狀態庫：{'、'.join(saved)}"
            self.feedback.color = TOKENS.text_secondary
        try:
            self.update()
        except RuntimeError:
            pass
