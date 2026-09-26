"""使用者工作區資料夾的位置（State Library 等使用者資料）。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

WORKSPACE_DIR_ENV = "HVAC_WORKSPACE_DIR"
DEFAULT_WORKSPACE_DIRNAME = ".hvac_workspace"


def workspace_directory(environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """回傳使用者工作區資料夾；資料夾在第一次寫入時才建立。

預設為使用者家目錄下的 ``.hvac_workspace``，更新程式或更換執行目錄都不影響；
設定環境變數 ``HVAC_WORKSPACE_DIR`` 時改用該資料夾（例如測試或可攜式安裝）。

參數：
    environ: 環境變數；None 時使用 ``os.environ``。
    home: 家目錄；None 時使用 ``Path.home()``。

回傳：
    資料夾路徑。"""
    environ = os.environ if environ is None else environ
    override = (environ.get(WORKSPACE_DIR_ENV) or "").strip()
    if override:
        return Path(override).expanduser()
    return (home if home is not None else Path.home()) / DEFAULT_WORKSPACE_DIRNAME
