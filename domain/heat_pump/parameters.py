"""多元取熱雙效熱泵動態模擬的參數（canonical SI）。

預設值與來源見 ``docs/simulation-model.md`` §1。所有溫度為 K、功率為 W、
熱導（UA、ε·ṁ·cp）為 W/K、質量流率為 kg/s。
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    """Panasonic 5JS330MAA21 雙缸迴轉式壓縮機（§1.1）。"""

    displacement_m3: float = 33.0e-6
    clearance_coefficient: float = 0.0892
    polytropic_exponent: float = 1.341
    overall_efficiency: float = 0.66
    min_frequency_hz: float = 30.0
    max_frequency_hz: float = 60.0


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


@dataclass(frozen=True)
class ControlParameters:
    """模式切換、頻率 PI 與保護門檻（§2.2、§2.3）。"""

    cooling_hot_switch_k: float = celsius(40.0)
    cooling_hot_return_k: float = celsius(38.0)
    heating_cold_switch_k: float = celsius(5.0)
    heating_cold_return_k: float = celsius(7.0)

    cooling_setpoint_k: float = celsius(7.0)
    heating_setpoint_k: float = celsius(45.0)
    auto_stop_margin_k: float = 1.0
    cooling_restart_k: float = celsius(10.0)
    heating_restart_k: float = celsius(42.0)
    min_off_time_s: float = 180.0

    kp_hz_per_k: float = 10.0
    integral_time_s: float = 300.0

    hp_limit_start_k: float = celsius(57.0)
    hp_limit_release_k: float = celsius(55.0)
    hp_limit_down_hz_per_s: float = 0.2
    hp_limit_up_hz_per_s: float = 0.04

    trip_condensing_k: float = celsius(60.0)
    trip_discharge_k: float = celsius(110.0)
    warn_high_pressure_k: float = celsius(58.0)
    warn_frost_k: float = celsius(0.0)

    max_evaporating_k: float = celsius(15.0)


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
    outdoor_ua_w_k: float = 13_780.0 / 25.0
    fan_coils: tuple[FanCoilUnit, ...] = DEFAULT_FAN_COILS
    cold_tank: TankParameters = field(default_factory=TankParameters)
    hot_tank: TankParameters = field(default_factory=TankParameters)
    pump_power_w: float = 500.0
    pump_count: int = 2
    control: ControlParameters = field(default_factory=ControlParameters)
