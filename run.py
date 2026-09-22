"""Application entry point for the Flet desktop/web application.

The Telegram bot remains an independent package, but this launcher intentionally
starts only the Flet UI so there is one supported graphical entry point.
"""

import flet as ft

from Flet_ui.flet_app import main as flet_main
from Telegram_bot.config import logger, setup_logging


def main() -> None:
    """Configure logging and run the Flet application."""
    setup_logging()
    logger.info("應用程式啟動...")
    ft.run(flet_main)


if __name__ == "__main__":
    main()
