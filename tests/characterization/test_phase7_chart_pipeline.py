"""Phase 7 tests for headless chart input parsing."""

from __future__ import annotations

import pytest

from chart.models import StatePoint
from chart.state_point_parser import StatePointParser


def test_state_point_parser_has_no_flet_dependency() -> None:
    """Chart input parsing returns neutral SI state-point models."""
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
    """Each pressure must have a matching temperature."""
    with pytest.raises(ValueError, match="same number"):
        StatePointParser().parse(
            pressures="100, 200",
            temperatures="20",
            pressure_unit="kPa",
            temperature_unit="°C",
        )


def test_state_point_parser_rejects_invalid_numeric_values() -> None:
    """Malformed chart inputs fail before CoolProp or Matplotlib is called."""
    with pytest.raises(ValueError, match="numeric"):
        StatePointParser().parse(
            pressures="not-a-number",
            temperatures="20",
            pressure_unit="kPa",
            temperature_unit="°C",
        )
