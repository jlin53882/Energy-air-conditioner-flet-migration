"""Phase 6B tests for the first incremental compressor migration."""

from __future__ import annotations

import pytest

from application.analysis_services import CompressionRatioService
from application.models import CompressionRatioRequest


def test_compression_ratio_application_service_uses_si_request_schema() -> None:
    """The first migrated analysis accepts a neutral request, not controls."""
    result = CompressionRatioService().calculate(
        CompressionRatioRequest(
            suction_pressure_pa=100_000.0,
            discharge_pressure_pa=500_000.0,
        )
    )
    assert result == pytest.approx(5.0)


def test_compression_ratio_request_rejects_non_positive_pressure() -> None:
    """The migrated analysis preserves the physical input boundary."""
    with pytest.raises(ValueError):
        CompressionRatioService().calculate(
            CompressionRatioRequest(
                suction_pressure_pa=0.0,
                discharge_pressure_pa=500_000.0,
            )
        )
