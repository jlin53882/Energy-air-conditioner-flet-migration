"""多元取熱雙效熱泵動態模擬的 domain 測試（使用實際 CoolProp）。

驗證基準為 ``docs/simulation-model.md`` §4 的原型計算結果。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from domain.heat_pump import (
    VALVES_OPEN,
    WARNING_TRIPPED,
    ControlParameters,
    CycleSettings,
    CycleTable,
    FrequencyMode,
    HeatPumpParameters,
    HeatPumpSimulation,
    OperatingConditions,
    OperatingPointSolver,
    OperationMode,
    PlateExchanger,
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
from domain.heat_pump.parameters import CompressorParameters, PlateGeometry, RefrigerantSideCalibration
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter

HOUR = 3600.0


@pytest.fixture(scope="module")
def provider() -> ThermodynamicStateService:
    """共用 CoolProp 狀態服務。

回傳：
    ThermodynamicStateService。"""
    return ThermodynamicStateService(CanonicalUnitConverter())


@pytest.fixture(scope="module")
def table(provider: ThermodynamicStateService) -> CycleTable:
    """預設設定（SH 5 K、SC 5 K、總效率 0.66）的完整性質表。

回傳：
    CycleTable。"""
    return CycleTable.build(provider)


def _run(table: CycleTable, operation: OperationMode, fans: set[str], hours: float = 3.0, **overrides):
    """以預設環境執行情境。

參數：
    table: 性質表。
    operation: 運轉方式。
    fans: 開啟的送風機。
    hours: 模擬時數。
    overrides: 覆寫的設定欄位。

回傳：
    (模擬器, 記錄, 摘要)。"""
    settings = replace(default_settings(operation), fans=frozenset(fans), **overrides)
    sim = HeatPumpSimulation(table, settings=settings)
    records = sim.run(hours * HOUR)
    return sim, records, summarize(records, sim.events)


# ---- 單元：參數換算與元件模型 ----


def test_gpm_conversion_matches_spec() -> None:
    """12.06 GPM × 3.785 L/gal ÷ 60 = 0.761 kg/s。

回傳：
    無。"""
    assert gpm_to_kg_s(12.06) == pytest.approx(0.761, abs=5e-4)


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(1.7, 0.957), (2.0, 0.940), (2.6, 0.907), (3.4, 0.867), (4.1, 0.834), (5.0, 0.793)],
)
def test_volumetric_efficiency_follows_clearance_model(ratio: float, expected: float) -> None:
    """餘隙容積模型與規格 §1.8 表一致。

回傳：
    無。"""
    assert volumetric_efficiency(CompressorParameters(), ratio) == pytest.approx(expected, abs=1.5e-3)


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


# ---- 性質表與壓縮機 ----


def test_cycle_table_interpolation_matches_direct_state_queries(
    table: CycleTable, provider: ThermodynamicStateService
) -> None:
    """網格之間的內插值與直接查詢的差異在 0.1 % 以內。

回傳：
    無。"""
    te, tc = celsius(5.3), celsius(41.7)
    props = table.properties(te, tc)
    pe = provider.calculate_state_si("R410A", [("T", te), ("Q", 1.0)], "ASHRAE")["P"]
    pc = provider.calculate_state_si("R410A", [("T", tc), ("Q", 0.0)], "ASHRAE")["P"]
    suction = provider.calculate_state_si("R410A", [("T", te + 5.0), ("P", pe)], "ASHRAE")
    liquid = provider.calculate_state_si("R410A", [("T", tc - 5.0), ("P", pc)], "ASHRAE")
    h2s = provider.calculate_state_si("R410A", [("P", pc), ("S", suction["S"])], "ASHRAE")["H"]
    h2 = suction["H"] + (h2s - suction["H"]) / 0.66
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
    """額定點 7.2/54.4 °C、SH 11.1 K、SC 8.3 K、60 Hz：冷量 9.70 kW、耗電 3.32 kW（原廠 9.7／3.325）。

回傳：
    無。"""
    settings = CycleSettings(superheat_k=11.1, subcooling_k=8.3)
    rated = CycleTable.build(
        provider,
        settings,
        evaporating_range_k=(celsius(6.0), celsius(9.0)),
        condensing_range_k=(celsius(53.0), celsius(56.0)),
        step_k=0.2,
    )
    perf = compressor_performance(rated, CompressorParameters(), celsius(7.2), celsius(54.4), 60.0)
    assert perf.cooling_w == pytest.approx(9_700.0, rel=1e-2)
    assert perf.power_w == pytest.approx(3_320.0, rel=1e-2)
    assert perf.pressure_ratio == pytest.approx(3.40, abs=0.01)


def test_compressor_design_point_and_frequency_scaling(table: CycleTable) -> None:
    """設計點 5/40 °C：冷量 10.66 kW、耗電 2.52 kW、排氣約 71 °C；能力與頻率成正比。

回傳：
    無。"""
    params = CompressorParameters()
    at60 = compressor_performance(table, params, celsius(5.0), celsius(40.0), 60.0)
    assert at60.cooling_w == pytest.approx(10_660.0, rel=1e-2)
    assert at60.power_w == pytest.approx(2_520.0, rel=1e-2)
    assert at60.properties.discharge_temperature_k == pytest.approx(celsius(71.0), abs=0.5)
    at30 = compressor_performance(table, params, celsius(5.0), celsius(40.0), 30.0)
    assert at30.cooling_w == pytest.approx(at60.cooling_w / 2.0, rel=1e-9)


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
        frequency_hz=45.0,
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
    """冰水很熱時蒸發溫度不超過 15 °C 上限。

回傳：
    無。"""
    params = HeatPumpParameters()
    conditions = OperatingConditions(
        RefrigerantMode.DUAL, celsius(30.0), celsius(30.0), celsius(30.0), 60.0, 1_290.0, 2_217.0, 551.0
    )
    perf = OperatingPointSolver(table, params).solve(conditions)
    assert perf.evaporating_k == pytest.approx(params.control.max_evaporating_k, abs=1e-6)


# ---- 情境（規格 §4.3） ----


def test_cooling_with_fan_b_holds_setpoint_by_frequency(table: CycleTable) -> None:
    """冷房、送風機 B：6.7 min 切智慧冷房，之後連續降頻把冰水穩定在 7 °C，不停機。

回傳：
    無。"""
    sim, records, summary = _run(table, OperationMode.COOLING, {"B"})
    first = sim.events[0]
    assert first.code == "smart_cooling"
    assert first.time_s / 60 == pytest.approx(6.7, abs=0.3)
    assert summary.stops == 0
    assert records[-1].cold_water_k == pytest.approx(celsius(7.0), abs=0.05)
    assert records[-1].frequency_hz == pytest.approx(33.3, abs=0.5)
    assert summary.mean_frequency_hz == pytest.approx(39.2, abs=1.0)
    assert summary.system_cop == pytest.approx(1.66, abs=0.03)
    assert records[-1].valves_open == VALVES_OPEN[RefrigerantMode.SMART_COOLING]


def test_cooling_with_fan_a_cycles_below_minimum_frequency(table: CycleTable) -> None:
    """冷房、送風機 A：負荷低於 30 Hz 能力，壓縮機啟停；停機期間水泵與送風機仍耗電。

回傳：
    無。"""
    sim, records, summary = _run(table, OperationMode.COOLING, {"A"}, hours=1.5)
    assert summary.stops >= 2
    stop = next(e for e in sim.events if e.code == "stop")
    assert stop.time_s / 60 == pytest.approx(36.9, abs=1.0)
    off = [r for r in records if not r.compressor_on]
    assert off
    assert all(r.total_power_w == pytest.approx(0.085e3 + 1_000.0) for r in off)
    start = next(e for e in sim.events if e.code == "start")
    assert start.time_s - stop.time_s >= 180.0


def test_cooling_with_both_fans_runs_at_full_frequency(table: CycleTable) -> None:
    """冷房、送風機 A+B：能力不足，全程 60 Hz，冰水平衡在約 8.5 °C。

回傳：
    無。"""
    _sim, records, summary = _run(table, OperationMode.COOLING, {"A", "B"})
    assert summary.stops == 0
    assert summary.mean_frequency_hz == pytest.approx(60.0)
    assert records[-1].cold_water_k == pytest.approx(celsius(8.48), abs=0.1)
    assert summary.system_cop == pytest.approx(1.73, abs=0.03)
    assert summary.max_condensing_k == pytest.approx(celsius(56.7), abs=0.3)


def test_heating_with_fan_b_holds_hot_water_setpoint(table: CycleTable) -> None:
    """暖房、送風機 B：31 min 切智慧暖房，熱水穩定在 45 °C。

回傳：
    無。"""
    sim, records, summary = _run(table, OperationMode.HEATING, {"B"})
    switch = next(e for e in sim.events if e.code == "smart_heating")
    assert switch.time_s / 60 == pytest.approx(31.3, abs=1.0)
    assert summary.stops == 0
    assert records[-1].hot_water_k == pytest.approx(celsius(45.0), abs=0.05)
    assert summary.system_cop == pytest.approx(2.31, abs=0.03)
    assert records[-1].valves_open == VALVES_OPEN[RefrigerantMode.SMART_HEATING]


def test_heating_with_both_fans_switches_to_outdoor_evaporator(table: CycleTable) -> None:
    """暖房、送風機 A+B：約 25 min 冰水降到 5 °C，切換智慧暖房（室外吸熱）。

回傳：
    無。"""
    sim, records, _summary = _run(table, OperationMode.HEATING, {"A", "B"}, hours=0.75)
    switch = next(e for e in sim.events if e.code == "smart_heating")
    assert switch.time_s / 60 == pytest.approx(25.4, abs=1.0)
    after = [r for r in records if r.time_s > switch.time_s + 60]
    assert after and all(r.mode is RefrigerantMode.SMART_HEATING and r.compressor_on for r in after)
    assert all(r.evaporating_k is not None and r.evaporating_k < celsius(10.0) for r in after)


# ---- 控制行為 ----


def test_manual_frequency_is_respected_and_stops_at_setpoint(table: CycleTable) -> None:
    """手動 40 Hz：運轉時頻率固定；冰水到 7 °C 停機（手動不使用 1 K 餘裕）。

回傳：
    無。"""
    sim, records, _summary = _run(
        table,
        OperationMode.COOLING,
        {"A"},
        hours=1.5,
        frequency_mode=FrequencyMode.MANUAL,
        manual_frequency_hz=40.0,
    )
    running = [r for r in records if r.compressor_on]
    assert running and all(r.frequency_hz == pytest.approx(40.0) for r in running)
    assert records[0].compressor_power_w < compressor_performance(
        table, CompressorParameters(), records[0].evaporating_k, records[0].condensing_k, 60.0
    ).power_w
    stop_index = next(i for i, e in enumerate(sim.events) if e.code == "stop")
    stop_time = sim.events[stop_index].time_s
    at_stop = min(records, key=lambda r: abs(r.time_s - stop_time + 5.0))
    assert at_stop.cold_water_k <= celsius(7.0)
    assert at_stop.cold_water_k > celsius(6.8)


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
    """累計耗電 = Σ(壓縮機 + 開啟送風機 + 2 台水泵) × dt。

回傳：
    無。"""
    sim = HeatPumpSimulation(table, settings=replace(default_settings(OperationMode.COOLING), fans=frozenset({"B"})))
    records = sim.run(300.0, dt_s=5.0)
    expected = sum(r.compressor_power_w + 125.0 + 1_000.0 for r in records) * 5.0
    assert records[-1].energy_used_j == pytest.approx(expected)
    assert records[-1].system_cop == pytest.approx(records[-1].fan_coil_energy_j / expected)


@pytest.mark.parametrize(
    "settings",
    [
        SimulationSettings(fans=frozenset({"C"})),
        SimulationSettings(cold_pump_gpm=0.0),
        SimulationSettings(hot_pump_gpm=-1.0),
        SimulationSettings(manual_frequency_hz=25.0),
        SimulationSettings(manual_frequency_hz=61.0),
    ],
)
def test_invalid_settings_are_rejected(table: CycleTable, settings: SimulationSettings) -> None:
    """未知送風機、非正 GPM、超出 30～60 Hz 的手動頻率都明確失敗。

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
    """手動頻率與手動→自動切換在下一步立即生效；切回自動時為無擾切換。

回傳：
    無。"""
    settings = replace(default_settings(OperationMode.COOLING), frequency_mode=FrequencyMode.MANUAL, manual_frequency_hz=40.0)
    sim = HeatPumpSimulation(table, settings=settings)
    assert sim.step().frequency_hz == pytest.approx(40.0)
    sim.set_manual_frequency(35.0)
    assert sim.step().frequency_hz == pytest.approx(35.0)
    sim.update_settings(replace(sim.settings, frequency_mode=FrequencyMode.AUTO))
    assert sim.step().frequency_hz == pytest.approx(35.0, abs=0.5)


def test_heating_with_fan_a_cycles_with_auto_stop_and_restart(table: CycleTable) -> None:
    """暖房、送風機 A：30 Hz 仍過頭時熱水 ≥ 46 °C 停機，≤ 42 °C 且停滿 3 min 重啟。

回傳：
    無。"""
    sim, records, summary = _run(table, OperationMode.HEATING, {"A"}, hours=1.0)
    stop = next(e for e in sim.events if e.code == "stop")
    assert stop.time_s / 60 == pytest.approx(17.8, abs=1.0)
    start = next(e for e in sim.events if e.code == "start")
    assert start.time_s - stop.time_s >= 180.0
    at_stop = next(r for r in records if r.time_s + r.dt_s == pytest.approx(stop.time_s))
    at_start = next(r for r in records if r.time_s + r.dt_s == pytest.approx(start.time_s))
    assert at_stop.hot_water_k >= celsius(46.0)
    assert at_start.hot_water_k <= celsius(42.0)
    assert summary.stops >= 2


def test_switch_to_outdoor_condenser_preempts_high_pressure_trip(table: CycleTable) -> None:
    """外氣 36 °C 時切換智慧冷房會讓冷凝溫度跳升；切換前預先限頻，不應安全停機。

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


def test_pump_and_fan_changes_mid_run_take_effect(table: CycleTable) -> None:
    """執行中改 GPM 或送風機：下一步的換熱與送風機負荷跟著改變。

回傳：
    無。"""
    sim = HeatPumpSimulation(table, settings=replace(default_settings(OperationMode.COOLING), fans=frozenset({"A"})))
    sim.run(15 * 60.0)
    base = sim.step()
    sim.update_settings(replace(sim.settings, fans=frozenset({"A", "B"})))
    both = sim.step()
    assert base.fan_coil_load_w > 0
    assert both.fan_coil_load_w > base.fan_coil_load_w * 2.0
    sim.update_settings(replace(sim.settings, cold_pump_gpm=20.0))
    faster = sim.step()
    assert faster.evaporating_k > both.evaporating_k


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
    flow = gpm_to_kg_s(12.06) * 4186.0
    assert record.evaporator_water_in_k == pytest.approx(celsius(30.0))
    assert record.evaporator_water_out_k == pytest.approx(celsius(30.0) - record.cooling_w / flow)
    assert record.condenser_water_out_k == pytest.approx(celsius(30.0) + record.heating_w / flow)
    assert record.outdoor_heat_w == 0.0
    assert record.suction_temperature_k == pytest.approx(record.evaporating_k + 5.0)
    sim.run(15 * 60.0)
    smart = sim.step()
    assert smart.mode is RefrigerantMode.SMART_COOLING
    assert smart.condenser_water_in_k is None and smart.condenser_water_out_k is None
    assert smart.outdoor_heat_w == pytest.approx(smart.heating_w)
