"""冰水盤管：部分乾／部分濕的焓基 ε-NTU 模型（``docs/simulation-model.md`` §8.2）。

依 EnergyPlus Engineering Reference「Coil:Cooling:Water」的詳細（part-wet part-dry）做法，逆流排列：
- 空氣先經過**乾區**（只有顯熱，含濕量不變），再經過**濕區**（Braun 焓基 ε-NTU，同時處理顯熱與潛熱）；
  冰水由濕區端進入、乾區端流出。
- 乾濕交界：交界處的盤管表面溫度等於進風露點。以濕區面積比例 f 為未知數，用夾擠的割線法求解；
  f = 0 為全乾、f = 1 為全濕（兩端的判斷同 EnergyPlus）。這讓冷量在乾濕切換時連續，取代「全乾／全濕取大者」。
- 出口狀態由**出口焓**與出口溫度決定，若推得的含濕量超過飽和或高於進風，會在保持出口焓不變下修正，
  因此空氣側焓降永遠等於水側得熱（能量守恆）。

水側 UA 隨水量以冪次修正（UA_w ∝ ṁ_w^n），風側 UA 在定風量下固定；所以水泵降頻會降低盤管能力與除濕量。
濕表面的風側 UA 可乘上 ``wet_air_side_factor``（濕表面的熱質傳增強；預設 1）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from . import psychrometrics as psy
from .parameters import WATER_CP_J_KG_K

MAX_ITERATIONS = 40
WATER_TOLERANCE_K = 1e-4
INTERFACE_TOLERANCE_K = 1e-3


@dataclass(frozen=True)
class CoilParameters:
    """單台送風機盤管參數（canonical SI）。

    - ``air_flow_kg_s``：定風量（乾空氣）。
    - ``air_side_ua_w_k``：乾表面的風側（含鰭片效率）UA；濕表面乘 ``wet_air_side_factor``。
    - ``water_side_ua_w_k``：額定水量 ``rated_water_flow_kg_s`` 下的水側 UA；其他水量以
      ``(ṁ_w / rated)^water_flow_exponent`` 修正。
    """

    name: str
    air_flow_kg_s: float
    air_side_ua_w_k: float
    water_side_ua_w_k: float
    rated_water_flow_kg_s: float
    water_flow_exponent: float = 0.8
    fan_power_w: float = 0.0
    wet_air_side_factor: float = 1.0


@dataclass(frozen=True)
class CoilResult:
    """盤管計算結果。``sensible_w``、``latent_w`` 冷房為正（自空氣移除）。"""

    total_w: float
    sensible_w: float
    latent_w: float
    air_out_k: float
    air_out_humidity_ratio: float
    water_out_k: float
    wet: bool
    condensate_kg_s: float
    wet_fraction: float = 0.0
    converged: bool = True

    @property
    def sensible_heat_ratio(self) -> float:
        """顯熱比 SHR。

回傳：
            無因次；總量為 0 時為 1。"""
        return self.sensible_w / self.total_w if self.total_w > 0 else 1.0


def counterflow_effectiveness(ntu: float, capacity_ratio: float) -> float:
    """逆流換熱器效能 ε(NTU, C_r)。

參數：
    ntu: 傳熱單元數（以 C_min 計）。
    capacity_ratio: C_min ÷ C_max（0–1）。

回傳：
    ε。"""
    if ntu <= 0:
        return 0.0
    if abs(1.0 - capacity_ratio) < 1e-6:
        return ntu / (1.0 + ntu)
    e = math.exp(-ntu * (1.0 - capacity_ratio))
    return (1.0 - e) / (1.0 - capacity_ratio * e)


def water_side_ua(coil: CoilParameters, water_flow_kg_s: float) -> float:
    """依水量修正水側 UA。

參數：
    coil: 盤管參數。
    water_flow_kg_s: 流經此盤管的水量。

回傳：
    W/K（水量 ≤ 0 時為 0）。"""
    if water_flow_kg_s <= 0:
        return 0.0
    return coil.water_side_ua_w_k * (water_flow_kg_s / coil.rated_water_flow_kg_s) ** coil.water_flow_exponent


@dataclass(frozen=True)
class _Section:
    """一段（乾或濕）的進出口溫度與熱量。"""

    heat_w: float
    air_out_k: float
    water_out_k: float


def _dry_section(fraction: float, ua_a: float, ua_w: float, c_air: float, c_water: float,
                 air_in_k: float, water_in_k: float) -> _Section:
    """乾區逆流 ε-NTU（UA 依面積比例縮放）。

參數：
    fraction: 乾區面積比例。
    ua_a: 全盤管風側 UA。
    ua_w: 全盤管水側 UA。
    c_air: 空氣熱容量流率。
    c_water: 水熱容量流率。
    air_in_k: 進風溫度。
    water_in_k: 進水溫度。

回傳：
    _Section。"""
    if fraction <= 0:
        return _Section(0.0, air_in_k, water_in_k)
    ua = fraction / (1.0 / ua_a + 1.0 / ua_w)
    c_min, c_max = min(c_air, c_water), max(c_air, c_water)
    q = counterflow_effectiveness(ua / c_min, c_min / c_max) * c_min * (air_in_k - water_in_k)
    return _Section(q, air_in_k - q / c_air, water_in_k + q / c_water)


def _wet_section(fraction: float, ua_a_wet: float, ua_w: float, m_air: float, cp_air: float, c_water: float,
                 air_in_h: float, water_in_k: float, water_out_guess_k: float) -> tuple[float, float]:
    """濕區 Braun 焓基 ε-NTU（c_s 取進水到出水猜值之間的飽和焓割線）。

參數：
    fraction: 濕區面積比例。
    ua_a_wet: 全盤管濕表面風側 UA。
    ua_w: 全盤管水側 UA。
    m_air: 乾空氣流量。
    cp_air: 濕空氣比熱。
    c_water: 水熱容量流率。
    air_in_h: 濕區進風焓。
    water_in_k: 濕區進水溫度。
    water_out_guess_k: 濕區出水溫度猜值（決定 c_s）。

回傳：
    (熱量 W, 濕區出水溫度 K)。"""
    if fraction <= 0:
        return 0.0, water_in_k
    span = max(0.2, water_out_guess_k - water_in_k)
    h_s_in = psy.saturated_enthalpy_j_kg(water_in_k)
    c_s = (psy.saturated_enthalpy_j_kg(water_in_k + span) - h_s_in) / span
    ua_star = fraction / (cp_air / ua_a_wet + c_s / ua_w)
    c_air_h, c_water_h = m_air, c_water / c_s
    c_min, c_max = min(c_air_h, c_water_h), max(c_air_h, c_water_h)
    q = counterflow_effectiveness(ua_star / c_min, c_min / c_max) * c_min * max(0.0, air_in_h - h_s_in)
    return q, water_in_k + q / c_water


@dataclass(frozen=True)
class _Solution:
    dry: _Section
    wet_heat_w: float
    interface_water_k: float
    converged: bool


def _solve(coil: CoilParameters, wet_fraction: float, air_in_k: float, w_in: float, water_in_k: float,
           c_water: float, ua_w: float) -> _Solution:
    """給定濕區比例，求交界水溫（濕區出水 = 乾區進水）使兩段一致。

參數：
    coil: 盤管參數。
    wet_fraction: 濕區面積比例。
    air_in_k: 進風溫度。
    w_in: 進風含濕量。
    water_in_k: 進水溫度。
    c_water: 水熱容量流率。
    ua_w: 水側 UA。

回傳：
    _Solution。"""
    cp_air = psy.moist_air_cp(w_in)
    c_air = coil.air_flow_kg_s * cp_air
    ua_a = coil.air_side_ua_w_k
    ua_a_wet = ua_a * coil.wet_air_side_factor
    interface = water_in_k + 0.5 * max(0.0, air_in_k - water_in_k) * min(1.0, c_air / c_water)
    previous_error: float | None = None
    previous_interface = interface
    converged = False
    dry = _dry_section(1.0 - wet_fraction, ua_a, ua_w, c_air, c_water, air_in_k, interface)
    wet_q = 0.0
    for _ in range(MAX_ITERATIONS):
        dry = _dry_section(1.0 - wet_fraction, ua_a, ua_w, c_air, c_water, air_in_k, interface)
        h_mid = psy.enthalpy_j_kg(dry.air_out_k, w_in)
        wet_q, new_interface = _wet_section(wet_fraction, ua_a_wet, ua_w, coil.air_flow_kg_s, cp_air, c_water,
                                            h_mid, water_in_k, interface)
        error = new_interface - interface
        if abs(error) < WATER_TOLERANCE_K:
            interface = new_interface
            converged = True
            break
        if previous_error is not None and abs(error - previous_error) > 1e-12:
            # 割線加速；失敗時退回直接代入。
            candidate = interface - error * (interface - previous_interface) / (error - previous_error)
            if not water_in_k - 1e-9 <= candidate <= max(air_in_k, water_in_k):
                candidate = new_interface
        else:
            candidate = new_interface
        previous_interface, previous_error, interface = interface, error, candidate
    return _Solution(dry, wet_q, interface, converged)


def _surface_k(air_k: float, water_k: float, ua_a: float, ua_w: float) -> float:
    """盤管表面溫度（風側與水側熱阻分壓）。

參數：
    air_k: 該處空氣溫度。
    water_k: 該處水溫。
    ua_a: 風側 UA。
    ua_w: 水側 UA。

回傳：
    K。"""
    return (ua_a * air_k + ua_w * water_k) / (ua_a + ua_w)


def _outlet_state(h_out: float, t_guess_k: float, w_in: float) -> tuple[float, float]:
    """在**保持出口焓**下修正出口狀態：0 ≤ W ≤ W_in、RH ≤ 100 %。

參數：
    h_out: 出口焓。
    t_guess_k: 出口溫度（由表面溫度法求得）。
    w_in: 進風含濕量。

回傳：
    (出口溫度 K, 出口含濕量)。"""
    t_c = t_guess_k - psy.CELSIUS_OFFSET_K
    w = (h_out - psy.DRY_AIR_CP_J_KG_K * t_c) / (psy.LATENT_HEAT_J_KG + psy.VAPOR_CP_J_KG_K * t_c)
    if w >= w_in:
        return psy.temperature_from_enthalpy(h_out, w_in), w_in
    if w > psy.saturation_humidity_ratio(t_guess_k):
        t_sat = psy.saturation_temperature_from_enthalpy(h_out)
        return t_sat, psy.saturation_humidity_ratio(t_sat)
    return t_guess_k, max(0.0, w)


def coil_performance(coil: CoilParameters, air_in_k: float, air_in_humidity_ratio: float, water_in_k: float,
                     water_flow_kg_s: float) -> CoilResult:
    """盤管性能（部分乾／部分濕，逆流）。進水不低於進風時視為乾盤管（加熱或無熱傳）。

參數：
    coil: 盤管參數。
    air_in_k: 進風乾球溫度。
    air_in_humidity_ratio: 進風含濕量。
    water_in_k: 進水溫度。
    water_flow_kg_s: 流經此盤管的水量（≤ 0 時無熱傳）。

回傳：
    CoilResult。"""
    w_in = air_in_humidity_ratio
    ua_w = water_side_ua(coil, water_flow_kg_s)
    if ua_w <= 0 or coil.air_flow_kg_s <= 0:
        return CoilResult(0.0, 0.0, 0.0, air_in_k, w_in, water_in_k, False, 0.0)
    c_water = water_flow_kg_s * WATER_CP_J_KG_K
    ua_a = coil.air_side_ua_w_k
    ua_a_wet = ua_a * coil.wet_air_side_factor
    dew_k = psy.dew_point_k(w_in)

    def interface_surface(solution: _Solution) -> float:
        # 乾區冷端（交界）表面溫度；全乾時即盤管冷端。
        return _surface_k(solution.dry.air_out_k, solution.interface_water_k, ua_a, ua_w)

    dry_only = _solve(coil, 0.0, air_in_k, w_in, water_in_k, c_water, ua_w)
    if water_in_k >= air_in_k or interface_surface(dry_only) >= dew_k:
        return _finish(coil, dry_only, 0.0, air_in_k, w_in, water_in_k, c_water)
    wet_only = _solve(coil, 1.0, air_in_k, w_in, water_in_k, c_water, ua_w)
    if _surface_k(air_in_k, _wet_end_water(wet_only, water_in_k, c_water), ua_a_wet, ua_w) <= dew_k:
        return _finish(coil, wet_only, 1.0, air_in_k, w_in, water_in_k, c_water)
    # 部分濕：f 增加時交界表面溫度上升；以夾擠割線法找 T_s(f) = 露點。
    low, high = 0.0, 1.0
    g_low = interface_surface(dry_only) - dew_k
    g_high = _surface_k(air_in_k, _wet_end_water(wet_only, water_in_k, c_water), ua_a_wet, ua_w) - dew_k
    best = dry_only
    fraction = 0.0
    converged = False
    for _ in range(MAX_ITERATIONS):
        fraction = low - g_low * (high - low) / (g_high - g_low) if g_high != g_low else 0.5 * (low + high)
        fraction = min(max(fraction, low + 1e-4 * (high - low)), high - 1e-4 * (high - low))
        best = _solve(coil, fraction, air_in_k, w_in, water_in_k, c_water, ua_w)
        g = interface_surface(best) - dew_k
        if abs(g) < INTERFACE_TOLERANCE_K or high - low < 1e-6:
            converged = best.converged
            break
        if g < 0:
            low, g_low = fraction, g
            g_high *= 0.5  # Illinois 修正，避免單側停滯
        else:
            high, g_high = fraction, g
            g_low *= 0.5
    result = _finish(coil, best, fraction, air_in_k, w_in, water_in_k, c_water)
    return result if converged else _replace_converged(result, False)


def _wet_end_water(solution: _Solution, water_in_k: float, c_water: float) -> float:
    """全濕時空氣入口端（水出口端）的水溫。

參數：
    solution: 全濕解。
    water_in_k: 進水溫度。
    c_water: 水熱容量流率。

回傳：
    K。"""
    return water_in_k + solution.wet_heat_w / c_water


def _replace_converged(result: CoilResult, converged: bool) -> CoilResult:
    """複製結果並設定收斂旗標。

參數：
    result: 結果。
    converged: 旗標。

回傳：
    CoilResult。"""
    return replace(result, converged=converged)


def _finish(coil: CoilParameters, solution: _Solution, wet_fraction: float, air_in_k: float, w_in: float,
            water_in_k: float, c_water: float) -> CoilResult:
    """由兩段結果組出口狀態（保持焓守恆）。

參數：
    coil: 盤管參數。
    solution: 求解結果。
    wet_fraction: 濕區比例。
    air_in_k: 進風溫度。
    w_in: 進風含濕量。
    water_in_k: 進水溫度。
    c_water: 水熱容量流率。

回傳：
    CoilResult。"""
    m_air = coil.air_flow_kg_s
    q = solution.dry.heat_w + solution.wet_heat_w
    h_in = psy.enthalpy_j_kg(air_in_k, w_in)
    h_out = h_in - q / m_air
    water_out = water_in_k + q / c_water
    if solution.wet_heat_w <= 0 or wet_fraction <= 0:
        t_out = psy.temperature_from_enthalpy(h_out, w_in)
        return CoilResult(q, q, 0.0, t_out, w_in, water_out, False, 0.0, 0.0, solution.converged)
    # 濕區出口：有效表面焓法（EnergyPlus 的凝結溫度），NTU 以濕區風側 UA 計。
    t_mid = solution.dry.air_out_k
    h_mid = psy.enthalpy_j_kg(t_mid, w_in)
    cp_air = psy.moist_air_cp(w_in)
    factor = math.exp(-wet_fraction * coil.air_side_ua_w_k * coil.wet_air_side_factor / (m_air * cp_air))
    h_surface = h_mid - (h_mid - h_out) / (1.0 - factor)
    t_surface = psy.saturation_temperature_from_enthalpy(h_surface)
    t_out, w_out = _outlet_state(h_out, t_surface + (t_mid - t_surface) * factor, w_in)
    condensate = m_air * (w_in - w_out)
    latent = condensate * psy.LATENT_HEAT_J_KG
    return CoilResult(q, q - latent, latent, t_out, w_out, water_out, condensate > 0, condensate, wet_fraction,
                      solution.converged)


def invariant_violations(coil: CoilParameters, air_in_k: float, air_in_humidity_ratio: float, water_in_k: float,
                         water_flow_kg_s: float, result: CoilResult) -> list[str]:
    """檢查盤管結果的物理不變量（模擬每步與測試共用）。

- 空氣側焓降 = 水側得熱（相對誤差 ≤ 1e-4，或絕對 ≤ 0.05 W）
- 0 ≤ W_out ≤ W_in、出口 RH ≤ 100 %、凝結水量 ≥ 0
- 迭代收斂

參數：
    coil: 盤管參數。
    air_in_k: 進風溫度。
    air_in_humidity_ratio: 進風含濕量。
    water_in_k: 進水溫度。
    water_flow_kg_s: 水量。
    result: 計算結果。

回傳：
    違反項目（空串列表示通過）。"""
    problems: list[str] = []
    air_side = coil.air_flow_kg_s * (psy.enthalpy_j_kg(air_in_k, air_in_humidity_ratio)
                                     - psy.enthalpy_j_kg(result.air_out_k, result.air_out_humidity_ratio))
    water_side = water_flow_kg_s * WATER_CP_J_KG_K * (result.water_out_k - water_in_k) if water_flow_kg_s > 0 else 0.0
    if abs(air_side - result.total_w) > max(0.05, 1e-4 * abs(result.total_w)):
        problems.append("air_side_balance")
    if abs(water_side - result.total_w) > max(0.05, 1e-4 * abs(result.total_w)):
        problems.append("water_side_balance")
    if not -1e-12 <= result.air_out_humidity_ratio <= air_in_humidity_ratio + 1e-12:
        problems.append("humidity_ratio_range")
    if result.air_out_humidity_ratio > psy.saturation_humidity_ratio(result.air_out_k) * (1 + 1e-6) + 1e-9:
        problems.append("supersaturated")
    if result.condensate_kg_s < 0:
        problems.append("negative_condensate")
    if not result.converged:
        problems.append("not_converged")
    return problems
