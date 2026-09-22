"""Neutral adapter for the excluded legacy psychrometric implementation."""

from __future__ import annotations

from typing import Any

from Flet_ui.PsychrometricChart import PsychrometricChart_01_ASHF_model as legacy_model


class LegacyPsychrometricModelAdapter:
    """Expose the excluded model through a channel-neutral callable boundary."""

    def cal_p(self, altitude_m: float) -> float:
        """Delegate atmospheric-pressure calculation without changing formulas."""
        return legacy_model.cal_p(altitude_m)

    def Calculation_process_m_Tdb_Twb(self, **kwargs: Any) -> tuple[Any, ...]:
        """Delegate dry/wet-bulb calculation to the excluded model."""
        return legacy_model.Calculation_process_m_Tdb_Twb(**kwargs)

    def Calculation_process_m_Tdb_RH(self, **kwargs: Any) -> tuple[Any, ...]:
        """Delegate dry-bulb/RH calculation to the excluded model."""
        return legacy_model.Calculation_process_m_Tdb_RH(**kwargs)

    def cal_Tdp_from_Pw(self, vapor_pressure: float) -> float:
        """Delegate dew-point calculation to the excluded model."""
        return legacy_model.cal_Tdp_from_Pw(vapor_pressure)
