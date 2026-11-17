"""多元取熱雙效熱泵動態模擬的參數（canonical SI）。

預設值與來源見 ``docs/simulation-model.md`` §1。所有溫度為 K、功率為 W、
熱導（UA、ε·ṁ·cp）為 W/K、質量流率為 kg/s。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

CELSIUS_OFFSET_K = 273.15
GALLON_US_M3 = 3.785e-3
WATER_DENSITY_KG_M3 = 1000.0
WATER_CP_J_KG_K = 4186.0


def celsius(value_c: float) -> float:
    """°C 轉 K。

參數：
    value_c: 攝氏溫度。

回傳：
    絕對溫度 K。"""
    return value_c + CELSIUS_OFFSET_K


def gpm_to_kg_s(gpm: float) -> float:
    """美制 GPM 轉水的質量流率（水密度取 1000 kg/m³）。

參數：
    gpm: 體積流量（US gal/min）。

回傳：
    kg/s。"""
    return gpm * GALLON_US_M3 / 60.0 * WATER_DENSITY_KG_M3


@dataclass(frozen=True)
class CompressorParameters:
    """日立 E505DH-49A2W 渦卷式壓縮機（5 HP、定頻機型，以外接變頻器分段運轉；§1.1）。

    ``clearance_coefficient``、``overall_efficiency`` 由原廠額定點反推（額定冷量 12.9 kW、
    耗電 5.13 kW；原廠資料表未註明額定工況與頻率，**假設**為蒸發 7.2 °C、冷凝 54.4 °C、
    過熱 11.1 K、過冷 8.3 K、60 Hz）。
    """

    model: str = "Hitachi E505DH-49A2W"
    displacement_m3: float = 49.0e-6
    clearance_coefficient: float = 0.1498
    polytropic_exponent: float = 1.341
    overall_efficiency: float = 0.5683
    frequency_steps_hz: tuple[float, ...] = (30.0, 40.0, 50.0, 60.0)
    rated_frequency_hz: float = 60.0
    rated_cooling_w: float = 12_900.0
    rated_power_w: float = 5_130.0
    manufacturer_min_frequency_hz: float = 50.0

    @property
    def min_frequency_hz(self) -> float:
        """最低運轉頻率（階梯最小值）。

回傳：
            Hz。"""
        return min(self.frequency_steps_hz)

    @property
    def max_frequency_hz(self) -> float:
        """最高運轉頻率（階梯最大值）。

回傳：
            Hz。"""
        return max(self.frequency_steps_hz)


def interpolate_table(table: tuple[tuple[float, float], ...], x: float) -> float:
    """分段線性內插（超出範圍時夾在端點）。

參數：
    table: 依 x 遞增的 (x, y)。
    x: 查詢值。

回傳：
    y。"""
    if x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def interpolate_power_law(table: tuple[tuple[float, float], ...], x: float) -> float:
    """對數座標內插；低於最小點時沿最近兩點的冪次外插，高於最大點時沿最後兩點外插。

參數：
    table: 依 x 遞增的 (x, y)，x、y 皆須為正。
    x: 查詢值。

回傳：
    y。"""
    import math

    if x <= table[0][0]:
        (x0, y0), (x1, y1) = table[0], table[1]
    elif x >= table[-1][0]:
        (x0, y0), (x1, y1) = table[-2], table[-1]
    else:
        x0, y0, x1, y1 = next((a, b, c, d) for (a, b), (c, d) in zip(table, table[1:]) if x <= c)
    exponent = math.log(y1 / y0) / math.log(x1 / x0)
    return y0 * (x / x0) ** exponent


# 實測：冰水泵在不同變頻頻率下的流量（報告表 8.1.1，冰水流量 kg/s）與耗電（√3·V·I，W）。
MEASURED_PUMP_FLOW_KG_S: tuple[tuple[float, float], ...] = (
    (20.0, 0.19), (30.0, 0.30), (40.0, 0.43), (50.0, 0.56), (60.0, 0.62),
)
MEASURED_PUMP_POWER_W: tuple[tuple[float, float], ...] = ((40.0, 241.4), (50.0, 320.7), (60.0, 391.9))
_RATED_FLOW_KG_S = MEASURED_PUMP_FLOW_KG_S[-1][1]
MEASURED_PUMP_FLOW_RATIO: tuple[tuple[float, float], ...] = tuple(
    (hz, kg_s / _RATED_FLOW_KG_S) for hz, kg_s in MEASURED_PUMP_FLOW_KG_S
)

@dataclass(frozen=True)
class PumpParameters:
    """定頻水泵加變頻器（§1.6）。

    - 流量：``flow_ratio_by_hz``（相對 60 Hz 的比例，預設為冰水泵實測）× 額定流量；
      沒有曲線時流量 ∝ f。
    - 耗電：``power_w_by_hz``（預設為實測 √3·V·I；40–60 Hz 實測，低於 40 Hz 以冪次外插）；
      沒有曲線時耗電 ∝ f³（相似定律）。實測值為 √3·V·I（視在功率），``power_factor`` 預設 1.0
      （使用者決定：視為有效功率，不另外折減）；有效功率 = 曲線值 × power_factor。
    """

    rated_flow_gpm: float = 12.06
    rated_frequency_hz: float = 60.0
    rated_power_w: float = 391.9
    frequency_steps_hz: tuple[float, ...] = (30.0, 40.0, 50.0, 60.0)
    flow_ratio_by_hz: tuple[tuple[float, float], ...] = MEASURED_PUMP_FLOW_RATIO
    power_w_by_hz: tuple[tuple[float, float], ...] = MEASURED_PUMP_POWER_W
    power_factor: float = 1.0

    def flow_gpm(self, frequency_hz: float) -> float:
        """某頻率下的流量。

參數：
            frequency_hz: 泵浦頻率。

回傳：
            US GPM。"""
        if self.flow_ratio_by_hz:
            return self.rated_flow_gpm * interpolate_table(self.flow_ratio_by_hz, frequency_hz)
        return self.rated_flow_gpm * frequency_hz / self.rated_frequency_hz

    def power_w(self, frequency_hz: float) -> float:
        """某頻率下的耗電。

參數：
            frequency_hz: 泵浦頻率。

回傳：
            W。"""
        if self.power_w_by_hz:
            return interpolate_power_law(self.power_w_by_hz, frequency_hz) * self.power_factor
        return self.rated_power_w * (frequency_hz / self.rated_frequency_hz) ** 3 * self.power_factor


@dataclass(frozen=True)
class ReheatParameters:
    """除濕後再熱盤管（熱水桶供熱；§1.9）。

    再熱需求 = 再熱比例 × 送風機冷卻盤管負荷；盤管能力 = UA × (熱水溫度 − 盤管出風溫度)，
    盤管出風溫度 ≈ 冰水溫度 + ``coil_air_approach_k``。以上皆為**假設**。
    """

    ua_ratio_to_fan_coil: float = 0.2
    coil_air_approach_k: float = 5.0
    max_fraction: float = 0.6


@dataclass(frozen=True)
class CycleSettings:
    """循環設定（§1.2）。"""

    fluid: str = "R410A"
    superheat_k: float = 5.0
    subcooling_k: float = 5.0
    reference_state: str = "ASHRAE"


@dataclass(frozen=True)
class WaterTransportProperties:
    """板式換熱器水側熱傳計算用的水物性（固定參考溫度，2 bar；CoolProp 計算值）。"""

    viscosity_pa_s: float
    conductivity_w_m_k: float
    prandtl: float


# 參考溫度下的水物性（CoolProp 7，P = 2 bar）。
WATER_AT_12C = WaterTransportProperties(1.2340e-3, 0.5830, 8.873)
WATER_AT_45C = WaterTransportProperties(0.5958e-3, 0.6348, 3.923)
WATER_AT_56C = WaterTransportProperties(0.4957e-3, 0.6471, 3.205)


@dataclass(frozen=True)
class PlateGeometry:
    """板式換熱器水側流道幾何（典型值，假設）與經驗式係數（§1.4）。"""

    channel_width_m: float = 0.106
    channel_gap_m: float = 0.002
    nusselt_coefficient: float = 0.348
    reynolds_exponent: float = 0.663
    prandtl_exponent: float = 0.33

    @property
    def hydraulic_diameter_m(self) -> float:
        """水力直徑 Dh = 2 × 間隙。

回傳：
            m。"""
        return 2.0 * self.channel_gap_m


@dataclass(frozen=True)
class PlateHeatExchangerParameters:
    """板式換熱器參數。

    ``anchor_flow_kg_s``／``anchor_ua_w_k`` 有值時，UA 曲線乘上常數使該水量下的 UA 等於錨定值。
    """

    area_m2: float
    water_channels: int
    water: WaterTransportProperties
    anchor_flow_kg_s: float | None = None
    anchor_ua_w_k: float | None = None


@dataclass(frozen=True)
class RefrigerantSideCalibration:
    """由報告冷凝器設計點反推冷媒側＋板片熱阻 R_r（§1.4）。"""

    design_heat_w: float = 13_780.0
    design_area_m2: float = 1.53
    design_lmtd_k: float = 3.632
    design_water_flow_kg_s: float = 1.333
    design_water_channels: int = 30
    design_water: WaterTransportProperties = WATER_AT_56C


KCAL_PER_H_TO_W = 1.163
AIR_DENSITY_KG_M3 = 1.145
AIR_CP_J_KG_K = 1006.0


@dataclass(frozen=True)
class OutdoorHeatExchangerParameters:
    """室外熱交換器（大菱冷凍機械廠，報告表 2.1.5；§1.4）。

    原廠資料：能量 11,348 kcal/hr、處理風量 56.4 CMM、冷媒進／出口 57／52 °C、冷媒流量 370 kg/hr、
    銅管 ψ5/8" × 3 排、鋁鰭片 10 FPI（節距 2.54 mm）、迎風面積約 0.36 m²。
    **資料表沒有設計進風溫度，假設 35 °C**。

    模型以「進風溫差基準的有效熱導」G = Q ÷ (T_冷媒平均 − T_進風) 計算，
    即 ``Q = G·(T_冷媒 − T_進風)``（冷凝）或 ``Q = G·(T_進風 − T_冷媒)``（蒸發）；
    這等於 ε·ṁ_air·cp，與板式換熱器的 ε-NTU 處理一致。
    """

    rated_capacity_w: float = 11_348.0 * KCAL_PER_H_TO_W
    air_flow_cmm: float = 56.4
    refrigerant_inlet_c: float = 57.0
    refrigerant_outlet_c: float = 52.0
    refrigerant_flow_kg_s: float = 370.0 / 3600.0
    design_air_inlet_c: float = 35.0
    face_area_m2: float = 0.36
    tube_rows: int = 3

    @property
    def air_capacity_rate_w_k(self) -> float:
        """風側熱容量流率 ṁ_air·cp。

回傳：
            W/K。"""
        return self.air_flow_cmm / 60.0 * AIR_DENSITY_KG_M3 * AIR_CP_J_KG_K

    @property
    def refrigerant_mean_c(self) -> float:
        """冷媒進出口平均溫度（視為冷凝溫度）。

回傳：
            °C。"""
        return (self.refrigerant_inlet_c + self.refrigerant_outlet_c) / 2.0

    @property
    def conductance_w_k(self) -> float:
        """有效熱導 G = Q ÷ (T_冷媒平均 − T_設計進風)。

回傳：
            W/K。"""
        return self.rated_capacity_w / (self.refrigerant_mean_c - self.design_air_inlet_c)

    @property
    def effectiveness(self) -> float:
        """效能 ε = G ÷ (ṁ_air·cp)。

回傳：
            無因次。"""
        return self.conductance_w_k / self.air_capacity_rate_w_k

    @property
    def ua_w_k(self) -> float:
        """總熱傳係數與面積乘積 UA = −ln(1 − ε) × ṁ_air·cp（冷媒等溫，C_r = 0）。

回傳：
            W/K。"""
        import math

        return -math.log(1.0 - self.effectiveness) * self.air_capacity_rate_w_k


@dataclass(frozen=True)
class FanCoilUnit:
    """吊隱式送風機（§1.5）。UA = 額定冷量 ÷ 20 K。"""

    name: str
    ua_w_k: float
    fan_power_w: float


DEFAULT_FAN_COILS: tuple[FanCoilUnit, ...] = (
    FanCoilUnit("A", 3_516.0 / 20.0, 85.0),
    FanCoilUnit("B", 5_274.0 / 20.0, 125.0),
)


@dataclass(frozen=True)
class TankParameters:
    """冰水桶／熱水桶（§1.3）。"""

    volume_l: float = 160.0
    loss_ua_w_k: float = 0.93

    @property
    def heat_capacity_j_k(self) -> float:
        """m·cp。

回傳：
            J/K。"""
        return self.volume_l * WATER_DENSITY_KG_M3 / 1000.0 * WATER_CP_J_KG_K


class CoolingControlMode(str, Enum):
    """冷房壓縮機控制架構（§2.3、§8.12）。

    - ``LEGACY``：PID 目標＝停機點（7 °C），≥ 8 °C 重啟，每次重啟清除 PID（§4 原行為）。
    - ``SPLIT``：PID 目標、停機門檻、重啟門檻分離（預設 7.5／7.0／8.0 °C）；運轉中允許負誤差降載，
      只有在最低階仍持續低於停機門檻才停機；重啟時以上一運轉週期的平均頻率預設積分。
    """

    LEGACY = "legacy"
    SPLIT = "split"


@dataclass(frozen=True)
class ControlParameters:
    """模式切換、頻率 PID 與保護門檻（§2.2、§2.3）。"""

    cooling_hot_switch_k: float = celsius(40.0)
    cooling_hot_return_k: float = celsius(38.0)
    heating_cold_switch_k: float = celsius(5.0)
    heating_cold_return_k: float = celsius(7.0)

    cooling_setpoint_k: float = celsius(7.0)
    heating_setpoint_k: float = celsius(45.0)
    auto_stop_margin_k: float = 1.0
    cooling_restart_k: float = celsius(8.0)
    heating_restart_k: float = celsius(42.0)
    min_off_time_s: float = 180.0

    kp_hz_per_k: float = 10.0
    integral_time_s: float = 300.0
    derivative_time_s: float = 30.0
    derivative_filter_ratio: float = 5.0
    step_hysteresis_hz: float = 2.0
    step_dwell_s: float = 60.0
    mode_return_dwell_s: float = 300.0

    hp_limit_start_k: float = celsius(57.0)
    hp_limit_release_k: float = celsius(55.0)
    hp_limit_down_hz_per_s: float = 0.2
    hp_limit_up_hz_per_s: float = 0.04

    # 防凍保護以「板式蒸發器冰水出水溫度」判斷（非蒸發溫度）。
    freeze_limit_start_k: float = celsius(4.0)
    freeze_release_k: float = celsius(5.0)
    freeze_limit_down_hz_per_s: float = 0.5
    freeze_limit_up_hz_per_s: float = 0.04
    freeze_stop_delay_s: float = 60.0

    # 水泵自動頻率：板式換熱器水側溫差目標（假設值）、遲滯與變階最短停留。
    pump_cold_delta_t_k: float = 3.5
    pump_hot_delta_t_k: float = 5.0
    pump_hysteresis_k: float = 0.5
    pump_step_dwell_s: float = 60.0

    trip_condensing_k: float = celsius(60.0)
    trip_discharge_k: float = celsius(110.0)
    warn_high_pressure_k: float = celsius(58.0)
    warn_frost_k: float = celsius(0.0)

    max_evaporating_k: float = celsius(15.0)

    # 冷房目標分離控制（§8.12；預設 LEGACY，不影響 §4）。三個門檻都以冰水「基準」（停機點，
    # 房間模型的冰水重設會移動它）加偏移產生：停機 = 基準、PID 目標 = 基準 + target_offset、
    # 重啟 = 基準 + (cooling_restart_k − cooling_setpoint_k)。
    cooling_control_mode: CoolingControlMode = CoolingControlMode.LEGACY
    cooling_target_offset_k: float = 0.5
    # 已在最低階、桶溫 ≤ 停機門檻持續此時間才停機；低於停機門檻 − backstop 時立即停機。
    cooling_stop_hold_s: float = 30.0
    cooling_stop_backstop_k: float = 0.3
    # 最短運轉時間：只擋一般停機，不擋後備低溫、防凍、跳脫與排程停機。
    split_min_on_time_s: float = 180.0
    # 目標分離模式的 PID 參數（預設 PI；微分對量測值）。預設 Ti 300 s 時，積分退回太慢，
    # 撐不住 ±0.5 K 的帶寬（§8.12），故另設。
    split_integral_time_s: float = 120.0
    split_derivative_time_s: float = 0.0
    split_integral_min_hz: float = -5.0


@dataclass(frozen=True)
class ElectricalParameters:
    """耗電漏項（§8.5）。預設全為 0／1，維持 §4 的原始口徑；全系統比較（§8）改用 ``FULL_ELECTRICAL``。

    - ``outdoor_fan_w``：室外換熱器風扇，只在室外換熱器在流路（智慧冷房／智慧暖房）且壓縮機運轉時計入。
    - ``compressor_drive_efficiency``：壓縮機變頻器效率（壓縮機電功率 ÷ 此值）。
    - ``standby_w``：控制器待機（系統啟用時）。
    """

    outdoor_fan_w: float = 0.0
    compressor_drive_efficiency: float = 1.0
    standby_w: float = 0.0


# 全系統耗電口徑（假設值：5 HP 級 56.4 CMM 軸流扇約 150–250 W；變頻器 96 %；待機 30 W）。
FULL_ELECTRICAL = ElectricalParameters(outdoor_fan_w=200.0, compressor_drive_efficiency=0.96, standby_w=30.0)


@dataclass(frozen=True)
class HeatPumpParameters:
    """完整系統參數。"""

    compressor: CompressorParameters = field(default_factory=CompressorParameters)
    cycle: CycleSettings = field(default_factory=CycleSettings)
    condenser: PlateHeatExchangerParameters = field(
        default_factory=lambda: PlateHeatExchangerParameters(
            area_m2=1.53,
            water_channels=30,
            water=WATER_AT_45C,
            anchor_flow_kg_s=gpm_to_kg_s(12.06),
            anchor_ua_w_k=13_780.0 / 3.632,
        )
    )
    evaporator: PlateHeatExchangerParameters = field(
        default_factory=lambda: PlateHeatExchangerParameters(area_m2=0.714, water_channels=15, water=WATER_AT_12C)
    )
    refrigerant_side: RefrigerantSideCalibration = field(default_factory=RefrigerantSideCalibration)
    geometry: PlateGeometry = field(default_factory=PlateGeometry)
    outdoor: OutdoorHeatExchangerParameters = field(default_factory=OutdoorHeatExchangerParameters)
    fan_coils: tuple[FanCoilUnit, ...] = DEFAULT_FAN_COILS
    cold_tank: TankParameters = field(default_factory=TankParameters)
    hot_tank: TankParameters = field(default_factory=TankParameters)
    # 冰水泵：額定流量 = 實測 0.62 kg/s；熱水泵無實測，沿用報告設計 12.06 GPM 與同一條泵浦曲線形狀。
    cold_pump: PumpParameters = field(
        default_factory=lambda: PumpParameters(rated_flow_gpm=MEASURED_PUMP_FLOW_KG_S[-1][1] / gpm_to_kg_s(1.0))
    )
    hot_pump: PumpParameters = field(default_factory=PumpParameters)
    reheat: ReheatParameters = field(default_factory=ReheatParameters)
    control: ControlParameters = field(default_factory=ControlParameters)
    electrical: ElectricalParameters = field(default_factory=ElectricalParameters)

    @property
    def outdoor_ua_w_k(self) -> float:
        """室外換熱器的有效熱導（求解器使用；稱 UA_out，見 ``OutdoorHeatExchangerParameters``）。

回傳：
            W/K。"""
        return self.outdoor.conductance_w_k
