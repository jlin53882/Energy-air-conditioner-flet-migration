"""批次計算與比較的 application service：參數掃描、冷媒比較與單因子敏感度。

把 ``RefrigerationService`` 的冷凍循環與冷凝器 Exergy 計算包裝成批次引擎
（``domain/batch.py``）使用的「輸入 dict → 指標 dict」函式。指標只取結構化結果中
與 reference state 無關的量（COP、壓縮比、焓差、溫度、壓力、功率、Exergy 平衡），
不取絕對焓或絕對熵；因此批次計算一律以各流體的預設 policy（Auto）求解，
不提供 Reference State 選單。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from domain.batch import (
    BatchResult,
    InputValue,
    Perturbation,
    SensitivityResult,
    SweepAxis,
    run_sensitivity,
    run_sweep,
)

from .models import CondenserExergyRequest, RefrigerationCycleRequest
from .refrigeration import RefrigerationService

TARGET_CYCLE = "cycle"
TARGET_CONDENSER_EXERGY = "condenser_exergy"
FLUID_VARIABLE = "fluid"


@dataclass(frozen=True)
class BatchVariable:
    """可掃描的輸入：request 欄位名稱、顯示名稱、簡短符號與 UnitConverter 性質代碼。

    ``symbol`` 只含 ASCII 等非中文字元，用於數值欄位中標示位置；``delta_prop_code`` 是
    敏感度變動量使用的性質代碼（例如溫度用 DeltaT）。"""

    key: str
    label: str
    symbol: str
    prop_code: str
    delta_prop_code: str


@dataclass(frozen=True)
class BatchMetric:
    """可比較的輸出指標；``prop_code`` 為 None 表示無因次（例如 COP）。

    ``requires`` 列出這個指標需要的 request 欄位：這些欄位必須有值（例如系統量需要冷凍能力），
    指標才適用。一次批次只能選擇對基準條件（含掃描變數）適用的指標，因此每個成功的點都一定
    帶有所選指標。"""

    key: str
    label: str
    prop_code: str | None = None
    requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class BatchTarget:
    """一個可批次執行的計算：可掃描的輸入與可比較的指標。"""

    key: str
    label: str
    variables: tuple[BatchVariable, ...]
    metrics: tuple[BatchMetric, ...]

    def variable(self, key: str) -> BatchVariable:
        """依 request 欄位名稱取得輸入定義。

參數：
    key: 欄位名稱。

回傳：
    BatchVariable。

引發：
    ValueError：不是此計算可掃描的輸入時。"""
        for variable in self.variables:
            if variable.key == key:
                return variable
        raise ValueError(f"「{self.label}」沒有可掃描的輸入：{key}")

    def available_metrics(self, inputs: Mapping[str, InputValue]) -> tuple[BatchMetric, ...]:
        """回傳在這組輸入下適用的指標（``requires`` 的欄位都有值）。

參數：
    inputs: 輸入 dict（缺少的欄位或值為 None 視為未提供）。

回傳：
    BatchMetric tuple，依宣告順序。"""
        return tuple(metric for metric in self.metrics
                     if all(inputs.get(name) is not None for name in metric.requires))

    def metric(self, key: str) -> BatchMetric:
        """依指標名稱取得指標定義。

參數：
    key: 指標名稱。

回傳：
    BatchMetric。

引發：
    ValueError：不是此計算的指標時。"""
        for metric in self.metrics:
            if metric.key == key:
                return metric
        raise ValueError(f"「{self.label}」沒有指標：{key}")


# 冷凍循環的系統量（功率、流量）需要冷凍能力；未提供時只有單位質量結果。
SYSTEM = ("refrigeration_capacity_w",)

CYCLE_TARGET = BatchTarget(
    TARGET_CYCLE,
    "蒸氣壓縮冷凍循環",
    variables=(
        BatchVariable("evaporating_temperature_k", "蒸發溫度", "T_e", "T", "DeltaT"),
        BatchVariable("condensing_temperature_k", "冷凝溫度", "T_c", "T", "DeltaT"),
        BatchVariable("superheat_k", "過熱度", "SH", "DeltaT", "DeltaT"),
        BatchVariable("subcooling_k", "過冷度", "SC", "DeltaT", "DeltaT"),
        BatchVariable("isentropic_efficiency", "壓縮機等熵效率", "eta_isen", "Eff", "Eff"),
        BatchVariable("refrigeration_capacity_w", "冷凍能力", "Q_L", "Power", "Power"),
    ),
    metrics=(
        BatchMetric("cop_cooling", "冷房 COP"),
        BatchMetric("cop_heating", "暖房 COP（熱泵）"),
        BatchMetric("pressure_ratio", "壓縮比"),
        BatchMetric("discharge_temperature_k", "排氣溫度", "T"),
        BatchMetric("refrigerating_effect_j_kg", "冷凍效果 q_L", "H"),
        BatchMetric("compressor_work_j_kg", "壓縮功 w", "H"),
        BatchMetric("heat_rejection_j_kg", "冷凝放熱 q_H", "H"),
        BatchMetric("compressor_power_w", "壓縮機功率", "Power", SYSTEM),
        BatchMetric("heat_rejection_w", "冷凝器放熱量", "Power", SYSTEM),
        BatchMetric("mass_flow_kg_s", "冷媒質量流率", "MassFlow", SYSTEM),
        BatchMetric("suction_volume_flow_m3_s", "吸入體積流量", "VolumeFlow", SYSTEM),
        BatchMetric("evaporating_pressure_pa", "蒸發壓力（絕對）", "P"),
        BatchMetric("condensing_pressure_pa", "冷凝壓力（絕對）", "P"),
    ),
)

CONDENSER_EXERGY_TARGET = BatchTarget(
    TARGET_CONDENSER_EXERGY,
    "冷凝器 Exergy 分析",
    variables=(
        BatchVariable("pressure_pa", "冷凝壓力（絕對）", "P", "P", "P"),
        BatchVariable("inlet_temperature_k", "冷媒入口溫度", "T_in", "T", "DeltaT"),
        BatchVariable("outlet_temperature_k", "冷媒出口溫度", "T_out", "T", "DeltaT"),
        BatchVariable("mass_flow_kg_s", "冷媒質量流率", "m", "MassFlow", "MassFlow"),
        BatchVariable("dead_state_temperature_k", "死狀態（環境）溫度 T0", "T0", "T", "DeltaT"),
        BatchVariable("boundary_temperature_k", "等效傳熱邊界溫度 T_b", "T_b", "T", "DeltaT"),
    ),
    metrics=(
        BatchMetric("exergy_efficiency", "Exergy 效率 η", "Eff"),
        BatchMetric("exergy_destruction_w", "Exergy 破壞率", "Power"),
        BatchMetric("heat_rejection_w", "放熱量 Q_H", "Power"),
        BatchMetric("exergy_decrease_w", "冷媒 Exergy 減少量", "Power"),
        BatchMetric("heat_exergy_w", "熱帶走的 Exergy", "Power"),
        BatchMetric("entropy_generation_w_k", "熵產生率", "EntropyFlow"),
        BatchMetric("mean_heat_rejection_temperature_k", "冷媒平均放熱溫度", "T"),
    ),
)

TARGETS = {target.key: target for target in (CYCLE_TARGET, CONDENSER_EXERGY_TARGET)}


def batch_target(key: str) -> BatchTarget:
    """依代碼取得批次計算對象。

參數：
    key: ``cycle`` 或 ``condenser_exergy``。

回傳：
    BatchTarget。

引發：
    ValueError：代碼不支援時。"""
    try:
        return TARGETS[key]
    except KeyError:
        raise ValueError(f"不支援的批次計算：{key}") from None


BaseRequest = RefrigerationCycleRequest | CondenserExergyRequest


@dataclass(frozen=True)
class SweepAxisRequest:
    """一個掃描軸：輸入欄位名稱（或 ``fluid``）與依序計算的 SI 數值（或冷媒名稱）。"""

    variable: str
    values: tuple[InputValue, ...]


@dataclass(frozen=True)
class ParameterSweepRequest:
    """參數掃描：在基準條件上掃描一或兩個輸入，比較指定指標。

    ``boundary_at_dead_state`` 只用於冷凝器 Exergy：分析邊界涵蓋到整體排熱至環境時
    T_b 恆等於 T0，每一點都以該點的 T0 作為 T_b（此時 T_b 不能單獨掃描）。"""

    base: BaseRequest
    axes: tuple[SweepAxisRequest, ...]
    metric: str
    boundary_at_dead_state: bool = False


@dataclass(frozen=True)
class RefrigerantComparisonRequest:
    """冷媒比較：同一組冷凍循環條件換不同冷媒；可另掃描一個輸入（每個冷媒一條曲線）。"""

    base: RefrigerationCycleRequest
    fluids: tuple[str, ...]
    metric: str
    axis: SweepAxisRequest | None = None


@dataclass(frozen=True)
class SensitivityRequest:
    """單因子敏感度：每個輸入各自在基準值上下變動 delta（SI），比較指定指標。"""

    base: BaseRequest
    perturbations: tuple[tuple[str, float], ...]
    metric: str
    boundary_at_dead_state: bool = False


@dataclass(frozen=True)
class SweepOutcome:
    """批次掃描結果、計算對象與所選指標（每個成功的點都帶有這個指標）。"""

    target: BatchTarget
    result: BatchResult
    metric: BatchMetric


@dataclass(frozen=True)
class SensitivityOutcome:
    """敏感度結果、計算對象與所選指標。"""

    target: BatchTarget
    result: SensitivityResult
    metric: BatchMetric


class BatchService:
    """以既有 RefrigerationService 執行批次計算；只讀取結構化結果，不解析顯示文字。"""

    def __init__(self, refrigeration: RefrigerationService) -> None:
        """以冷凍 application service 初始化。

參數：
    refrigeration: RefrigerationService。

回傳：
    無。"""
        self.refrigeration = refrigeration

    # ======================================================
    # 單點計算
    # ======================================================
    @staticmethod
    def target_for(base: BaseRequest) -> BatchTarget:
        """依基準 request 型別決定計算對象。

參數：
    base: 基準 request。

回傳：
    BatchTarget。

引發：
    TypeError：request 型別不支援時。"""
        if isinstance(base, RefrigerationCycleRequest):
            return CYCLE_TARGET
        if isinstance(base, CondenserExergyRequest):
            return CONDENSER_EXERGY_TARGET
        raise TypeError(f"不支援的批次基準 request：{type(base).__name__}")

    @staticmethod
    def _base_inputs(base: BaseRequest, boundary_at_dead_state: bool = False) -> dict[str, InputValue]:
        """把基準 request 轉為輸入 dict（含冷媒；reference state 一律 Auto）。

參數：
    base: 基準 request。
    boundary_at_dead_state: T_b 是否隨 T0；是時 T_b 不列為輸入（不能單獨變動）。

回傳：
    {欄位名稱: 值}；未提供的選填欄位為 None。"""
        target = BatchService.target_for(base)
        inputs: dict[str, InputValue] = {FLUID_VARIABLE: base.fluid}
        for variable in target.variables:
            if boundary_at_dead_state and variable.key == "boundary_temperature_k":
                continue
            # 選填欄位（例如冷凍能力）未提供時保留為 None：仍可作為掃描變數，但不能作為敏感度變數，
            # 需要它的指標也不適用（見 BatchTarget.available_metrics）。
            inputs[variable.key] = getattr(base, variable.key)
        return inputs

    def _evaluator(self, base: BaseRequest, boundary_at_dead_state: bool = False):
        """建立「輸入 dict → 指標 dict」的計算函式。

參數：
    base: 基準 request（決定計算對象與未掃描欄位）。
    boundary_at_dead_state: 冷凝器 Exergy 的 T_b 是否隨每一點的 T0。

回傳：
    計算函式。

引發：
    ValueError：冷凍循環要求 T_b 隨 T0 時。"""
        target = self.target_for(base)
        if boundary_at_dead_state and target is not CONDENSER_EXERGY_TARGET:
            raise ValueError("只有冷凝器 Exergy 分析有等效傳熱邊界溫度。")

        def evaluate(inputs: Mapping[str, InputValue]) -> dict[str, float]:
            """以輸入 dict 覆寫基準 request 後計算。

參數：
    inputs: 完整輸入。

回傳：
    {指標名稱: SI 數值}。"""
            # 指標與 reference state 無關，一律以各流體的預設 policy 求解。
            request = replace(base, reference_state=None, **dict(inputs))
            if boundary_at_dead_state:
                request = replace(request, boundary_temperature_k=request.dead_state_temperature_k)
            values = self._cycle_metrics(request) if target is CYCLE_TARGET else self._condenser_metrics(request)
            # 只回傳這一點適用的指標，因此每個成功的點都帶有全部適用指標的數值。
            metrics = {metric.key: values[metric.key] for metric in target.available_metrics(inputs)}
            missing = [key for key, value in metrics.items() if value is None]
            if missing:
                # 適用的指標沒有值是程式錯誤（宣告的 requires 與求解結果不一致），不是單點計算失敗。
                raise RuntimeError(f"適用的批次指標沒有數值：{', '.join(missing)}")
            return metrics

        return evaluate

    def _cycle_metrics(self, request: RefrigerationCycleRequest) -> dict[str, float | None]:
        """求解冷凍循環並取出與 reference state 無關的指標。

參數：
    request: 冷凍循環 request。

回傳：
    {指標名稱: SI 數值或 None}；未提供冷凍能力時系統量為 None。"""
        result = self.refrigeration.solve_cycle(request)
        metrics = {
            "cop_cooling": result.cop_cooling,
            "cop_heating": result.cop_heating,
            "pressure_ratio": result.pressure_ratio,
            "discharge_temperature_k": result.states["2"].temperature_k,
            "refrigerating_effect_j_kg": result.refrigerating_effect_j_kg,
            "compressor_work_j_kg": result.compressor_work_j_kg,
            "heat_rejection_j_kg": result.heat_rejection_j_kg,
            "evaporating_pressure_pa": result.evaporating_pressure_pa,
            "condensing_pressure_pa": result.condensing_pressure_pa,
        }
        # 系統量只在提供冷凍能力時有值；是否適用由 BatchTarget.available_metrics 決定。
        metrics.update({
            "compressor_power_w": result.compressor_power_w,
            "heat_rejection_w": result.heat_rejection_w,
            "mass_flow_kg_s": result.mass_flow_kg_s,
            "suction_volume_flow_m3_s": result.suction_volume_flow_m3_s,
        })
        return metrics

    def _condenser_metrics(self, request: CondenserExergyRequest) -> dict[str, float]:
        """分析冷凝器 Exergy 並取出平衡量。

參數：
    request: 冷凝器 Exergy request。

回傳：
    {指標名稱: SI 數值}。"""
        balance = self.refrigeration.analyze_condenser_exergy(request).balance
        return {
            "exergy_efficiency": balance.exergy_efficiency,
            "exergy_destruction_w": balance.exergy_destruction_w,
            "heat_rejection_w": balance.heat_rejection_w,
            "exergy_decrease_w": balance.exergy_decrease_w,
            "heat_exergy_w": balance.heat_exergy_w,
            "entropy_generation_w_k": balance.entropy_generation_w_k,
            "mean_heat_rejection_temperature_k": balance.mean_heat_rejection_temperature_k,
        }

    # ======================================================
    # 批次
    # ======================================================
    @staticmethod
    def _check_metric(target: BatchTarget, base_inputs: Mapping[str, InputValue], swept: tuple[str, ...],
                      metric_key: str) -> BatchMetric:
        """確認指標對基準條件（含掃描變數）適用。

參數：
    target: 計算對象。
    base_inputs: 基準輸入 dict。
    swept: 掃描或變動的輸入欄位名稱（這些欄位在每一點都有數值）。
    metric_key: 指標名稱。

回傳：
    BatchMetric。

引發：
    ValueError：不是此計算的指標，或指標需要的輸入未提供時。"""
        metric = target.metric(metric_key)
        inputs = {**base_inputs, **{name: 0.0 for name in swept}}
        if metric not in target.available_metrics(inputs):
            missing = "、".join(target.variable(name).label for name in metric.requires if inputs.get(name) is None)
            raise ValueError(f"「{metric.label}」需要提供{missing}。")
        return metric

    @staticmethod
    def _check_variable(target: BatchTarget, variable: str, boundary_at_dead_state: bool) -> None:
        """確認輸入可以單獨變動。

參數：
    target: 計算對象。
    variable: 輸入欄位名稱。
    boundary_at_dead_state: T_b 是否隨 T0。

回傳：
    無。

引發：
    ValueError：不是此計算的輸入，或 T_b 隨 T0 時要求單獨變動 T_b。"""
        target.variable(variable)
        if boundary_at_dead_state and variable == "boundary_temperature_k":
            raise ValueError("等效傳熱邊界溫度等於 T0（整體排熱至環境）時，T_b 會隨 T0 變化，不能單獨變動。")

    def sweep(self, request: ParameterSweepRequest) -> SweepOutcome:
        """參數掃描：一或兩個輸入的所有組合。

參數：
    request: 參數掃描 request。

回傳：
    SweepOutcome（第一軸為曲線橫軸，第二軸每個數值一條曲線）。

引發：
    ValueError：掃描變數不是此計算可掃描的輸入，或引擎驗證失敗時。"""
        target = self.target_for(request.base)
        for axis in request.axes:
            self._check_variable(target, axis.variable, request.boundary_at_dead_state)
        follows = request.boundary_at_dead_state
        base_inputs = self._base_inputs(request.base, follows)
        metric = self._check_metric(target, base_inputs, tuple(axis.variable for axis in request.axes), request.metric)
        axes = [SweepAxis(axis.variable, axis.values) for axis in request.axes]
        return SweepOutcome(target, run_sweep(self._evaluator(request.base, follows), base_inputs, axes), metric)

    def compare_refrigerants(self, request: RefrigerantComparisonRequest) -> SweepOutcome:
        """冷媒比較：冷媒為一個類別維度；另有掃描軸時，每個冷媒沿該軸一條曲線。

參數：
    request: 冷媒比較 request。

回傳：
    SweepOutcome；有掃描軸時軸為 (掃描軸, 冷媒)，否則為 (冷媒,)。

引發：
    ValueError：冷媒少於兩種、名稱空白或重複、掃描變數不合法時。"""
        fluids = tuple(fluid.strip() for fluid in request.fluids)
        if any(not fluid for fluid in fluids):
            raise ValueError("冷媒名稱不可空白。")
        if len(fluids) < 2:
            raise ValueError("冷媒比較至少需要兩種冷媒。")
        fluid_axis = SweepAxis(FLUID_VARIABLE, fluids)
        axes = [fluid_axis]
        swept: tuple[str, ...] = ()
        if request.axis is not None:
            CYCLE_TARGET.variable(request.axis.variable)
            axes = [SweepAxis(request.axis.variable, request.axis.values), fluid_axis]
            swept = (request.axis.variable,)
        base_inputs = self._base_inputs(request.base)
        metric = self._check_metric(CYCLE_TARGET, base_inputs, swept, request.metric)
        return SweepOutcome(CYCLE_TARGET, run_sweep(self._evaluator(request.base), base_inputs, axes), metric)

    def sensitivity(self, request: SensitivityRequest) -> SensitivityOutcome:
        """單因子敏感度（龍捲風圖）。

參數：
    request: 敏感度 request。

回傳：
    SensitivityOutcome；列依指標變化幅度由大到小排列。

引發：
    ValueError：輸入或指標不是此計算所有、變動量不合理，或基準條件無法計算時。"""
        target = self.target_for(request.base)
        perturbations = []
        for variable, delta in request.perturbations:
            self._check_variable(target, variable, request.boundary_at_dead_state)
            perturbations.append(Perturbation(variable, delta))
        follows = request.boundary_at_dead_state
        base_inputs = self._base_inputs(request.base, follows)
        # 變動只在基準值附近加減，需要的輸入是否提供由基準條件決定。
        metric = self._check_metric(target, base_inputs, (), request.metric)
        return SensitivityOutcome(target, run_sensitivity(
            self._evaluator(request.base, follows), base_inputs, perturbations, request.metric), metric)
