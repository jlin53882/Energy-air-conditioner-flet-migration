"""Neutral chart-domain models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatePoint:
    """Represent one chart state point in canonical SI quantities."""

    pressure_pa: float
    temperature_k: float
