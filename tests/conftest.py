"""全測試共用設定。"""

from __future__ import annotations

import pytest

from infrastructure.storage import WORKSPACE_DIR_ENV


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path_factory, monkeypatch):
    """讓每個測試的使用者工作區（State Library 檔案）位於暫存資料夾，不寫入真正的家目錄。

參數：
    tmp_path_factory: pytest 暫存資料夾工廠。
    monkeypatch: pytest monkeypatch。

回傳：
    暫存工作區路徑。"""
    workspace = tmp_path_factory.mktemp("workspace")
    monkeypatch.setenv(WORKSPACE_DIR_ENV, str(workspace))
    return workspace
