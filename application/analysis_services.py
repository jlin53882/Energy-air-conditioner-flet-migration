"""Application services for analysis workflows."""

from __future__ import annotations

from domain.hvac.basic import calculate_compression_ratio_si

from .models import CompressionRatioRequest


class CompressionRatioService:
    """Calculate compression ratio from canonical absolute pressures."""

    def calculate(self, request: CompressionRatioRequest) -> float:
        """Return the dimensionless compression ratio."""
        return calculate_compression_ratio_si(
            request.suction_pressure_pa,
            request.discharge_pressure_pa,
        )
