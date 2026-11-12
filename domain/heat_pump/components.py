"""壓縮機、板式換熱器與室外換熱器模型，以及每個時間步的運轉點求解。"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from .cycle_table import CycleProperties, CycleTable
from .parameters import (
    WATER_CP_J_KG_K,
    CompressorParameters,
    HeatPumpParameters,
    PlateGeometry,
    PlateHeatExchangerParameters,
    RefrigerantSideCalibration,
    WaterTransportProperties,
)


class RefrigerantMode(str, Enum):
    """冷媒流路模式（§2.1）。"""

    DUAL = "dual"
    SMART_COOLING = "smart_cooling"
    SMART_HEATING = "smart_heating"


VALVES_OPEN: dict[RefrigerantMode, frozenset[int]] = {
    RefrigerantMode.DUAL: frozenset({1, 6, 7, 8, 10}),
    RefrigerantMode.SMART_COOLING: frozenset({1, 6, 7, 9, 10}),
    RefrigerantMode.SMART_HEATING: frozenset({1, 6, 7, 8, 11}),
}


@dataclass(frozen=True)
class CompressorPerformance:
    """壓縮機在某 (Te, Tc, f) 的性能。"""

    evaporating_k: float
    condensing_k: float
    frequency_hz: float
    pressure_ratio: float
    volumetric_efficiency: float
    mass_flow_kg_s: float
    cooling_w: float
    heating_w: float
    power_w: float
    properties: CycleProperties


def volumetric_efficiency(params: CompressorParameters, pressure_ratio: float) -> float:
    """餘隙容積模型 η_v = 1 − C (PR^(1/k) − 1)，下限 0。

參數：
    params: 壓縮機參數。
    pressure_ratio: 壓縮比。

回傳：
    容積效率。"""
    value = 1.0 - params.clearance_coefficient * (pressure_ratio ** (1.0 / params.polytropic_exponent) - 1.0)
    return max(0.0, value)


def compressor_performance(
    table: CycleTable,
    params: CompressorParameters,
    evaporating_k: float,
    condensing_k: float,
    frequency_hz: float,
) -> CompressorPerformance:
    """計算壓縮機流量與能力（§3.1）。

參數：
    table: 循環性質表。
    params: 壓縮機參數。
    evaporating_k: 蒸發溫度。
    condensing_k: 冷凝溫度。
    frequency_hz: 運轉頻率。

回傳：
    CompressorPerformance。"""
    props = table.properties(evaporating_k, condensing_k)
    ratio = props.condensing_pressure_pa / props.evaporating_pressure_pa
    eta_v = volumetric_efficiency(params, ratio)
    mass_flow = params.displacement_m3 * frequency_hz * eta_v * props.suction_density_kg_m3
    cooling = mass_flow * (props.suction_enthalpy_j_kg - props.liquid_enthalpy_j_kg)
    power = mass_flow * (props.discharge_enthalpy_j_kg - props.suction_enthalpy_j_kg)
    return CompressorPerformance(
        evaporating_k=evaporating_k,
        condensing_k=condensing_k,
        frequency_hz=frequency_hz,
        pressure_ratio=ratio,
        volumetric_efficiency=eta_v,
        mass_flow_kg_s=mass_flow,
        cooling_w=cooling,
        heating_w=cooling + power,
        power_w=power,
        properties=props,
    )


def water_side_coefficient(
    flow_kg_s: float, channels: int, water: WaterTransportProperties, geometry: PlateGeometry
) -> float:
    """板式換熱器水側熱傳係數 h_w = 0.348 Re^0.663 Pr^0.33 k / Dh。

參數：
    flow_kg_s: 水質量流率。
    channels: 水側流道數。
    water: 水物性。
    geometry: 流道幾何與經驗式係數。

回傳：
    W/(m²·K)。

引發：
    ValueError：流量或流道數不為正時。"""
    if flow_kg_s <= 0 or channels <= 0:
        raise ValueError("水流量與流道數必須大於 0。")
    dh = geometry.hydraulic_diameter_m
    area = channels * geometry.channel_width_m * geometry.channel_gap_m
    reynolds = flow_kg_s / area * dh / water.viscosity_pa_s
    nusselt = (
        geometry.nusselt_coefficient
        * reynolds**geometry.reynolds_exponent
        * water.prandtl**geometry.prandtl_exponent
    )
    return nusselt * water.conductivity_w_m_k / dh


def refrigerant_side_resistance(calibration: RefrigerantSideCalibration, geometry: PlateGeometry) -> float:
    """由冷凝器設計點反推冷媒側＋板片熱阻 R_r = 1/U − 1/h_w（m²·K/W）。

參數：
    calibration: 設計點資料。
    geometry: 流道幾何。

回傳：
    m²·K/W。

引發：
    ValueError：反推結果不為正時。"""
    overall_u = calibration.design_heat_w / (calibration.design_area_m2 * calibration.design_lmtd_k)
    h_w = water_side_coefficient(
        calibration.design_water_flow_kg_s,
        calibration.design_water_channels,
        calibration.design_water,
        geometry,
    )
    resistance = 1.0 / overall_u - 1.0 / h_w
    if resistance <= 0:
        raise ValueError("設計點反推的冷媒側熱阻不為正，請檢查設計資料。")
    return resistance


@dataclass(frozen=True)
class PlateExchanger:
    """板式換熱器：UA 隨水量修正，冷媒側視為定溫（C_r = 0）。"""

    params: PlateHeatExchangerParameters
    geometry: PlateGeometry
    refrigerant_resistance_m2k_w: float

    def _raw_ua(self, flow_kg_s: float) -> float:
        """未錨定的 UA。

參數：
            flow_kg_s: 水流量。

回傳：
            W/K。"""
        h_w = water_side_coefficient(flow_kg_s, self.params.water_channels, self.params.water, self.geometry)
        return self.params.area_m2 / (self.refrigerant_resistance_m2k_w + 1.0 / h_w)

    @property
    def anchor_scale(self) -> float:
        """錨定係數（無錨定時為 1）。

回傳：
            無因次。"""
        if self.params.anchor_flow_kg_s is None or self.params.anchor_ua_w_k is None:
            return 1.0
        return self.params.anchor_ua_w_k / self._raw_ua(self.params.anchor_flow_kg_s)

    def ua(self, flow_kg_s: float) -> float:
        """UA(ṁ_w)。

參數：
            flow_kg_s: 水流量。

回傳：
            W/K。"""
        return self.anchor_scale * self._raw_ua(flow_kg_s)

    def conductance(self, flow_kg_s: float) -> float:
        """ε·ṁ_w·cp：每 1 K「冷媒溫度 − 進水溫度」可傳的熱量。

參數：
            flow_kg_s: 水流量。

回傳：
            W/K。"""
        capacity_rate = flow_kg_s * WATER_CP_J_KG_K
        effectiveness = 1.0 - math.exp(-self.ua(flow_kg_s) / capacity_rate)
        return effectiveness * capacity_rate


def _bisect(func: Callable[[float], float], low: float, high: float, iterations: int = 40) -> float:
    """在 [low, high] 以二分法解遞增函數 func(x) = 0；端點同號時回傳較接近的端點。

參數：
    func: 遞增函數。
    low: 下限。
    high: 上限。
    iterations: 迭代次數。

回傳：
    根。"""
    if high <= low:
        return low
    f_low = func(low)
    if f_low >= 0:
        return low
    f_high = func(high)
    if f_high <= 0:
        return high
    for _ in range(iterations):
        mid = 0.5 * (low + high)
        if func(mid) < 0:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


@dataclass(frozen=True)
class OperatingConditions:
    """求解運轉點所需的邊界條件。"""

    mode: RefrigerantMode
    cold_water_k: float
    hot_water_k: float
    outdoor_k: float
    frequency_hz: float
    evaporator_conductance_w_k: float
    condenser_conductance_w_k: float
    outdoor_ua_w_k: float


class OperatingPointSolver:
    """交替求解蒸發溫度與冷凝溫度，使冷媒側與換熱器側能量平衡（§1.4）。"""

    MIN_APPROACH_K = 0.05
    ALTERNATIONS = 6

    def __init__(self, table: CycleTable, params: HeatPumpParameters) -> None:
        """建立求解器。

參數：
    table: 循環性質表。
    params: 系統參數。

回傳：
    無。"""
        self.table = table
        self.params = params

    def solve(
        self, conditions: OperatingConditions, guess: tuple[float, float] | None = None
    ) -> CompressorPerformance:
        """求解運轉點。

參數：
    conditions: 邊界條件。
    guess: (Te, Tc) 初值。

回傳：
    CompressorPerformance。"""
        te_min, te_table_max = self.table.evaporating_range_k
        tc_min, tc_max = self.table.condensing_range_k
        te_cap = min(self.params.control.max_evaporating_k, te_table_max)
        compressor = self.params.compressor
        f = conditions.frequency_hz
        evaporator_outdoor = conditions.mode is RefrigerantMode.SMART_HEATING
        condenser_outdoor = conditions.mode is RefrigerantMode.SMART_COOLING
        source_k = conditions.outdoor_k if evaporator_outdoor else conditions.cold_water_k
        sink_k = conditions.outdoor_k if condenser_outdoor else conditions.hot_water_k
        g_evap = conditions.outdoor_ua_w_k if evaporator_outdoor else conditions.evaporator_conductance_w_k
        g_cond = conditions.outdoor_ua_w_k if condenser_outdoor else conditions.condenser_conductance_w_k

        te_high = min(source_k - self.MIN_APPROACH_K, te_cap)
        if guess is None:
            te, tc = min(te_high, source_k - 5.0), max(sink_k + 5.0, tc_min)
        else:
            te, tc = guess
        for _ in range(self.ALTERNATIONS):
            tc_low = max(sink_k + self.MIN_APPROACH_K, te + 1.0, tc_min)
            tc = _bisect(
                lambda x: g_cond * (x - sink_k) - compressor_performance(self.table, compressor, te, x, f).heating_w,
                tc_low,
                tc_max,
            )
            te_upper = min(te_high, tc - 1.0)
            te = _bisect(
                lambda x: compressor_performance(self.table, compressor, x, tc, f).cooling_w - g_evap * (source_k - x),
                te_min,
                te_upper,
            )
        return compressor_performance(self.table, compressor, te, tc, f)
