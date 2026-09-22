"""Phase 8 tests for neutral Flet bootstrap ownership."""

from __future__ import annotations

from pathlib import Path


def test_flet_launcher_does_not_import_telegram_configuration() -> None:
    """The Flet executable owns no Telegram logging/config side effect."""
    source = (Path(__file__).parents[2] / "run.py").read_text(encoding="utf-8")
    assert "Telegram_bot.config" not in source
    assert "infrastructure.logging" in source
