"""濕空氣性質（ASHRAE Fundamentals 2017 第 1 章；canonical SI：溫度 K、焓 J/kg 乾空氣、含濕量 kg/kg 乾空氣）。

只用於房間與濕盤管模型（``docs/simulation-model.md`` §8）。大氣壓預設 101,325 Pa。

專案的 ``domain.psychrometrics.PsychrometricService`` 透過注入的舊模型 adapter 計算，供 UI 與單點計算使用；
熱泵時間步進每模擬一天需呼叫數萬次（含露點與飽和焓反解），因此這裡用同一組 ASHRAE 式的純函式實作，
與該服務的一致性由 ``tests/test_heat_pump_room.py`` 交叉驗證（W、h 誤差 < 0.05 %）。
"""

from __future__ import annotations

import math

from .parameters import CELSIUS_OFFSET_K

STANDARD_PRESSURE_PA = 101_325.0
MOLAR_RATIO = 0.621945
DRY_AIR_CP_J_KG_K = 1006.0
VAPOR_CP_J_KG_K = 1860.0
LATENT_HEAT_J_KG = 2_501_000.0


def saturation_pressure_pa(temperature_k: float) -> float:
    """飽和水蒸氣壓（Hyland–Wexler；0 °C 以下為冰面）。

參數：
    temperature_k: 溫度 K（173–473 K）。

回傳：
    Pa。"""
    t = temperature_k
    if t >= CELSIUS_OFFSET_K:
        ln_p = (-5.8002206e3 / t + 1.3914993 - 4.8640239e-2 * t + 4.1764768e-5 * t**2
                - 1.4452093e-8 * t**3 + 6.5459673 * math.log(t))
    else:
        ln_p = (-5.6745359e3 / t + 6.3925247 - 9.677843e-3 * t + 6.2215701e-7 * t**2
                + 2.0747825e-9 * t**3 - 9.484024e-13 * t**4 + 4.1635019 * math.log(t))
    return math.exp(ln_p)


def humidity_ratio_from_vapor_pressure(vapor_pressure_pa: float, pressure_pa: float = STANDARD_PRESSURE_PA) -> float:
    """含濕量 W = 0.621945 p_w ÷ (P − p_w)。

參數：
    vapor_pressure_pa: 水蒸氣分壓。
    pressure_pa: 大氣壓。

回傳：
    kg/kg 乾空氣。"""
    return MOLAR_RATIO * vapor_pressure_pa / (pressure_pa - vapor_pressure_pa)


def vapor_pressure_from_humidity_ratio(humidity_ratio: float, pressure_pa: float = STANDARD_PRESSURE_PA) -> float:
    """含濕量反算水蒸氣分壓。

參數：
    humidity_ratio: kg/kg。
    pressure_pa: 大氣壓。

回傳：
    Pa。"""
    return pressure_pa * humidity_ratio / (MOLAR_RATIO + humidity_ratio)


def saturation_humidity_ratio(temperature_k: float, pressure_pa: float = STANDARD_PRESSURE_PA) -> float:
    """飽和含濕量 W_s(T)。

參數：
    temperature_k: 溫度。
    pressure_pa: 大氣壓。

回傳：
    kg/kg。"""
    return humidity_ratio_from_vapor_pressure(saturation_pressure_pa(temperature_k), pressure_pa)


def humidity_ratio(temperature_k: float, relative_humidity: float, pressure_pa: float = STANDARD_PRESSURE_PA) -> float:
    """由乾球溫度與相對濕度求含濕量。

參數：
    temperature_k: 乾球溫度。
    relative_humidity: 0–1。
    pressure_pa: 大氣壓。

回傳：
    kg/kg。"""
    return humidity_ratio_from_vapor_pressure(relative_humidity * saturation_pressure_pa(temperature_k), pressure_pa)


def relative_humidity(temperature_k: float, humidity_ratio_kg_kg: float, pressure_pa: float = STANDARD_PRESSURE_PA) -> float:
    """相對濕度（上限 1）。

參數：
    temperature_k: 乾球溫度。
    humidity_ratio_kg_kg: 含濕量。
    pressure_pa: 大氣壓。

回傳：
    0–1。"""
    return min(1.0, vapor_pressure_from_humidity_ratio(humidity_ratio_kg_kg, pressure_pa)
               / saturation_pressure_pa(temperature_k))


def enthalpy_j_kg(temperature_k: float, humidity_ratio_kg_kg: float) -> float:
    """濕空氣比焓 h = cp_a·t + W·(h_fg + cp_v·t)（t 為 °C，0 °C 乾空氣為基準）。

參數：
    temperature_k: 乾球溫度。
    humidity_ratio_kg_kg: 含濕量。

回傳：
    J/kg 乾空氣。"""
    t = temperature_k - CELSIUS_OFFSET_K
    return DRY_AIR_CP_J_KG_K * t + humidity_ratio_kg_kg * (LATENT_HEAT_J_KG + VAPOR_CP_J_KG_K * t)


def temperature_from_enthalpy(enthalpy: float, humidity_ratio_kg_kg: float) -> float:
    """由焓與含濕量反算乾球溫度。

參數：
    enthalpy: J/kg 乾空氣。
    humidity_ratio_kg_kg: 含濕量。

回傳：
    K。"""
    t = (enthalpy - humidity_ratio_kg_kg * LATENT_HEAT_J_KG) / (DRY_AIR_CP_J_KG_K + humidity_ratio_kg_kg * VAPOR_CP_J_KG_K)
    return t + CELSIUS_OFFSET_K


def moist_air_cp(humidity_ratio_kg_kg: float) -> float:
    """濕空氣定壓比熱（每 kg 乾空氣）。

參數：
    humidity_ratio_kg_kg: 含濕量。

回傳：
    J/(kg·K)。"""
    return DRY_AIR_CP_J_KG_K + humidity_ratio_kg_kg * VAPOR_CP_J_KG_K


def saturated_enthalpy_j_kg(temperature_k: float, pressure_pa: float = STANDARD_PRESSURE_PA) -> float:
    """飽和空氣焓 h_s(T)。

參數：
    temperature_k: 溫度。
    pressure_pa: 大氣壓。

回傳：
    J/kg 乾空氣。"""
    return enthalpy_j_kg(temperature_k, saturation_humidity_ratio(temperature_k, pressure_pa))


def saturation_temperature_from_enthalpy(enthalpy: float, pressure_pa: float = STANDARD_PRESSURE_PA) -> float:
    """飽和焓反算溫度（h_s 單調遞增，以割線法＋二分保護求解）。

參數：
    enthalpy: J/kg 乾空氣。
    pressure_pa: 大氣壓。

回傳：
    K（夾在 −20～60 °C）。"""
    low, high = CELSIUS_OFFSET_K - 20.0, CELSIUS_OFFSET_K + 60.0
    if enthalpy <= saturated_enthalpy_j_kg(low, pressure_pa):
        return low
    if enthalpy >= saturated_enthalpy_j_kg(high, pressure_pa):
        return high
    for _ in range(60):
        mid = 0.5 * (low + high)
        if saturated_enthalpy_j_kg(mid, pressure_pa) < enthalpy:
            low = mid
        else:
            high = mid
        if high - low < 1e-4:
            break
    return 0.5 * (low + high)


def dew_point_k(humidity_ratio_kg_kg: float, pressure_pa: float = STANDARD_PRESSURE_PA) -> float:
    """露點溫度（以二分法反解飽和蒸氣壓）。

參數：
    humidity_ratio_kg_kg: 含濕量。
    pressure_pa: 大氣壓。

回傳：
    K（夾在 −40～60 °C）。"""
    target = vapor_pressure_from_humidity_ratio(humidity_ratio_kg_kg, pressure_pa)
    low, high = CELSIUS_OFFSET_K - 40.0, CELSIUS_OFFSET_K + 60.0
    if target <= saturation_pressure_pa(low):
        return low
    for _ in range(60):
        mid = 0.5 * (low + high)
        if saturation_pressure_pa(mid) < target:
            low = mid
        else:
            high = mid
        if high - low < 1e-4:
            break
    return 0.5 * (low + high)
