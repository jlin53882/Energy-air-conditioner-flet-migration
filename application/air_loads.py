"""空調側負荷的 application service：新風負荷、加濕負荷、風量與冷量換算。"""

from __future__ import annotations

from domain.psychrometrics.loads import (
    HumidificationResult,
    OutdoorAirLoadResult,
    StandardAirResult,
    StateAirflowCapacityResult,
    humidification_load,
    outdoor_air_load,
    standard_air_airflow,
    standard_air_capacity,
    state_airflow_from_capacity,
    state_capacity_from_airflow,
)
from domain.psychrometrics.processes import dry_air_mass_flow_from_volume
from domain.refrigeration import ThermodynamicStateProvider, saturation_properties
from domain.thermodynamics.reference_state import ReferenceStatePolicy

from .air_processes import AirProcessService
from .models import HumidificationRequest, OutdoorAirLoadRequest, StateAirflowCapacityRequest

STEAM_FLUID = "Water"


class AirLoadService:
    """把 canonical SI request 轉為濕空氣狀態，並協調空調側負荷計算。"""

    def __init__(self, air_processes: AirProcessService, water_properties: ThermodynamicStateProvider) -> None:
        """以共用的空氣處理服務與水性質服務初始化。

參數：
    air_processes: 解析濕空氣狀態的 application service。
    water_properties: 查詢水蒸發潛熱的狀態服務（canonical SI）。

回傳：
    無。"""
        self.air_processes = air_processes
        self.psychrometrics = air_processes.psychrometrics
        self.water_properties = water_properties

    def outdoor_air(self, request: OutdoorAirLoadRequest) -> OutdoorAirLoadResult:
        """計算新風負荷（焓差法，拆顯熱／潛熱）。

參數：
    request: 新風負荷 request。

回傳：
    OutdoorAirLoadResult。"""
        outdoor = self.air_processes.resolve_state(request.outdoor, request.altitude_m)
        room = self.air_processes.resolve_state(request.room, request.altitude_m)
        mass_flow = dry_air_mass_flow_from_volume(request.outdoor_volume_flow_m3_s, outdoor)
        return outdoor_air_load(self.psychrometrics, outdoor, room, mass_flow)

    def steam_latent_heat_j_kg(self, pressure_pa: float) -> float:
        """回傳水在指定絕對壓力下的蒸發潛熱（同壓飽和液→飽和蒸氣焓差）。

參數：
    pressure_pa: 絕對壓力（Pa），通常為當地大氣壓力。

回傳：
    蒸發潛熱（J/kg）。"""
        result = saturation_properties(
            self.water_properties, STEAM_FLUID, pressure_pa=pressure_pa, reference_state=ReferenceStatePolicy.DEFAULT
        )
        assert result.latent_heat_j_kg is not None  # 已知壓力時一定提供潛熱
        return result.latent_heat_j_kg

    def humidification(self, request: HumidificationRequest) -> HumidificationResult:
        """計算加濕水量與蒸汽加濕熱量（以當地大氣壓力的水蒸發潛熱）。

參數：
    request: 加濕負荷 request。

回傳：
    HumidificationResult。"""
        inlet = self.air_processes.resolve_state(request.inlet, request.altitude_m)
        target = self.air_processes.resolve_state(request.target, request.altitude_m)
        mass_flow = dry_air_mass_flow_from_volume(request.volume_flow_m3_s, inlet)
        return humidification_load(inlet, target, mass_flow, self.steam_latent_heat_j_kg(float(inlet["P"])))

    @staticmethod
    def standard_air_capacity(volume_flow_m3_s: float, temperature_difference_k: float) -> StandardAirResult:
        """標準空氣快算：由風量與溫差求顯熱量。

參數：
    volume_flow_m3_s: 風量（m³/s）。
    temperature_difference_k: 溫差（K）。

回傳：
    StandardAirResult。"""
        return standard_air_capacity(volume_flow_m3_s, temperature_difference_k)

    @staticmethod
    def standard_air_airflow(sensible_capacity_w: float, temperature_difference_k: float) -> StandardAirResult:
        """標準空氣快算：由顯熱量與溫差求風量。

參數：
    sensible_capacity_w: 顯熱量（W）。
    temperature_difference_k: 溫差（K）。

回傳：
    StandardAirResult。"""
        return standard_air_airflow(sensible_capacity_w, temperature_difference_k)

    def state_airflow_capacity(self, request: StateAirflowCapacityRequest) -> StateAirflowCapacityResult:
        """濕空氣狀態精算：已知風量求冷量，或已知全熱量求風量（兩者恰好提供一個）。

參數：
    request: 精算 request。

回傳：
    StateAirflowCapacityResult。

引發：
    ValueError：風量與全熱量未恰好提供一個時。"""
        if (request.entering_volume_flow_m3_s is None) == (request.total_capacity_w is None):
            raise ValueError("請只提供風量或冷量其中一個。")
        entering = self.air_processes.resolve_state(request.entering, request.altitude_m)
        leaving = self.air_processes.resolve_state(request.leaving, request.altitude_m)
        if request.entering_volume_flow_m3_s is not None:
            return state_capacity_from_airflow(
                self.psychrometrics, entering, leaving, request.entering_volume_flow_m3_s
            )
        return state_airflow_from_capacity(self.psychrometrics, entering, leaving, request.total_capacity_w)
