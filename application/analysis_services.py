"""分析工作流程的 Application services。"""

from __future__ import annotations

from domain.hvac.basic import calculate_compression_ratio_si

from .models import CompressionRatioRequest


class CompressionRatioService:
    """由 canonical 絕對壓力計算壓縮比。"""

    def calculate(self, request: CompressionRatioRequest) -> float:
        """回傳無因次壓縮比。

參數：
    request (CompressionRatioRequest): 函數輸入值。

回傳：
    float：函數計算或處理後的結果。"""
        return calculate_compression_ratio_si(
            request.suction_pressure_pa,
            request.discharge_pressure_pa,
        )
