"""中立的 chart-domain models。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatePoint:
    """表示一個使用 canonical SI quantity 的 chart state point。"""

    pressure_pa: float
    temperature_k: float
