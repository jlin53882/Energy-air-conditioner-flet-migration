"""冷凝器的能量、熵與㶲平衡（canonical SI）。

冷媒由入口狀態 1 放熱到出口狀態 2，熱量 Q_H 在等效傳熱邊界溫度 T_b 穿越所選的
分析控制邊界 (control boundary) 離開系統：

- 放熱量：Q_H = ṁ · (h1 − h2)
- 冷媒㶲減少量：ṁ · (ex1 − ex2) = ṁ · [(h1 − h2) − T0 · (s1 − s2)]
- 熱帶走的㶲：Ex_Q = Q_H · (1 − T0 / T_b)
- 㶲破壞：X_dest = ṁ · (ex1 − ex2) − Ex_Q
- 熵產生：S_gen = ṁ · (s2 − s1) + Q_H / T_b，並滿足 X_dest = T0 · S_gen
- 㶲效率：η = Ex_Q / [ṁ · (ex1 − ex2)]

T_b 是熱量穿越所選控制邊界時的等效傳熱邊界溫度，取決於控制容積的劃定方式，
不一定等於外部熱匯（外氣、熱水、室內空氣）的 bulk temperature：

- 控制容積只涵蓋冷凝器本體時，T_b 應是冷凝器表面／邊界處對應的等效溫度；
  不可直接把外氣溫度（例如 25 °C）當成冷凝器本體的 T_b。
- 只有把分析邊界定義為「冷凝器直到最終向環境排熱的整體系統」時，T_b = T0
  才代表熱最終排到環境；此時 Ex_Q = 0，冷媒減少的㶲在這個整體邊界內全部被破壞。

T_b 沒有預設值，必須由呼叫端依所選控制邊界明確指定。T_b 必須介於 T0 與冷媒
平均放熱溫度 (h1 − h2) / (s1 − s2) 之間，超過上限時熵產生為負，違反熱力學第二
定律。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from domain.state_points import StateSource, ThermoStatePoint, require_same_basis
from domain.thermodynamics.reference_state import ReferenceStatePolicy, normalize_reference_state_policy

from .states import ThermodynamicStateProvider, query_state

# 判斷熵產生是否為負時容許的相對浮點誤差。
_ENTROPY_TOLERANCE = 1e-9


def coolant_mean_temperature_k(inlet_temperature_k: float, outlet_temperature_k: float) -> float:
    """由冷卻介質進出口溫度計算熱力學平均溫度，作為冷凝器的等效傳熱邊界溫度。

冷卻介質（冷卻水、熱回收熱水或空冷空氣）由 T_in 被加熱到 T_out，比熱視為定值時：
Q = ṁ·cp·(T_out − T_in)、ΔS = ṁ·cp·ln(T_out / T_in)，因此
T_b = Q / ΔS = (T_out − T_in) / ln(T_out / T_in)，與流率和比熱無關。
以此 T_b 計算的 Ex_Q = Q·(1 − T0/T_b) 等於冷卻介質獲得的㶲，對應的 η 即熱交換器㶲效率。
適用於無相變、壓降可忽略且對外無明顯散熱的冷卻介質；不適用於蒸發式冷凝器。

參數：
    inlet_temperature_k: 冷卻介質入口溫度（K）。
    outlet_temperature_k: 冷卻介質出口溫度（K），不可低於入口溫度。

回傳：
    熱力學平均溫度（K）；進出口溫度相同時即為該溫度。

引發：
    ValueError：溫度不為正，或出口溫度低於入口溫度（介質沒有被加熱）時。"""
    if inlet_temperature_k <= 0 or outlet_temperature_k <= 0:
        raise ValueError("冷卻介質溫度必須是大於 0 的絕對溫度。")
    if outlet_temperature_k < inlet_temperature_k:
        raise ValueError("冷卻介質出口溫度不可低於入口溫度（冷卻介質應被加熱）。")
    if math.isclose(outlet_temperature_k, inlet_temperature_k, rel_tol=1e-12, abs_tol=0.0):
        return inlet_temperature_k
    return (outlet_temperature_k - inlet_temperature_k) / math.log(outlet_temperature_k / inlet_temperature_k)


@dataclass(frozen=True)
class CondenserExergyBalance:
    """冷凝器平衡的計算結果（W、W/K、K；效率為無單位比值）。"""

    heat_rejection_w: float
    exergy_decrease_w: float
    heat_exergy_w: float
    exergy_destruction_w: float
    entropy_generation_w_k: float
    exergy_efficiency: float
    mean_heat_rejection_temperature_k: float


def condenser_exergy_balance(
    mass_flow_kg_s: float,
    inlet_enthalpy_j_kg: float,
    outlet_enthalpy_j_kg: float,
    inlet_entropy_j_kgk: float,
    outlet_entropy_j_kgk: float,
    dead_state_temperature_k: float,
    *,
    boundary_temperature_k: float,
) -> CondenserExergyBalance:
    """由進出口狀態計算冷凝器的能量、熵與㶲平衡。

參數：
    mass_flow_kg_s: 冷媒質量流率（kg/s）。
    inlet_enthalpy_j_kg: 入口比焓（J/kg）。
    outlet_enthalpy_j_kg: 出口比焓（J/kg）。
    inlet_entropy_j_kgk: 入口比熵（J/(kg·K)）。
    outlet_entropy_j_kgk: 出口比熵（J/(kg·K)）。
    dead_state_temperature_k: 死狀態（環境）溫度 T0（K）。
    boundary_temperature_k: 等效傳熱邊界溫度 T_b（K），即熱量穿越所選控制邊界時
        的溫度；分析邊界涵蓋到整體排熱至環境時為 T0。

回傳：
    CondenserExergyBalance。

引發：
    ValueError：流率或溫度不為正、冷媒沒有放熱、T_b 低於 T0，或 T_b 高於冷媒平均
    放熱溫度（熵產生為負）時。"""
    if mass_flow_kg_s <= 0:
        raise ValueError("冷媒質量流率必須大於 0。")
    if dead_state_temperature_k <= 0 or boundary_temperature_k <= 0:
        raise ValueError("死狀態溫度與等效傳熱邊界溫度必須是大於 0 的絕對溫度。")
    enthalpy_drop = inlet_enthalpy_j_kg - outlet_enthalpy_j_kg
    entropy_drop = inlet_entropy_j_kgk - outlet_entropy_j_kgk
    if enthalpy_drop <= 0 or entropy_drop <= 0:
        raise ValueError("冷凝器出口的比焓與比熵必須低於入口（冷媒須放熱）。")
    if boundary_temperature_k < dead_state_temperature_k:
        raise ValueError("等效傳熱邊界溫度不可低於死狀態溫度 T0；分析邊界涵蓋到整體排熱至環境時請使用 T0。")

    mean_temperature_k = enthalpy_drop / entropy_drop
    heat_rejection_w = mass_flow_kg_s * enthalpy_drop
    entropy_generation_w_k = -mass_flow_kg_s * entropy_drop + heat_rejection_w / boundary_temperature_k
    if entropy_generation_w_k < -_ENTROPY_TOLERANCE * mass_flow_kg_s * entropy_drop:
        raise ValueError(
            f"等效傳熱邊界溫度 {boundary_temperature_k - 273.15:.2f} °C 高於冷媒平均放熱溫度 "
            f"{mean_temperature_k - 273.15:.2f} °C，熵產生為負，違反熱力學第二定律。"
        )
    entropy_generation_w_k = max(entropy_generation_w_k, 0.0)

    exergy_decrease_w = mass_flow_kg_s * (enthalpy_drop - dead_state_temperature_k * entropy_drop)
    if exergy_decrease_w <= 0:
        raise ValueError("冷媒的 Exergy 減少量必須大於 0；請確認冷媒溫度高於死狀態溫度 T0。")
    heat_exergy_w = heat_rejection_w * (1.0 - dead_state_temperature_k / boundary_temperature_k)
    return CondenserExergyBalance(
        heat_rejection_w=heat_rejection_w,
        exergy_decrease_w=exergy_decrease_w,
        heat_exergy_w=heat_exergy_w,
        exergy_destruction_w=dead_state_temperature_k * entropy_generation_w_k,
        entropy_generation_w_k=entropy_generation_w_k,
        exergy_efficiency=heat_exergy_w / exergy_decrease_w,
        mean_heat_rejection_temperature_k=mean_temperature_k,
    )


@dataclass(frozen=True)
class CondenserExergyResult:
    """以冷媒進出口量測值分析冷凝器的結果（canonical SI）。"""

    fluid: str
    pressure_pa: float
    inlet: ThermoStatePoint
    outlet: ThermoStatePoint
    dew_point_k: float
    bubble_point_k: float
    mass_flow_kg_s: float
    dead_state_temperature_k: float
    boundary_temperature_k: float
    balance: CondenserExergyBalance


def analyze_condenser_exergy(
    provider: ThermodynamicStateProvider,
    fluid: str,
    pressure_pa: float,
    inlet_temperature_k: float,
    outlet_temperature_k: float,
    mass_flow_kg_s: float,
    dead_state_temperature_k: float,
    *,
    boundary_temperature_k: float,
    reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT,
) -> CondenserExergyResult:
    """以冷凝壓力與進出口溫度查詢狀態，計算冷凝器的㶲平衡（忽略冷凝器壓降）。

參數：
    provider: canonical SI 狀態服務。
    fluid: CoolProp 流體名稱。
    pressure_pa: 冷凝絕對壓力（Pa），進出口相同。
    inlet_temperature_k: 冷媒入口溫度（K），通常為過熱蒸氣。
    outlet_temperature_k: 冷媒出口溫度（K），通常為過冷液體。
    mass_flow_kg_s: 冷媒質量流率（kg/s）。
    dead_state_temperature_k: 死狀態（環境）溫度 T0（K）。
    boundary_temperature_k: 等效傳熱邊界溫度 T_b（K），即熱量穿越所選控制邊界時
        的溫度；分析邊界涵蓋到整體排熱至環境時為 T0。
    reference_state: reference-state policy（焓熵差與此無關，只影響查詢交易）。

回傳：
    CondenserExergyResult。

引發：
    ValueError：輸入無效、狀態無法計算（例如溫度剛好等於飽和溫度），或平衡違反
    熱力學第二定律時。"""
    fluid = fluid.strip()
    if not fluid:
        raise ValueError("請輸入冷媒名稱。")
    if pressure_pa <= 0 or inlet_temperature_k <= 0 or outlet_temperature_k <= 0:
        raise ValueError("壓力與溫度必須是有效的絕對值（壓力請使用絕對壓力）。")
    if inlet_temperature_k <= outlet_temperature_k:
        raise ValueError("冷凝器入口溫度必須高於出口溫度。")
    resolved_policy = normalize_reference_state_policy(reference_state)
    inlet = ThermoStatePoint.from_state_mapping(query_state(
        provider, fluid, [("P", pressure_pa), ("T", inlet_temperature_k)], reference_state,
        "冷凝器入口狀態（溫度不可剛好等於飽和溫度）"),
        fluid=fluid, reference_state=resolved_policy, source=StateSource.CONDENSER_EXERGY,
        key="1", label="冷凝器入口")
    outlet = ThermoStatePoint.from_state_mapping(query_state(
        provider, fluid, [("P", pressure_pa), ("T", outlet_temperature_k)], reference_state,
        "冷凝器出口狀態（溫度不可剛好等於飽和溫度）"),
        fluid=fluid, reference_state=resolved_policy, source=StateSource.CONDENSER_EXERGY,
        key="2", label="冷凝器出口")
    # 㶲平衡只使用進出口的焓差與熵差，兩端必須是同一基準。
    require_same_basis(inlet, outlet)
    dew = query_state(provider, fluid, [("P", pressure_pa), ("Q", 1.0)], reference_state, "露點飽和溫度")
    bubble = query_state(provider, fluid, [("P", pressure_pa), ("Q", 0.0)], reference_state, "泡點飽和溫度")
    balance = condenser_exergy_balance(
        mass_flow_kg_s,
        inlet.enthalpy_j_kg,
        outlet.enthalpy_j_kg,
        inlet.entropy_j_kgk,
        outlet.entropy_j_kgk,
        dead_state_temperature_k,
        boundary_temperature_k=boundary_temperature_k,
    )
    return CondenserExergyResult(
        fluid=fluid,
        pressure_pa=pressure_pa,
        inlet=inlet,
        outlet=outlet,
        dew_point_k=float(dew["T"]),
        bubble_point_k=float(bubble["T"]),
        mass_flow_kg_s=mass_flow_kg_s,
        dead_state_temperature_k=dead_state_temperature_k,
        boundary_temperature_k=boundary_temperature_k,
        balance=balance,
    )
