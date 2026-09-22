"""中立 application logging infrastructure。"""

from __future__ import annotations

import logging

logger = logging.getLogger("energy_air_conditioner")


def setup_logging() -> None:
    """一次設定保守的 process-wide logging 預設值。

回傳：
    無。"""
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO)
