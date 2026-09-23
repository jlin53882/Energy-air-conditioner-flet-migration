"""Phase 7 的 headless chart input parsing test。"""

from __future__ import annotations

import pytest

from chart.models import StatePoint
from chart.state_point_parser import StatePointParser


def test_state_point_parser_has_no_flet_dependency() -> None:
    """Chart input parsing 回傳中立 SI state-point model。

回傳：
    無。"""
    points = StatePointParser().parse(
        pressures="100, 200",
        temperatures="20, 30",
        pressure_unit="kPa",
        temperature_unit="°C",
    )
    assert points == [
        StatePoint(pressure_pa=100_000.0, temperature_k=293.15),
        StatePoint(pressure_pa=200_000.0, temperature_k=303.15),
    ]


def test_state_point_parser_rejects_mismatched_lengths() -> None:
    """每個壓力都必須有對應的溫度。

回傳：
    無。"""
    with pytest.raises(ValueError, match="same number"):
        StatePointParser().parse(
            pressures="100, 200",
            temperatures="20",
            pressure_unit="kPa",
            temperature_unit="°C",
        )


def test_state_point_parser_rejects_invalid_numeric_values() -> None:
    """格式錯誤的 chart input 必須在呼叫 CoolProp 或 Matplotlib 前失敗。

回傳：
    無。"""
    with pytest.raises(ValueError, match="numeric"):
        StatePointParser().parse(
            pressures="not-a-number",
            temperatures="20",
            pressure_unit="kPa",
            temperature_unit="°C",
        )
