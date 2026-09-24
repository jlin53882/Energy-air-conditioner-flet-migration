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

    def cal_Pws(self, dry_bulb_c: float) -> float:
        """將飽和水蒸氣分壓（kPa）計算委派給排除的 model。

參數：
    dry_bulb_c: 乾球溫度（°C）。

回傳：
    飽和水蒸氣分壓（kPa）。"""
        return legacy_model.cal_Pws(dry_bulb_c)

    def cal_Ws(self, total_pressure_kpa: float, vapor_pressure_kpa: float) -> float:
        """將由分壓計算濕度比的公式委派給排除的 model。

參數：
    total_pressure_kpa: 大氣壓力（kPa）。
    vapor_pressure_kpa: 水蒸氣分壓（kPa）。

回傳：
    濕度比（kg/kg）。"""
        return legacy_model.cal_Ws(total_pressure_kpa, vapor_pressure_kpa)

    def cal_Pw(self, total_pressure_kpa: float, humidity_ratio: float) -> float:
        """將由濕度比計算水蒸氣分壓的公式委派給排除的 model。

參數：
    total_pressure_kpa: 大氣壓力（kPa）。
    humidity_ratio: 濕度比（kg/kg）。

回傳：
    水蒸氣分壓（kPa）。"""
        return legacy_model.cal_Pw(total_pressure_kpa, humidity_ratio)

    def cal_h(self, dry_bulb_c: float, humidity_ratio: float) -> float:
        """將濕空氣比焓（kJ/kg）計算委派給排除的 model。

參數：
    dry_bulb_c: 乾球溫度（°C）。
    humidity_ratio: 濕度比（kg/kg）。

回傳：
    比焓（kJ/kg 乾空氣）。"""
        return legacy_model.cal_h(dry_bulb_c, humidity_ratio)
