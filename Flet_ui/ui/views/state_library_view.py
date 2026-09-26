"""State Library 畫面：管理已保存的狀態點（改名、複製、刪除），並比較 A 與 B。

資料與比較邏輯來自 :class:`~application.state_library.StateLibraryService`；畫面只負責
呈現與換算輸出單位，不重新計算狀態。比較的差值一律為 B − A；溫度差以溫差（ΔT）換算，
避免英制換算時誤加溫度零點偏移。
"""

from __future__ import annotations

import flet as ft

from application.state_library import StateLibraryService
from domain.state_library import MAX_NAME_LENGTH, SavedState
from domain.state_points import AirStatePoint, StateBasisMismatchError, StateComparison, ThermoStatePoint

from ...ui_components.analysis_modules.result_formatting import ResultFormatter
from ...ui_components.unit.UnitConverter import UnitConverter
from ..components.engineering_card import EngineeringCard
from ..theme import TOKENS, style_dropdown, style_text_field

# 比較表各性質的小數位數；差值的換算代碼（溫度改用溫差）。
_DIGITS = {"T": 2, "P": 2, "H": 2, "S": 4, "D": 3, "V": 5, "RH": 1, "W": 3, "L": 1, "-": 4}
_DIFFERENCE_CODE = {"T": "DeltaT"}
KIND_LABELS = {"thermo": "冷媒", "air": "濕空氣"}
EMPTY_TEXT = "尚未保存任何狀態。在飽和性質、過熱／過冷、冷凍循環、冷凝器 Exergy、狀態查詢或濕空氣性質頁計算後，按「儲存狀態點」。"


class StateLibraryView(ft.Column):
    """狀態庫與 A／B 比較。"""

    def __init__(self, service: StateLibraryService, unit_converter: UnitConverter) -> None:
        """建立畫面並訂閱狀態庫變更。

參數：
    service: State Library 服務。
    unit_converter: 共用單位轉換器。

回傳：
    無。"""
        super().__init__(expand=True, spacing=TOKENS.spacing_md, scroll=ft.ScrollMode.AUTO)
        self.service = service
        self.unit_converter = unit_converter
        self.use_imperial = False
        self.renaming_id: str | None = None
        self.pending_delete_id: str | None = None
        self.a_id: str | None = None
        self.b_id: str | None = None
        self.comparison: StateComparison | None = None
        self.entry_rows: dict[str, ft.Control] = {}
        self.rename_field: ft.TextField | None = None
        self.message = ft.Text("", size=TOKENS.caption, color=TOKENS.text_secondary)
        self.load_error = ft.Container(
            content=ft.Text(service.load_error or "", color=TOKENS.error, size=TOKENS.body),
            visible=service.load_error is not None,
            padding=TOKENS.spacing_sm,
            border=ft.Border.all(1, TOKENS.error),
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
        )
        self.entries_column = ft.Column(spacing=TOKENS.spacing_sm)
        self.a_dropdown = style_dropdown(ft.Dropdown(label="狀態 A", expand=True, on_select=self._on_select_a))
        self.b_dropdown = style_dropdown(ft.Dropdown(label="狀態 B", expand=True, on_select=self._on_select_b))
        self.comparison_note = ft.Text("", size=TOKENS.caption, color=TOKENS.text_secondary)
        self.comparison_table = ft.Column(spacing=0)
        self.controls = [
            self.load_error,
            ft.ResponsiveRow(
                [
                    ft.Container(
                        content=EngineeringCard(
                            "已保存的狀態",
                            ft.Column([self.message, self.entries_column], spacing=TOKENS.spacing_sm),
                            "改名、複製或刪除；名稱不影響狀態數值。",
                            icon=ft.Icons.BOOKMARKS_OUTLINED,
                        ),
                        col={"xs": 12, "lg": 5},
                    ),
                    ft.Container(
                        content=EngineeringCard(
                            "狀態比較（B − A）",
                            ft.Column(
                                [ft.Row([self.a_dropdown, self.b_dropdown], spacing=TOKENS.spacing_sm),
                                 self.comparison_note, self.comparison_table],
                                spacing=TOKENS.spacing_sm,
                            ),
                            "焓、熵只在流體、Reference State 與性質模型都相同時相減。",
                            icon=ft.Icons.COMPARE_ARROWS,
                        ),
                        col={"xs": 12, "lg": 7},
                    ),
                ],
                spacing=TOKENS.spacing_md,
                run_spacing=TOKENS.spacing_md,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ]
        service.add_listener(self.refresh)
        self.refresh()

    # ======================================================
    # 外部協定
    # ======================================================
    def activate_route(self, _route_key: str) -> None:
        """切換到此畫面時重新整理（AppShell 的 generic route activation 協定）。

參數：
    _route_key: 路由鍵。

回傳：
    無。"""
        self.refresh()

    def set_output_unit_system(self, unit_system: str) -> None:
        """以新的輸出單位系統重新呈現（不改變保存的數值）。

參數：
    unit_system: ``SI`` 或 ``Imperial``。

回傳：
    無。"""
        self.use_imperial = unit_system == "Imperial"
        self.refresh()

    # ======================================================
    # 呈現
    # ======================================================
    def _formatter(self) -> ResultFormatter:
        """回傳目前輸出單位系統的格式化器。

回傳：
    ResultFormatter。"""
        return ResultFormatter(self.unit_converter, self.use_imperial)

    def _quantity(self, prop_code: str, value: float | None, *, difference: bool = False) -> str:
        """格式化數值與單位；無值時為「—」。

參數：
    prop_code: 性質代碼；``-`` 為無因次。
    value: SI 數值。
    difference: 是否為差值（溫度改以溫差換算）。

回傳：
    顯示文字。"""
        if value is None:
            return "—"
        digits = _DIGITS.get(prop_code, 2)
        if prop_code == "-":
            return f"{value:.{digits}f}"
        code = _DIFFERENCE_CODE.get(prop_code, prop_code) if difference else prop_code
        return self._formatter().quantity(code, value, digits)

    def summary(self, entry: SavedState) -> str:
        """回傳清單中一筆狀態的摘要。

參數：
    entry: 保存的狀態。

回傳：
    摘要文字。"""
        point = entry.point
        if isinstance(point, ThermoStatePoint):
            basis = f"{point.fluid}／{point.reference_state}{'／理想氣體' if point.is_ideal_gas else ''}"
            return (f"{basis} · {self._quantity('T', point.temperature_k)} · "
                    f"{self._quantity('P', point.pressure_pa)}")
        assert isinstance(point, AirStatePoint)
        return (f"濕空氣 · {self._quantity('T', point.dry_bulb_k)} · "
                f"RH {self._quantity('RH', point.relative_humidity)}")

    def refresh(self) -> None:
        """依目前狀態庫內容重建清單與比較。

回傳：
    無。"""
        entries = self.service.entries
        ids = {entry.id for entry in entries}
        if self.renaming_id not in ids:
            self.renaming_id = None
        if self.pending_delete_id not in ids:
            self.pending_delete_id = None
        self.entry_rows = {entry.id: self._entry_row(entry) for entry in entries}
        self.entries_column.controls = list(self.entry_rows.values()) or [
            ft.Text(EMPTY_TEXT, size=TOKENS.body, color=TOKENS.text_secondary)
        ]
        options = [ft.dropdown.Option(entry.id, entry.name) for entry in entries]
        self.a_dropdown.options = options
        self.b_dropdown.options = [ft.dropdown.Option(entry.id, entry.name) for entry in entries]
        if self.a_id not in ids:
            self.a_id = entries[0].id if entries else None
        if self.b_id not in ids:
            self.b_id = next((entry.id for entry in entries if entry.id != self.a_id), None)
        self.a_dropdown.value = self.a_id
        self.b_dropdown.value = self.b_id
        self._render_comparison()
        self._update()

    def _entry_row(self, entry: SavedState) -> ft.Control:
        """建立一筆狀態的清單列（一般、改名中或確認刪除中）。

參數：
    entry: 保存的狀態。

回傳：
    清單列控制項。"""
        badge = ft.Container(
            content=ft.Text(KIND_LABELS[entry.kind], size=TOKENS.caption, color=TOKENS.primary),
            bgcolor=TOKENS.primary_soft,
            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
        )
        summary = ft.Text(self.summary(entry), size=TOKENS.caption, color=TOKENS.text_secondary)
        if entry.id == self.renaming_id:
            # 改名時輸入框獨佔一列（寬度受外層限制），並隱藏右側操作按鈕。
            self.rename_field = style_text_field(ft.TextField(
                value=entry.name, max_length=MAX_NAME_LENGTH, expand=True, autofocus=True,
                on_submit=lambda _event, state_id=entry.id: self.confirm_rename(state_id),
            ), dense=True)
            content: ft.Control = ft.Column([
                ft.Row([badge, summary], spacing=TOKENS.spacing_sm),
                ft.Row([
                    self.rename_field,
                    ft.TextButton("儲存", on_click=lambda _event, state_id=entry.id: self.confirm_rename(state_id)),
                    ft.TextButton("取消", on_click=lambda _event: self.cancel_edit()),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=TOKENS.spacing_xs)
        else:
            if entry.id == self.pending_delete_id:
                actions = [
                    ft.TextButton("確認刪除", style=ft.ButtonStyle(color=TOKENS.error),
                                  on_click=lambda _event, state_id=entry.id: self.confirm_delete(state_id)),
                    ft.TextButton("取消", on_click=lambda _event: self.cancel_edit()),
                ]
            else:
                actions = [
                    ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="改名",
                                  on_click=lambda _event, state_id=entry.id: self.start_rename(state_id)),
                    ft.IconButton(ft.Icons.CONTENT_COPY_OUTLINED, tooltip="複製",
                                  on_click=lambda _event, state_id=entry.id: self.duplicate(state_id)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="刪除",
                                  on_click=lambda _event, state_id=entry.id: self.request_delete(state_id)),
                ]
            title = ft.Text(entry.name, size=TOKENS.body, weight=ft.FontWeight.W_600,
                            color=TOKENS.text_primary, expand=True)
            content = ft.Row(
                [
                    ft.Column([ft.Row([badge, title], spacing=TOKENS.spacing_sm), summary],
                              spacing=4, expand=True),
                    ft.Row(actions, spacing=0),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        return ft.Container(
            content=content,
            padding=TOKENS.spacing_sm,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
        )

    def _render_comparison(self) -> None:
        """依 A、B 選擇重建比較表。

回傳：
    無。"""
        self.comparison = None
        self.comparison_table.controls = []
        if self.a_id is None or self.b_id is None:
            self.comparison_note.value = "至少保存兩個狀態後即可比較。"
            return
        try:
            comparison = self.service.compare(self.a_id, self.b_id)
        except StateBasisMismatchError as exc:
            self.comparison_note.value = str(exc)
            return
        self.comparison = comparison
        self.comparison_note.value = comparison.basis_note
        self.comparison_table.controls = [self._table_row(("性質", "A", "B", "B − A"), header=True)] + [
            self._table_row((
                row.label,
                self._quantity(row.prop_code, row.a),
                self._quantity(row.prop_code, row.b),
                self._quantity(row.prop_code, row.difference, difference=True)
                if row.difference is not None else (row.note or "—"),
            ))
            for row in comparison.rows
        ]

    @staticmethod
    def _table_row(cells: tuple[str, str, str, str], *, header: bool = False) -> ft.Control:
        """建立比較表的一列。

參數：
    cells: 四欄文字。
    header: 是否為標題列。

回傳：
    列控制項。"""
        weight = ft.FontWeight.W_600 if header else ft.FontWeight.W_400
        color = TOKENS.text_secondary if header else TOKENS.text_primary
        return ft.Container(
            content=ft.ResponsiveRow([
                ft.Text(cell, size=TOKENS.body, weight=weight, color=color, col={"xs": 3})
                for cell in cells
            ]),
            padding=ft.Padding.symmetric(vertical=6),
            border=ft.Border.only(bottom=ft.BorderSide(1, TOKENS.border)),
        )

    def comparison_rows(self) -> list[tuple[str, str, str, str]]:
        """回傳比較表目前顯示的文字（不含標題列），供測試與複製使用。

回傳：
    (性質, A, B, B − A) 清單。"""
        rows = []
        for control in self.comparison_table.controls[1:]:
            cells = control.content.controls
            rows.append(tuple(cell.value for cell in cells))
        return rows

    # ======================================================
    # 操作
    # ======================================================
    def _run(self, action, success: str | None = None) -> None:
        """執行狀態庫操作；失敗時在清單上方顯示原因。

參數：
    action: 無參數函式。
    success: 成功後的提示文字。

回傳：
    無。"""
        try:
            action()
        except (ValueError, KeyError) as exc:
            self.message.value = f"操作失敗：{exc}"
            self.message.color = TOKENS.error
            self.refresh()
            return
        self.message.value = success or ""
        self.message.color = TOKENS.text_secondary
        self.refresh()

    def start_rename(self, state_id: str) -> None:
        """開始改名。

參數：
    state_id: 識別碼。

回傳：
    無。"""
        self.renaming_id, self.pending_delete_id = state_id, None
        self.refresh()

    def confirm_rename(self, state_id: str) -> None:
        """以輸入框內容改名。

參數：
    state_id: 識別碼。

回傳：
    無。"""
        name = self.rename_field.value if self.rename_field is not None else ""

        def action() -> None:
            """改名並結束編輯。

回傳：
    無。"""
            self.service.rename(state_id, name or "")
            self.renaming_id = None

        self._run(action, "已改名。")

    def cancel_edit(self) -> None:
        """取消改名或刪除確認。

回傳：
    無。"""
        self.renaming_id = self.pending_delete_id = None
        self.refresh()

    def duplicate(self, state_id: str) -> None:
        """複製一筆狀態。

參數：
    state_id: 識別碼。

回傳：
    無。"""
        self.renaming_id = self.pending_delete_id = None
        self._run(lambda: self.service.duplicate(state_id), "已建立複本。")

    def request_delete(self, state_id: str) -> None:
        """要求刪除：顯示「確認刪除」，再按一次才刪除。

參數：
    state_id: 識別碼。

回傳：
    無。"""
        self.pending_delete_id, self.renaming_id = state_id, None
        self.refresh()

    def confirm_delete(self, state_id: str) -> None:
        """確認刪除。

參數：
    state_id: 識別碼。

回傳：
    無。"""
        self._run(lambda: self.service.delete(state_id), "已刪除。")

    def _on_select_a(self, event: ft.ControlEvent) -> None:
        """選擇狀態 A。

參數：
    event: 下拉選單事件。

回傳：
    無。"""
        self.a_id = event.control.value
        self.refresh()

    def _on_select_b(self, event: ft.ControlEvent) -> None:
        """選擇狀態 B。

參數：
    event: 下拉選單事件。

回傳：
    無。"""
        self.b_id = event.control.value
        self.refresh()

    def _update(self) -> None:
        """更新已掛載的畫面；未掛載時略過。

回傳：
    無。"""
        try:
            self.update()
        except RuntimeError:
            pass
