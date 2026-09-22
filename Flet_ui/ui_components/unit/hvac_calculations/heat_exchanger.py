# hvac_calculations/heat_exchanger.py
# 職責：蒸發器計算
from domain.hvac.basic import calculate_evaporator_heat_rate_si

    #蒸發器的計算方程式
def calculate_evaporator_heat_rate(mass_flow_rate, h1, h2):
    """針對舊版 kJ/kg API 回傳以 kW 為單位的蒸發器熱傳率。

參數：
    mass_flow_rate (未指定型別): 函數輸入值。
    h1 (未指定型別): 函數輸入值。
    h2 (未指定型別): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
    return calculate_evaporator_heat_rate_si(mass_flow_rate, h1 * 1000.0, h2 * 1000.0) / 1000.0