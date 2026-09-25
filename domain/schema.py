"""可保存文件（狀態點、設定）共用的 schema 標記與版本檢查。

每份文件都以 ``schema``（文件種類）與 ``schema_version``（整數版本）標記，讀取時
先檢查兩者，再解析內容；版本不符時明確失敗，不猜測舊資料或較新資料的意義。
"""

from __future__ import annotations

from collections.abc import Mapping

SCHEMA_KEY = "schema"
SCHEMA_VERSION_KEY = "schema_version"


def versioned_document(kind: str, version: int, payload: Mapping[str, object]) -> dict[str, object]:
    """在文件內容前加上 schema 種類與版本。

參數：
    kind: 文件種類，例如 ``thermo_state_point``。
    version: 文件格式版本。
    payload: 文件內容；不得包含 schema 標記欄位。

回傳：
    含 ``schema``、``schema_version`` 與內容的新 dict。

引發：
    ValueError：內容已含 schema 標記欄位時。"""
    if SCHEMA_KEY in payload or SCHEMA_VERSION_KEY in payload:
        raise ValueError("文件內容不得自行包含 schema 標記欄位。")
    return {SCHEMA_KEY: kind, SCHEMA_VERSION_KEY: version, **payload}


def document_payload(data: object, *, kind: str, version: int) -> dict[str, object]:
    """檢查文件的 schema 種類與版本，回傳去除標記後的內容。

參數：
    data: 讀入的文件（應為 mapping）。
    kind: 預期的文件種類。
    version: 目前支援的文件格式版本。

回傳：
    不含 schema 標記的內容 dict。

引發：
    ValueError：不是 mapping、種類不符，或版本缺漏、不是整數、較新或較舊時。"""
    if not isinstance(data, Mapping):
        raise ValueError(f"{kind} 文件必須是物件（mapping）。")
    actual_kind = data.get(SCHEMA_KEY)
    if actual_kind != kind:
        raise ValueError(f"文件種類不符：預期 {kind}，實際為 {actual_kind!r}。")
    actual_version = data.get(SCHEMA_VERSION_KEY)
    if not isinstance(actual_version, int) or isinstance(actual_version, bool):
        raise ValueError(f"{kind} 文件缺少有效的 schema_version。")
    if actual_version > version:
        raise ValueError(
            f"{kind} 文件由較新的版本建立（schema_version={actual_version}），目前只支援 {version}。"
        )
    if actual_version != version:
        raise ValueError(f"不支援的 {kind} schema_version：{actual_version}（目前為 {version}）。")
    return {key: value for key, value in data.items() if key not in (SCHEMA_KEY, SCHEMA_VERSION_KEY)}


def require_exact_fields(payload: Mapping[str, object], fields: set[str], *, kind: str) -> None:
    """確認文件內容恰好包含指定欄位，缺漏或多出都明確失敗。

參數：
    payload: 去除 schema 標記後的內容。
    fields: 必須存在的欄位名稱。
    kind: 錯誤訊息中的文件種類。

回傳：
    無。

引發：
    ValueError：缺少欄位或含未知欄位時。"""
    missing = sorted(fields - payload.keys())
    unknown = sorted(payload.keys() - fields)
    if missing:
        raise ValueError(f"{kind} 文件缺少欄位：{', '.join(missing)}。")
    if unknown:
        raise ValueError(f"{kind} 文件含未知欄位：{', '.join(unknown)}。")
