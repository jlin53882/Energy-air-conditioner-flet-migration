"""Neutral application logging infrastructure."""

from __future__ import annotations

import logging

logger = logging.getLogger("energy_air_conditioner")


def setup_logging() -> None:
    """Configure a conservative process-wide logging default once."""
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO)
