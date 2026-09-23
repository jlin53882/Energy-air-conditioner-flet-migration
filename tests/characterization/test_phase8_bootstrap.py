"""Phase 8 的 neutral Flet bootstrap ownership test。"""

from __future__ import annotations

from pathlib import Path


def test_flet_launcher_does_not_import_telegram_configuration() -> None:
    """Flet executable 不得擁有 Telegram logging/config side effect。

回傳：
    無。"""
    source = (Path(__file__).parents[2] / "run.py").read_text(encoding="utf-8")
    assert "Telegram_bot.config" not in source
    assert "infrastructure.logging" in source
