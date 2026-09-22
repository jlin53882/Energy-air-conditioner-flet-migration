"""排除的舊版 psychrometric 實作的中立 adapter。"""

from __future__ import annotations

from typing import Any

from Flet_ui.PsychrometricChart import PsychrometricChart_01_ASHF_model as legacy_model


class LegacyPsychrometricModelAdapter:
    """透過 channel-neutral callable 邊界公開排除的 model。"""

    def cal_p(self, altitude_m: float) -> float:
        """在不修改公式的情況下委派大氣壓力計算。

參數：
    altitude_m (float): 函數輸入值。

回傳：
    float：函數計算或處理後的結果。"""
        return legacy_model.cal_p(altitude_m)

    def Calculation_process_m_Tdb_Twb(self, **kwargs: Any) -> tuple[Any, ...]:
        """將乾球／濕球計算委派給排除的 model。

參數：
    kwargs (Any): 函數輸入值。

回傳：
    tuple[Any, ...]：函數計算或處理後的結果。"""
        return legacy_model.Calculation_process_m_Tdb_Twb(**kwargs)

    def Calculation_process_m_Tdb_RH(self, **kwargs: Any) -> tuple[Any, ...]:
        """將乾球／RH 計算委派給排除的 model。

參數：
    kwargs (Any): 函數輸入值。

回傳：
    tuple[Any, ...]：函數計算或處理後的結果。"""
        return legacy_model.Calculation_process_m_Tdb_RH(**kwargs)

    def cal_Tdp_from_Pw(self, vapor_pressure: float) -> float:
        """將露點計算委派給排除的 model。

參數：
    vapor_pressure (float): 函數輸入值。

回傳：
    float：函數計算或處理後的結果。"""
        return legacy_model.cal_Tdp_from_Pw(vapor_pressure)
