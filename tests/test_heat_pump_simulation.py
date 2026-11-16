"""多元取熱雙效熱泵動態模擬的 domain 測試（使用實際 CoolProp）。

壓縮機為日立 E505DH-49A2W（49 cc 渦卷式，額定 12.9 kW／5.13 kW），以外接變頻器在
30／40／50／60 Hz 階梯運轉；水泵同樣為四段變頻；冷房時熱水桶供除濕後再熱盤管。
情境數值對照 ``docs/simulation-model.md`` §4。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from domain.heat_pump import (
    VALVES_OPEN,
    WARNING_FREEZE_LIMITING,
    WARNING_FREEZE_STOPPED,
    WARNING_HP_LIMITING,
    WARNING_TRIPPED,
    ControlParameters,
    CycleSettings,
    CycleTable,
    FrequencyMode,
    FrequencyStepper,
    HeatPumpParameters,
    HeatPumpSimulation,
    OperatingConditions,
    OperatingPointSolver,
    OperationMode,
    OutdoorHeatExchangerParameters,
    PidController,
    PlateExchanger,
    PumpParameters,
    RefrigerantMode,
    SimulationSettings,
    celsius,
    compressor_performance,
    default_settings,
    gpm_to_kg_s,
    refrigerant_side_resistance,
    summarize,
    volumetric_efficiency,
)
from domain.heat_pump.parameters import (
    CompressorParameters,
    PlateGeometry,
    RefrigerantSideCalibration,
    interpolate_power_law,
    interpolate_table,
)
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter

HOUR = 3600.0
STEPS = (30.0, 40.0, 50.0, 60.0)


@pytest.fixture(scope="module")
def provider() -> ThermodynamicStateService:
    """共用 CoolProp 狀態服務。

回傳：
    ThermodynamicStateService。"""
    return ThermodynamicStateService(CanonicalUnitConverter())


@pytest.fixture(scope="module")
def table(provider: ThermodynamicStateService) -> CycleTable:
    """預設設定（SH 5 K、SC 5 K、壓縮機總效率 0.5683）的完整性質表。

回傳：
    CycleTable。"""
    return CycleTable.build(provider)


_SCENARIOS: dict = {}


def _run(table: CycleTable, operation: OperationMode, fans: set[str], hours: float = 3.0, **overrides):
    """以預設環境執行情境（相同參數的情境只計算一次）。

參數：
    table: 性質表。
    operation: 運轉方式。
    fans: 開啟的送風機。
    hours: 模擬時數。
    overrides: 覆寫的設定欄位。

回傳：
    (模擬器, 記錄, 摘要)。"""
    key = (operation, tuple(sorted(fans)), hours, tuple(sorted(overrides.items(), key=lambda item: item[0])))
    if key not in _SCENARIOS:
        settings = replace(default_settings(operation), fans=frozenset(fans), **overrides)
        sim = HeatPumpSimulation(table, settings=settings)
        records = sim.run(hours * HOUR)
        _SCENARIOS[key] = (sim, records, summarize(records, sim.events))
    return _SCENARIOS[key]


# ---- 單元：參數換算與元件模型 ----


def test_gpm_conversion_matches_spec() -> None:
    """12.06 GPM × 3.785 L/gal ÷ 60 = 0.761 kg/s。

回傳：
    無。"""
    assert gpm_to_kg_s(12.06) == pytest.approx(0.761, abs=5e-4)


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(1.7, 0.9273), (2.0, 0.8986), (2.6, 0.8443), (3.4, 0.7767), (4.1, 0.7208), (5.0, 0.6524)],
)
def test_volumetric_efficiency_follows_clearance_model(ratio: float, expected: float) -> None:
    """餘隙容積模型（C = 0.1498、k = 1.341）與規格 §1.8 表一致。

回傳：
    無。"""
    assert volumetric_efficiency(CompressorParameters(), ratio) == pytest.approx(expected, abs=1e-3)


def test_compressor_defaults_describe_hitachi_scroll() -> None:
    """新壓縮機：日立 E505DH-49A2W、49 cc、階梯 30／40／50／60 Hz。

回傳：
    無。"""
    compressor = CompressorParameters()
    assert compressor.model == "Hitachi E505DH-49A2W"
    assert compressor.displacement_m3 == pytest.approx(49e-6)
    assert compressor.frequency_steps_hz == STEPS
    assert (compressor.min_frequency_hz, compressor.max_frequency_hz) == (30.0, 60.0)
    assert compressor.rated_cooling_w == 12_900.0 and compressor.rated_power_w == 5_130.0


def test_refrigerant_side_resistance_reproduces_design_ua() -> None:
    """R_r 由設計點反推；未錨定的冷凝器在設計水量與水溫下 UA = 13.78 kW ÷ 3.632 K。

回傳：
    無。"""
    geometry = PlateGeometry()
    calibration = RefrigerantSideCalibration()
    resistance = refrigerant_side_resistance(calibration, geometry)
    assert resistance == pytest.approx(3.157e-4, rel=1e-2)
    raw = PlateExchanger(
        replace(HeatPumpParameters().condenser, water=calibration.design_water, anchor_flow_kg_s=None),
        geometry,
        resistance,
    )
    assert raw.ua(calibration.design_water_flow_kg_s) == pytest.approx(13_780.0 / 3.632, rel=1e-6)


def test_plate_exchangers_match_spec_table() -> None:
    """§1.4 的 GPM 對照表：冷凝器錨定 12.06 GPM 時 3.79 kW/K，蒸發器約 1.65 kW/K。

回傳：
    無。"""
    params = HeatPumpParameters()
    resistance = refrigerant_side_resistance(params.refrigerant_side, params.geometry)
    condenser = PlateExchanger(params.condenser, params.geometry, resistance)
    evaporator = PlateExchanger(params.evaporator, params.geometry, resistance)
    flow = gpm_to_kg_s(12.06)
    assert condenser.ua(flow) == pytest.approx(3_794.0, rel=1e-3)
    assert condenser.anchor_scale == pytest.approx(1.121, abs=2e-3)
    assert condenser.conductance(flow) == pytest.approx(2_217.0, rel=5e-3)
    assert evaporator.ua(flow) == pytest.approx(1_650.0, rel=1e-2)
    assert evaporator.conductance(flow) == pytest.approx(1_290.0, rel=1e-2)
    for gpm, cond_ua, evap_ua in ((6.0, 3_220.0, 1_430.0), (20.0, 4_150.0, 1_790.0)):
        assert condenser.ua(gpm_to_kg_s(gpm)) == pytest.approx(cond_ua, rel=1e-2)
        assert evaporator.ua(gpm_to_kg_s(gpm)) == pytest.approx(evap_ua, rel=1e-2)


def test_water_side_coefficient_rejects_non_positive_flow() -> None:
    """水流量必須大於 0。

回傳：
    無。"""
    params = HeatPumpParameters()
    resistance = refrigerant_side_resistance(params.refrigerant_side, params.geometry)
    with pytest.raises(ValueError):
        PlateExchanger(params.condenser, params.geometry, resistance).ua(0.0)


def test_outdoor_heat_exchanger_follows_manufacturer_table() -> None:
    """室外熱交換器（表 2.1.5）：11,348 kcal/hr = 13.2 kW、56.4 CMM、冷媒 57／52 °C、370 kg/hr；
    設計進風溫度為假設值 35 °C。有效熱導 G = 13.2 kW ÷ (54.5 − 35) K = 0.677 kW/K。

回傳：
    無。"""
    outdoor = OutdoorHeatExchangerParameters()
    assert outdoor.rated_capacity_w == pytest.approx(13_198.0, rel=1e-3)
    assert outdoor.refrigerant_flow_kg_s == pytest.approx(0.1028, abs=1e-4)
    assert outdoor.air_capacity_rate_w_k == pytest.approx(1_083.0, rel=1e-2)
    assert outdoor.conductance_w_k == pytest.approx(677.0, rel=1e-2)
    assert outdoor.effectiveness == pytest.approx(0.625, abs=2e-3)
    assert outdoor.ua_w_k == pytest.approx(1_062.0, rel=1e-2)
    assert HeatPumpParameters().outdoor_ua_w_k == pytest.approx(outdoor.conductance_w_k)
    assert replace(outdoor, design_air_inlet_c=32.0).conductance_w_k < outdoor.conductance_w_k


def test_pump_curves_follow_measured_data() -> None:
    """水泵曲線採實測（報告表 8.1.1 與電功率計算）：冰水泵 60 Hz 為 0.62 kg/s（9.83 GPM）、392 W；
    40／50／60 Hz 耗電 241.4／320.7／391.9 W；30 Hz 以冪次外插約 167 W。熱水泵無實測，額定流量沿用設計
    12.06 GPM，曲線形狀與耗電同冰水泵。

回傳：
    無。"""
    params = HeatPumpParameters()
    cold, hot = params.cold_pump, params.hot_pump
    assert cold.frequency_steps_hz == STEPS and hot.frequency_steps_hz == STEPS
    for hz, cold_gpm, hot_gpm, watts in (
        (60.0, 9.83, 12.06, 391.9), (50.0, 8.88, 10.89, 320.7), (40.0, 6.82, 8.36, 241.4), (30.0, 4.76, 5.84, 167.4)
    ):
        assert cold.flow_gpm(hz) == pytest.approx(cold_gpm, abs=0.01)
        assert hot.flow_gpm(hz) == pytest.approx(hot_gpm, abs=0.01)
        assert cold.power_w(hz) == pytest.approx(watts, abs=0.5) == pytest.approx(hot.power_w(hz), abs=0.5)
    assert gpm_to_kg_s(cold.flow_gpm(30.0)) == pytest.approx(0.30, abs=2e-3)
    # 實測耗電隨頻率遠比立方律平緩（指數約 1.1–1.3）。
    assert cold.power_w(40.0) / cold.power_w(60.0) == pytest.approx(0.616, abs=1e-3)
    assert cold.power_w(40.0) > 0.296 * cold.power_w(60.0)


def test_pump_without_curves_falls_back_to_affinity_laws() -> None:
    """沒有流量／耗電曲線時，退回相似定律：流量 ∝ f、耗電 ∝ f³。

回傳：
    無。"""
    pump = PumpParameters(rated_flow_gpm=12.06, rated_power_w=500.0, flow_ratio_by_hz=(), power_w_by_hz=())
    for hz, gpm, watts in ((60.0, 12.06, 500.0), (50.0, 10.05, 289.0), (40.0, 8.04, 148.1), (30.0, 6.03, 62.5)):
        assert pump.flow_gpm(hz) == pytest.approx(gpm, abs=0.01)
        assert pump.power_w(hz) == pytest.approx(watts, abs=0.5)


def test_interpolation_helpers() -> None:
    """分段線性內插夾端點；冪次內插通過資料點並可外插。

回傳：
    無。"""
    table = ((20.0, 1.0), (40.0, 3.0), (60.0, 4.0))
    assert interpolate_table(table, 10.0) == 1.0 and interpolate_table(table, 70.0) == 4.0
    assert interpolate_table(table, 30.0) == pytest.approx(2.0)
    power = ((40.0, 100.0), (50.0, 200.0), (60.0, 400.0))
    assert interpolate_power_law(power, 50.0) == pytest.approx(200.0)
    assert interpolate_power_law(power, 30.0) == pytest.approx(100.0 * 0.75 ** 3.106, rel=1e-3)
    assert interpolate_power_law(power, 70.0) > 400.0


# ---- PID 與階梯量化器 ----


def test_pid_proportional_action_and_clamping() -> None:
    """純比例：輸出 = bias + Kp·e，並夾在上下限內。

回傳：
    無。"""
    pid = PidController(kp=10.0, ti_s=0.0, td_s=0.0, out_min=30.0, out_max=60.0, bias=30.0)
    assert pid.update(1.5, 5.0) == pytest.approx(45.0)
    assert pid.update(-2.0, 5.0) == 30.0
    assert pid.update(9.0, 5.0) == 60.0
    assert pid.update(9.0, 5.0, out_max=50.0) == 50.0


def test_pid_integral_accumulates_and_does_not_wind_up() -> None:
    """積分項在輸出未飽和時累積；輸出已頂到上限時不再累積（抗積分飽和）。

回傳：
    無。"""
    pid = PidController(kp=10.0, ti_s=100.0, td_s=0.0, out_min=30.0, out_max=60.0, bias=30.0)
    pid.update(1.0, 10.0)
    first = pid.integral
    assert first == pytest.approx(10.0 / 100.0 * 1.0 * 10.0)
    for _ in range(50):
        pid.update(5.0, 10.0)
    saturated = pid.integral
    for _ in range(50):
        pid.update(5.0, 10.0)
    assert pid.integral == pytest.approx(saturated)
    assert pid.update(5.0, 10.0) == 60.0


def test_pid_derivative_damps_a_falling_error() -> None:
    """誤差正在下降時，微分項讓輸出低於沒有微分的 PI（提早減速）。

回傳：
    無。"""
    with_d = PidController(kp=10.0, ti_s=0.0, td_s=30.0, out_min=0.0, out_max=100.0, bias=30.0)
    without_d = PidController(kp=10.0, ti_s=0.0, td_s=0.0, out_min=0.0, out_max=100.0, bias=30.0)
    errors = [3.0, 2.9, 2.8, 2.7, 2.6]
    out_with = [with_d.update(e, 5.0) for e in errors]
    out_without = [without_d.update(e, 5.0) for e in errors]
    assert out_with[0] == pytest.approx(out_without[0])
    assert out_with[-1] < out_without[-1]


def test_pid_preset_is_bumpless_and_reset_clears_state() -> None:
    """preset 讓下一次輸出等於指定值；reset 清除積分與微分狀態；dt 必須為正。

回傳：
    無。"""
    pid = PidController(kp=10.0, ti_s=300.0, td_s=30.0, out_min=30.0, out_max=60.0, bias=30.0)
    pid.preset(45.0, 0.5)
    assert pid.output(0.5) == pytest.approx(45.0)
    pid.update(2.0, 5.0)
    pid.reset()
    assert pid.integral == 0.0 and pid.output(0.0) == pytest.approx(30.0)
    with pytest.raises(ValueError):
        pid.update(1.0, 0.0)


def test_stepper_uses_hysteresis_dwell_and_cap() -> None:
    """階梯量化：過中點加遲滯才升階；變階後至少停留 dwell；高於上限立即降階。

回傳：
    無。"""
    stepper = FrequencyStepper(STEPS, hysteresis_hz=2.0, dwell_s=60.0)
    assert stepper.nearest(44.0) == 40.0 and stepper.nearest(46.0) == 50.0
    assert stepper.start(58.0, 60.0, now_s=0.0) == 60.0
    assert stepper.update(33.0, 60.0, now_s=30.0) == 60.0  # 停留時間未到
    assert stepper.update(33.0, 60.0, now_s=61.0) == 50.0  # 一次只降一階
    assert stepper.update(44.0, 60.0, now_s=125.0) == 50.0  # 低於中點 45 但未超過遲滯（43）
    assert stepper.update(42.9, 60.0, now_s=130.0) == 40.0
    assert stepper.update(60.0, 60.0, now_s=200.0) == 50.0  # 升階一次（40 → 50）
    assert stepper.update(60.0, 45.0, now_s=201.0) == 40.0  # 上限 45 Hz：立即降到 40
    assert stepper.cap_step(20.0) == 30.0  # 上限低於最低階時取最低階
    with pytest.raises(ValueError):
        FrequencyStepper(())


# ---- 性質表與壓縮機 ----


def test_cycle_table_interpolation_matches_direct_state_queries(
    table: CycleTable, provider: ThermodynamicStateService
) -> None:
    """網格之間的內插值與直接查詢的差異在 0.1 % 以內。

回傳：
    無。"""
    efficiency = CompressorParameters().overall_efficiency
    te, tc = celsius(5.3), celsius(41.7)
    props = table.properties(te, tc)
    pe = provider.calculate_state_si("R410A", [("T", te), ("Q", 1.0)], "ASHRAE")["P"]
    pc = provider.calculate_state_si("R410A", [("T", tc), ("Q", 0.0)], "ASHRAE")["P"]
    suction = provider.calculate_state_si("R410A", [("T", te + 5.0), ("P", pe)], "ASHRAE")
    liquid = provider.calculate_state_si("R410A", [("T", tc - 5.0), ("P", pc)], "ASHRAE")
    h2s = provider.calculate_state_si("R410A", [("P", pc), ("S", suction["S"])], "ASHRAE")["H"]
    h2 = suction["H"] + (h2s - suction["H"]) / efficiency
    assert table.overall_efficiency == pytest.approx(efficiency)
    assert props.evaporating_pressure_pa == pytest.approx(pe, rel=1e-3)
    assert props.condensing_pressure_pa == pytest.approx(pc, rel=1e-3)
    assert props.suction_density_kg_m3 == pytest.approx(suction["D"], rel=1e-3)
    assert props.discharge_enthalpy_j_kg - props.suction_enthalpy_j_kg == pytest.approx(h2 - suction["H"], rel=1e-3)
    assert props.suction_enthalpy_j_kg - props.liquid_enthalpy_j_kg == pytest.approx(
        suction["H"] - liquid["H"], rel=1e-3
    )


def test_cycle_table_rejects_condensing_not_above_evaporating(table: CycleTable) -> None:
    """冷凝溫度不得低於蒸發溫度。

回傳：
    無。"""
    with pytest.raises(ValueError):
        table.properties(celsius(10.0), celsius(10.0))


def test_compressor_reproduces_manufacturer_rating(provider: ThermodynamicStateService) -> None:
    """額定點 7.2/54.4 °C、SH 11.1 K、SC 8.3 K、60 Hz：冷量 12.9 kW、耗電 5.13 kW（原廠資料表）。

    額定工況為假設（資料表未註明）；本測試確認 C 與總效率是由該點反推。

回傳：
    無。"""
    compressor = CompressorParameters()
    settings = CycleSettings(superheat_k=11.1, subcooling_k=8.3)
    rated = CycleTable.build(
        provider,
        settings,
        evaporating_range_k=(celsius(6.0), celsius(9.0)),
        condensing_range_k=(celsius(53.0), celsius(56.0)),
        step_k=0.2,
    )
    perf = compressor_performance(rated, compressor, celsius(7.2), celsius(54.4), compressor.rated_frequency_hz)
    assert perf.cooling_w == pytest.approx(compressor.rated_cooling_w, rel=1e-2)
    assert perf.power_w == pytest.approx(compressor.rated_power_w, rel=1e-2)
    assert perf.pressure_ratio == pytest.approx(3.40, abs=0.01)


def test_compressor_design_point_and_frequency_scaling(table: CycleTable) -> None:
    """設計點 5/40 °C、60 Hz：冷量 14.7 kW、耗電 4.04 kW、排氣約 76 °C；能力與頻率成正比、COP 不變。

回傳：
    無。"""
    params = CompressorParameters()
    at60 = compressor_performance(table, params, celsius(5.0), celsius(40.0), 60.0)
    assert at60.cooling_w == pytest.approx(14_730.0, rel=1e-2)
    assert at60.power_w == pytest.approx(4_040.0, rel=1e-2)
    assert at60.properties.discharge_temperature_k == pytest.approx(celsius(76.4), abs=0.5)
    for hz in (30.0, 40.0, 50.0):
        at_step = compressor_performance(table, params, celsius(5.0), celsius(40.0), hz)
        assert at_step.cooling_w == pytest.approx(at60.cooling_w * hz / 60.0, rel=1e-9)
        assert at_step.cooling_w / at_step.power_w == pytest.approx(at60.cooling_w / at60.power_w)


@pytest.mark.parametrize("mode", list(RefrigerantMode))
def test_operating_point_balances_both_heat_exchangers(table: CycleTable, mode: RefrigerantMode) -> None:
    """求解結果滿足冷媒側與換熱器側能量平衡。

回傳：
    無。"""
    params = HeatPumpParameters()
    conditions = OperatingConditions(
        mode=mode,
        cold_water_k=celsius(12.0),
        hot_water_k=celsius(38.0),
        outdoor_k=celsius(30.0 if mode is RefrigerantMode.SMART_COOLING else 15.0),
        frequency_hz=40.0,
        evaporator_conductance_w_k=1_290.0,
        condenser_conductance_w_k=2_217.0,
        outdoor_ua_w_k=params.outdoor_ua_w_k,
    )
    perf = OperatingPointSolver(table, params).solve(conditions)
    outdoor_evap = mode is RefrigerantMode.SMART_HEATING
    outdoor_cond = mode is RefrigerantMode.SMART_COOLING
    evap_side = (params.outdoor_ua_w_k if outdoor_evap else 1_290.0) * (
        (conditions.outdoor_k if outdoor_evap else conditions.cold_water_k) - perf.evaporating_k
    )
    cond_side = (params.outdoor_ua_w_k if outdoor_cond else 2_217.0) * (
        perf.condensing_k - (conditions.outdoor_k if outdoor_cond else conditions.hot_water_k)
    )
    assert perf.cooling_w == pytest.approx(evap_side, rel=2e-3)
    assert perf.heating_w == pytest.approx(cond_side, rel=2e-3)


def test_evaporating_temperature_is_capped(table: CycleTable) -> None:
    """冰水很熱、能力不大（30 Hz）時蒸發溫度頂在 15 °C 上限；60 Hz 時壓縮機吸得更多，蒸發溫度落在上限以下。

回傳：
    無。"""
    params = HeatPumpParameters()

    def solve(frequency_hz: float):
        conditions = OperatingConditions(
            RefrigerantMode.DUAL, celsius(30.0), celsius(30.0), celsius(30.0), frequency_hz, 1_290.0, 2_217.0, 677.0
        )
        return OperatingPointSolver(table, params).solve(conditions)

    assert solve(30.0).evaporating_k == pytest.approx(params.control.max_evaporating_k, abs=1e-6)
    assert solve(60.0).evaporating_k < params.control.max_evaporating_k - 0.5


# ---- 情境（規格 §4） ----


def _frequencies(records) -> set[float]:
    """運轉中記錄出現過的頻率。

參數：
    records: 時間步記錄。

回傳：
    頻率集合。"""
    return {r.frequency_hz for r in records if r.compressor_on}


@pytest.mark.parametrize(
    ("operation", "fans"),
    [(OperationMode.COOLING, {"A", "B"}), (OperationMode.COOLING, {"B"}), (OperationMode.HEATING, {"B"})],
)
def test_compressor_only_runs_on_frequency_steps(table: CycleTable, operation: OperationMode, fans: set[str]) -> None:
    """自動控制下，運轉中的頻率只會是 30／40／50／60 Hz，且變階之間至少相隔停留時間。

回傳：
    無。"""
    _sim, records, _summary = _run(table, operation, fans)
    assert _frequencies(records) <= set(STEPS)
    previous = None
    last_change = None
    dwell = ControlParameters().step_dwell_s
    for record in records:
        if not record.compressor_on:
            previous = None
            continue
        if previous is not None and record.frequency_hz != previous:
            # 因高壓限頻而降階可以立即發生；升階與一般降階必須遵守停留時間。
            if record.frequency_hz > previous and last_change is not None:
                assert record.time_s - last_change >= dwell - 1e-6
            last_change = record.time_s
        previous = record.frequency_hz


def test_cooling_with_both_fans_is_held_near_minimum_frequency_by_freeze_protection(table: CycleTable) -> None:
    """冷房、送風機 A+B：開機降溫時 60 Hz，之後防凍保護（冰水出水溫度 < 4 °C）限頻，
    冰水可降到約 7.5～8 °C（接近 7 °C 目標），出水溫度不低於約 3.5 °C；此時蒸發溫度可低於 0 °C。

回傳：
    無。"""
    sim, records, summary = _run(table, OperationMode.COOLING, {"A", "B"})
    assert sim.events[0].code == "smart_cooling" and sim.events[0].time_s / 60 == pytest.approx(5.0, abs=1.0)
    assert records[0].frequency_hz == 60.0
    assert summary.stops == 0 and not any(e.code == "freeze_stop" for e in sim.events)
    assert WARNING_FREEZE_LIMITING in summary.warnings
    steady = [r for r in records if r.time_s > 2 * HOUR]
    assert all(celsius(7.0) < r.cold_water_k < celsius(8.6) for r in steady)
    assert summary.max_condensing_k < celsius(58.5)
    plate = [r for r in records if r.compressor_on and r.mode is not RefrigerantMode.SMART_HEATING]
    assert min(r.evaporator_water_out_k for r in plate) > celsius(3.5)
    assert 1.4 < summary.system_cop < 2.0


def test_cooling_with_fan_b_cycles_on_freeze_protection(table: CycleTable) -> None:
    """冷房、送風機 B：負荷小於最低頻率能力，防凍保護（出水 < 4 °C）反覆停機；冰水在 6～10 °C 之間循環。

回傳：
    無。"""
    sim, records, summary = _run(table, OperationMode.COOLING, {"B"})
    freeze_stops = [e for e in sim.events if e.code == "freeze_stop"]
    assert 2 <= len(freeze_stops) <= 20
    assert WARNING_FREEZE_STOPPED in summary.warnings and WARNING_FREEZE_LIMITING in summary.warnings
    assert 0.6 < summary.run_fraction < 0.9
    steady = [r for r in records if r.time_s > 2 * HOUR]
    assert all(celsius(6.0) < r.cold_water_k < celsius(10.5) for r in steady)
    plate = [r for r in records if r.compressor_on and r.mode is not RefrigerantMode.SMART_HEATING]
    assert min(r.evaporator_water_out_k for r in plate) > celsius(3.5)
    assert 1.2 < summary.system_cop < 1.9


def test_cooling_with_fan_a_freeze_stops_restart_after_dwell(table: CycleTable) -> None:
    """冷房、送風機 A：防凍停機後至少 3 min 才能重啟；停機期間水泵與送風機仍耗電。

回傳：
    無。"""
    sim, records, summary = _run(table, OperationMode.COOLING, {"A"})
    stop = next(e for e in sim.events if e.code == "freeze_stop")
    start = next(e for e in sim.events if e.code == "start" and e.time_s > stop.time_s)
    assert start.time_s - stop.time_s >= 180.0
    assert summary.run_fraction < 0.7
    off = [r for r in records if not r.compressor_on]
    assert off
    pumps = 2 * PumpParameters().power_w(60.0)
    assert all(r.total_power_w == pytest.approx(85.0 + pumps) for r in off if r.time_s > 60)


def test_heating_switches_to_outdoor_evaporator_when_freeze_protection_trips(table: CycleTable) -> None:
    """暖房、送風機 A+B：冰水出水溫度低於 4 °C，防凍保護停機並改由室外換熱器吸熱
    （不必等冰水降到 5 °C）；切換後持續運轉，熱水維持在約 45 °C。

回傳：
    無。"""
    sim, records, summary = _run(table, OperationMode.HEATING, {"A", "B"})
    switch = next(e for e in sim.events if e.code == "smart_heating")
    assert "防凍" in switch.message and any(e.code == "freeze_stop" for e in sim.events)
    at_switch = next(r for r in records if r.time_s + r.dt_s >= switch.time_s)
    assert at_switch.cold_water_k > celsius(5.0)  # 尚未降到一般切換條件（5 °C）就因防凍提前切換
    after = [r for r in records if r.time_s > switch.time_s + 600]
    assert all(r.mode is RefrigerantMode.SMART_HEATING for r in after)
    assert sum(r.compressor_on for r in after) / len(after) > 0.95
    assert records[-1].valves_open == VALVES_OPEN[RefrigerantMode.SMART_HEATING]
    assert celsius(44.0) < records[-1].hot_water_k < celsius(46.0)
    # 防凍保護只針對板式蒸發器；室外換熱器當蒸發器時蒸發溫度可以低於 4 °C。
    outdoor = [r for r in records if r.compressor_on and r.mode is RefrigerantMode.SMART_HEATING]
    assert min(r.evaporating_k for r in outdoor) < celsius(4.0)
    assert not any(WARNING_FREEZE_LIMITING in r.warnings for r in outdoor[10:])


def test_heating_with_fan_a_stops_at_46_and_restarts_at_42(table: CycleTable) -> None:
    """暖房、送風機 A：30 Hz 仍過頭時熱水 ≥ 46 °C 停機，≤ 42 °C 且停滿 3 min 重啟。

回傳：
    無。"""
    sim, records, summary = _run(table, OperationMode.HEATING, {"A"}, hours=1.5)
    stop = next(e for e in sim.events if e.code == "stop")
    start = next(e for e in sim.events if e.code == "start" and e.time_s > stop.time_s)
    assert start.time_s - stop.time_s >= 180.0
    at_stop = next(r for r in records if r.time_s + r.dt_s == pytest.approx(stop.time_s))
    at_start = next(r for r in records if r.time_s + r.dt_s == pytest.approx(start.time_s))
    assert at_stop.hot_water_k >= celsius(46.0) and at_stop.frequency_hz == 30.0
    assert at_start.hot_water_k <= celsius(42.0)
    assert summary.stops >= 2


def test_freeze_protection_limits_frequency_when_leaving_water_below_four_degrees(table: CycleTable) -> None:
    """冰水 7 °C、板式蒸發器流路：全速運轉出水溫度會低於 4 °C，保護逐步降頻並維持出水不低於約 3.5 °C。

回傳：
    無。"""
    settings = replace(default_settings(OperationMode.COOLING), fans=frozenset({"A", "B"}))
    sim = HeatPumpSimulation(table, settings=settings, initial_cold_k=celsius(7.0), initial_hot_k=celsius(30.0))
    first = sim.step()
    assert first.frequency_hz == 60.0 and first.evaporator_water_out_k < celsius(4.0)
    records = sim.run(600.0)
    assert any(WARNING_FREEZE_LIMITING in r.warnings for r in records[:40])
    assert records[-1].frequency_hz < 60.0
    assert records[-1].evaporator_water_out_k > celsius(3.5)
    assert records[-1].frequency_limit_hz >= 30.0  # 高壓限頻未動作；限頻來自防凍保護


def test_freeze_protection_stops_at_minimum_frequency_and_restarts_only_when_safe(table: CycleTable) -> None:
    """以較高的防凍設定（出水 9 °C）讓保護必然停機：最低頻率運轉仍過低 60 s 後停機；
    預測最低頻率仍不安全時即使溫度條件成立也不重啟，冰水夠熱後才重啟。

回傳：
    無。"""
    params = HeatPumpParameters(control=ControlParameters(freeze_limit_start_k=celsius(9.0), freeze_release_k=celsius(10.0)))
    settings = replace(default_settings(OperationMode.COOLING), fans=frozenset())  # 無負荷，冰水溫度不會自己回升
    sim = HeatPumpSimulation(table, params, settings, initial_cold_k=celsius(10.5))
    sim.run(900.0)
    assert any(e.code == "freeze_stop" for e in sim.events)
    sim.cold_water_k = celsius(11.0)  # 已達一般重啟溫度（≥ 10 °C），但最低頻率預測出水溫度仍低於 9 °C
    records = sim.run(900.0)
    assert not any(r.compressor_on for r in records)
    assert WARNING_FREEZE_STOPPED in records[-1].warnings
    assert not any(e.code == "start" for e in sim.events)
    sim.cold_water_k = celsius(25.0)
    resumed = sim.run(30.0)
    assert any(e.code == "start" for e in sim.events) and resumed[-1].compressor_on
    assert WARNING_FREEZE_STOPPED not in resumed[-1].warnings


def test_pump_power_factor_scales_measured_power() -> None:
    """功率因數預設 1.0（實測 √3·V·I 視為有效功率）；可調整為折減。

回傳：
    無。"""
    assert PumpParameters().power_factor == 1.0
    scaled = PumpParameters(power_factor=0.8)
    assert scaled.power_w(60.0) == pytest.approx(0.8 * PumpParameters().power_w(60.0))
    assert scaled.power_w(40.0) == pytest.approx(0.8 * 241.4, abs=0.5)
    cubic = PumpParameters(flow_ratio_by_hz=(), power_w_by_hz=(), rated_power_w=500.0, power_factor=0.5)
    assert cubic.power_w(60.0) == pytest.approx(250.0)


def test_pump_frequency_sets_flow_power_and_evaporator_performance(table: CycleTable) -> None:
    """泵頻率 30 Hz：冰水泵 4.76 GPM、熱水泵 5.84 GPM、每台 167 W；流量減少使蒸發器溫差變大，蒸發溫度較低。

回傳：
    無。"""
    base = default_settings(OperationMode.COOLING)
    full = HeatPumpSimulation(table, settings=base).step()
    slow = HeatPumpSimulation(table, settings=replace(base, cold_pump_hz=30.0, hot_pump_hz=30.0)).step()
    assert (full.cold_pump_hz, full.cold_pump_gpm, full.hot_pump_gpm) == (
        60.0, pytest.approx(9.83, abs=0.01), pytest.approx(12.06, abs=0.01))
    assert full.pump_power_w == pytest.approx(2 * 391.9, abs=0.5)
    assert slow.cold_pump_gpm == pytest.approx(4.76, abs=0.01) and slow.hot_pump_gpm == pytest.approx(5.84, abs=0.01)
    assert slow.cold_pump_power_w == pytest.approx(167.4, abs=0.5) and slow.pump_power_w == pytest.approx(334.8, abs=1.0)
    assert slow.evaporating_k < full.evaporating_k
    assert slow.condenser_water_out_k - slow.condenser_water_in_k > full.condenser_water_out_k - full.condenser_water_in_k


def test_fan_coil_load_does_not_depend_on_pump_frequency(table: CycleTable) -> None:
    """送風機冷卻能力與水泵頻率無關（表 8.1.1 的量測對象不確定，暫不套用實測係數）。

回傳：
    無。"""
    base = default_settings(OperationMode.COOLING)

    def load(hz: float) -> float:
        sim = HeatPumpSimulation(table, settings=replace(base, cold_pump_hz=hz), initial_cold_k=celsius(12.0))
        return sim.step().fan_coil_load_w

    assert load(30.0) == pytest.approx(load(60.0))
    assert load(40.0) == pytest.approx(load(60.0))


def test_reheat_takes_the_smaller_of_demand_and_coil_capacity(table: CycleTable) -> None:
    """再熱 = min(再熱比例 × 盤管負荷, UA_rh × (熱水 − 盤管出風溫度))；熱水桶扣除同量熱。

回傳：
    無。"""
    params = HeatPumpParameters()
    settings = replace(default_settings(OperationMode.COOLING), reheat_fraction=0.2)
    fan_ua = 3_516.0 / 20.0 + 5_274.0 / 20.0
    ua_rh = params.reheat.ua_ratio_to_fan_coil * fan_ua

    warm = HeatPumpSimulation(table, settings=settings, initial_cold_k=celsius(10.0), initial_hot_k=celsius(40.0))
    r = warm.step()
    load = fan_ua * (celsius(27.0) - celsius(10.0))
    assert r.fan_coil_load_w == pytest.approx(load)
    assert r.reheat_demand_w == pytest.approx(0.2 * load)
    capacity = ua_rh * (celsius(40.0) - (celsius(10.0) + params.reheat.coil_air_approach_k))
    assert capacity > r.reheat_demand_w
    assert r.reheat_w == pytest.approx(r.reheat_demand_w)
    assert r.net_cooling_w == pytest.approx(load - r.reheat_w)

    cool = HeatPumpSimulation(table, settings=settings, initial_cold_k=celsius(10.0), initial_hot_k=celsius(20.0))
    r = cool.step()
    capacity = ua_rh * (celsius(20.0) - (celsius(10.0) + params.reheat.coil_air_approach_k))
    assert capacity < r.reheat_demand_w
    assert r.reheat_w == pytest.approx(capacity)


def test_reheat_energy_is_taken_from_the_hot_tank(table: CycleTable) -> None:
    """同樣條件下，開啟再熱使熱水桶升溫較慢；再熱為 0 或暖房時不再熱。

回傳：
    無。"""
    on = default_settings(OperationMode.COOLING)
    off = replace(on, reheat_fraction=0.0)
    sim_on = HeatPumpSimulation(table, settings=on, initial_cold_k=celsius(12.0), initial_hot_k=celsius(30.0))
    sim_off = HeatPumpSimulation(table, settings=off, initial_cold_k=celsius(12.0), initial_hot_k=celsius(30.0))
    on_records, off_records = sim_on.run(120.0), sim_off.run(120.0)
    assert sim_on.hot_water_k < sim_off.hot_water_k
    expected = sum(r.reheat_w * r.dt_s for r in on_records)
    assert on_records[-1].reheat_energy_j == pytest.approx(expected)
    assert expected > 0 and all(r.reheat_w == 0.0 for r in off_records)
    heating = HeatPumpSimulation(table, settings=default_settings(OperationMode.HEATING)).step()
    assert heating.reheat_w == 0.0 and heating.net_cooling_w == 0.0


def test_reheat_extends_dual_mode_before_hot_water_saturates(table: CycleTable) -> None:
    """冷房 3 小時：再熱讓熱水桶不會長時間停在 40 °C，雙效與智慧冷房交替出現。

回傳：
    無。"""
    sim, records, summary = _run(table, OperationMode.COOLING, {"B"})
    assert summary.reheat_energy_j / 3.6e6 > 1.0
    modes = [e.code for e in sim.events if e.code in ("dual", "smart_cooling")]
    assert modes.count("smart_cooling") >= 2 and "dual" in modes
    assert max(r.hot_water_k for r in records) < celsius(41.0)


def test_mode_return_waits_for_minimum_dwell(table: CycleTable) -> None:
    """智慧冷房切回雙效前，至少要在智慧冷房停留 mode_return_dwell_s（即使熱水已降到回切溫度）。

回傳：
    無。"""
    sim = HeatPumpSimulation(table, settings=default_settings(OperationMode.COOLING))
    sim.run(15 * 60.0)
    assert sim.mode is RefrigerantMode.SMART_COOLING
    entered = next(e.time_s for e in reversed(sim.events) if e.code == "smart_cooling")
    sim.hot_water_k = celsius(30.0)
    records = sim.run(HeatPumpParameters().control.mode_return_dwell_s + 30.0)
    first_dual = next(r for r in records if r.mode is RefrigerantMode.DUAL)
    assert first_dual.time_s - entered >= HeatPumpParameters().control.mode_return_dwell_s - 5.0
    assert records[0].mode is RefrigerantMode.SMART_COOLING


# ---- 控制行為 ----


def test_manual_frequency_is_respected_and_stops_at_setpoint(table: CycleTable) -> None:
    """暖房、送風機 A、手動 40 Hz：運轉時頻率固定；熱水到 45 °C 停機（手動不使用 1 K 餘裕）。

回傳：
    無。"""
    sim, records, _summary = _run(
        table,
        OperationMode.HEATING,
        {"A"},
        hours=1.0,
        frequency_mode=FrequencyMode.MANUAL,
        manual_frequency_hz=40.0,
    )
    stop = next(e for e in sim.events if e.code == "stop")
    running = [r for r in records if r.compressor_on and r.time_s < stop.time_s]
    assert running and all(r.frequency_hz == pytest.approx(40.0) for r in running)
    assert records[0].compressor_power_w < compressor_performance(
        sim.table, CompressorParameters(), records[0].evaporating_k, records[0].condensing_k, 60.0
    ).power_w
    at_stop = min(records, key=lambda r: abs(r.time_s - stop.time_s + 5.0))
    assert celsius(45.0) <= at_stop.hot_water_k < celsius(45.3)


def test_manual_frequency_is_capped_by_freeze_protection(table: CycleTable) -> None:
    """冷房手動 60 Hz：防凍保護仍會把頻率限制下來（保護優先於手動）。

回傳：
    無。"""
    settings = replace(default_settings(OperationMode.COOLING), frequency_mode=FrequencyMode.MANUAL,
                       manual_frequency_hz=60.0, fans=frozenset({"A", "B"}))
    sim = HeatPumpSimulation(table, settings=settings, initial_cold_k=celsius(8.0))
    records = sim.run(600.0)
    assert records[0].frequency_hz == 60.0
    assert records[-1].frequency_hz < 60.0 and records[-1].evaporator_water_out_k > celsius(3.5)


def test_safety_trip_latches_until_reset(table: CycleTable) -> None:
    """冷凝溫度超過安全上限時停機並保持，直到手動復歸。

回傳：
    無。"""
    params = HeatPumpParameters(control=ControlParameters(trip_condensing_k=celsius(36.0)))
    sim = HeatPumpSimulation(table, params, default_settings(OperationMode.COOLING))
    records = sim.run(600.0)
    assert any(e.code == "trip" for e in sim.events)
    assert all(not r.compressor_on for r in records[1:])
    assert WARNING_TRIPPED in records[-1].warnings
    sim.reset_trip()
    assert not sim.step().warnings & {WARNING_TRIPPED}
    assert "trip_reset" in [e.code for e in sim.events]
    trip = next(e for e in sim.events if e.code == "trip")
    assert trip.time_s == pytest.approx(records[0].time_s + records[0].dt_s)


def test_trip_reset_resumes_when_restart_condition_holds(table: CycleTable) -> None:
    """復歸後依一般重啟條件（冰水 ≥ 10 °C、已停 ≥ 3 min）重新運轉。

回傳：
    無。"""
    params = HeatPumpParameters(control=ControlParameters(trip_condensing_k=celsius(36.0)))
    sim = HeatPumpSimulation(table, params, default_settings(OperationMode.COOLING))
    sim.run(300.0)
    sim.params = replace(params, control=ControlParameters())
    sim.reset_trip()
    records = sim.run(30.0)
    assert any(r.compressor_on for r in records)


def test_switching_operation_returns_to_dual_mode(table: CycleTable) -> None:
    """冷房中切到暖房：冷媒模式回到雙效並記錄事件。

回傳：
    無。"""
    sim = HeatPumpSimulation(table, settings=default_settings(OperationMode.COOLING))
    sim.run(15 * 60.0)
    assert sim.mode is RefrigerantMode.SMART_COOLING
    sim.update_settings(default_settings(OperationMode.HEATING))
    assert sim.mode is RefrigerantMode.DUAL
    assert sim.events[-1].code == "operation"
    record = sim.step()
    assert record.operation is OperationMode.HEATING


def test_energy_accounts_for_compressor_fans_and_pumps(table: CycleTable) -> None:
    """累計耗電 = Σ(壓縮機 + 開啟送風機 + 兩台水泵) × dt；水泵耗電隨頻率。

回傳：
    無。"""
    settings = replace(default_settings(OperationMode.COOLING), fans=frozenset({"B"}), cold_pump_hz=50.0, hot_pump_hz=40.0)
    sim = HeatPumpSimulation(table, settings=settings)
    records = sim.run(300.0, dt_s=5.0)
    pumps = PumpParameters().power_w(50.0) + PumpParameters().power_w(40.0)
    expected = sum(r.compressor_power_w + 125.0 + pumps for r in records) * 5.0
    assert records[-1].energy_used_j == pytest.approx(expected)
    assert records[-1].pump_power_w == pytest.approx(pumps)
    assert records[-1].system_cop == pytest.approx(records[-1].fan_coil_energy_j / expected)


@pytest.mark.parametrize(
    "settings",
    [
        SimulationSettings(fans=frozenset({"C"})),
        SimulationSettings(cold_pump_hz=35.0),
        SimulationSettings(hot_pump_hz=0.0),
        SimulationSettings(manual_frequency_hz=35.0),
        SimulationSettings(manual_frequency_hz=70.0),
        SimulationSettings(reheat_fraction=-0.1),
        SimulationSettings(reheat_fraction=0.9),
    ],
)
def test_invalid_settings_are_rejected(table: CycleTable, settings: SimulationSettings) -> None:
    """未知送風機、不在階梯上的泵／壓縮機頻率、超出範圍的再熱比例都明確失敗。

回傳：
    無。"""
    with pytest.raises(ValueError):
        HeatPumpSimulation(table, settings=settings)


def test_invalid_time_step_and_mismatched_table_are_rejected(table: CycleTable) -> None:
    """時間步長須在 (0, 10] 秒；性質表設定須與參數一致。

回傳：
    無。"""
    sim = HeatPumpSimulation(table)
    with pytest.raises(ValueError):
        sim.step(0.0)
    with pytest.raises(ValueError):
        sim.step(11.0)
    with pytest.raises(ValueError):
        HeatPumpSimulation(table, HeatPumpParameters(cycle=CycleSettings(superheat_k=3.0)))
    with pytest.raises(ValueError):
        HeatPumpSimulation(table, HeatPumpParameters(compressor=CompressorParameters(overall_efficiency=0.7)))


def test_frequency_changes_apply_on_the_next_step(table: CycleTable) -> None:
    """手動頻率與手動→自動切換在下一步立即生效；切回自動時頻率不跳動。

回傳：
    無。"""
    settings = replace(default_settings(OperationMode.COOLING), frequency_mode=FrequencyMode.MANUAL, manual_frequency_hz=40.0)
    sim = HeatPumpSimulation(table, settings=settings)
    assert sim.step().frequency_hz == pytest.approx(40.0)
    sim.set_manual_frequency(30.0)
    assert sim.step().frequency_hz == pytest.approx(30.0)
    sim.update_settings(replace(sim.settings, frequency_mode=FrequencyMode.AUTO))
    assert sim.step().frequency_hz == pytest.approx(30.0)


def test_switch_to_outdoor_condenser_preempts_high_pressure_trip(table: CycleTable) -> None:
    """外氣 36 °C 時切換智慧冷房會讓冷凝溫度跳升；切換前預先限頻到階梯，不應安全停機。

回傳：
    無。"""
    settings = replace(default_settings(OperationMode.COOLING), outdoor_k=celsius(36.0))
    sim = HeatPumpSimulation(table, settings=settings)
    records = sim.run(1_200.0)
    codes = [e.code for e in sim.events]
    assert "smart_cooling" in codes and "hp_preempt" in codes
    assert "trip" not in codes
    running = [r for r in records if r.compressor_on]
    assert max(r.condensing_k for r in running) < celsius(60.0)
    preempt = next(e for e in sim.events if e.code == "hp_preempt")
    assert preempt.time_s == pytest.approx(next(e.time_s for e in sim.events if e.code == "smart_cooling"))
    assert any(WARNING_HP_LIMITING in r.warnings for r in records) or _frequencies(records) <= set(STEPS)


def test_pump_and_fan_changes_mid_run_take_effect(table: CycleTable) -> None:
    """執行中改泵頻率或送風機：下一步的換熱與送風機負荷跟著改變。

回傳：
    無。"""
    sim = HeatPumpSimulation(table, settings=replace(default_settings(OperationMode.COOLING), fans=frozenset({"A"})))
    sim.run(15 * 60.0)
    base = sim.step()
    sim.update_settings(replace(sim.settings, fans=frozenset({"A", "B"})))
    both = sim.step()
    assert base.fan_coil_load_w > 0
    assert both.fan_coil_load_w > base.fan_coil_load_w * 2.0
    sim.update_settings(replace(sim.settings, cold_pump_hz=30.0))
    slower = sim.step()
    assert slower.cold_pump_gpm == pytest.approx(4.76, abs=0.01)
    assert slower.evaporating_k < both.evaporating_k


def test_summary_handles_uneven_last_step(table: CycleTable) -> None:
    """時間不能整除步長時，最後一步較短，摘要以每步實際 dt 累計。

回傳：
    無。"""
    sim = HeatPumpSimulation(table)
    records = sim.run(1_000.0, dt_s=3.0)
    assert records[-1].dt_s == pytest.approx(1.0)
    summary = summarize(records, sim.events)
    assert summary.duration_s == pytest.approx(1_000.0)
    single = summarize(records[:1], sim.events)
    assert single.duration_s == pytest.approx(3.0)
    assert single.energy_used_j == pytest.approx(records[0].total_power_w * 3.0)


@pytest.mark.parametrize(
    "overrides",
    [{"outdoor_k": celsius(-15.0)}, {"outdoor_k": celsius(50.0)}, {"room_k": celsius(5.0)}],
)
def test_environment_out_of_range_is_rejected(table: CycleTable, overrides: dict) -> None:
    """外氣 −10～45 °C、室溫 10～35 °C 以外明確失敗（避免超出性質表）。

回傳：
    無。"""
    with pytest.raises(ValueError):
        HeatPumpSimulation(table, settings=replace(SimulationSettings(), **overrides))


def test_cycle_entropies_match_direct_state_queries(
    table: CycleTable, provider: ThermodynamicStateService
) -> None:
    """T-s 圖用的四點熵與直接查詢一致；節流後熵增加。

回傳：
    無。"""
    te, tc = celsius(5.0), celsius(40.0)
    props = table.properties(te, tc)
    pe, pc = props.evaporating_pressure_pa, props.condensing_pressure_pa
    s1 = provider.calculate_state_si("R410A", [("T", te + 5.0), ("P", pe)], "ASHRAE")["S"]
    s2 = provider.calculate_state_si("R410A", [("P", pc), ("H", props.discharge_enthalpy_j_kg)], "ASHRAE")["S"]
    s3 = provider.calculate_state_si("R410A", [("T", tc - 5.0), ("P", pc)], "ASHRAE")["S"]
    s4 = provider.calculate_state_si("R410A", [("P", pe), ("H", props.liquid_enthalpy_j_kg)], "ASHRAE")["S"]
    assert props.suction_entropy_j_kg_k == pytest.approx(s1, rel=1e-3)
    assert props.discharge_entropy_j_kg_k == pytest.approx(s2, rel=2e-3)
    assert props.liquid_entropy_j_kg_k == pytest.approx(s3, rel=1e-3)
    assert props.evaporator_inlet_entropy_j_kg_k == pytest.approx(s4, rel=2e-3)
    assert props.evaporator_inlet_entropy_j_kg_k > props.liquid_entropy_j_kg_k
    assert props.discharge_entropy_j_kg_k > props.suction_entropy_j_kg_k


def test_record_reports_plate_water_temperatures_and_outdoor_heat(table: CycleTable) -> None:
    """雙效時兩個板式換熱器都有進出水溫；智慧冷房時冷凝熱改由室外排出。

回傳：
    無。"""
    sim = HeatPumpSimulation(table)
    record = sim.step()
    cold_flow = gpm_to_kg_s(record.cold_pump_gpm) * 4186.0
    hot_flow = gpm_to_kg_s(record.hot_pump_gpm) * 4186.0
    assert cold_flow == pytest.approx(0.62 * 4186.0, rel=1e-3) and hot_flow == pytest.approx(0.761 * 4186.0, rel=1e-3)
    assert record.evaporator_water_in_k == pytest.approx(celsius(30.0))
    assert record.evaporator_water_out_k == pytest.approx(celsius(30.0) - record.cooling_w / cold_flow)
    assert record.condenser_water_out_k == pytest.approx(celsius(30.0) + record.heating_w / hot_flow)
    assert record.outdoor_heat_w == 0.0
    assert record.suction_temperature_k == pytest.approx(record.evaporating_k + 5.0)
    sim.run(15 * 60.0)
    smart = sim.step()
    assert smart.mode is RefrigerantMode.SMART_COOLING
    assert smart.condenser_water_in_k is None and smart.condenser_water_out_k is None
    assert smart.outdoor_heat_w == pytest.approx(smart.heating_w)
