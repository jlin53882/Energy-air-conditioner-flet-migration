"""用於 thermodynamic property query 的中立 application request。"""

from __future__ import annotations

from dataclasses import dataclass

from domain.thermodynamics.reference_state import ReferenceStatePolicy
from domain.thermodynamics.state_service import KnownProperty


@dataclass(frozen=True)
class PropertyQueryRequest:
    """描述不依賴 channel UI 的 property query。"""

    fluid: str
    known_properties: tuple[KnownProperty, ...]
    is_ideal_gas: bool = False
    reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT


@dataclass(frozen=True)
class CompressionRatioRequest:
    """描述以 canonical pascal 為單位的壓縮比計算。"""

    suction_pressure_pa: float
    discharge_pressure_pa: float


@dataclass(frozen=True)
class AirStateInput:
    """以乾球溫度加上 RH 分率或濕球溫度（擇一）描述的濕空氣狀態（canonical SI）。"""

    dry_bulb_k: float
    relative_humidity: float | None = None
    wet_bulb_k: float | None = None


@dataclass(frozen=True)
class AirStreamInput:
    """一股空氣：狀態與該狀態下量測的體積風量（m³/s）。"""

    state: AirStateInput
    volume_flow_m3_s: float


@dataclass(frozen=True)
class MixingRequest:
    """多股空氣絕熱混合。"""

    altitude_m: float
    streams: tuple[AirStreamInput, ...]


@dataclass(frozen=True)
class SensibleProcessRequest:
    """濕度比不變的加熱或冷卻；風量以入口狀態量測。"""

    altitude_m: float
    inlet: AirStateInput
    outlet_dry_bulb_k: float
    volume_flow_m3_s: float


@dataclass(frozen=True)
class CoolingCoilRequest:
    """冷卻除濕盤管；風量以入口狀態量測。"""

    altitude_m: float
    inlet: AirStateInput
    outlet: AirStateInput
    volume_flow_m3_s: float


@dataclass(frozen=True)
class SupplyAirflowRequest:
    """依室內顯熱負荷估算送風量。"""

    altitude_m: float
    room: AirStateInput
    supply_dry_bulb_k: float
    sensible_load_w: float


@dataclass(frozen=True)
class RefrigerationCycleRequest:
    """單級蒸氣壓縮循環；reference_state 為 None 時依流體套用預設 policy。"""

    fluid: str
    evaporating_temperature_k: float
    condensing_temperature_k: float
    superheat_k: float = 0.0
    subcooling_k: float = 0.0
    isentropic_efficiency: float = 1.0
    refrigeration_capacity_w: float | None = None
    reference_state: str | None = None


@dataclass(frozen=True)
class SuperheatCheckRequest:
    """以量測絕對壓力與管溫判斷過熱度／過冷度。"""

    fluid: str
    pressure_pa: float
    measured_temperature_k: float
