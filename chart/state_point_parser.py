"""不依賴 UI 的 thermodynamic chart state-point input parser。"""

from __future__ import annotations

from domain.units.converter import CanonicalUnitConverter

from .models import StatePoint


class StatePointParser:
    """將逗號分隔的 chart input 解析為中立 SI state point。"""

    def __init__(self, unit_converter: CanonicalUnitConverter | None = None) -> None:
        """使用 shared canonical unit converter 初始化。

參數：
    unit_converter (CanonicalUnitConverter | None): 函數輸入值。

回傳：
    無。"""
        self.unit_converter = unit_converter or CanonicalUnitConverter()

    def parse(
        self,
        pressures: str,
        temperatures: str,
        pressure_unit: str,
        temperature_unit: str,
    ) -> list[StatePoint]:
        """解析成對的逗號分隔壓力與溫度。

參數：
    pressures (str): 函數輸入值。
    temperatures (str): 函數輸入值。
    pressure_unit (str): 函數輸入值。
    temperature_unit (str): 函數輸入值。

回傳：
    list[StatePoint]：函數計算或處理後的結果。"""
        pressure_values = self._parse_numbers(pressures)
        temperature_values = self._parse_numbers(temperatures)
        if len(pressure_values) != len(temperature_values):
            raise ValueError("pressures and temperatures must contain the same number of values")
        return [
            StatePoint(
                pressure_pa=self.unit_converter.convert_to_si("P", pressure, pressure_unit),
                temperature_k=self.unit_converter.convert_to_si("T", temperature, temperature_unit),
            )
            for pressure, temperature in zip(pressure_values, temperature_values)
        ]

    @staticmethod
    def _parse_numbers(raw_value: str) -> list[float]:
        """解析非空的逗號分隔數值字串。

參數：
    raw_value (str): 函數輸入值。

回傳：
    list[float]：函數計算或處理後的結果。"""
        try:
            values = [float(item.strip()) for item in raw_value.split(",") if item.strip()]
        except ValueError as exc:
            raise ValueError("chart inputs must be numeric") from exc
        if not values:
            raise ValueError("chart inputs must contain at least one numeric value")
        return values
