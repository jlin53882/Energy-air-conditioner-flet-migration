"""以 JSON 檔保存文件的最小儲存實作。"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path

# 文件名稱只允許小寫英數、底線與連字號，避免路徑穿越或平台不相容的檔名。
_DOCUMENT_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class JsonDocumentStore:
    """在單一資料夾中以 ``<name>.json`` 保存文件。

    寫入時先寫到同資料夾的暫存檔再原子替換，程式中斷時不會留下寫了一半的檔案；
    拒絕 NaN／Infinity，保存的檔案一律是標準 JSON。
    """

    def __init__(self, root: Path | str) -> None:
        """指定保存資料夾；資料夾在第一次寫入時才建立。

參數：
    root: 保存資料夾。

回傳：
    無。"""
        self.root = Path(root)

    def path_for(self, name: str) -> Path:
        """回傳文件對應的檔案路徑。

參數：
    name: 文件名稱（小寫英數、底線、連字號，最多 64 字元）。

回傳：
    檔案路徑。

引發：
    ValueError：名稱不合法時。"""
        if not isinstance(name, str) or not _DOCUMENT_NAME.fullmatch(name):
            raise ValueError(f"不合法的文件名稱：{name!r}。")
        return self.root / f"{name}.json"

    def read(self, name: str) -> dict[str, object] | None:
        """讀取文件。

參數：
    name: 文件名稱。

回傳：
    文件內容 dict；檔案不存在時回傳 None。

引發：
    ValueError：檔案不是有效 JSON 或最外層不是物件時。"""
        path = self.path_for(name)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} 不是有效的 JSON：{exc}") from None
        if not isinstance(document, dict):
            raise ValueError(f"{path} 的最外層必須是 JSON 物件。")
        return document

    def write(self, name: str, document: Mapping[str, object]) -> None:
        """以原子替換寫入文件。

參數：
    name: 文件名稱。
    document: 可序列化為標準 JSON 的內容。

回傳：
    無。

引發：
    ValueError：名稱不合法，或內容含 NaN／Infinity 等無法寫成標準 JSON 的值時。"""
        path = self.path_for(name)
        try:
            payload = json.dumps(dict(document), ensure_ascii=False, indent=2, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"文件 {name} 無法保存為標準 JSON：{exc}") from None
        self.root.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
