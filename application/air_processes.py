"""濕空氣處理過程的 application service。"""

from __future__ import annotations

from typing import Any

from domain.psychrometrics.processes import (
    AirStream,
    CoolingCoilResult,
    MixingResult,
    SensibleProcessResult,
    SupplyAirflowResult,
    cooling_dehumidification,
    dry_air_mass_flow_from_volume,
    mix_air_streams,
    sensible_heating_cooling,
    supply_airflow_for_sensible_load,
)
from domain.psychrometrics.service import PsychrometricService

from .models import (
    AirStateInput,
    CoolingCoilRequest,
    MixingRequest,
    SensibleProcessRequest,
    SupplyAirflowRequest,
)


class AirProcessService:
    """將 canonical SI request 轉為濕空氣狀態，並協調 domain 過程計算。"""

    def __init__(self, psychrometrics: PsychrometricService) -> None:
        """以共用的濕空氣服務初始化。

參數：
    psychrometrics: domain 濕空氣服務。

回傳：
    無。"""
        self.psychrometrics = psychrometrics

    def resolve_state(self, spec: AirStateInput, altitude_m: float) -> dict[str, Any]:
        """依輸入組合計算完整濕空氣狀態。

參數：
    spec: 乾球溫度加上 RH 或濕球溫度（擇一）。
    altitude_m: 海拔（m）。

回傳：
    中立狀態 dict。

引發：
    ValueError：同時或都未提供 RH／濕球溫度，或濕球高於乾球時。"""
        has_rh = spec.relative_humidity is not None
        has_wb = spec.wet_bulb_k is not None
        if has_rh == has_wb:
            raise ValueError("請以「相對濕度」或「濕球溫度」其中一種方式描述空氣狀態。")
        if has_wb:
            if spec.wet_bulb_k > spec.dry_bulb_k:
                raise ValueError("濕球溫度不可高於乾球溫度。")
            return self.psychrometrics.calculate_from_tdb_twb(spec.dry_bulb_k, spec.wet_bulb_k, altitude_m)
        return self.psychrometrics.calculate_from_tdb_rh(spec.dry_bulb_k, spec.relative_humidity, altitude_m)

    def mix(self, request: MixingRequest) -> MixingResult:
        """計算多股空氣混合；各股風量以其自身狀態比容換算為乾空氣質量流率。

參數：
    request: 混合 request。

回傳：
    MixingResult。"""
        streams = []
        for stream in request.streams:
            state = self.resolve_state(stream.state, request.altitude_m)
            streams.append(AirStream(state, dry_air_mass_flow_from_volume(stream.volume_flow_m3_s, state)))
        return mix_air_streams(self.psychrometrics, streams, request.altitude_m)

    def sensible(self, request: SensibleProcessRequest) -> SensibleProcessResult:
        """計算顯熱加熱或冷卻。

參數：
    request: 顯熱過程 request。

回傳：
    SensibleProcessResult。"""
        inlet = self.resolve_state(request.inlet, request.altitude_m)
        mass_flow = dry_air_mass_flow_from_volume(request.volume_flow_m3_s, inlet)
        return sensible_heating_cooling(
            self.psychrometrics, inlet, request.outlet_dry_bulb_k, mass_flow, request.altitude_m
        )

    def cooling_coil(self, request: CoolingCoilRequest) -> CoolingCoilResult:
        """計算冷卻除濕盤管負荷。

參數：
    request: 冷卻盤管 request。

回傳：
    CoolingCoilResult。"""
        inlet = self.resolve_state(request.inlet, request.altitude_m)
        outlet = self.resolve_state(request.outlet, request.altitude_m)
        mass_flow = dry_air_mass_flow_from_volume(request.volume_flow_m3_s, inlet)
        return cooling_dehumidification(self.psychrometrics, inlet, outlet, mass_flow)

    def supply_airflow(self, request: SupplyAirflowRequest) -> SupplyAirflowResult:
        """依顯熱負荷估算送風量。

參數：
    request: 送風量 request。

回傳：
    SupplyAirflowResult。"""
        room = self.resolve_state(request.room, request.altitude_m)
        return supply_airflow_for_sensible_load(
            self.psychrometrics, room, request.supply_dry_bulb_k, request.sensible_load_w, request.altitude_m
        )
