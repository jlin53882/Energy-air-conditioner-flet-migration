"""Flet desktop/web application 的 application entry point。

Telegram bot 仍是獨立套件，但此 launcher 刻意
只啟動 Flet UI，讓支援的圖形化 entry point 僅有一個。
"""

import flet as ft

from Flet_ui.flet_app import main as flet_main
from infrastructure.logging import logger, setup_logging


def main() -> None:
    """設定 logging 並執行 Flet application。

回傳：
    無。"""
    setup_logging()
    logger.info("應用程式啟動...")
    ft.run(flet_main)


if __name__ == "__main__":
    main()
