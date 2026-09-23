"""Phase 6B 的第一個 incremental compressor migration test。"""

from __future__ import annotations

import pytest

from application.analysis_services import CompressionRatioService
from application.models import CompressionRatioRequest


def test_compression_ratio_application_service_uses_si_request_schema() -> None:
    """第一個已遷移的 analysis 接受中立 request，而不是 control。

回傳：
    無。"""
    result = CompressionRatioService().calculate(
        CompressionRatioRequest(
            suction_pressure_pa=100_000.0,
            discharge_pressure_pa=500_000.0,
        )
    )
    assert result == pytest.approx(5.0)


def test_compression_ratio_request_rejects_non_positive_pressure() -> None:
    """已遷移的 analysis 保留 physical input boundary。

回傳：
    無。"""
    with pytest.raises(ValueError):
        CompressionRatioService().calculate(
            CompressionRatioRequest(
                suction_pressure_pa=0.0,
                discharge_pressure_pa=500_000.0,
            )
        )
