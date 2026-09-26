"""批次計算與比較：domain 引擎、application service 與「批次與比較」頁。"""

from __future__ import annotations

import warnings

import matplotlib.pyplot as plt
import pytest
from matplotlib import font_manager

from application.batch import (
    CONDENSER_EXERGY_TARGET,
    CYCLE_TARGET,
    BatchService,
    ParameterSweepRequest,
    RefrigerantComparisonRequest,
    SensitivityRequest,
    SweepAxisRequest,
)
from application.models import CondenserExergyRequest, RefrigerationCycleRequest
from application.refrigeration import RefrigerationService
from domain.batch import (
    MAX_AXIS_POINTS,
    MAX_TOTAL_POINTS,
    Perturbation,
    SweepAxis,
    linear_values,
    run_sensitivity,
    run_sweep,
)
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units import CanonicalUnitConverter
from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui.analysis_presentation import ANALYSIS_PRESENTATION
from Flet_ui.ui.components.figure_panel import CJK_FONT_CANDIDATES, use_cjk_fallback_fonts
from Flet_ui.ui.navigation import ROUTES

C = 273.15
# CoolProp 在不同 reference-state 交易之間的結果可能不是逐位元相同（見 docs/state-invalidation.md §3.1）；
# 1e-7 遠小於顯示精度。
REL = 1e-7


# ======================================================
# domain 引擎（以純函式測試，不依賴 CoolProp）
# ======================================================
def _linear(inputs) -> dict[str, float]:
    """測試用計算函式：y = 2a + b；a < 0 時視為輸入不合理。

參數：
    inputs: 輸入 dict。

回傳：
    {"y": 數值}。

引發：
    ValueError：a < 0 時。"""
    if inputs["a"] < 0:
        raise ValueError("a 不可為負")
    return {"y": 2 * inputs["a"] + inputs["b"]}


def test_linear_values_include_both_ends_exactly() -> None:
    """等距數值包含兩端，最後一點精確等於終點（避免浮點累積誤差）。

回傳：
    無。"""
    values = linear_values(0.1, 0.7, 7)
    assert len(values) == 7
    assert values[0] == 0.1 and values[-1] == 0.7
    assert values[1] == pytest.approx(0.2)
    assert linear_values(10.0, 0.0, 3) == (10.0, 5.0, 0.0)
    # start + step·(n−1) 在浮點下不一定等於終點（例如 137.28 → 362.32 取 8 點）；終點必須原樣保留。
    assert linear_values(137.28, 362.32, 8)[-1] == 362.32


@pytest.mark.parametrize("start, stop, count", [
    (0.0, 1.0, 1), (0.0, 1.0, MAX_AXIS_POINTS + 1), (0.0, 1.0, 2.5), (0.0, 1.0, True),
    (1.0, 1.0, 5), (0.0, float("inf"), 5), (float("nan"), 1.0, 5),
])
def test_linear_values_reject_invalid_ranges(start, stop, count) -> None:
    """點數超出範圍或不是整數、起終點相同或不是有限數字時明確失敗。

參數：
    start: 起點。
    stop: 終點。
    count: 點數。

回傳：
    無。"""
    with pytest.raises(ValueError):
        linear_values(start, stop, count)


@pytest.mark.parametrize("values", [(), (1.0, 1.0), (float("nan"),), (True,), tuple(range(MAX_AXIS_POINTS + 1))])
def test_sweep_axis_rejects_invalid_values(values) -> None:
    """掃描軸拒絕空白、重複、非有限、布林與超過上限的數值。

參數：
    values: 數值。

回傳：
    無。"""
    with pytest.raises(ValueError):
        SweepAxis("a", values)


def test_sweep_runs_the_cartesian_product_with_first_axis_slowest() -> None:
    """雙軸掃描計算所有組合，第一軸變化最慢；series 依第二軸分組、以第一軸為 x。

回傳：
    無。"""
    result = run_sweep(_linear, {"a": 0.0, "b": 0.0}, [SweepAxis("a", (1.0, 2.0)), SweepAxis("b", (10.0, 20.0))])
    assert [(p.inputs["a"], p.inputs["b"]) for p in result.points] == [(1, 10), (1, 20), (2, 10), (2, 20)]
    assert [p.metrics["y"] for p in result.points] == [12, 22, 14, 24]
    assert result.series("y") == [(10.0, [(1.0, 12.0), (2.0, 14.0)]), (20.0, [(1.0, 22.0), (2.0, 24.0)])]


def test_sweep_keeps_going_after_a_point_fails_and_records_the_reason() -> None:
    """單一點的 ValueError 只使該點失敗（附原因），其餘點照常計算；series 以 None 表示失敗點。

回傳：
    無。"""
    result = run_sweep(_linear, {"a": 0.0, "b": 1.0}, [SweepAxis("a", (-1.0, 0.0, 1.0))])
    assert [p.ok for p in result.points] == [False, True, True]
    assert result.failed[0].error == "a 不可為負"
    assert result.failed[0].inputs == {"a": -1.0, "b": 1.0}
    assert result.series("y") == [(None, [(-1.0, None), (0.0, 1.0), (1.0, 3.0)])]


def test_sweep_does_not_swallow_programming_errors() -> None:
    """ValueError 以外的例外是程式錯誤，直接拋出而不是記成失敗點。

回傳：
    無。"""
    def broken(_inputs):
        """總是引發 KeyError。

參數：
    _inputs: 輸入。

回傳：
    無。"""
        raise KeyError("bug")

    with pytest.raises(KeyError):
        run_sweep(broken, {"a": 0.0}, [SweepAxis("a", (1.0,))])


def test_sweep_rejects_bad_axis_sets() -> None:
    """軸數不合、變數重複、變數不在基準輸入或總點數超過上限時明確失敗。

回傳：
    無。"""
    base = {"a": 0.0, "b": 0.0, "c": 0.0}
    axis = SweepAxis("a", (1.0,))
    with pytest.raises(ValueError, match="1 至 2"):
        run_sweep(_linear, base, [])
    with pytest.raises(ValueError, match="1 至 2"):
        run_sweep(_linear, base, [axis, SweepAxis("b", (1.0,)), SweepAxis("c", (1.0,))])
    with pytest.raises(ValueError, match="不可相同"):
        run_sweep(_linear, base, [axis, SweepAxis("a", (2.0,))])
    with pytest.raises(ValueError, match="未知"):
        run_sweep(_linear, base, [SweepAxis("z", (1.0,))])
    many = tuple(float(i) for i in range(MAX_AXIS_POINTS))
    assert MAX_AXIS_POINTS * MAX_AXIS_POINTS > MAX_TOTAL_POINTS
    with pytest.raises(ValueError, match=str(MAX_TOTAL_POINTS)):
        run_sweep(_linear, base, [SweepAxis("a", many), SweepAxis("b", many)])


def test_sensitivity_ranks_inputs_by_swing_and_keeps_failed_sides() -> None:
    """一次只變動一個輸入；依指標變化幅度排序，失敗的一側記錄原因且不計入幅度。

回傳：
    無。"""
    result = run_sensitivity(_linear, {"a": 0.5, "b": 1.0}, [Perturbation("b", 0.5), Perturbation("a", 1.0)], "y")
    assert result.base_value == 2.0
    assert [row.variable for row in result.rows] == ["a", "b"]
    a_row, b_row = result.rows
    assert not a_row.low.ok and "負" in a_row.low.error
    assert a_row.metric(a_row.high, "y") == 4.0
    assert result.swing(a_row) == 2.0
    assert (b_row.metric(b_row.low, "y"), b_row.metric(b_row.high, "y")) == (1.5, 2.5)
    assert result.swing(b_row) == 0.5
    # 基準值不被變動汙染：每一側只改自己的輸入。
    assert a_row.high.inputs == {"a": 1.5, "b": 1.0}


def test_sensitivity_swing_counts_the_larger_side() -> None:
    """變化幅度取兩側相對基準的較大者：非線性時往下變動的影響可能大於往上。

回傳：
    無。"""
    result = run_sensitivity(lambda inputs: {"y": (inputs["a"] - 2.0) ** 2}, {"a": 1.0}, [Perturbation("a", 1.0)], "y")
    row, = result.rows
    assert (row.metric(row.low, "y"), row.metric(row.high, "y")) == (4.0, 0.0)
    assert result.swing(row) == 3.0


def test_sensitivity_rejects_invalid_requests() -> None:
    """沒有輸入、重複、非數值輸入、變動量不為正、基準點失敗或指標不存在時明確失敗。

回傳：
    無。"""
    base = {"a": 0.5, "b": 1.0, "fluid": "R32"}
    with pytest.raises(ValueError, match="至少"):
        run_sensitivity(_linear, base, [], "y")
    with pytest.raises(ValueError, match="重複"):
        run_sensitivity(_linear, base, [Perturbation("a", 1.0), Perturbation("a", 2.0)], "y")
    with pytest.raises(ValueError, match="數值"):
        run_sensitivity(_linear, base, [Perturbation("fluid", 1.0)], "y")
    for delta in (0.0, -1.0, float("inf")):
        with pytest.raises(ValueError, match="正的有限"):
            Perturbation("a", delta)
    with pytest.raises(ValueError, match="基準條件"):
        run_sensitivity(_linear, {"a": -1.0, "b": 0.0}, [Perturbation("b", 1.0)], "y")
    with pytest.raises(ValueError, match="未知的指標"):
        run_sensitivity(_linear, base, [Perturbation("a", 1.0)], "z")


# ======================================================
# application service（CoolProp）
# ======================================================
@pytest.fixture(scope="module")
def refrigeration() -> RefrigerationService:
    """建立冷凍 application service。

回傳：
    RefrigerationService。"""
    return RefrigerationService(ThermodynamicStateService(CanonicalUnitConverter()))


@pytest.fixture(scope="module")
def batch(refrigeration) -> BatchService:
    """建立批次 application service。

參數：
    refrigeration: 冷凍 application service。

回傳：
    BatchService。"""
    return BatchService(refrigeration)


def _cycle(**overrides) -> RefrigerationCycleRequest:
    """建立冷凍循環基準 request。

參數：
    overrides: 要覆寫的欄位。

回傳：
    RefrigerationCycleRequest。"""
    fields = dict(fluid="R32", evaporating_temperature_k=5 + C, condensing_temperature_k=45 + C,
                  superheat_k=5.0, subcooling_k=5.0, isentropic_efficiency=0.7, refrigeration_capacity_w=10_000.0)
    fields.update(overrides)
    return RefrigerationCycleRequest(**fields)


def _condenser(**overrides) -> CondenserExergyRequest:
    """建立冷凝器 Exergy 基準 request。

參數：
    overrides: 要覆寫的欄位。

回傳：
    CondenserExergyRequest。"""
    fields = dict(fluid="R134a", pressure_pa=1_000_000.0, inlet_temperature_k=60 + C, outlet_temperature_k=35 + C,
                  mass_flow_kg_s=0.05, dead_state_temperature_k=25 + C, boundary_temperature_k=35 + C)
    fields.update(overrides)
    return CondenserExergyRequest(**fields)


def test_cycle_sweep_points_match_single_cycle_solutions(batch, refrigeration) -> None:
    """掃描的每一點與單獨求解同一條件的循環結果一致（引擎只讀結構化結果、不改寫）。

參數：
    batch: 批次服務。
    refrigeration: 冷凍服務。

回傳：
    無。"""
    temperatures = (35 + C, 45 + C, 55 + C)
    outcome = batch.sweep(ParameterSweepRequest(_cycle(), (SweepAxisRequest("condensing_temperature_k", temperatures),)))
    assert outcome.target is CYCLE_TARGET
    for point, tc in zip(outcome.result.points, temperatures):
        single = refrigeration.solve_cycle(_cycle(condensing_temperature_k=tc))
        assert point.metrics["cop_cooling"] == pytest.approx(single.cop_cooling, rel=REL)
        assert point.metrics["discharge_temperature_k"] == pytest.approx(single.states["2"].temperature_k, rel=REL)
        assert point.metrics["compressor_power_w"] == pytest.approx(single.compressor_power_w, rel=REL)
        assert point.metrics["pressure_ratio"] == pytest.approx(single.pressure_ratio, rel=REL)
    cops = [point.metrics["cop_cooling"] for point in outcome.result.points]
    assert cops[0] > cops[1] > cops[2]


def test_cycle_metrics_do_not_depend_on_the_reference_state(batch) -> None:
    """批次指標與 reference state 無關：基準 request 指定 IIR 與 ASHRAE 得到相同指標（一律以 Auto 求解）。

參數：
    batch: 批次服務。

回傳：
    無。"""
    axis = (SweepAxisRequest("evaporating_temperature_k", (0 + C, 10 + C)),)
    iir = batch.sweep(ParameterSweepRequest(_cycle(reference_state="IIR"), axis)).result.points
    ashrae = batch.sweep(ParameterSweepRequest(_cycle(reference_state="ASHRAE"), axis)).result.points
    for left, right in zip(iir, ashrae):
        assert left.metrics == pytest.approx(right.metrics, rel=1e-9)
    assert not {"enthalpy", "entropy"} & {word for key in iir[0].metrics for word in key.split("_")}


def test_batch_always_solves_with_the_fluid_default_reference_state(refrigeration) -> None:
    """批次計算送出的每個 request 都以 Auto（None）求解，不沿用基準 request 的 reference state。

參數：
    refrigeration: 冷凍服務。

回傳：
    無。"""
    class Recorder:
        """記錄 request 後委派真正的冷凍服務。"""

        def __init__(self) -> None:
            """初始化紀錄。

回傳：
    無。"""
            self.requests = []

        def solve_cycle(self, request):
            """記錄並求解循環。

參數：
    request: 循環 request。

回傳：
    VaporCompressionResult。"""
            self.requests.append(request)
            return refrigeration.solve_cycle(request)

        def analyze_condenser_exergy(self, request):
            """記錄並分析冷凝器。

參數：
    request: 冷凝器 request。

回傳：
    CondenserExergyResult。"""
            self.requests.append(request)
            return refrigeration.analyze_condenser_exergy(request)

    recorder = Recorder()
    service = BatchService(recorder)
    service.sweep(ParameterSweepRequest(_cycle(reference_state="IIR"), (SweepAxisRequest("superheat_k", (1.0, 2.0)),)))
    service.sensitivity(SensitivityRequest(_condenser(reference_state="NBP"), (("mass_flow_kg_s", 0.01),),
                                           "exergy_efficiency"))
    assert len(recorder.requests) == 5
    assert {request.reference_state for request in recorder.requests} == {None}


def test_two_variable_sweep_records_infeasible_points(batch) -> None:
    """雙變數掃描：冷凝溫度不高於蒸發溫度的組合記錄為失敗點，其餘照常計算。

參數：
    batch: 批次服務。

回傳：
    無。"""
    outcome = batch.sweep(ParameterSweepRequest(_cycle(), (
        SweepAxisRequest("condensing_temperature_k", (30 + C, 40 + C)),
        SweepAxisRequest("evaporating_temperature_k", (0 + C, 35 + C)),
    )))
    points = outcome.result.points
    assert [p.ok for p in points] == [True, False, True, True]
    assert "冷凝溫度必須高於蒸發溫度" in points[1].error
    series = dict(outcome.result.series("cop_cooling"))
    assert series[35 + C][0] == (30 + C, None)
    assert series[35 + C][1][1] > series[0 + C][1][1]


def test_sweep_rejects_variables_the_target_does_not_have(batch) -> None:
    """掃描變數必須是該計算可掃描的輸入。

參數：
    batch: 批次服務。

回傳：
    無。"""
    with pytest.raises(ValueError, match="沒有可掃描的輸入"):
        batch.sweep(ParameterSweepRequest(_cycle(), (SweepAxisRequest("pressure_pa", (1e6, 2e6)),)))
    with pytest.raises(ValueError, match="沒有可掃描的輸入"):
        batch.sweep(ParameterSweepRequest(_condenser(), (SweepAxisRequest("superheat_k", (1.0, 2.0)),)))


def test_condenser_sweep_matches_single_analysis(batch, refrigeration) -> None:
    """冷凝器 Exergy 掃描的每一點與單獨分析一致。

參數：
    batch: 批次服務。
    refrigeration: 冷凍服務。

回傳：
    無。"""
    t0s = (15 + C, 25 + C)
    outcome = batch.sweep(ParameterSweepRequest(_condenser(), (SweepAxisRequest("dead_state_temperature_k", t0s),)))
    assert outcome.target is CONDENSER_EXERGY_TARGET
    for point, t0 in zip(outcome.result.points, t0s):
        balance = refrigeration.analyze_condenser_exergy(_condenser(dead_state_temperature_k=t0)).balance
        assert point.metrics["exergy_efficiency"] == pytest.approx(balance.exergy_efficiency, rel=REL)
        assert point.metrics["exergy_destruction_w"] == pytest.approx(balance.exergy_destruction_w, rel=REL)


def test_condenser_boundary_can_follow_the_dead_state(batch, refrigeration) -> None:
    """T_b = T0（整體排熱至環境）時，每一點以該點的 T0 作為 T_b；此時不能單獨掃描 T_b。

參數：
    batch: 批次服務。
    refrigeration: 冷凍服務。

回傳：
    無。"""
    t0s = (15 + C, 25 + C)
    outcome = batch.sweep(ParameterSweepRequest(
        _condenser(boundary_temperature_k=99 + C), (SweepAxisRequest("dead_state_temperature_k", t0s),),
        boundary_at_dead_state=True))
    for point, t0 in zip(outcome.result.points, t0s):
        balance = refrigeration.analyze_condenser_exergy(
            _condenser(dead_state_temperature_k=t0, boundary_temperature_k=t0)).balance
        assert point.metrics["exergy_destruction_w"] == pytest.approx(balance.exergy_destruction_w, rel=REL)
        assert point.metrics["exergy_efficiency"] == pytest.approx(0.0, abs=1e-12)
        assert "boundary_temperature_k" not in point.inputs
    with pytest.raises(ValueError, match="T_b 會隨 T0"):
        batch.sweep(ParameterSweepRequest(_condenser(), (SweepAxisRequest("boundary_temperature_k", (300.0, 310.0)),),
                                          boundary_at_dead_state=True))
    with pytest.raises(ValueError, match="T_b 會隨 T0"):
        batch.sensitivity(SensitivityRequest(_condenser(), (("boundary_temperature_k", 2.0),), "exergy_efficiency",
                                             boundary_at_dead_state=True))
    with pytest.raises(ValueError, match="只有冷凝器"):
        batch.sweep(ParameterSweepRequest(_cycle(), (SweepAxisRequest("superheat_k", (1.0, 2.0)),),
                                          boundary_at_dead_state=True))


def test_refrigerant_comparison_uses_each_fluid_with_the_same_conditions(batch, refrigeration) -> None:
    """冷媒比較：每種冷媒以相同條件求解；有掃描軸時每種冷媒一條曲線。

參數：
    batch: 批次服務。
    refrigeration: 冷凍服務。

回傳：
    無。"""
    fluids = ("R32", "R134a", "R290")
    outcome = batch.compare_refrigerants(RefrigerantComparisonRequest(_cycle(), fluids))
    assert [point.inputs["fluid"] for point in outcome.result.points] == list(fluids)
    for point in outcome.result.points:
        single = refrigeration.solve_cycle(_cycle(fluid=point.inputs["fluid"]))
        assert point.metrics["cop_cooling"] == pytest.approx(single.cop_cooling, rel=REL)
    curves = batch.compare_refrigerants(RefrigerantComparisonRequest(
        _cycle(), fluids, SweepAxisRequest("condensing_temperature_k", (40 + C, 50 + C))))
    assert [group for group, _ in curves.result.series("cop_cooling")] == list(fluids)


@pytest.mark.parametrize("fluids, message", [(("R32",), "至少需要兩種"), (("R32", " "), "不可空白"),
                                             (("R32", "R32"), "不可重複")])
def test_refrigerant_comparison_rejects_invalid_fluid_lists(batch, fluids, message) -> None:
    """冷媒比較至少兩種、不可空白或重複。

參數：
    batch: 批次服務。
    fluids: 冷媒清單。
    message: 預期錯誤訊息片段。

回傳：
    無。"""
    with pytest.raises(ValueError, match=message):
        batch.compare_refrigerants(RefrigerantComparisonRequest(_cycle(), fluids))


def test_unknown_refrigerant_fails_only_its_own_points(batch) -> None:
    """無法計算的冷媒只使自己的點失敗。

參數：
    batch: 批次服務。

回傳：
    無。"""
    outcome = batch.compare_refrigerants(RefrigerantComparisonRequest(_cycle(), ("R32", "NotAFluid")))
    first, second = outcome.result.points
    assert first.ok and not second.ok and second.error


def test_cycle_sensitivity_ranks_known_drivers(batch, refrigeration) -> None:
    """冷房 COP 對冷凝溫度與蒸發溫度的敏感度遠大於過熱度；±Δ 的值與單獨求解一致。

參數：
    batch: 批次服務。
    refrigeration: 冷凍服務。

回傳：
    無。"""
    outcome = batch.sensitivity(SensitivityRequest(
        _cycle(), (("superheat_k", 2.0), ("condensing_temperature_k", 2.0), ("evaporating_temperature_k", 2.0)),
        "cop_cooling"))
    result = outcome.result
    assert [row.variable for row in result.rows][-1] == "superheat_k"
    assert result.base_value == pytest.approx(refrigeration.solve_cycle(_cycle()).cop_cooling)
    tc_row = next(row for row in result.rows if row.variable == "condensing_temperature_k")
    assert tc_row.metric(tc_row.high, "cop_cooling") == pytest.approx(
        refrigeration.solve_cycle(_cycle(condensing_temperature_k=47 + C)).cop_cooling)
    assert tc_row.metric(tc_row.low, "cop_cooling") > result.base_value > tc_row.metric(tc_row.high, "cop_cooling")


def test_sensitivity_rejects_metrics_of_another_target(batch) -> None:
    """敏感度指標必須屬於該計算。

參數：
    batch: 批次服務。

回傳：
    無。"""
    with pytest.raises(ValueError, match="沒有指標"):
        batch.sensitivity(SensitivityRequest(_cycle(), (("superheat_k", 1.0),), "exergy_efficiency"))


def test_targets_declare_units_for_every_variable_and_metric() -> None:
    """每個輸入都有數值與變動量的性質代碼與只含 ASCII 的符號；指標名稱不重複。

回傳：
    無。"""
    for target in (CYCLE_TARGET, CONDENSER_EXERGY_TARGET):
        for variable in target.variables:
            assert variable.prop_code and variable.delta_prop_code
            assert variable.symbol.isascii()
        keys = [metric.key for metric in target.metrics]
        assert len(keys) == len(set(keys))


# ======================================================
# 圖表字型
# ======================================================
def test_cjk_fallback_fonts_follow_the_primary_family() -> None:
    """已安裝的中文字型接在原本的字族之後作為逐字備援；未安裝的不加入；重複呼叫結果相同。

回傳：
    無。"""
    original = list(plt.rcParams["font.family"])
    try:
        plt.rcParams["font.family"] = ["sans-serif"]
        families = use_cjk_fallback_fonts({"Microsoft JhengHei", "Noto Sans CJK TC", "Arial"})
        assert families == ["sans-serif", "Microsoft JhengHei", "Noto Sans CJK TC"]
        assert plt.rcParams["font.family"] == families
        assert use_cjk_fallback_fonts({"Microsoft JhengHei", "Noto Sans CJK TC"}) == families
        assert use_cjk_fallback_fonts(set()) == ["sans-serif"]
    finally:
        plt.rcParams["font.family"] = original


def test_chart_text_renders_chinese_without_missing_glyphs_when_a_cjk_font_is_installed() -> None:
    """有安裝中文字型時，圖表中文字不會出現缺字（方框）警告。

回傳：
    無。"""
    installed = {font.name for font in font_manager.fontManager.ttflist}
    if not set(CJK_FONT_CANDIDATES) & installed:
        pytest.skip("此環境沒有安裝任何候選中文字型")
    use_cjk_fallback_fonts()
    figure = plt.figure()
    figure.add_subplot(111).set_xlabel("冷凝溫度 [°C]")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        figure.canvas.draw()
    plt.close(figure)


# ======================================================
# UI：「批次與比較」頁
# ======================================================
class DummyPage:
    """提供建構完整工作區所需的最小 page 介面。"""

    def __init__(self) -> None:
        """初始化控制項與 overlay 容器。

回傳：
    無。"""
        self.controls = []
        self.overlay = []

    def add(self, *controls) -> None:
        """收集進入點新增的控制項。

參數：
    controls: 要加入頁面的控制項。

回傳：
    無。"""
        self.controls.extend(controls)

    def update(self) -> None:
        """在沒有 Flet session 時接受更新呼叫。

回傳：
    無。"""


@pytest.fixture
def view(isolated_workspace):
    """建構完整工作區並取得「批次與比較」頁（工作區為本測試的暫存資料夾）。

參數：
    isolated_workspace: conftest 提供的暫存工作區。

回傳：
    BatchView。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    shell.navigate("batch")
    yield shell.views["batch"]
    plt.close("all")


def _result(view) -> dict[str, str]:
    """回傳結果文字中的「名稱: 數值」。

參數：
    view: 分析頁。

回傳：
    dict。"""
    lines = [line.split(": ", 1) for line in (view.adapter.result_text or "").splitlines() if ": " in line]
    return {label: value for label, value in lines}


def _select(control, value: str) -> None:
    """模擬使用者在分段按鈕或下拉選單選擇一個值（觸發已綁定的處理器）。

參數：
    control: SegmentedButton 或 Dropdown。
    value: 值。

回傳：
    無。"""
    if hasattr(control, "selected"):
        control.selected = [value]
        control.on_change(None)
    else:
        control.value = value
        control.on_select(None)


def test_batch_route_lists_three_analyses(view) -> None:
    """「批次與比較」位於冷凍系統分區，提供三項分析；每項都有說明。

參數：
    view: 批次頁。

回傳：
    無。"""
    route = next(route for route in ROUTES if route.key == "batch")
    assert route.section == "冷凍系統"
    keys = [key for key, _ in view.adapter.tool_items()]
    assert keys == ["batch.parameter_sweep", "batch.refrigerant_comparison", "batch.sensitivity"]
    assert all(key in ANALYSIS_PRESENTATION for key in keys)


def test_default_sweep_plots_cop_against_condensing_temperature(view) -> None:
    """預設掃描冷凍循環的冷凝溫度 30–60 °C、7 點，輸出冷房 COP 並畫一條曲線。

參數：
    view: 批次頁。

回傳：
    無。"""
    module = view.adapter.modules[0]
    assert module.dropdowns["sw_x"].value == "condensing_temperature_k"
    assert module.all_entries["sw_x_start"]["label_control"].value == "冷凝溫度起點"
    assert not module.all_entries["sw_y_start"]["ui_row"].visible
    view.perform_calculation(None)

    assert view.result_panel.status == "success"
    values = _result(view)
    assert values["計算點數"] == "7 / 7"
    assert values["最大值位置"] == "T_c = 30.0 °C"
    assert values["冷凝溫度 45.0 °C"] == "3.872"
    lines = module.chart_panel.figure.axes[0].get_lines()
    assert len(lines) == 1 and len(lines[0].get_xdata()) == 7
    assert list(lines[0].get_xdata())[0] == pytest.approx(30.0)


def test_second_variable_draws_one_curve_per_value_and_lists_failures(view) -> None:
    """第二變數的每個數值一條曲線；無法計算的點列在最後並附原因，不中斷計算。

參數：
    view: 批次頁。

回傳：
    無。"""
    module = view.adapter.modules[0]
    _select(module.dropdowns["sw_y"], "evaporating_temperature_k")
    assert module.all_entries["sw_y_start"]["ui_row"].visible
    module.all_entries["sw_y_stop"]["val"].value = "50"
    module.text_entries["sw_y_count"]["val"].value = "3"
    view.perform_calculation(None)

    assert view.result_panel.status == "success"
    assert _result(view)["計算點數"] == "16 / 21"
    assert "--- 無法計算的點 ---" in view.adapter.result_text
    assert "冷凝溫度 30.0 °C、蒸發溫度 50.0 °C：冷凝溫度必須高於蒸發溫度。" in view.adapter.result_text
    assert len(module.chart_panel.figure.axes[0].get_lines()) == 3


def test_switching_to_condenser_changes_inputs_metrics_and_invalidates(view) -> None:
    """切換計算對象：顯示冷凝器條件、變數與指標改為冷凝器 Exergy，且屬語意輸入（結果失效）。

參數：
    view: 批次頁。

回傳：
    無。"""
    module = view.adapter.modules[0]
    view.perform_calculation(None)
    _select(module.targets["sw"], "condenser_exergy")

    assert view.result_panel.status != "success"
    assert not module.all_entries["sw_evaporating_temperature_k"]["ui_row"].visible
    assert module.all_entries["sw_pressure_pa"]["ui_row"].visible
    assert module.dropdowns["sw_x"].value == "pressure_pa"
    assert module.dropdowns["sw_metric"].value == "exergy_efficiency"
    assert module.all_entries["sw_x_start"]["unit"].value == "kPa"
    view.perform_calculation(None)
    assert view.result_panel.status == "success"
    assert _result(view)["計算點數"] == "7 / 7"


def test_ambient_boundary_hides_tb_and_removes_it_from_the_variables(view) -> None:
    """T_b = T0 時隱藏 T_b 欄位，且 T_b 不再是可掃描的變數。

參數：
    view: 批次頁。

回傳：
    無。"""
    module = view.adapter.modules[0]
    _select(module.targets["sw"], "condenser_exergy")
    assert module.all_entries["sw_boundary_temperature_k"]["ui_row"].visible
    _select(module.dropdowns["sw_x"], "boundary_temperature_k")
    _select(module.boundaries["sw"], "ambient")

    assert not module.all_entries["sw_boundary_temperature_k"]["ui_row"].visible
    options = [option.key for option in module.dropdowns["sw_x"].options]
    assert "boundary_temperature_k" not in options
    assert module.dropdowns["sw_x"].value == options[0]
    # 隱藏的 T_b 欄位不再是輸入：留空也不影響計算。
    module.all_entries["sw_boundary_temperature_k"]["val"].value = ""
    view.perform_calculation(None)
    assert view.result_panel.status == "success", view.result_panel.message


def test_changing_the_boundary_keeps_a_still_valid_axis_range(view) -> None:
    """切換邊界設定時，仍有效的掃描變數與使用者輸入的範圍不被重設。

參數：
    view: 批次頁。

回傳：
    無。"""
    module = view.adapter.modules[0]
    _select(module.targets["sw"], "condenser_exergy")
    _select(module.dropdowns["sw_x"], "dead_state_temperature_k")
    module.all_entries["sw_x_start"]["val"].value = "12"
    _select(module.boundaries["sw"], "ambient")

    assert module.dropdowns["sw_x"].value == "dead_state_temperature_k"
    assert module.all_entries["sw_x_start"]["val"].value == "12"


def test_invalid_count_is_reported_with_the_field_name(view) -> None:
    """點數不是整數時以欄名提示錯誤。

參數：
    view: 批次頁。

回傳：
    無。"""
    module = view.adapter.modules[0]
    module.text_entries["sw_x_count"]["val"].value = "3.5"
    view.perform_calculation(None)
    assert view.result_panel.status == "error"
    assert "點數" in view.result_panel.message


def test_refrigerant_comparison_draws_bars_per_fluid(view) -> None:
    """冷媒比較（不掃描）：每種冷媒一個數值與一根長條；最大值位置為冷媒名稱。

參數：
    view: 批次頁。

回傳：
    無。"""
    view._handle_tool_change("batch.refrigerant_comparison")
    view.perform_calculation(None)

    module = view.adapter.modules[0]
    values = _result(view)
    assert view.result_panel.status == "success"
    assert set(values) >= {"R32", "R410A", "R134a", "R290"}
    assert values["最大值位置"] == "R134a"
    axes = module.chart_panel.figure.axes[0]
    assert len(axes.patches) == 4
    assert [label.get_text() for label in axes.get_xticklabels()] == ["R32", "R410A", "R134a", "R290"]


def test_refrigerant_comparison_with_a_sweep_draws_one_curve_per_fluid(view) -> None:
    """冷媒比較加掃描變數：每種冷媒一條曲線，圖例為冷媒名稱。

參數：
    view: 批次頁。

回傳：
    無。"""
    view._handle_tool_change("batch.refrigerant_comparison")
    module = view.adapter.modules[0]
    module.text_entries["rc_fluids"]["val"].value = "R32, R290"
    _select(module.dropdowns["rc_x"], "evaporating_temperature_k")
    module.text_entries["rc_x_count"]["val"].value = "3"
    view.perform_calculation(None)

    assert view.result_panel.status == "success"
    assert "--- 冷房 COP（R290） ---" in view.adapter.result_text
    axes = module.chart_panel.figure.axes[0]
    assert [text.get_text() for text in axes.get_legend().get_texts()] == ["R32", "R290"]


def test_sensitivity_ranks_inputs_and_draws_a_tornado(view) -> None:
    """敏感度：預設以冷房 COP 排序，影響最大者在龍捲風圖最上方；變動量 0 的輸入不分析。

參數：
    view: 批次頁。

回傳：
    無。"""
    view._handle_tool_change("batch.sensitivity")
    module = view.adapter.modules[0]
    module.all_entries[module.delta_keys["cycle:refrigeration_capacity_w"]]["val"].value = "0"
    view.perform_calculation(None)

    assert view.result_panel.status == "success"
    values = _result(view)
    assert values["基準值"] == "3.872"
    assert values["影響最大"] == "eta_isen"
    assert "冷凍能力" not in view.adapter.result_text
    axes = module.chart_panel.figure.axes[0]
    labels = [label.get_text() for label in axes.get_yticklabels()]
    assert len(labels) == 5
    assert labels[-1].startswith("壓縮機等熵效率")
    assert labels[0].startswith("過熱度")


def test_sensitivity_rejects_negative_deltas(view) -> None:
    """變動量為負時以欄名提示錯誤。

參數：
    view: 批次頁。

回傳：
    無。"""
    view._handle_tool_change("batch.sensitivity")
    module = view.adapter.modules[0]
    module.all_entries[module.delta_keys["cycle:superheat_k"]]["val"].value = "-1"
    view.perform_calculation(None)
    assert view.result_panel.status == "error"
    assert "過熱度 ±" in view.result_panel.message


def test_temperature_swing_is_reported_as_a_temperature_difference(view) -> None:
    """指標為溫度時，變化幅度以溫差（K）表示，而不是被當成絕對溫度換算成 °C。

參數：
    view: 批次頁。

回傳：
    無。"""
    view._handle_tool_change("batch.sensitivity")
    module = view.adapter.modules[0]
    _select(module.dropdowns["se_metric"], "discharge_temperature_k")
    view.perform_calculation(None)

    swing = _result(view)["最大變化幅度"]
    assert swing.endswith(" K")
    assert 0 < float(swing.split()[0]) < 20


def test_imperial_output_converts_axis_and_metric_units(view) -> None:
    """英制輸出時結果與圖表座標都換成英制單位。

參數：
    view: 批次頁。

回傳：
    無。"""
    view.set_output_unit_system("Imperial")
    view.perform_calculation(None)

    assert _result(view)["冷凝溫度 86.0 °F"] == "6.815"
    axes = view.adapter.modules[0].chart_panel.figure.axes[0]
    assert axes.get_xlabel() == "冷凝溫度 [°F]"
    assert list(axes.get_lines()[0].get_xdata())[0] == pytest.approx(86.0)


def test_condenser_defaults_describe_a_real_condensing_process(view, refrigeration) -> None:
    """冷凝器的預設條件對預設冷媒是真正的冷凝過程：入口高於露點（過熱蒸氣）、出口低於泡點（過冷液體），
    而且預設掃描範圍的兩端也成立。

參數：
    view: 批次頁。
    refrigeration: 冷凍服務。

回傳：
    無。"""
    module = view.adapter.modules[0]
    _select(module.targets["sw"], "condenser_exergy")
    base = module._condenser_request("sw")
    for pressure in (module.read_si("sw_x_start"), base.pressure_pa, module.read_si("sw_x_stop")):
        result = refrigeration.analyze_condenser_exergy(
            CondenserExergyRequest(**{**base.__dict__, "pressure_pa": pressure}))
        assert result.inlet.temperature_k > result.dew_point_k
        assert result.outlet.temperature_k < result.bubble_point_k
