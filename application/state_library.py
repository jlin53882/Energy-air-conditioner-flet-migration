"""State Library 的 application service：保存、改名、複製、刪除與比較狀態點。

儲存由注入的 :class:`~application.settings.DocumentStore` 負責（infrastructure 實作）；
本層不匯入 infrastructure。每次變更都先寫入儲存，成功後才更新記憶體中的清單，
寫入失敗時清單維持原狀。一次保存多個狀態（:meth:`StateLibraryService.save_many`）
在狀態庫文件層級是全有或全無：只寫入一次，失敗時不新增任何一筆。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from uuid import uuid4

from domain.state_library import SavedPoint, SavedState, StateLibrary, default_state_name
from domain.state_points import AirStatePoint, StateComparison, ThermoStatePoint, compare_states

from .settings import DocumentStore

STATE_LIBRARY_DOCUMENT_NAME = "state_library"

logger = logging.getLogger(__name__)


def _new_id() -> str:
    """產生新的狀態識別碼。

回傳：
    32 字元十六進位字串。"""
    return uuid4().hex


class StateLibraryService:
    """管理使用者保存的狀態點。

    建構時讀取既有文件。文件無效（損壞、版本不符）或無法讀取（權限不足、路徑是資料夾等
    檔案系統錯誤）時不改用空清單覆蓋：記錄錯誤、清單視為空，並拒絕所有寫入，直到使用者
    處理該檔案。狀態庫是附加功能，讀取失敗不得讓應用程式無法啟動。
    """

    def __init__(self, store: DocumentStore, *, id_factory: Callable[[], str] = _new_id) -> None:
        """讀取狀態庫文件。

參數：
    store: 文件儲存。
    id_factory: 產生新識別碼的函式（測試可注入）。

回傳：
    無。"""
        self._store = store
        self._id_factory = id_factory
        self._listeners: list[Callable[[], None]] = []
        self.load_error: str | None = None
        self._library = StateLibrary()
        try:
            document = store.read(STATE_LIBRARY_DOCUMENT_NAME)
            if document is not None:
                self._library = StateLibrary.from_dict(document)
        except (ValueError, OSError) as exc:
            # 儲存層以 None 表示文件不存在；其他讀取失敗（含檔案系統錯誤）都不能視為「沒有檔案」。
            self.load_error = f"狀態庫檔案無法讀取，為避免覆蓋已暫停儲存：{exc}"

    # ------------------------------------------------------
    # 查詢
    # ------------------------------------------------------
    @property
    def entries(self) -> tuple[SavedState, ...]:
        """依保存順序排列的項目。

回傳：
    項目 tuple。"""
        return self._library.entries

    def get(self, state_id: str) -> SavedState:
        """依識別碼取得項目。

參數：
    state_id: 識別碼。

回傳：
    SavedState。

引發：
    KeyError：找不到時。"""
        return self._library.get(state_id)

    def compare(self, a_id: str, b_id: str) -> StateComparison:
        """比較兩個保存的狀態；差值為 B − A。

參數：
    a_id: 狀態 A 的識別碼。
    b_id: 狀態 B 的識別碼。

回傳：
    StateComparison。

引發：
    KeyError：找不到項目時。
    StateBasisMismatchError：一個是冷媒、另一個是濕空氣狀態時。"""
        return compare_states(self.get(a_id).point, self.get(b_id).point)

    # ------------------------------------------------------
    # 變更
    # ------------------------------------------------------
    def save(self, point: SavedPoint, name: str | None = None) -> SavedState:
        """保存一個狀態點（排在最後）。

參數：
    point: 冷媒或濕空氣狀態點。
    name: 名稱；None 時使用 :func:`default_state_name`。

回傳：
    新增的 SavedState。

引發：
    ValueError：名稱無效、狀態點型別不支援、狀態庫檔案無法讀取或寫入失敗時。"""
        state = self._new_state(point, name)
        self._commit(self._library.with_added(state))
        return state

    def save_many(self, points: Sequence[SavedPoint]) -> tuple[SavedState, ...]:
        """以預設名稱一次保存多個狀態點（依序排在最後），全有或全無。

先建立全部項目再寫入一次：任何一筆驗證失敗或寫入失敗時，一筆都不新增，檔案、
記憶體中的清單都不變，也不通知訂閱者；成功時只寫入一次、通知一次。

參數：
    points: 冷媒或濕空氣狀態點。

回傳：
    新增的 SavedState（與 points 同順序）；points 為空時回傳空 tuple 且不寫入。

引發：
    ValueError：狀態點型別不支援、狀態庫檔案無法讀取或寫入失敗時。"""
        points = tuple(points)
        if not points:
            return ()
        created = tuple(self._new_state(point, None) for point in points)
        candidate = self._library
        for state in created:
            candidate = candidate.with_added(state)
        self._commit(candidate)
        return created

    def rename(self, state_id: str, name: str) -> SavedState:
        """改名。

參數：
    state_id: 識別碼。
    name: 新名稱。

回傳：
    改名後的 SavedState。

引發：
    KeyError：找不到項目時。
    ValueError：名稱無效、狀態庫檔案無法讀取或寫入失敗時。"""
        self._commit(self._library.renamed(state_id, name))
        return self.get(state_id)

    def duplicate(self, state_id: str) -> SavedState:
        """在原項目後插入一份複本。

參數：
    state_id: 識別碼。

回傳：
    複本。

引發：
    KeyError：找不到項目時。
    ValueError：狀態庫檔案無法讀取或寫入失敗時。"""
        new_id = self._id_factory()
        self._commit(self._library.duplicated(state_id, new_id))
        return self.get(new_id)

    def delete(self, state_id: str) -> None:
        """刪除項目。

參數：
    state_id: 識別碼。

回傳：
    無。

引發：
    KeyError：找不到項目時。
    ValueError：狀態庫檔案無法讀取或寫入失敗時。"""
        self._commit(self._library.removed(state_id))

    def _new_state(self, point: SavedPoint, name: str | None) -> SavedState:
        """建立新項目（驗證狀態點型別與名稱）；不寫入。

參數：
    point: 狀態點。
    name: 名稱；None 時使用預設名稱。

回傳：
    SavedState。

引發：
    ValueError：狀態點型別不支援或名稱無效時。"""
        if not isinstance(point, (ThermoStatePoint, AirStatePoint)):
            raise ValueError("只支援冷媒（ThermoStatePoint）與濕空氣（AirStatePoint）狀態點。")
        return SavedState(
            id=self._id_factory(), name=default_state_name(point) if name is None else name, point=point
        )

    # ------------------------------------------------------
    # 通知
    # ------------------------------------------------------
    def add_listener(self, listener: Callable[[], None]) -> None:
        """登記清單變更後要呼叫的函式（例如狀態庫畫面重新整理）。

訂閱者失敗只記錄在 log，不影響已完成的變更，也不阻止其他訂閱者。

參數：
    listener: 無參數函式。

回傳：
    無。"""
        self._listeners.append(listener)

    def _commit(self, library: StateLibrary) -> None:
        """先寫入儲存，成功後才更新清單並通知訂閱者。

變更在寫入成功時即已完成；訂閱者（畫面重新整理）失敗不會讓這次變更看起來失敗，
只記錄在 log，並繼續通知其他訂閱者。

參數：
    library: 新的清單。

回傳：
    無。

引發：
    ValueError：狀態庫檔案無法讀取（避免覆蓋）或寫入失敗時。"""
        if self.load_error is not None:
            raise ValueError(self.load_error)
        try:
            self._store.write(STATE_LIBRARY_DOCUMENT_NAME, library.to_dict())
        except OSError as exc:
            raise ValueError(f"狀態庫寫入失敗：{exc}") from exc
        self._library = library
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # 訂閱者錯誤與已完成的持久化變更隔離
                logger.exception("狀態庫訂閱者更新失敗；變更已保存。")
