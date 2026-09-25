"""單級蒸氣壓縮冷凍循環（含過熱、過冷與壓縮機等熵效率）。

狀態點定義：
- 蒸發壓力：蒸發溫度下的飽和蒸氣（露點）壓力。
- 冷凝壓力：冷凝溫度下的飽和液體（泡點）壓力。
- 1 壓縮機入口：蒸發壓力，溫度 = 露點 + 過熱度（過熱度為 0 時為飽和蒸氣）。
- 2s 等熵出口：冷凝壓力、s = s1；2 實際出口：h2 = h1 + (h2s − h1) / η_isen。
- 3 冷凝器出口：冷凝壓力，溫度 = 泡點 − 過冷度（過冷度為 0 時為飽和液體）。
- 4 蒸發器入口：蒸發壓力、h4 = h3（等焓節流）。
忽略管路壓降與熱損失。所有量為 canonical SI。
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.thermodynamics.reference_state import ReferenceStatePolicy, normalize_reference_state_policy

from .states import CycleState, ThermodynamicStateProvider, query_state


@dataclass(frozen=True)
class VaporCompressionInputs:
    """蒸氣壓縮循環的設計條件。refrigeration_capacity_w 未提供時只回傳單位質量結果。"""

    fluid: str
    evaporating_temperature_k: float
    condensing_temperature_k: float
    superheat_k: float = 0.0
    subcooling_k: float = 0.0
    isentropic_efficiency: float = 1.0
    refrigeration_capacity_w: float | None = None
    reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.ASHRAE


@dataclass(frozen=True)
class VaporCompressionResult:
    """循環狀態點與性能指標。系統量（kg/s、W、m³/s）只在提供冷凍能力時才有值。

    ``reference_state`` 是求解時實際使用的 reference-state policy code（例如
    ``ASHRAE``）；焓、熵等數值都以此為基準，繪製同一循環的圖表必須沿用它，
    不可重新解析。
    """

    fluid: str
    states: dict[str, CycleState]
    evaporating_pressure_pa: float
    condensing_pressure_pa: float
    refrigerating_effect_j_kg: float
    compressor_work_j_kg: float
    heat_rejection_j_kg: float
    cop_cooling: float
    cop_heating: float
    pressure_ratio: float
    reference_state: str
    mass_flow_kg_s: float | None = None
    refrigeration_capacity_w: float | None = None
    compressor_power_w: float | None = None
    heat_rejection_w: float | None = None
    suction_volume_flow_m3_s: float | None = None

    @property
    def cycle_path(self) -> tuple[CycleState, ...]:
        """回傳依循環順序排列、首尾相接的狀態點，供圖表連線使用。

回傳：
    1 → 2 → 3 → 4 → 1 的狀態點序列。"""
        return tuple(self.states[key] for key in ("1", "2", "3", "4", "1"))


def _validate(inputs: VaporCompressionInputs) -> None:
    """檢查循環設計條件的物理合理性。

參數：
    inputs: 設計條件。

回傳：
    無。

引發：
    ValueError：任何條件不合理時。"""
    if not inputs.fluid.strip():
        raise ValueError("請輸入冷媒名稱。")
    if inputs.evaporating_temperature_k <= 0 or inputs.condensing_temperature_k <= 0:
        raise ValueError("蒸發與冷凝溫度必須是有效的絕對溫度。")
    if inputs.condensing_temperature_k <= inputs.evaporating_temperature_k:
        raise ValueError("冷凝溫度必須高於蒸發溫度。")
    if inputs.superheat_k < 0 or inputs.subcooling_k < 0:
        raise ValueError("過熱度與過冷度不可為負值。")
    if not 0 < inputs.isentropic_efficiency <= 1:
        raise ValueError("壓縮機等熵效率必須介於 0–100%。")
    if inputs.refrigeration_capacity_w is not None and inputs.refrigeration_capacity_w <= 0:
        raise ValueError("冷凍能力必須大於 0。")


def solve_vapor_compression_cycle(
    provider: ThermodynamicStateProvider, inputs: VaporCompressionInputs
) -> VaporCompressionResult:
    """求解單級蒸氣壓縮循環。

參數：
    provider: canonical SI 狀態服務。
    inputs: 循環設計條件。

回傳：
    循環結果。

引發：
    ValueError：條件不合理或任何狀態點無法計算時。"""
    _validate(inputs)
    fluid = inputs.fluid.strip()
    policy = inputs.reference_state

    def state(known: list[tuple[str, float]], description: str):
        """查詢一個狀態點。

參數：
    known: SI 已知性質。
    description: 錯誤訊息用說明。

回傳：
    狀態 dict。"""
        return query_state(provider, fluid, known, policy, description)

    evap_dew = state([("T", inputs.evaporating_temperature_k), ("Q", 1.0)], "蒸發飽和狀態")
    cond_bubble = state([("T", inputs.condensing_temperature_k), ("Q", 0.0)], "冷凝飽和狀態")
    p_evap = float(evap_dew["P"])
    p_cond = float(cond_bubble["P"])

    if inputs.superheat_k > 0:
        s1 = state([("P", p_evap), ("T", float(evap_dew["T"]) + inputs.superheat_k)], "壓縮機入口")
    else:
        s1 = evap_dew
    s2s = state([("P", p_cond), ("S", float(s1["S"]))], "等熵壓縮出口")
    h1 = float(s1["H"])
    h2 = h1 + (float(s2s["H"]) - h1) / inputs.isentropic_efficiency
    s2 = state([("P", p_cond), ("H", h2)], "壓縮機出口")
    if inputs.subcooling_k > 0:
        s3 = state([("P", p_cond), ("T", float(cond_bubble["T"]) - inputs.subcooling_k)], "冷凝器出口")
    else:
        s3 = cond_bubble
    h3 = float(s3["H"])
    s4 = state([("P", p_evap), ("H", h3)], "蒸發器入口")

    states = {
        "1": CycleState.from_mapping("1", "壓縮機入口", s1),
        "2s": CycleState.from_mapping("2s", "等熵壓縮出口", s2s),
        "2": CycleState.from_mapping("2", "壓縮機出口", s2),
        "3": CycleState.from_mapping("3", "冷凝器出口", s3),
        "4": CycleState.from_mapping("4", "蒸發器入口", s4),
    }
    refrigerating_effect = h1 - h3
    compressor_work = h2 - h1
    heat_rejection = h2 - h3
    if refrigerating_effect <= 0 or compressor_work <= 0:
        raise ValueError("此條件無法形成有效的冷凍循環，請確認溫度與過熱／過冷設定。")

    system: dict[str, float] = {}
    if inputs.refrigeration_capacity_w is not None:
        mass_flow = inputs.refrigeration_capacity_w / refrigerating_effect
        system = {
            "mass_flow_kg_s": mass_flow,
            "refrigeration_capacity_w": inputs.refrigeration_capacity_w,
            "compressor_power_w": mass_flow * compressor_work,
            "heat_rejection_w": mass_flow * heat_rejection,
            "suction_volume_flow_m3_s": mass_flow / states["1"].density_kg_m3,
        }
    return VaporCompressionResult(
        fluid=fluid,
        states=states,
        evaporating_pressure_pa=p_evap,
        condensing_pressure_pa=p_cond,
        refrigerating_effect_j_kg=refrigerating_effect,
        compressor_work_j_kg=compressor_work,
        heat_rejection_j_kg=heat_rejection,
        cop_cooling=refrigerating_effect / compressor_work,
        cop_heating=heat_rejection / compressor_work,
        pressure_ratio=p_cond / p_evap,
        reference_state=normalize_reference_state_policy(policy),
        **system,
    )
