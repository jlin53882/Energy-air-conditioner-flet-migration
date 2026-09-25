"""濕空氣處理過程：混合、顯熱加熱／冷卻、冷卻除濕與送風量估算。

所有輸入輸出皆為 canonical SI（K、Pa、J/kg、kg/s、W、m³/s）。狀態性質一律
透過 `PsychrometricService` 取得，本模組只負責質量／能量平衡，不另行實作
濕空氣性質公式。狀態以服務回傳的中立 dict 表示（鍵值見 `PsychrometricService`）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .service import PsychrometricService

AirState = Mapping[str, Any]

# 判斷「濕度比未增加」等比較時的數值容許誤差（kg/kg）。
_HUMIDITY_RATIO_TOLERANCE = 1e-9


def _require_positive(value: float, message: str) -> None:
    """值不為正數時拋出帶有使用者訊息的 ValueError。

參數：
    value: 要檢查的數值。
    message: 錯誤訊息。

回傳：
    無。

引發：
    ValueError：value 小於或等於 0 時。"""
    if not value > 0:
        raise ValueError(message)


def dry_air_mass_flow_from_volume(volume_flow_m3_s: float, state: AirState) -> float:
    """以濕空氣比容（m³/kg 乾空氣）將體積風量換算為乾空氣質量流率。

參數：
    volume_flow_m3_s: 體積風量（m³/s）。
    state: 風量量測位置的濕空氣狀態。

回傳：
    乾空氣質量流率（kg/s）。

引發：
    ValueError：風量或比容不為正數時。"""
    _require_positive(volume_flow_m3_s, "風量必須大於 0。")
    specific_volume = float(state["V"])
    _require_positive(specific_volume, "濕空氣比容必須大於 0。")
    return volume_flow_m3_s / specific_volume


@dataclass(frozen=True)
class AirStream:
    """一股具有狀態與乾空氣質量流率的空氣。"""

    state: AirState
    dry_air_mass_flow_kg_s: float


@dataclass(frozen=True)
class MixingResult:
    """絕熱混合後的狀態與流量。"""

    state: AirState
    dry_air_mass_flow_kg_s: float
    volume_flow_m3_s: float
    mass_fractions: tuple[float, ...]


def mix_air_streams(
    service: PsychrometricService, streams: Sequence[AirStream], altitude_m: float
) -> MixingResult:
    """計算多股空氣在同一大氣壓力下的絕熱混合狀態。

以乾空氣質量加權濕度比與比焓（質量與能量守恆），再反解混合後乾球溫度。

參數：
    service: 濕空氣性質服務。
    streams: 至少兩股空氣。
    altitude_m: 海拔高度（m），決定大氣壓力。

回傳：
    混合結果。

引發：
    ValueError：少於兩股、流量不為正，或混合後過飽和時。"""
    if len(streams) < 2:
        raise ValueError("混合計算至少需要兩股空氣。")
    for stream in streams:
        _require_positive(stream.dry_air_mass_flow_kg_s, "每股空氣的流量都必須大於 0。")
    total_mass = sum(stream.dry_air_mass_flow_kg_s for stream in streams)
    humidity_ratio = sum(
        stream.dry_air_mass_flow_kg_s * float(stream.state["W"]) for stream in streams
    ) / total_mass
    enthalpy = sum(
        stream.dry_air_mass_flow_kg_s * float(stream.state["H"]) for stream in streams
    ) / total_mass
    dry_bulb_k = service.dry_bulb_from_enthalpy(enthalpy, humidity_ratio)
    try:
        state = service.calculate_from_tdb_w(dry_bulb_k, humidity_ratio, altitude_m)
    except ValueError as exc:
        raise ValueError(f"混合後狀態無法以單相濕空氣表示：{exc}") from exc
    return MixingResult(
        state=state,
        dry_air_mass_flow_kg_s=total_mass,
        volume_flow_m3_s=total_mass * float(state["V"]),
        mass_fractions=tuple(stream.dry_air_mass_flow_kg_s / total_mass for stream in streams),
    )


@dataclass(frozen=True)
class SensibleProcessResult:
    """濕度比不變的加熱或冷卻過程。heat_rate_w 為正代表加熱、負代表冷卻。"""

    inlet: AirState
    outlet: AirState
    dry_air_mass_flow_kg_s: float
    heat_rate_w: float


def sensible_heating_cooling(
    service: PsychrometricService,
    inlet: AirState,
    outlet_tdb_k: float,
    dry_air_mass_flow_kg_s: float,
    altitude_m: float,
) -> SensibleProcessResult:
    """計算濕度比不變的顯熱加熱或冷卻。

參數：
    service: 濕空氣性質服務。
    inlet: 入口狀態。
    outlet_tdb_k: 出口乾球溫度（K）。
    dry_air_mass_flow_kg_s: 乾空氣質量流率（kg/s）。
    altitude_m: 海拔高度（m）。

回傳：
    顯熱過程結果。

引發：
    ValueError：流量不為正，或出口溫度低於入口露點（會凝結）時。"""
    _require_positive(dry_air_mass_flow_kg_s, "風量必須大於 0。")
    if outlet_tdb_k < float(inlet["Tdp"]):
        raise ValueError("出口溫度低於入口露點，冷卻時會產生凝結；請改用「冷卻除濕」計算。")
    outlet = service.calculate_from_tdb_w(outlet_tdb_k, float(inlet["W"]), altitude_m)
    heat_rate = dry_air_mass_flow_kg_s * (float(outlet["H"]) - float(inlet["H"]))
    return SensibleProcessResult(inlet, outlet, dry_air_mass_flow_kg_s, heat_rate)


@dataclass(frozen=True)
class CoolingCoilResult:
    """冷卻除濕盤管的負荷分解。熱量皆為正值（W），冷凝水為 kg/s。"""

    inlet: AirState
    outlet: AirState
    dry_air_mass_flow_kg_s: float
    total_load_w: float
    sensible_load_w: float
    latent_load_w: float
    sensible_heat_ratio: float
    condensate_kg_s: float


def cooling_dehumidification(
    service: PsychrometricService,
    inlet: AirState,
    outlet: AirState,
    dry_air_mass_flow_kg_s: float,
) -> CoolingCoilResult:
    """計算冷卻除濕盤管的全熱、顯熱、潛熱、顯熱比與冷凝水量。

全熱 = ṁ(h1 − h2)；以「入口乾球溫度、出口濕度比」的中間點 x 分解：
顯熱 = ṁ(hx − h2)、潛熱 = ṁ(h1 − hx)。冷凝水帶走的焓量很小，此處忽略。

參數：
    service: 濕空氣性質服務。
    inlet: 盤管入口狀態。
    outlet: 盤管出口狀態。
    dry_air_mass_flow_kg_s: 乾空氣質量流率（kg/s）。

回傳：
    盤管負荷結果。

引發：
    ValueError：流量不為正、出口未降溫，或出口濕度比高於入口時。"""
    _require_positive(dry_air_mass_flow_kg_s, "風量必須大於 0。")
    inlet_tdb, outlet_tdb = float(inlet["Tdb"]), float(outlet["Tdb"])
    inlet_w, outlet_w = float(inlet["W"]), float(outlet["W"])
    if outlet_tdb >= inlet_tdb:
        raise ValueError("冷卻除濕的出口乾球溫度必須低於入口。")
    if outlet_w > inlet_w + _HUMIDITY_RATIO_TOLERANCE:
        raise ValueError("出口濕度比高於入口，這不是除濕過程；請確認出口條件。")
    inlet_h, outlet_h = float(inlet["H"]), float(outlet["H"])
    intermediate_h = service.enthalpy_at(inlet_tdb, outlet_w)
    total = dry_air_mass_flow_kg_s * (inlet_h - outlet_h)
    sensible = dry_air_mass_flow_kg_s * (intermediate_h - outlet_h)
    latent = dry_air_mass_flow_kg_s * (inlet_h - intermediate_h)
    return CoolingCoilResult(
        inlet=inlet,
        outlet=outlet,
        dry_air_mass_flow_kg_s=dry_air_mass_flow_kg_s,
        total_load_w=total,
        sensible_load_w=sensible,
        latent_load_w=latent,
        sensible_heat_ratio=sensible / total if total else 0.0,
        condensate_kg_s=dry_air_mass_flow_kg_s * max(inlet_w - outlet_w, 0.0),
    )


@dataclass(frozen=True)
class SupplyAirflowResult:
    """依室內顯熱負荷估算的送風量。"""

    room: AirState
    supply: AirState
    dry_air_mass_flow_kg_s: float
    supply_volume_flow_m3_s: float
    temperature_difference_k: float


def supply_airflow_for_sensible_load(
    service: PsychrometricService,
    room: AirState,
    supply_tdb_k: float,
    sensible_load_w: float,
    altitude_m: float,
) -> SupplyAirflowResult:
    """以室內顯熱負荷與送風溫度估算所需送風量（送風與室內濕度比相同）。

ṁ = Q_s / (h_room − h_supply)，體積風量以送風狀態比容換算。

參數：
    service: 濕空氣性質服務。
    room: 室內設計狀態。
    supply_tdb_k: 送風乾球溫度（K）。
    sensible_load_w: 室內顯熱負荷（W）。
    altitude_m: 海拔高度（m）。

回傳：
    送風量結果。

引發：
    ValueError：負荷不為正、送風溫度不低於室溫，或低於室內露點時。"""
    _require_positive(sensible_load_w, "顯熱負荷必須大於 0。")
    room_tdb = float(room["Tdb"])
    if supply_tdb_k >= room_tdb:
        raise ValueError("冷房送風溫度必須低於室內乾球溫度。")
    if supply_tdb_k < float(room["Tdp"]):
        raise ValueError("送風溫度低於室內露點，濕度比無法維持不變；請提高送風溫度。")
    supply = service.calculate_from_tdb_w(supply_tdb_k, float(room["W"]), altitude_m)
    mass_flow = sensible_load_w / (float(room["H"]) - float(supply["H"]))
    return SupplyAirflowResult(
        room=room,
        supply=supply,
        dry_air_mass_flow_kg_s=mass_flow,
        supply_volume_flow_m3_s=mass_flow * float(supply["V"]),
        temperature_difference_k=room_tdb - supply_tdb_k,
    )
