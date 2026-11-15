"""各頁 Reference State 選單的工作區預設值。

工作區設定 :attr:`~application.settings.WorkspaceSettings.default_reference_state` 只決定各頁
選單的「初始值」：組合根讀取設定後呼叫各頁的 ``apply_default_reference_state``，每頁再透過
:class:`ReferenceStateDefault` 只改動使用者尚未自行選過的選單。使用者在頁面上的選擇一律優先，
之後再套用新的設定也不會覆寫；套用時不呼叫 process-global 的 ``set_reference_state()``，
實際計算仍由各頁在每次 request 以 ``resolve_thermo_policy`` 解析。

工作區預設不等於使用者手動指定：計算時以 :meth:`ReferenceStateDefault.request_reference`
取得 (要求基準, 偏好基準)，未經使用者選過的預設值只當成偏好；流體不支援（例如 Water、Air
不支援 IIR）時退回 Auto 規則，而不是無法計算。
"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from domain.thermodynamics.thermo_policy import AUTO, normalize_reference_selection


def default_reference_choice(value: object) -> str:
    """把設定值正規化為選單選項；無效值（含 ``CURRENT``）改用 ``Auto``。

參數：
    value: 設定中的預設 Reference State。

回傳：
    ``Auto``、``IIR``、``ASHRAE``、``NBP`` 或 ``DEF``。"""
    try:
        return normalize_reference_selection(value)
    except ValueError:
        return AUTO


class DefaultReferenceApplied:
    """套用工作區預設值時送給選單 ``on_select`` 的事件；不視為使用者的選擇。

屬性：
    control: 被改值的選單。
    data: 新的選單值。"""

    def __init__(self, control: ft.Dropdown) -> None:
        """建立事件。

參數：
    control: 被改值的選單。

回傳：
    無。"""
        self.control = control
        self.data = control.value


@dataclass
class _TrackedDropdown:
    """一個受追蹤的選單與其套用狀態。"""

    dropdown: ft.Dropdown
    applied: str
    user_chosen: bool = False


class ReferenceStateDefault:
    """追蹤一頁內的 Reference State 選單，只把工作區預設值套用到使用者尚未改過的選單。

屬性：
    choice: 目前的工作區預設值（``Auto`` 或 policy code）。"""

    def __init__(self) -> None:
        """建立追蹤器；預設值為 ``Auto``。

回傳：
    無。"""
        self.choice = AUTO
        self._tracked: list[_TrackedDropdown] = []

    def register(self, dropdown: ft.Dropdown, *, track_selection: bool = True) -> ft.Dropdown:
        """登記選單並設為目前預設值。

參數：
    dropdown: Reference State 選單。
    track_selection: 是否包裝 ``on_select`` 以記錄使用者的選擇；頁面自行呼叫
        :meth:`mark_user_choice` 時設為 False。

回傳：
    同一個選單。"""
        dropdown.value = self.choice
        tracked = _TrackedDropdown(dropdown, self.choice)
        self._tracked.append(tracked)
        if track_selection:
            original = dropdown.on_select

            def handler(event: object) -> None:
                if not isinstance(event, DefaultReferenceApplied):
                    tracked.user_chosen = True
                if original is not None:
                    original(event)

            dropdown.on_select = handler
        return dropdown

    def _entry(self, dropdown: ft.Dropdown) -> _TrackedDropdown:
        """回傳選單的追蹤資料。

引發：
    KeyError：選單未登記時。"""
        for tracked in self._tracked:
            if tracked.dropdown is dropdown:
                return tracked
        raise KeyError("Reference State 選單尚未登記。")

    def mark_user_choice(self, dropdown: ft.Dropdown) -> None:
        """記錄使用者已自行選擇此選單；之後套用設定不再改動它。

參數：
    dropdown: 已登記的選單。

回傳：
    無。"""
        self._entry(dropdown).user_chosen = True

    def is_user_choice(self, dropdown: ft.Dropdown) -> bool:
        """此選單是否已由使用者自行選擇。

參數：
    dropdown: 已登記的選單。

回傳：
    bool。"""
        return self._entry(dropdown).user_chosen

    def request_reference(self, dropdown: ft.Dropdown) -> tuple[str, str | None]:
        """回傳計算 request 用的 (要求基準, 工作區預設偏好)。

只有「選單值仍是工作區預設套用的值、且使用者沒選過」時，預設值才只是偏好：要求基準為
``Auto``，由 resolver 判斷流體是否支援。使用者選過或被程式改成其他值時視為手動指定。

參數：
    dropdown: 已登記的選單。

回傳：
    ``(reference, preferred_reference)``；沒有偏好時 preferred 為 None。"""
        tracked = self._entry(dropdown)
        value = dropdown.value or AUTO
        if tracked.user_chosen or value == AUTO or value != tracked.applied:
            return value, None
        return AUTO, value

    def reset(self, dropdown: ft.Dropdown) -> None:
        """把選單設回目前預設值（例如模型由不適用切回適用時）。

參數：
    dropdown: 已登記的選單。

回傳：
    無。"""
        tracked = self._entry(dropdown)
        dropdown.value = self.choice
        tracked.applied = self.choice

    def apply(self, value: object) -> list[ft.Dropdown]:
        """更新預設值，並套用到使用者尚未改過、目前可用的選單。

使用者選過（或值已被程式改成別的值）的選單維持原狀；停用中的選單（模型不適用參考基準）
也不改動。

參數：
    value: 設定中的預設 Reference State；無效時改用 ``Auto``。

回傳：
    值有改變的選單清單。"""
        self.choice = default_reference_choice(value)
        changed: list[ft.Dropdown] = []
        for tracked in self._tracked:
            dropdown = tracked.dropdown
            if tracked.user_chosen or dropdown.disabled or dropdown.value != tracked.applied:
                continue
            tracked.applied = self.choice
            if dropdown.value != self.choice:
                dropdown.value = self.choice
                changed.append(dropdown)
        return changed
