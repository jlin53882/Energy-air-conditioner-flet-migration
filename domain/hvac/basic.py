"""所有 channel adapter 共用的 canonical SI HVAC 方程式。"""

from __future__ import annotations


def _validate_nonnegative(*values: float) -> None:
    """拒絕基本能量方程式使用的負值物理輸入。

參數：
    values (float): 函數輸入值。

回傳：
    無。"""
    if any(value < 0 for value in values):
        raise ValueError("mass flow and enthalpy values must be non-negative")


def calculate_compressor_work_si(
    mass_flow_kg_per_s: float,
    inlet_enthalpy_j_per_kg: float,
    outlet_enthalpy_j_per_kg: float,
) -> float:
    """由 SI 量回傳以 watt 為單位的壓縮機功率。

參數：
    mass_flow_kg_per_s (float): 函數輸入值。
    inlet_enthalpy_j_per_kg (float): 函數輸入值。
    outlet_enthalpy_j_per_kg (float): 函數輸入值。

回傳：
    float：函數計算或處理後的結果。"""
    _validate_nonnegative(mass_flow_kg_per_s, inlet_enthalpy_j_per_kg, outlet_enthalpy_j_per_kg)
    return mass_flow_kg_per_s * (outlet_enthalpy_j_per_kg - inlet_enthalpy_j_per_kg)


def calculate_evaporator_heat_rate_si(
    mass_flow_kg_per_s: float,
    inlet_enthalpy_j_per_kg: float,
    outlet_enthalpy_j_per_kg: float,
) -> float:
    """由 SI 量回傳以 watt 為單位的蒸發器熱傳率。

參數：
    mass_flow_kg_per_s (float): 函數輸入值。
    inlet_enthalpy_j_per_kg (float): 函數輸入值。
    outlet_enthalpy_j_per_kg (float): 函數輸入值。

回傳：
    float：函數計算或處理後的結果。"""
    _validate_nonnegative(mass_flow_kg_per_s, inlet_enthalpy_j_per_kg, outlet_enthalpy_j_per_kg)
    if outlet_enthalpy_j_per_kg < inlet_enthalpy_j_per_kg:
        raise ValueError("outlet enthalpy must be greater than or equal to inlet enthalpy")
    return mass_flow_kg_per_s * (outlet_enthalpy_j_per_kg - inlet_enthalpy_j_per_kg)


def calculate_condenser_heat_rate_si(
    mass_flow_kg_per_s: float,
    inlet_enthalpy_j_per_kg: float,
    outlet_enthalpy_j_per_kg: float,
) -> float:
    """由 SI 量回傳以 watt 為單位的冷凝器熱傳率。

參數：
    mass_flow_kg_per_s (float): 函數輸入值。
    inlet_enthalpy_j_per_kg (float): 函數輸入值。
    outlet_enthalpy_j_per_kg (float): 函數輸入值。

回傳：
    float：函數計算或處理後的結果。"""
    _validate_nonnegative(mass_flow_kg_per_s, inlet_enthalpy_j_per_kg, outlet_enthalpy_j_per_kg)
    if outlet_enthalpy_j_per_kg > inlet_enthalpy_j_per_kg:
        raise ValueError("inlet enthalpy must be greater than or equal to outlet enthalpy")
    return mass_flow_kg_per_s * (inlet_enthalpy_j_per_kg - outlet_enthalpy_j_per_kg)


def calculate_compression_ratio_si(
    suction_pressure_pa: float,
    discharge_pressure_pa: float,
) -> float:
    """回傳無因次的絕對壓力壓縮比。

參數：
    suction_pressure_pa (float): 函數輸入值。
    discharge_pressure_pa (float): 函數輸入值。

回傳：
    float：函數計算或處理後的結果。"""
    if suction_pressure_pa <= 0 or discharge_pressure_pa <= 0:
        raise ValueError("absolute pressures must be greater than zero")
    if suction_pressure_pa > discharge_pressure_pa:
        raise ValueError("discharge pressure must be greater than or equal to suction pressure")
    return discharge_pressure_pa / suction_pressure_pa
