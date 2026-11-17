"""冰水（熱水）盤管：焓差驅動的乾／濕盤管 ε-NTU 模型（``docs/simulation-model.md`` §8.2）。

冷房採 Braun–Klein–Mitchell（1989）的焓基 ε-NTU：以飽和空氣焓 h_s(T) 的斜率 c_s 把水側換算成
「焓的熱容量」，同時處理顯熱與潛熱；乾盤管以一般 ε-NTU 計算，兩者取熱傳量較大者
（濕盤管模型在盤管部分乾燥時會低估，取大值是 TRNSYS／EnergyPlus 簡化盤管的常用做法）。
出風狀態以「有效表面溫度」法求得（風側 NTU）。暖房（熱水）盤管為純顯熱。

水側 UA 隨水流量以冪次修正（UA_w ∝ ṁ_w^n），風側 UA 在定風量下固定；所以水泵降頻會降低盤管能力
（尤其是除濕量），這是本模型取代原「UA × (室溫 − 水溫)」的主要原因。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import psychrometrics as psy
from .parameters import WATER_CP_J_KG_K


@dataclass(frozen=True)
class CoilParameters:
    """單台送風機盤管參數（canonical SI）。

    - ``air_flow_kg_s``：定風量（乾空氣）。
    - ``air_side_ua_w_k``：風側（含鰭片效率）UA。
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


@dataclass(frozen=True)
class CoilResult:
    """盤管計算結果。``sensible_w``、``latent_w`` 冷房為正（自空氣移除），暖房 ``sensible_w`` 為負（加熱空氣）。"""

    total_w: float
    sensible_w: float
    latent_w: float
    air_out_k: float
    air_out_humidity_ratio: float
    water_out_k: float
    wet: bool
    condensate_kg_s: float

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


def _dry_coil(coil: CoilParameters, air_in_k: float, w_in: float, water_in_k: float, water_flow_kg_s: float,
              ua_w: float) -> CoilResult:
    """乾盤管（純顯熱）ε-NTU。冷卻與加熱共用。

參數：
    coil: 盤管參數。
    air_in_k: 進風乾球溫度。
    w_in: 進風含濕量。
    water_in_k: 進水溫度。
    water_flow_kg_s: 水量。
    ua_w: 水側 UA。

回傳：
    CoilResult（冷卻時 sensible_w > 0）。"""
    c_air = coil.air_flow_kg_s * psy.moist_air_cp(w_in)
    c_water = water_flow_kg_s * WATER_CP_J_KG_K
    ua = 1.0 / (1.0 / coil.air_side_ua_w_k + 1.0 / ua_w)
    c_min, c_max = min(c_air, c_water), max(c_air, c_water)
    eps = counterflow_effectiveness(ua / c_min, c_min / c_max)
    q = eps * c_min * (air_in_k - water_in_k)
    return CoilResult(total_w=q, sensible_w=q, latent_w=0.0, air_out_k=air_in_k - q / c_air,
                      air_out_humidity_ratio=w_in, water_out_k=water_in_k + q / c_water, wet=False,
                      condensate_kg_s=0.0)


def _wet_coil(coil: CoilParameters, air_in_k: float, w_in: float, water_in_k: float, water_flow_kg_s: float,
              ua_w: float) -> CoilResult | None:
    """完全濕盤管（Braun 焓基 ε-NTU）。

參數：
    coil: 盤管參數。
    air_in_k: 進風乾球溫度。
    w_in: 進風含濕量。
    water_in_k: 進水溫度。
    water_flow_kg_s: 水量。
    ua_w: 水側 UA。

回傳：
    CoilResult；推動力 ≤ 0（進風焓不高於進水溫度的飽和焓）時為 None。"""
    h_in = psy.enthalpy_j_kg(air_in_k, w_in)
    h_s_water_in = psy.saturated_enthalpy_j_kg(water_in_k)
    if h_in <= h_s_water_in:
        return None
    cp_a = psy.moist_air_cp(w_in)
    c_water = water_flow_kg_s * WATER_CP_J_KG_K
    water_out_k = water_in_k + 3.0
    q = 0.0
    for _ in range(4):
        # 飽和焓斜率 c_s 取進水到出水之間的割線（至少 0.5 K 寬）。
        span = max(0.5, water_out_k - water_in_k)
        c_s = (psy.saturated_enthalpy_j_kg(water_in_k + span) - h_s_water_in) / span
        ua_star = 1.0 / (cp_a / coil.air_side_ua_w_k + c_s / ua_w)  # kg/s（焓基）
        c_air_h = coil.air_flow_kg_s
        c_water_h = c_water / c_s
        c_min, c_max = min(c_air_h, c_water_h), max(c_air_h, c_water_h)
        eps = counterflow_effectiveness(ua_star / c_min, c_min / c_max)
        q = eps * c_min * (h_in - h_s_water_in)
        new_out = water_in_k + q / c_water
        if abs(new_out - water_out_k) < 0.01:
            water_out_k = new_out
            break
        water_out_k = new_out
    h_out = h_in - q / coil.air_flow_kg_s
    ntu_air = coil.air_side_ua_w_k / (coil.air_flow_kg_s * cp_a)
    factor = math.exp(-ntu_air)
    h_surface = h_in - (h_in - h_out) / (1.0 - factor)
    t_surface = psy.saturation_temperature_from_enthalpy(h_surface)
    air_out_k = t_surface + (air_in_k - t_surface) * factor
    w_out = min(w_in, (h_out - psy.DRY_AIR_CP_J_KG_K * (air_out_k - psy.CELSIUS_OFFSET_K))
                / (psy.LATENT_HEAT_J_KG + psy.VAPOR_CP_J_KG_K * (air_out_k - psy.CELSIUS_OFFSET_K)))
    w_out = min(w_out, psy.saturation_humidity_ratio(air_out_k))
    condensate = coil.air_flow_kg_s * max(0.0, w_in - w_out)
    latent = condensate * psy.LATENT_HEAT_J_KG
    return CoilResult(total_w=q, sensible_w=q - latent, latent_w=latent, air_out_k=air_out_k,
                      air_out_humidity_ratio=w_out, water_out_k=water_out_k, wet=condensate > 0,
                      condensate_kg_s=condensate)


def coil_performance(coil: CoilParameters, air_in_k: float, air_in_humidity_ratio: float, water_in_k: float,
                     water_flow_kg_s: float) -> CoilResult:
    """盤管性能：冷卻時取乾／濕模型中熱傳量較大者；加熱（進水高於進風）時為乾盤管。

參數：
    coil: 盤管參數。
    air_in_k: 進風乾球溫度。
    air_in_humidity_ratio: 進風含濕量。
    water_in_k: 進水溫度。
    water_flow_kg_s: 流經此盤管的水量（≤ 0 時無熱傳）。

回傳：
    CoilResult。"""
    ua_w = water_side_ua(coil, water_flow_kg_s)
    if ua_w <= 0 or coil.air_flow_kg_s <= 0:
        return CoilResult(0.0, 0.0, 0.0, air_in_k, air_in_humidity_ratio, water_in_k, False, 0.0)
    dry = _dry_coil(coil, air_in_k, air_in_humidity_ratio, water_in_k, water_flow_kg_s, ua_w)
    if water_in_k >= air_in_k:
        return dry
    wet = _wet_coil(coil, air_in_k, air_in_humidity_ratio, water_in_k, water_flow_kg_s, ua_w)
    if wet is None or wet.total_w <= dry.total_w or wet.condensate_kg_s <= 0:
        return dry
    return wet
