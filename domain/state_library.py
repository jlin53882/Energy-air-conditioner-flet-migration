"""State Library：使用者保存的冷媒與濕空氣狀態點清單（canonical SI）。

資料模型本身不做 I/O；新增、改名、複製與刪除都回傳新的 :class:`StateLibrary`，
由 application 層決定何時保存。保存格式帶 schema 種類與版本（``domain/schema.py``）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from domain.schema import document_payload, require_exact_fields, versioned_document
from domain.state_points import AirStatePoint, ThermoStatePoint, state_point_from_dict
from domain.state_points.base import text

STATE_LIBRARY_SCHEMA = "state_library"
STATE_LIBRARY_VERSION = 1
MAX_NAME_LENGTH = 80
COPY_SUFFIX = "（複本）"

KIND_THERMO = "thermo"
KIND_AIR = "air"

_LIBRARY_FIELDS = {"entries"}
_ENTRY_FIELDS = {"id", "name", "point"}

SavedPoint = ThermoStatePoint | AirStatePoint


def normalize_state_name(name: object) -> str:
    """驗證並正規化狀態名稱（去除前後空白）。

參數：
    name: 名稱。

回傳：
    正規化後的名稱。

引發：
    ValueError：不是字串、空白或超過 ``MAX_NAME_LENGTH`` 字元時。"""
    normalized = text("狀態名稱", name).strip()
    if not normalized:
        raise ValueError("狀態名稱不可空白。")
    if len(normalized) > MAX_NAME_LENGTH:
        raise ValueError(f"狀態名稱最多 {MAX_NAME_LENGTH} 個字元。")
    return normalized


def default_state_name(point: SavedPoint) -> str:
    """回傳狀態點的預設保存名稱。

參數：
    point: 狀態點。

回傳：
    冷媒為「流體 · 顯示名稱」，濕空氣為「濕空氣 · 顯示名稱」；顯示名稱空白時省略。"""
    prefix = point.fluid if isinstance(point, ThermoStatePoint) else "濕空氣"
    name = f"{prefix} · {point.label}" if point.label else prefix
    return name[:MAX_NAME_LENGTH]


@dataclass(frozen=True)
class SavedState:
    """State Library 中的一筆保存狀態。

    屬性：
        id: 穩定識別碼（不隨改名改變）。
        name: 使用者可修改的名稱。
        point: 保存的狀態點。
    """

    id: str
    name: str
    point: SavedPoint

    def __post_init__(self) -> None:
        """驗證欄位。

回傳：
    無。

引發：
    ValueError：識別碼空白、名稱無效或狀態點型別不支援時。"""
        identifier = text("狀態識別碼", self.id).strip()
        if not identifier:
            raise ValueError("狀態識別碼不可空白。")
        if not isinstance(self.point, (ThermoStatePoint, AirStatePoint)):
            raise ValueError("只支援冷媒（ThermoStatePoint）與濕空氣（AirStatePoint）狀態點。")
        object.__setattr__(self, "id", identifier)
        object.__setattr__(self, "name", normalize_state_name(self.name))

    @property
    def kind(self) -> str:
        """狀態種類：``thermo``（冷媒／工作流體）或 ``air``（濕空氣）。

回傳：
    種類代碼。"""
        return KIND_THERMO if isinstance(self.point, ThermoStatePoint) else KIND_AIR

    def to_dict(self) -> dict[str, object]:
        """回傳可保存為 JSON 的 dict（不含外層 schema 標記）。

回傳：
    dict。"""
        return {"id": self.id, "name": self.name, "point": self.point.to_dict()}

    @classmethod
    def from_dict(cls, data: object) -> "SavedState":
        """由 :meth:`to_dict` 產生的 dict 還原。

參數：
    data: dict。

回傳：
    SavedState。

引發：
    ValueError：不是物件、欄位缺漏或多出，或內容無效時。"""
        if not isinstance(data, dict):
            raise ValueError("狀態庫項目必須是物件。")
        require_exact_fields(data, _ENTRY_FIELDS, kind="狀態庫項目")
        return cls(id=data["id"], name=data["name"], point=state_point_from_dict(data["point"]))


@dataclass(frozen=True)
class StateLibrary:
    """依保存順序排列的狀態清單；識別碼不可重複。"""

    entries: tuple[SavedState, ...] = ()

    def __post_init__(self) -> None:
        """驗證識別碼不重複。

回傳：
    無。

引發：
    ValueError：識別碼重複時。"""
        entries = tuple(self.entries)
        ids = [entry.id for entry in entries]
        if len(ids) != len(set(ids)):
            raise ValueError("狀態庫中有重複的識別碼。")
        object.__setattr__(self, "entries", entries)

    def get(self, state_id: str) -> SavedState:
        """依識別碼取得項目。

參數：
    state_id: 識別碼。

回傳：
    SavedState。

引發：
    KeyError：找不到時。"""
        for entry in self.entries:
            if entry.id == state_id:
                return entry
        raise KeyError(state_id)

    def with_added(self, state: SavedState) -> "StateLibrary":
        """回傳加入一筆項目（排在最後）的新清單。

參數：
    state: 新項目。

回傳：
    StateLibrary。"""
        return StateLibrary(self.entries + (state,))

    def renamed(self, state_id: str, name: str) -> "StateLibrary":
        """回傳指定項目改名後的新清單。

參數：
    state_id: 識別碼。
    name: 新名稱。

回傳：
    StateLibrary。

引發：
    KeyError：找不到項目時。
    ValueError：名稱無效時。"""
        target = self.get(state_id)
        updated = replace(target, name=name)
        return StateLibrary(tuple(updated if entry.id == state_id else entry for entry in self.entries))

    def duplicated(self, state_id: str, new_id: str) -> "StateLibrary":
        """回傳在原項目後插入一份複本的新清單；複本名稱加上「（複本）」。

參數：
    state_id: 要複製的識別碼。
    new_id: 複本的識別碼。

回傳：
    StateLibrary。

引發：
    KeyError：找不到項目時。"""
        target = self.get(state_id)
        base = target.name[: MAX_NAME_LENGTH - len(COPY_SUFFIX)]
        copy = SavedState(id=new_id, name=f"{base}{COPY_SUFFIX}", point=target.point)
        entries: list[SavedState] = []
        for entry in self.entries:
            entries.append(entry)
            if entry.id == state_id:
                entries.append(copy)
        return StateLibrary(tuple(entries))

    def removed(self, state_id: str) -> "StateLibrary":
        """回傳移除指定項目後的新清單。

參數：
    state_id: 識別碼。

回傳：
    StateLibrary。

引發：
    KeyError：找不到項目時。"""
        self.get(state_id)
        return StateLibrary(tuple(entry for entry in self.entries if entry.id != state_id))

    def to_dict(self) -> dict[str, object]:
        """回傳含 schema 標記、可保存為 JSON 的 dict。

回傳：
    dict。"""
        return versioned_document(STATE_LIBRARY_SCHEMA, STATE_LIBRARY_VERSION, {
            "entries": [entry.to_dict() for entry in self.entries],
        })

    @classmethod
    def from_dict(cls, data: object) -> "StateLibrary":
        """由 :meth:`to_dict` 產生的 dict 還原。

參數：
    data: 文件 dict。

回傳：
    StateLibrary。

引發：
    ValueError：schema 種類或版本不符、欄位缺漏或多出、項目無效或識別碼重複時。"""
        payload = document_payload(data, kind=STATE_LIBRARY_SCHEMA, version=STATE_LIBRARY_VERSION)
        require_exact_fields(payload, _LIBRARY_FIELDS, kind=STATE_LIBRARY_SCHEMA)
        entries = payload["entries"]
        if not isinstance(entries, list):
            raise ValueError("state_library 的 entries 必須是陣列。")
        return cls(tuple(SavedState.from_dict(entry) for entry in entries))
