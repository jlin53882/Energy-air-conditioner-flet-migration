"""Domain services 使用的 canonical SI 單位轉換。

Domain contract 使用明確的 SI 量。  Display-unit 偏好
屬於 channel adapter；本模組只定義物理轉換。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


Conversion = Callable[[float], float]


@dataclass(frozen=True)
class UnitDefinition:
    """描述一個 display unit 與其明確的雙向轉換。"""

    property_code: str
    unit_code: str
    to_si: Conversion
    from_si: Conversion


class CanonicalUnitConverter:
    """將核心 thermodynamic quantities 與 canonical SI units 互相轉換。"""

    CORE_PROPERTIES = frozenset({"P", "T", "H", "S", "D", "V", "U"})

    def __init__(self) -> None:
        """建立核心 quantities 的明確轉換定義。

回傳：
    無。"""
        self._definitions = self._build_definitions()

    @staticmethod
    def _build_definitions() -> dict[tuple[str, str], UnitDefinition]:
        """回傳 canonical core unit definitions。

        回傳：
            以 ``(property_code, unit_code)`` 為鍵的 mapping。
        """
        return {
            ("P", "Pa"): UnitDefinition("P", "Pa", lambda v: v, lambda v: v),
            ("P", "kPa"): UnitDefinition("P", "kPa", lambda v: v * 1_000.0, lambda v: v / 1_000.0),
            ("P", "MPa"): UnitDefinition("P", "MPa", lambda v: v * 1_000_000.0, lambda v: v / 1_000_000.0),
            ("P", "bar"): UnitDefinition("P", "bar", lambda v: v * 100_000.0, lambda v: v / 100_000.0),
            ("P", "psia"): UnitDefinition("P", "psia", lambda v: v * 6_894.757, lambda v: v / 6_894.757),
            ("P", "psi"): UnitDefinition("P", "psi", lambda v: v * 6_894.757, lambda v: v / 6_894.757),
            ("P", "kg/cm^2"): UnitDefinition("P", "kg/cm^2", lambda v: v * 98_066.5, lambda v: v / 98_066.5),
            ("T", "K"): UnitDefinition("T", "K", lambda v: v, lambda v: v),
            ("T", "°C"): UnitDefinition("T", "°C", lambda v: v + 273.15, lambda v: v - 273.15),
            ("T", "C"): UnitDefinition("T", "C", lambda v: v + 273.15, lambda v: v - 273.15),
            ("T", "°F"): UnitDefinition("T", "°F", lambda v: (v - 32.0) * 5.0 / 9.0 + 273.15, lambda v: (v - 273.15) * 9.0 / 5.0 + 32.0),
            ("T", "F"): UnitDefinition("T", "F", lambda v: (v - 32.0) * 5.0 / 9.0 + 273.15, lambda v: (v - 273.15) * 9.0 / 5.0 + 32.0),
            ("H", "J/kg"): UnitDefinition("H", "J/kg", lambda v: v, lambda v: v),
            ("H", "kJ/kg"): UnitDefinition("H", "kJ/kg", lambda v: v * 1_000.0, lambda v: v / 1_000.0),
            ("H", "Btu/lbm"): UnitDefinition("H", "Btu/lbm", lambda v: v * 2_326.0, lambda v: v / 2_326.0),
            ("S", "J/(kg.K)"): UnitDefinition("S", "J/(kg.K)", lambda v: v, lambda v: v),
            ("S", "kJ/(kg.K)"): UnitDefinition("S", "kJ/(kg.K)", lambda v: v * 1_000.0, lambda v: v / 1_000.0),
            ("S", "Btu/(lbm.R)"): UnitDefinition("S", "Btu/(lbm.R)", lambda v: v * 4_186.8, lambda v: v / 4_186.8),
            ("D", "kg/m³"): UnitDefinition("D", "kg/m³", lambda v: v, lambda v: v),
            ("D", "kg/cm³"): UnitDefinition("D", "kg/cm³", lambda v: v * 1_000_000.0, lambda v: v / 1_000_000.0),
            ("D", "lbm/ft³"): UnitDefinition("D", "lbm/ft³", lambda v: v * 16.0185, lambda v: v / 16.0185),
            ("V", "m³/kg"): UnitDefinition("V", "m³/kg", lambda v: v, lambda v: v),
            ("V", "ft³/lbm"): UnitDefinition("V", "ft³/lbm", lambda v: v * 0.062428, lambda v: v / 0.062428),
            ("U", "J/kg"): UnitDefinition("U", "J/kg", lambda v: v, lambda v: v),
            ("U", "kJ/kg"): UnitDefinition("U", "kJ/kg", lambda v: v * 1_000.0, lambda v: v / 1_000.0),
            ("U", "Btu/lbm"): UnitDefinition("U", "Btu/lbm", lambda v: v * 2_326.0, lambda v: v / 2_326.0),
        }

    def _get_definition(self, property_code: str, unit_code: str) -> UnitDefinition:
        """查找轉換定義，或引發明確的 contract error。

參數：
    property_code (str): 函數輸入值。
    unit_code (str): 函數輸入值。

回傳：
    UnitDefinition：函數計算或處理後的結果。"""
        try:
            return self._definitions[(property_code, unit_code)]
        except KeyError as exc:
            raise ValueError(f"Unknown unit '{unit_code}' for property '{property_code}'") from exc

    def convert_to_si(self, property_code: str, value: float, unit_code: str) -> float:
        """將 display value 轉換為 canonical SI quantity。

參數：
    property_code (str): 函數輸入值。
    value (float): 函數輸入值。
    unit_code (str): 函數輸入值。

回傳：
    float：函數計算或處理後的結果。"""
        return self._get_definition(property_code, unit_code).to_si(value)

    def convert_from_si(self, property_code: str, value_si: float, unit_code: str) -> float:
        """將 canonical SI quantity 轉換為 display value。

參數：
    property_code (str): 函數輸入值。
    value_si (float): 函數輸入值。
    unit_code (str): 函數輸入值。

回傳：
    float：函數計算或處理後的結果。"""
        return self._get_definition(property_code, unit_code).from_si(value_si)

    def get_available_units(self, property_code: str) -> list[str]:
        """回傳核心性質已明確註冊的 units。

參數：
    property_code (str): 函數輸入值。

回傳：
    list[str]：函數計算或處理後的結果。"""
        if property_code not in self.CORE_PROPERTIES:
            return []
        return [
            unit_code
            for (registered_property, unit_code) in self._definitions
            if registered_property == property_code
        ]
