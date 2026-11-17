"""單區房間溫濕度模型、日負載情境與室內控制器（``docs/simulation-model.md`` §8）。

房間：集總熱容（空氣＋家具＋結構）與含濕量平衡；送風狀態由濕盤管（``wet_coil``）加再熱求得。
室內控制器（冷房）：
- 室溫以**送風機啟停與 B→A 分級**控制（系統沒有盤管水閥，水路串聯）。
- **冰水溫度重設**（選用）：依室溫與濕度餘裕在 7–10 °C 之間調整冰水停機設定值。
- **按需再熱**（選用）：濕度偏高、室溫已到下限時才再熱；或沿用固定比例再熱（基準）。

本檔所有預設值都是**假設**（沒有房間與盤管型錄資料），見規格 §8.6。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from . import psychrometrics as psy
from .parameters import celsius
from .wet_coil import CoilParameters

HOUR_S = 3600.0


class ReheatMode(str, Enum):
    """再熱控制方式。"""

    OFF = "off"
    FIXED = "fixed"
    DEMAND = "demand"


# 盤管參數：B 對表 8.1.1 擬合（26／27／28 °C 三組 15 點，冷量 RMS 誤差約 3 %）；A 依額定冷量比 0.667 縮放。
_MEASURED_WATER_FLOW_KG_S = 0.62
DEFAULT_COILS: tuple[CoilParameters, ...] = (
    CoilParameters("A", air_flow_kg_s=0.22 * 3516.0 / 5274.0, air_side_ua_w_k=350.0 * 3516.0 / 5274.0,
                   water_side_ua_w_k=2900.0 * 3516.0 / 5274.0,
                   rated_water_flow_kg_s=_MEASURED_WATER_FLOW_KG_S * 3516.0 / 5274.0,
                   water_flow_exponent=0.5, fan_power_w=85.0),
    CoilParameters("B", air_flow_kg_s=0.22, air_side_ua_w_k=350.0, water_side_ua_w_k=2900.0,
                   rated_water_flow_kg_s=_MEASURED_WATER_FLOW_KG_S, water_flow_exponent=0.5, fan_power_w=125.0),
)


@dataclass(frozen=True)
class RoomParameters:
    """房間與內部負荷參數（假設：約 50 m² 辦公空間、高 3 m）。"""

    floor_area_m2: float = 50.0
    volume_m3: float = 150.0
    heat_capacity_j_k: float = 3.0e6
    moisture_buffer_factor: float = 3.0
    envelope_ua_w_k: float = 120.0
    infiltration_kg_s: float = 0.01
    outdoor_air_kg_s: float = 0.04
    people_sensible_w: float = 70.0
    people_moisture_kg_s: float = 2.4e-5
    fan_heat_to_room: bool = True

    @property
    def moisture_capacity_kg(self) -> float:
        """含濕量平衡的等效乾空氣質量（室內空氣 × 吸放濕緩衝倍數）。

回傳：
            kg。"""
        return self.volume_m3 * psy.STANDARD_PRESSURE_PA / (287.05 * celsius(26.0)) * self.moisture_buffer_factor


@dataclass(frozen=True)
class DailyScenario:
    """日負載情境：外氣乾球以餘弦變化（14 時最高），含濕量固定；日照為半正弦（07–18 時）。

    ``occupied_hours`` 內人員在室（12–13 時減半），也是空調啟用時段（另加 ``precool_h`` 預冷）。
    """

    name: str
    outdoor_mean_c: float
    outdoor_amplitude_k: float
    outdoor_humidity_ratio: float
    solar_peak_w: float
    people: int
    equipment_w: float
    occupied_hours: tuple[float, float] = (8.0, 18.0)
    precool_h: float = 0.5

    def outdoor_k(self, time_s: float) -> float:
        """外氣乾球溫度。

參數：
    time_s: 自當日 0 時起的秒數（可跨日）。

回傳：
    K。"""
        hour = (time_s / HOUR_S) % 24.0
        return celsius(self.outdoor_mean_c + self.outdoor_amplitude_k * math.cos(2 * math.pi * (hour - 14.0) / 24.0))

    def outdoor_humidity(self, time_s: float) -> float:
        """外氣含濕量（每日固定，但不超過飽和）。

參數：
    time_s: 秒數。

回傳：
    kg/kg。"""
        return min(self.outdoor_humidity_ratio, psy.saturation_humidity_ratio(self.outdoor_k(time_s)))

    def solar_w(self, time_s: float) -> float:
        """日照得熱。

參數：
    time_s: 秒數。

回傳：
    W。"""
        hour = (time_s / HOUR_S) % 24.0
        if not 7.0 <= hour <= 18.0:
            return 0.0
        return self.solar_peak_w * math.sin(math.pi * (hour - 7.0) / 11.0)

    def occupied(self, time_s: float) -> bool:
        """是否為在室（評分）時段。

參數：
    time_s: 秒數。

回傳：
    bool。"""
        hour = (time_s / HOUR_S) % 24.0
        return self.occupied_hours[0] <= hour < self.occupied_hours[1]

    def system_enabled(self, time_s: float) -> bool:
        """空調系統是否啟用（在室時段加預冷）。

參數：
    time_s: 秒數。

回傳：
    bool。"""
        hour = (time_s / HOUR_S) % 24.0
        return self.occupied_hours[0] - self.precool_h <= hour < self.occupied_hours[1]

    def people_count(self, time_s: float) -> float:
        """在室人數（午休 12–13 時減半）。

參數：
    time_s: 秒數。

回傳：
    人。"""
        if not self.occupied(time_s):
            return 0.0
        hour = (time_s / HOUR_S) % 24.0
        return self.people * (0.5 if 12.0 <= hour < 13.0 else 1.0)

    def equipment_load_w(self, time_s: float) -> float:
        """設備與照明（在室時段全額，其餘 10 %）。

參數：
    time_s: 秒數。

回傳：
    W。"""
        return self.equipment_w if self.occupied(time_s) else 0.1 * self.equipment_w


SCENARIOS: dict[str, DailyScenario] = {
    "hot": DailyScenario("高溫高負載", 31.5, 3.5, 0.0205, 1200.0, 6, 1000.0),
    "humid": DailyScenario("高濕低負載", 25.5, 1.5, 0.0190, 300.0, 6, 600.0),
    "mild": DailyScenario("一般部分負載", 28.5, 2.5, 0.0180, 800.0, 4, 800.0),
}


@dataclass(frozen=True)
class IndoorControlParameters:
    """室內控制器參數（舒適度目標與各策略門檻；皆為假設）。"""

    setpoint_k: float = celsius(26.0)
    band_k: float = 0.5
    rh_low: float = 0.50
    rh_high: float = 0.60
    # 送風機分級：先開 B，再加 A；關閉順序相反（除濕需求時至少保留一台）。
    stage1_on_k: float = celsius(26.4)
    stage2_on_k: float = celsius(26.7)
    stage2_off_k: float = celsius(25.9)
    stage1_off_k: float = celsius(25.6)
    fan_min_switch_s: float = 180.0
    # 冰水溫度重設（冷房停機設定值）。
    chw_min_k: float = celsius(7.0)
    chw_max_k: float = celsius(10.0)
    chw_step_k: float = 0.5
    chw_interval_s: float = 300.0
    chw_rh_raise_limit: float = 0.55
    chw_t_raise_limit_k: float = celsius(26.2)
    # 按需再熱：濕度高於上限且室溫低於設定值時開啟，以比例控制把室溫拉回 ``reheat_target_k``。
    reheat_on_t_k: float = celsius(26.0)
    reheat_off_t_k: float = celsius(26.4)
    reheat_off_rh: float = 0.55
    reheat_target_k: float = celsius(26.2)
    reheat_gain_w_k: float = 2000.0
    reheat_min_switch_s: float = 180.0
    # 再熱盤管：UA（W/K），能力 = ε·ṁ_a·cp·(熱水 − 盤管出風)。
    reheat_ua_w_k: float = 88.0


@dataclass
class RoomState:
    """房間狀態。"""

    temperature_k: float
    humidity_ratio: float


@dataclass(frozen=True)
class SupplyAir:
    """一台送風機的送風（盤管＋再熱之後）。"""

    air_flow_kg_s: float
    temperature_k: float
    humidity_ratio: float


@dataclass
class _IndoorState:
    fans_on: set[str] = field(default_factory=set)
    fan_switched_s: float = -1e9
    reheat_on: bool = False
    reheat_switched_s: float = -1e9
    chw_setpoint_k: float = celsius(7.0)
    chw_changed_s: float = -1e9


class RoomModel:
    """房間＋室內控制器（由 ``HeatPumpSimulation`` 每步呼叫）。"""

    def __init__(self, scenario: DailyScenario, params: RoomParameters | None = None,
                 control: IndoorControlParameters | None = None, coils: tuple[CoilParameters, ...] = DEFAULT_COILS,
                 reheat_mode: ReheatMode = ReheatMode.FIXED, reheat_fraction: float = 0.2,
                 chw_reset: bool = False, initial_k: float = celsius(29.0), initial_rh: float = 0.65,
                 water_split: dict[str, float] | None = None) -> None:
        """建立房間模型。

參數：
    scenario: 日負載情境。
    params: 房間參數。
    control: 室內控制器參數。
    coils: 送風機盤管。
    reheat_mode: 再熱方式。
    reheat_fraction: 固定比例再熱的比例（``ReheatMode.FIXED``）。
    chw_reset: 是否啟用冰水溫度重設。
    initial_k: 初始室溫。
    initial_rh: 初始相對濕度。
    water_split: 各盤管分流權重（預設依額定水量比）。

回傳：
    無。"""
        self.scenario = scenario
        self.params = params or RoomParameters()
        self.control = control or IndoorControlParameters()
        self.coils = {coil.name: coil for coil in coils}
        self.reheat_mode = reheat_mode
        self.reheat_fraction = reheat_fraction
        self.chw_reset = chw_reset
        self.state = RoomState(initial_k, psy.humidity_ratio(initial_k, initial_rh))
        self.water_split = water_split or {c.name: c.rated_water_flow_kg_s for c in coils}
        self._indoor = _IndoorState(chw_setpoint_k=self.control.chw_min_k)

    # ---- 讀值 ----
    @property
    def relative_humidity(self) -> float:
        """室內相對濕度。

回傳：
            0–1。"""
        return psy.relative_humidity(self.state.temperature_k, self.state.humidity_ratio)

    @property
    def fans_on(self) -> frozenset[str]:
        """目前運轉中的送風機。

回傳：
            名稱集合。"""
        return frozenset(self._indoor.fans_on)

    @property
    def chw_setpoint_k(self) -> float:
        """目前冰水停機設定值。

回傳：
            K。"""
        return self._indoor.chw_setpoint_k

    @property
    def reheat_on(self) -> bool:
        """按需再熱是否開啟。

回傳：
            bool。"""
        return self._indoor.reheat_on

    def water_flows(self, total_kg_s: float, fans: frozenset[str]) -> dict[str, float]:
        """總水量分配到各盤管（水流經所有盤管，與風機是否運轉無關）。

參數：
    total_kg_s: 總水量。
    fans: 盤管所在的送風機（設定中可用的送風機）。

回傳：
    名稱 → kg/s。"""
        weights = {name: self.water_split[name] for name in fans}
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return {}
        return {name: total_kg_s * weight / total_weight for name, weight in weights.items()}

    # ---- 控制 ----
    def update_fans(self, time_s: float, available: frozenset[str], enabled: bool) -> None:
        """送風機啟停與分級（B 優先；濕度過高時至少保留一台）。

參數：
    time_s: 時間。
    available: 可用送風機。
    enabled: 系統是否啟用。

回傳：
    無。"""
        ind = self._indoor
        if not enabled:
            ind.fans_on = set()
            return
        if time_s - ind.fan_switched_s < self.control.fan_min_switch_s:
            return
        c = self.control
        order = [name for name in ("B", "A") if name in available] + sorted(available - {"A", "B"})
        if not order:
            return
        t = self.state.temperature_k
        humid = self.relative_humidity > c.rh_high
        count = len(ind.fans_on & set(order))
        target = count
        if t >= c.stage2_on_k:
            target = len(order)
        elif t >= c.stage1_on_k:
            target = max(count, 1)
        if t <= c.stage1_off_k:
            target = 1 if humid else 0
        elif t <= c.stage2_off_k:
            target = min(count, 1)
        if humid:
            target = max(target, 1)
        target = min(target, len(order))
        new = set(order[:target])
        if new != ind.fans_on:
            ind.fans_on = new
            ind.fan_switched_s = time_s

    def update_chw_setpoint(self, time_s: float, enabled: bool) -> float:
        """冰水溫度重設：濕度偏高或室溫偏高且風機全開時降 0.5 K；濕度與室溫都有餘裕時升 0.5 K。

參數：
    time_s: 時間。
    enabled: 系統是否啟用。

回傳：
    冰水停機設定值（K）。"""
        ind = self._indoor
        c = self.control
        if not self.chw_reset:
            ind.chw_setpoint_k = c.chw_min_k
            return ind.chw_setpoint_k
        if not enabled or time_s - ind.chw_changed_s < c.chw_interval_s:
            return ind.chw_setpoint_k
        rh = self.relative_humidity
        t = self.state.temperature_k
        all_on = len(ind.fans_on) >= len(self.coils) or len(ind.fans_on) >= 2
        if rh > c.rh_high or (t > c.setpoint_k + c.band_k and all_on):
            ind.chw_setpoint_k = max(c.chw_min_k, ind.chw_setpoint_k - c.chw_step_k)
        elif rh < c.chw_rh_raise_limit and t <= c.chw_t_raise_limit_k:
            ind.chw_setpoint_k = min(c.chw_max_k, ind.chw_setpoint_k + c.chw_step_k)
        ind.chw_changed_s = time_s
        return ind.chw_setpoint_k

    def reheat_request_w(self, time_s: float, coil_load_w: float) -> float:
        """再熱需求（未受盤管能力限制）。

參數：
    time_s: 時間。
    coil_load_w: 本步盤管總冷量。

回傳：
    W。"""
        if self.reheat_mode is ReheatMode.OFF or coil_load_w <= 0:
            return 0.0
        if self.reheat_mode is ReheatMode.FIXED:
            return self.reheat_fraction * coil_load_w
        c = self.control
        ind = self._indoor
        t = self.state.temperature_k
        rh = self.relative_humidity
        if time_s - ind.reheat_switched_s >= c.reheat_min_switch_s:
            if not ind.reheat_on and rh > c.rh_high and t < c.reheat_on_t_k:
                ind.reheat_on, ind.reheat_switched_s = True, time_s
            elif ind.reheat_on and (rh < c.reheat_off_rh or t >= c.reheat_off_t_k):
                ind.reheat_on, ind.reheat_switched_s = False, time_s
        if not ind.reheat_on:
            return 0.0
        return max(0.0, c.reheat_gain_w_k * (c.reheat_target_k - t))

    def reheat_capacity_w(self, coil_air_out_k: float, air_flow_kg_s: float, hot_water_k: float) -> float:
        """再熱盤管能力 ε·ṁ_a·cp·(熱水 − 盤管出風)。

參數：
    coil_air_out_k: 冷卻盤管出風溫度。
    air_flow_kg_s: 風量。
    hot_water_k: 熱水溫度。

回傳：
    W。"""
        if air_flow_kg_s <= 0:
            return 0.0
        c_air = air_flow_kg_s * psy.DRY_AIR_CP_J_KG_K
        eps = 1.0 - math.exp(-self.control.reheat_ua_w_k * (air_flow_kg_s / 0.22) / c_air)
        return max(0.0, eps * c_air * (hot_water_k - coil_air_out_k))

    # ---- 狀態推進 ----
    def internal_loads(self, time_s: float) -> tuple[float, float]:
        """內部與外殼的顯熱得熱（不含送風、滲入、新風）與產濕量。

參數：
    time_s: 時間。

回傳：
    (W, kg/s)。"""
        p = self.params
        sc = self.scenario
        people = sc.people_count(time_s)
        sensible = (p.envelope_ua_w_k * (sc.outdoor_k(time_s) - self.state.temperature_k) + sc.solar_w(time_s)
                    + people * p.people_sensible_w + sc.equipment_load_w(time_s))
        return sensible, people * p.people_moisture_kg_s

    def step(self, time_s: float, dt_s: float, supplies: list[SupplyAir], fan_heat_w: float) -> tuple[float, float]:
        """推進房間狀態（顯式 Euler）。

參數：
    time_s: 本步開始時間。
    dt_s: 步長。
    supplies: 各送風機送風。
    fan_heat_w: 送風機馬達熱（計入房間）。

回傳：
    (送風顯冷 W, 送風除濕 kg/s)（以室內狀態為基準）。"""
        p = self.params
        sc = self.scenario
        t, w = self.state.temperature_k, self.state.humidity_ratio
        cp = psy.moist_air_cp(w)
        sensible, moisture = self.internal_loads(time_s)
        outdoor_air = p.outdoor_air_kg_s if sc.system_enabled(time_s) else 0.0
        exchange = p.infiltration_kg_s + outdoor_air
        sensible += exchange * cp * (sc.outdoor_k(time_s) - t)
        moisture += exchange * (sc.outdoor_humidity(time_s) - w)
        if p.fan_heat_to_room:
            sensible += fan_heat_w
        supply_sensible = sum(s.air_flow_kg_s * cp * (t - s.temperature_k) for s in supplies)
        supply_moisture = sum(s.air_flow_kg_s * (w - s.humidity_ratio) for s in supplies)
        self.state.temperature_k = t + (sensible - supply_sensible) / p.heat_capacity_j_k * dt_s
        new_w = w + (moisture - supply_moisture) / p.moisture_capacity_kg * dt_s
        self.state.humidity_ratio = min(max(new_w, 1e-4), psy.saturation_humidity_ratio(self.state.temperature_k))
        return supply_sensible, supply_moisture

