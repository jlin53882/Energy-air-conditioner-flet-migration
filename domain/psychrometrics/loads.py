"""空調側負荷：新風負荷、加濕負荷、風量與冷量換算。

所有輸入輸出皆為 canonical SI（K、Pa、J/kg、kg/s、W、m³/s）。濕空氣性質一律透過
`PsychrometricService` 取得；標準空氣快算使用下方明示的標準空氣常數，並在結果中
標示為近似值。熱量符號：正值表示要從空氣移除的熱（冷卻），負值表示要加入的熱（加熱）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .processes import AirState, _require_positive
from .service import PsychrometricService

# 標準空氣（海平面、約 20 °C 乾空氣）：密度與定壓比熱。只用於「標準空氣快算」。
STANDARD_AIR_DENSITY_KG_M3 = 1.2
STANDARD_AIR_CP_J_KGK = 1006.0

MODE_COOLING = "cooling"
MODE_HEATING = "heating"
MODE_NONE = "none"


def _mode(heat_w: float) -> str:
    """依熱量符號判斷冷卻或加熱。

參數：
    heat_w: 熱量（W；正值為冷卻）。

回傳：
    ``cooling``、``heating`` 或 ``none``。"""
    if heat_w > 0:
        return MODE_COOLING
    if heat_w < 0:
        return MODE_HEATING
    return MODE_NONE


@dataclass(frozen=True)
class SensibleLatentSplit:
    """全熱、顯熱與潛熱（W；正值為冷卻、負值為加熱）。"""

    total_w: float
    sensible_w: float
    latent_w: float

    @property
    def mode(self) -> str:
        """全熱的方向：``cooling``、``heating`` 或 ``none``。

回傳：
    方向代碼。"""
        return _mode(self.total_w)


def split_sensible_latent(
    service: PsychrometricService, entering: AirState, leaving: AirState, dry_air_mass_flow_kg_s: float
) -> SensibleLatentSplit:
    """把空氣由 entering 處理到 leaving 所需移除的熱量拆為顯熱與潛熱。

全熱 = ṁ(h_in − h_out)；以「進入乾球溫度、離開濕度比」的中間點 x 分解：
顯熱 = ṁ(h_x − h_out)、潛熱 = ṁ(h_in − h_x)。與冷卻盤管的分解方式相同。

參數：
    service: 濕空氣性質服務。
    entering: 處理前狀態。
    leaving: 處理後狀態。
    dry_air_mass_flow_kg_s: 乾空氣質量流率（kg/s）。

回傳：
    SensibleLatentSplit。"""
    intermediate_h = service.enthalpy_at(float(entering["Tdb"]), float(leaving["W"]))
    entering_h, leaving_h = float(entering["H"]), float(leaving["H"])
    return SensibleLatentSplit(
        total_w=dry_air_mass_flow_kg_s * (entering_h - leaving_h),
        sensible_w=dry_air_mass_flow_kg_s * (intermediate_h - leaving_h),
        latent_w=dry_air_mass_flow_kg_s * (entering_h - intermediate_h),
    )


# ======================================================
# 新風負荷
# ======================================================
@dataclass(frozen=True)
class OutdoorAirLoadResult:
    """把外氣處理到室內設計狀態所需的負荷（焓差法）。"""

    outdoor: AirState
    room: AirState
    dry_air_mass_flow_kg_s: float
    outdoor_volume_flow_m3_s: float
    load: SensibleLatentSplit


def outdoor_air_load(
    service: PsychrometricService, outdoor: AirState, room: AirState, dry_air_mass_flow_kg_s: float
) -> OutdoorAirLoadResult:
    """以焓差法計算新風負荷，並拆為顯熱與潛熱。

Q = ṁ(h_外氣 − h_室內)；正值為冷卻負荷（夏季），負值為加熱負荷（冬季）。顯熱、潛熱
可能符號不同（例如炎熱乾燥的外氣：顯熱為冷卻、潛熱為加濕）。

參數：
    service: 濕空氣性質服務。
    outdoor: 外氣狀態。
    room: 室內設計狀態。
    dry_air_mass_flow_kg_s: 新風的乾空氣質量流率（kg/s）。

回傳：
    OutdoorAirLoadResult。

引發：
    ValueError：流量不為正時。"""
    _require_positive(dry_air_mass_flow_kg_s, "新風量必須大於 0。")
    return OutdoorAirLoadResult(
        outdoor=outdoor,
        room=room,
        dry_air_mass_flow_kg_s=dry_air_mass_flow_kg_s,
        outdoor_volume_flow_m3_s=dry_air_mass_flow_kg_s * float(outdoor["V"]),
        load=split_sensible_latent(service, outdoor, room, dry_air_mass_flow_kg_s),
    )


# ======================================================
# 加濕負荷
# ======================================================
@dataclass(frozen=True)
class HumidificationResult:
    """把空氣由入口加濕到目標濕度比所需的水量與蒸汽熱量。

    ``steam_heat_w`` 以蒸汽加濕估算：加濕水量 × 水在當地大氣壓力下的蒸發潛熱
    （由呼叫端提供），即產生常壓飽和蒸汽所需熱量的下限，不含給水預熱與設備損失；
    不適用於滴濾、噴霧等等焓加濕（其熱量來自空氣本身的顯熱）。
    """

    inlet: AirState
    target: AirState
    dry_air_mass_flow_kg_s: float
    water_kg_s: float
    steam_latent_heat_j_kg: float

    @property
    def required(self) -> bool:
        """是否需要加濕（目標濕度比高於入口）。

回傳：
    bool。"""
        return self.water_kg_s > 0

    @property
    def steam_heat_w(self) -> float:
        """蒸汽加濕熱量（W）＝ 加濕水量 × 蒸發潛熱。

回傳：
    熱量；不需加濕時為 0。"""
        return self.water_kg_s * self.steam_latent_heat_j_kg


def humidification_load(
    inlet: AirState, target: AirState, dry_air_mass_flow_kg_s: float, steam_latent_heat_j_kg: float
) -> HumidificationResult:
    """計算加濕水量 ṁ_w = ṁ(W_目標 − W_入口)；目標不高於入口時為 0（不需加濕）。

參數：
    inlet: 加濕前狀態。
    target: 加濕後目標狀態。
    dry_air_mass_flow_kg_s: 乾空氣質量流率（kg/s）。
    steam_latent_heat_j_kg: 水在當地大氣壓力下的蒸發潛熱（J/kg）。

回傳：
    HumidificationResult。

引發：
    ValueError：流量或蒸發潛熱不為正時。"""
    _require_positive(dry_air_mass_flow_kg_s, "風量必須大於 0。")
    _require_positive(steam_latent_heat_j_kg, "蒸發潛熱必須大於 0。")
    water = dry_air_mass_flow_kg_s * max(float(target["W"]) - float(inlet["W"]), 0.0)
    return HumidificationResult(inlet, target, dry_air_mass_flow_kg_s, water, steam_latent_heat_j_kg)


# ======================================================
# 風量與冷量：標準空氣快算
# ======================================================
@dataclass(frozen=True)
class StandardAirResult:
    """標準空氣（ρ、cp 固定）下的顯熱量與風量；為近似值。"""

    volume_flow_m3_s: float
    temperature_difference_k: float
    sensible_capacity_w: float
    density_kg_m3: float = STANDARD_AIR_DENSITY_KG_M3
    cp_j_kgk: float = STANDARD_AIR_CP_J_KGK


def standard_air_capacity(volume_flow_m3_s: float, temperature_difference_k: float) -> StandardAirResult:
    """已知風量與溫差，以標準空氣計算顯熱量 Q = ρ·V·cp·ΔT。

參數：
    volume_flow_m3_s: 風量（m³/s）。
    temperature_difference_k: 進出風溫差（K，取正值）。

回傳：
    StandardAirResult。

引發：
    ValueError：風量或溫差不為正時。"""
    _require_positive(volume_flow_m3_s, "風量必須大於 0。")
    _require_positive(temperature_difference_k, "溫差必須大於 0。")
    capacity = STANDARD_AIR_DENSITY_KG_M3 * volume_flow_m3_s * STANDARD_AIR_CP_J_KGK * temperature_difference_k
    return StandardAirResult(volume_flow_m3_s, temperature_difference_k, capacity)


def standard_air_airflow(sensible_capacity_w: float, temperature_difference_k: float) -> StandardAirResult:
    """已知顯熱量與溫差，以標準空氣反算風量 V = Q / (ρ·cp·ΔT)。

參數：
    sensible_capacity_w: 顯熱量（W，取正值）。
    temperature_difference_k: 進出風溫差（K，取正值）。

回傳：
    StandardAirResult。

引發：
    ValueError：熱量或溫差不為正時。"""
    _require_positive(sensible_capacity_w, "冷量必須大於 0。")
    _require_positive(temperature_difference_k, "溫差必須大於 0。")
    volume = sensible_capacity_w / (STANDARD_AIR_DENSITY_KG_M3 * STANDARD_AIR_CP_J_KGK * temperature_difference_k)
    return StandardAirResult(volume, temperature_difference_k, sensible_capacity_w)


# ======================================================
# 風量與冷量：濕空氣狀態精算
# ======================================================
@dataclass(frozen=True)
class StateAirflowCapacityResult:
    """依進出風狀態計算的風量與全熱／顯熱／潛熱；體積風量以進風狀態比容換算。"""

    entering: AirState
    leaving: AirState
    dry_air_mass_flow_kg_s: float
    entering_volume_flow_m3_s: float
    load: SensibleLatentSplit


def state_capacity_from_airflow(
    service: PsychrometricService, entering: AirState, leaving: AirState, entering_volume_flow_m3_s: float
) -> StateAirflowCapacityResult:
    """已知進風狀態下的體積風量，計算全熱、顯熱與潛熱。

參數：
    service: 濕空氣性質服務。
    entering: 進風狀態。
    leaving: 出風狀態。
    entering_volume_flow_m3_s: 以進風狀態量測的體積風量（m³/s）。

回傳：
    StateAirflowCapacityResult。

引發：
    ValueError：風量不為正時。"""
    _require_positive(entering_volume_flow_m3_s, "風量必須大於 0。")
    mass_flow = entering_volume_flow_m3_s / float(entering["V"])
    return StateAirflowCapacityResult(
        entering, leaving, mass_flow, entering_volume_flow_m3_s,
        split_sensible_latent(service, entering, leaving, mass_flow),
    )


def state_airflow_from_capacity(
    service: PsychrometricService, entering: AirState, leaving: AirState, total_capacity_w: float
) -> StateAirflowCapacityResult:
    """已知全熱量（取正值，方向由進出風焓差決定），反算所需風量 ṁ = Q / |h_in − h_out|。

參數：
    service: 濕空氣性質服務。
    entering: 進風狀態。
    leaving: 出風狀態。
    total_capacity_w: 全熱量（W，取正值）。

回傳：
    StateAirflowCapacityResult。

引發：
    ValueError：熱量不為正，或進出風焓相同（無法反算風量）時。"""
    _require_positive(total_capacity_w, "冷量必須大於 0。")
    enthalpy_change = abs(float(entering["H"]) - float(leaving["H"]))
    if enthalpy_change < 1.0:
        raise ValueError("進出風焓值幾乎相同，無法由冷量反算風量；請確認進出風條件。")
    mass_flow = total_capacity_w / enthalpy_change
    return StateAirflowCapacityResult(
        entering, leaving, mass_flow, mass_flow * float(entering["V"]),
        split_sensible_latent(service, entering, leaving, mass_flow),
    )
