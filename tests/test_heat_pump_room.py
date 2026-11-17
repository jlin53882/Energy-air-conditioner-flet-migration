"""房間溫濕度＋濕盤管模型與策略比較的測試（``docs/simulation-model.md`` §8）。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from domain.heat_pump import CycleTable, HeatPumpSimulation, OperationMode, PumpMode, celsius, default_settings
from domain.heat_pump import psychrometrics as psy
from domain.heat_pump.comparison import (
    STRATEGIES,
    ComfortTolerance,
    Strategy,
    StrategyResult,
    best_relative_only,
    best_strategy,
    reference_result,
)
from domain.heat_pump.parameters import FULL_ELECTRICAL, HeatPumpParameters
from domain.heat_pump.room import (
    DEFAULT_COILS,
    SCENARIOS,
    DailyScenario,
    IndoorControlParameters,
    ReheatMode,
    RoomModel,
)
from domain.heat_pump.wet_coil import (
    coil_performance,
    counterflow_effectiveness,
    invariant_violations,
    water_side_ua,
)
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter

K = 273.15
COIL_B = next(c for c in DEFAULT_COILS if c.name == "B")
# 表 8.1.1（進風 70 %RH、冰水進水 11 °C、風量 0.22 kg/s）：(進風 °C, 冰水流量 kg/s, 空氣側冷量 kW)。
TABLE_8_1_1 = (
    (28, 0.19, 4.69), (28, 0.30, 5.26), (28, 0.43, 5.61), (28, 0.56, 5.83), (28, 0.62, 5.79),
    (27, 0.19, 4.11), (27, 0.30, 4.64), (27, 0.43, 5.08), (27, 0.56, 5.13), (27, 0.62, 5.06),
    (26, 0.19, 3.63), (26, 0.30, 4.09), (26, 0.43, 4.40), (26, 0.56, 4.47), (26, 0.62, 4.47),
)


@pytest.fixture(scope="module")
def table() -> CycleTable:
    """預設性質表。

回傳：
    CycleTable。"""
    return CycleTable.build(ThermodynamicStateService(CanonicalUnitConverter()))


# ---- 濕空氣 ----


def test_psychrometrics_match_ashrae_reference() -> None:
    """27 °C／50 %RH：W 0.01114、h 55.6 kJ/kg、露點 15.7 °C；20 °C 飽和壓 2339 Pa。

回傳：
    無。"""
    w = psy.humidity_ratio(celsius(27.0), 0.5)
    assert w == pytest.approx(0.01114, abs=5e-5)
    assert psy.enthalpy_j_kg(celsius(27.0), w) / 1000 == pytest.approx(55.6, abs=0.1)
    assert psy.dew_point_k(w) - K == pytest.approx(15.7, abs=0.1)
    assert psy.saturation_pressure_pa(celsius(20.0)) == pytest.approx(2339, abs=2)
    assert psy.relative_humidity(celsius(27.0), w) == pytest.approx(0.5, abs=1e-6)


@pytest.mark.parametrize(("tdb_k", "rh"), [(300.15, 0.5), (285.15, 0.9), (308.15, 0.6)])
def test_fast_psychrometrics_agree_with_project_service(tdb_k: float, rh: float) -> None:
    """熱泵迴圈用的快速濕空氣式與專案 ``PsychrometricService``（舊模型 adapter）一致：W、h 誤差 < 0.05 %、露點 < 0.01 K。

參數：
    tdb_k: 乾球溫度。
    rh: 相對濕度。

回傳：
    無。"""
    from domain.psychrometrics.service import PsychrometricService
    from infrastructure.psychrometrics import LegacyPsychrometricModelAdapter

    reference = PsychrometricService(LegacyPsychrometricModelAdapter()).calculate_from_tdb_rh(tdb_k, rh, 0.0)
    w = psy.humidity_ratio(tdb_k, rh)
    assert w == pytest.approx(reference["W"], rel=5e-4)
    assert psy.enthalpy_j_kg(tdb_k, w) == pytest.approx(reference["H"], rel=5e-4)
    assert psy.dew_point_k(w) == pytest.approx(reference["Tdp"], abs=0.01)


def test_saturation_temperature_inverts_saturated_enthalpy() -> None:
    """h_s⁻¹(h_s(T)) = T。

回傳：
    無。"""
    for t in (5.0, 12.0, 20.0):
        h = psy.saturated_enthalpy_j_kg(celsius(t))
        assert psy.saturation_temperature_from_enthalpy(h) - K == pytest.approx(t, abs=0.01)


# ---- 濕盤管 ----


def test_counterflow_effectiveness_limits() -> None:
    """C_r = 0 時 ε = 1 − e^(−NTU)；C_r = 1 時 ε = NTU ÷ (1 + NTU)。

回傳：
    無。"""
    assert counterflow_effectiveness(1.0, 0.0) == pytest.approx(1 - 2.718281828 ** -1, rel=1e-6)
    assert counterflow_effectiveness(2.0, 1.0) == pytest.approx(2 / 3, rel=1e-6)


@pytest.mark.parametrize(("air_c", "flow", "measured_kw"), TABLE_8_1_1)
def test_wet_coil_reproduces_table_8_1_1(air_c: float, flow: float, measured_kw: float) -> None:
    """盤管 B 對表 8.1.1 每一點的空氣側冷量誤差 ≤ 6 %（26／27 °C 為擬合點、28 °C 為驗證點）。

參數：
    air_c: 進風溫度。
    flow: 冰水流量。
    measured_kw: 實測空氣側冷量。

回傳：
    無。"""
    result = coil_performance(COIL_B, celsius(air_c), psy.humidity_ratio(celsius(air_c), 0.7), celsius(11.0), flow)
    assert result.total_w / 1000 == pytest.approx(measured_kw, rel=0.06)
    assert result.wet and result.latent_w > 0


def test_lower_water_flow_reduces_coil_capacity_and_dehumidification() -> None:
    """泵降頻（流量 0.62 → 0.30 kg/s）冷量約 −10 %、除濕量也下降（舊模型兩者都不變）。

回傳：
    無。"""
    w = psy.humidity_ratio(celsius(27.0), 0.6)
    full = coil_performance(COIL_B, celsius(27.0), w, celsius(7.0), 0.62)
    low = coil_performance(COIL_B, celsius(27.0), w, celsius(7.0), 0.30)
    assert 0.85 < low.total_w / full.total_w < 0.95
    assert low.latent_w < full.latent_w
    assert water_side_ua(COIL_B, 0.31) == pytest.approx(COIL_B.water_side_ua_w_k * 0.5 ** COIL_B.water_flow_exponent)


def test_warmer_chilled_water_cuts_latent_more_than_sensible() -> None:
    """冰水 7 → 10 °C：潛冷下降比例大於顯冷（冰水重設的除濕代價）。

回傳：
    無。"""
    w = psy.humidity_ratio(celsius(26.0), 0.55)
    cold = coil_performance(COIL_B, celsius(26.0), w, celsius(7.0), 0.62)
    warm = coil_performance(COIL_B, celsius(26.0), w, celsius(10.0), 0.62)
    assert warm.total_w < cold.total_w
    assert warm.latent_w / cold.latent_w < warm.sensible_w / cold.sensible_w


def test_coil_energy_balance_and_dry_coil() -> None:
    """空氣側焓降 = 水側得熱（≤ 1e-6）；進水高於露點時為全乾（W 不變、凝結 0）；無水量時無熱傳。

回傳：
    無。"""
    w = psy.humidity_ratio(celsius(27.0), 0.6)
    r = coil_performance(COIL_B, celsius(27.0), w, celsius(7.0), 0.62)
    air_side = COIL_B.air_flow_kg_s * (psy.enthalpy_j_kg(celsius(27.0), w)
                                       - psy.enthalpy_j_kg(r.air_out_k, r.air_out_humidity_ratio))
    assert air_side == pytest.approx(r.total_w, rel=1e-6)
    assert r.total_w == pytest.approx(0.62 * 4186 * (r.water_out_k - celsius(7.0)), rel=1e-9)
    dry_w = psy.humidity_ratio(celsius(26.0), 0.3)
    dry = coil_performance(COIL_B, celsius(26.0), dry_w, celsius(14.0), 0.62)
    assert not dry.wet and dry.latent_w == 0.0 and dry.total_w > 0 and dry.wet_fraction == 0.0
    assert dry.air_out_humidity_ratio == dry_w
    assert coil_performance(COIL_B, celsius(27.0), w, celsius(7.0), 0.0).total_w == 0.0


def test_coil_invariants_hold_over_operating_grid() -> None:
    """兩台盤管 × 進風 18–35 °C × RH 15–95 % × 進水 5–20 °C × 水量 0.05–0.62 kg/s：
    能量守恆、0 ≤ W_out ≤ W_in、RH_out ≤ 100 %、凝結 ≥ 0、迭代收斂全部成立。

回傳：
    無。"""
    failures = []
    for coil in DEFAULT_COILS:
        for air_c in range(18, 36, 3):
            for rh in (0.15, 0.35, 0.55, 0.75, 0.95):
                w = psy.humidity_ratio(celsius(air_c), rh)
                for water_c in (5.0, 8.0, 11.0, 14.0, 17.0, 20.0):
                    for flow in (0.05, 0.2, 0.43, 0.62):
                        result = coil_performance(coil, celsius(air_c), w, celsius(water_c), flow)
                        problems = invariant_violations(coil, celsius(air_c), w, celsius(water_c), flow, result)
                        if problems:
                            failures.append((coil.name, air_c, rh, water_c, flow, problems))
    assert failures == []


def test_part_wet_transition_is_continuous() -> None:
    """乾→部分濕→全濕的切換連續：進風 RH 每升 1 %，冷量增量不超過全濕區段斜率的 1.5 倍
    （約 80 W／%RH；舊「取大者」在切換點會跳）。

回傳：
    無。"""
    previous = None
    fractions = []
    w_hi = psy.humidity_ratio(celsius(26.0), 0.80)
    w_lo = psy.humidity_ratio(celsius(26.0), 0.70)
    wet_slope = (coil_performance(COIL_B, celsius(26.0), w_hi, celsius(10.0), 0.62).total_w
                 - coil_performance(COIL_B, celsius(26.0), w_lo, celsius(10.0), 0.62).total_w) / 10
    for rh_pct in range(20, 91):
        w = psy.humidity_ratio(celsius(26.0), rh_pct / 100)
        result = coil_performance(COIL_B, celsius(26.0), w, celsius(10.0), 0.62)
        fractions.append(result.wet_fraction)
        if previous is not None:
            assert 0.0 <= result.total_w - previous <= 1.5 * wet_slope
        previous = result.total_w
    assert fractions[0] == 0.0 and fractions[-1] == 1.0
    assert any(0.0 < f < 1.0 for f in fractions)  # 中間有部分濕區段


# ---- 房間 ----


def test_room_drifts_toward_outdoor_without_supply() -> None:
    """無送風時，高溫情境室溫上升、人員產濕使含濕量上升。

回傳：
    無。"""
    room = RoomModel(SCENARIOS["hot"], initial_k=celsius(26.0), initial_rh=0.5)
    w0 = room.state.humidity_ratio
    for i in range(360):
        room.step(10 * 3600 + i * 10.0, 10.0, [], 0.0)
    assert room.state.temperature_k > celsius(26.5)
    assert room.state.humidity_ratio > w0


def test_scenario_rejects_supersaturated_outdoor_air() -> None:
    """外氣含濕量超過當日最低溫度的飽和值時拒絕（原高濕情境 0.019 在 24 °C 已過飽和）。

回傳：
    無。"""
    with pytest.raises(ValueError, match="飽和"):
        DailyScenario("x", 25.5, 1.5, 0.0190, 0.0, 0, 0.0)
    for scenario in SCENARIOS.values():
        assert scenario.outdoor_humidity(5 * 3600) <= psy.saturation_humidity_ratio(scenario.outdoor_k(5 * 3600))


def test_trend_prediction_triggers_staging_before_limit() -> None:
    """室溫仍在帶內但持續上升時，以預測值提前加開送風機（不等到超標）。

回傳：
    無。"""
    room = RoomModel(SCENARIOS["hot"], initial_k=celsius(25.7), initial_rh=0.5)
    room.update_fans(0.0, frozenset({"A", "B"}), True)
    assert room.fans_on == frozenset()  # 尚未上升
    for i in range(60):  # 無送風，高溫情境午後持續升溫 300 s
        room.step(13 * 3600 + i * 5.0, 5.0, [], 0.0)
    assert room.state.temperature_k < celsius(26.5)
    assert room.predicted_temperature_k > room.state.temperature_k
    assert room.state.temperature_k < celsius(26.2)  # 實際值還沒到開機門檻
    room.update_fans(13 * 3600 + 600.0, frozenset({"A", "B"}), True)
    assert room.fans_on  # 預測已接近上限，提前開


def test_scenario_schedule_and_profiles() -> None:
    """外氣 14 時最高；日照 07–18 時；午休人數減半；空調 07:00 啟用（預冷 1 h）。

回傳：
    無。"""
    sc = SCENARIOS["hot"]
    assert sc.outdoor_k(14 * 3600) - K == pytest.approx(35.0)
    assert sc.outdoor_k(2 * 3600) - K == pytest.approx(28.0)
    assert sc.solar_w(3 * 3600) == 0.0 and sc.solar_w(12.5 * 3600) == pytest.approx(1200.0)
    assert sc.people_count(12.5 * 3600) == 3 and sc.people_count(9 * 3600) == 6
    assert not sc.system_enabled(6.9 * 3600) and sc.system_enabled(7.0 * 3600)
    assert sc.occupied(24 * 3600 + 9 * 3600)


def test_fan_staging_keeps_one_fan_when_humid() -> None:
    """室溫低於下限時關送風機，但濕度高於上限時至少保留一台（B）。

回傳：
    無。"""
    control = IndoorControlParameters()
    dry = RoomModel(SCENARIOS["mild"], initial_k=celsius(25.0), initial_rh=0.5)
    dry.update_fans(0.0, frozenset({"A", "B"}), True)
    assert dry.fans_on == frozenset()
    humid = RoomModel(SCENARIOS["mild"], initial_k=celsius(25.3), initial_rh=0.7)
    humid.update_fans(0.0, frozenset({"A", "B"}), True)
    assert humid.fans_on == frozenset({"B"})
    # 過冷下限：室溫 ≤ 25.0 °C 時即使潮濕也不為除濕保留送風機。
    cold_humid = RoomModel(SCENARIOS["mild"], initial_k=celsius(24.8), initial_rh=0.75)
    cold_humid.update_fans(0.0, frozenset({"A", "B"}), True)
    assert cold_humid.fans_on == frozenset()
    hot = RoomModel(SCENARIOS["mild"], initial_k=control.stage2_on_k + 0.1)
    hot.update_fans(0.0, frozenset({"A", "B"}), True)
    assert hot.fans_on == frozenset({"B"})  # 第二段需第一段已運轉 ≥ 3 min
    hot.update_fans(200.0, frozenset({"A", "B"}), True)
    assert hot.fans_on == frozenset({"A", "B"})
    hot.update_fans(1.0, frozenset({"A", "B"}), False)
    assert hot.fans_on == frozenset()


def test_chw_reset_moves_setpoint_with_humidity() -> None:
    """冰水重設（快降慢升）：有餘裕且壓縮機停機時每 5 min 升 0.5 K（上限 10 °C）；運轉中不升；
    需要除濕時直接降到 7 °C。

回傳：
    無。"""
    room = RoomModel(SCENARIOS["mild"], chw_reset=True, initial_k=celsius(26.0), initial_rh=0.5)
    for i in range(10):
        room.update_chw_setpoint(i * 300.0, True)
    assert room.chw_setpoint_k == pytest.approx(celsius(10.0))
    running = RoomModel(SCENARIOS["mild"], chw_reset=True, initial_k=celsius(26.0), initial_rh=0.5)
    for i in range(10):
        running.update_chw_setpoint(i * 300.0, True, compressor_on=True)
    assert running.chw_setpoint_k == pytest.approx(celsius(7.0))  # 運轉中不升
    room.state.humidity_ratio = psy.humidity_ratio(celsius(26.0), 0.65)
    room.update_chw_setpoint(4000.0, True)
    assert room.chw_setpoint_k == pytest.approx(celsius(7.0))
    fixed = RoomModel(SCENARIOS["mild"], chw_reset=False)
    assert fixed.update_chw_setpoint(0.0, True) == pytest.approx(celsius(7.0))


def test_humidity_control_uses_humidity_ratio_not_rh() -> None:
    """除濕判斷用含濕量：同一含濕量下降溫使 RH 升高，但不改變除濕需求（RH 判斷會自我觸發）。

回傳：
    無。"""
    w = psy.humidity_ratio(celsius(26.0), 0.57)  # 低於 12.6 g/kg 門檻
    warm = RoomModel(SCENARIOS["mild"], initial_k=celsius(26.0), initial_rh=0.57)
    cool = RoomModel(SCENARIOS["mild"], initial_k=celsius(25.4), initial_rh=0.57)
    cool.state.humidity_ratio = w
    assert cool.relative_humidity > 0.58  # RH 已超過舊的 58 % 門檻
    assert not warm.needs_dehumidification() and not cool.needs_dehumidification()


def test_comfort_tight_only_evaluated_with_fans_running() -> None:
    """送風機停轉時室溫上升是必然的，不判為 tight（不觸發升泵、降冰水）。

回傳：
    無。"""
    room = RoomModel(SCENARIOS["hot"], initial_k=celsius(26.2), initial_rh=0.5)
    for i in range(60):
        room.step(13 * 3600 + i * 5.0, 5.0, [], 0.0)
    assert room.predicted_temperature_k > room.control.tight_t_k
    assert not room.comfort_tight()


def test_demand_reheat_only_when_humid_and_cool() -> None:
    """按需再熱：RH > 60 % 且室溫 < 26 °C 才開；固定比例模式為比例 × 盤管負荷。

回傳：
    無。"""
    humid_cool = RoomModel(SCENARIOS["humid"], reheat_mode=ReheatMode.DEMAND, initial_k=celsius(25.0), initial_rh=0.7)
    assert humid_cool.reheat_request_w(0.0, 3000.0) == pytest.approx(2000.0 * 1.2)
    dry = RoomModel(SCENARIOS["humid"], reheat_mode=ReheatMode.DEMAND, initial_k=celsius(25.0), initial_rh=0.5)
    assert dry.reheat_request_w(0.0, 3000.0) == 0.0
    fixed = RoomModel(SCENARIOS["humid"], reheat_mode=ReheatMode.FIXED, reheat_fraction=0.2)
    assert fixed.reheat_request_w(0.0, 3000.0) == pytest.approx(600.0)


# ---- 整合：模擬器 ----


def _room_sim(table: CycleTable, scenario: str = "hot", hours: float = 2.0, start_h: float = 7.5, **settings):
    """建立房間模擬並執行。

參數：
    table: 性質表。
    scenario: 情境。
    hours: 時數。
    start_h: 起始時刻。
    settings: 設定覆寫（``reheat_mode``、``chw_reset`` 給房間模型）。

回傳：
    (模擬器, 房間, 記錄)。"""
    reheat_mode = settings.pop("reheat_mode", ReheatMode.FIXED)
    chw_reset = settings.pop("chw_reset", False)
    room = RoomModel(SCENARIOS[scenario], reheat_mode=reheat_mode, chw_reset=chw_reset)
    params = replace(HeatPumpParameters(), electrical=FULL_ELECTRICAL)
    sim = HeatPumpSimulation(table, params, replace(default_settings(OperationMode.COOLING), **settings),
                             initial_cold_k=celsius(12.0), room=room, start_time_s=start_h * 3600)
    return sim, room, sim.run(hours * 3600, 10.0)


def test_room_simulation_cools_and_dehumidifies(table: CycleTable) -> None:
    """高溫情境自 29 °C／65 % 起 2 h：室溫與濕度下降、盤管有顯冷與潛冷、記錄房間欄位。

回傳：
    無。"""
    sim, room, records = _room_sim(table, reheat_mode=ReheatMode.OFF)
    assert records[-1].room_k < celsius(27.5)
    assert records[-1].room_rh < 0.6
    assert any(r.coil_latent_w > 0 for r in records) and any(r.coil_sensible_w > 0 for r in records)
    first = next(r for r in records if r.fans_running)
    assert first.supply_k is not None and first.supply_k < first.room_k
    assert all(r.outdoor_k is not None and r.chw_setpoint_k == pytest.approx(celsius(7.0)) for r in records)


def test_fixed_reheat_warms_supply_and_room(table: CycleTable) -> None:
    """固定 20 % 再熱實際加回送風：同情境下室溫比不再熱高。

回傳：
    無。"""
    _, _, off = _room_sim(table, reheat_mode=ReheatMode.OFF)
    _, _, fixed = _room_sim(table, reheat_mode=ReheatMode.FIXED)
    assert sum(r.reheat_w for r in fixed) > 0
    assert fixed[-1].room_k > off[-1].room_k + 0.2


def test_system_disabled_outside_schedule(table: CycleTable) -> None:
    """排程外（18 時後）：壓縮機、水泵、送風機都停，耗電 0。

回傳：
    無。"""
    _, _, records = _room_sim(table, hours=1.0, start_h=18.5)
    assert all(not r.system_enabled and not r.compressor_on for r in records)
    assert all(r.total_power_w == 0.0 and r.cold_pump_hz == 0.0 and not r.fans_running for r in records)


def test_full_electrical_accounting(table: CycleTable) -> None:
    """全系統口徑：壓縮機電力含變頻器 96 %、待機 30 W；智慧冷房時計室外風扇 200 W。

回傳：
    無。"""
    _, _, records = _room_sim(table, hours=1.0)
    running = next(r for r in records if r.compressor_on)
    assert running.standby_power_w == 30.0
    smart = [r for r in records if r.compressor_on and r.mode.value == "smart_cooling"]
    dual = [r for r in records if r.compressor_on and r.mode.value == "dual"]
    assert all(r.outdoor_fan_power_w == 200.0 for r in smart)
    assert all(r.outdoor_fan_power_w == 0.0 for r in dual)


def test_idle_pump_off_stops_hot_pump_when_condenser_idle(table: CycleTable) -> None:
    """非必要迴路停泵：壓縮機停機或智慧冷房且無再熱時熱水泵為 0 Hz；壓縮機運轉於雙效時兩台都運轉。

回傳：
    無。"""
    _, _, records = _room_sim(table, hours=2.0, idle_pump_off=True, reheat_mode=ReheatMode.OFF)
    idle = [r for r in records[1:] if r.system_enabled and (not r.compressor_on or r.mode.value == "smart_cooling")]
    assert idle and all(r.hot_pump_hz == 0.0 and r.hot_pump_power_w == 0.0 for r in idle)
    dual = [r for r in records if r.compressor_on and r.mode.value == "dual"]
    assert dual and all(r.cold_pump_hz > 0 and r.hot_pump_hz > 0 for r in dual)


def test_chw_reset_raises_compressor_stop_temperature(table: CycleTable) -> None:
    """冰水重設時，壓縮機停機溫度跟著設定值移動（不再固定 7 °C）。

回傳：
    無。"""
    sim, _, records = _room_sim(table, scenario="mild", hours=6.0, start_h=8.0, chw_reset=True,
                                reheat_mode=ReheatMode.OFF)
    raised = [r for r in records if r.chw_setpoint_k > celsius(7.4)]
    assert raised
    stops = {e.time_s for e in sim.events if e.code == "stop"}
    stop_records = [r for r in records if r.time_s + r.dt_s in stops]
    # 每次停機時的冰水溫度都在當時設定值附近（不再固定 7 °C），且至少一次在 7.4 °C 以上停機。
    assert stop_records and all(abs(r.cold_water_k - r.chw_setpoint_k) < 0.3 for r in stop_records)
    assert any(r.cold_water_k > celsius(7.4) for r in stop_records)


def test_auto_pump_steps_up_when_comfort_tight(table: CycleTable) -> None:
    """水泵自動（房間模型）：送風機運轉且溫濕度（預測）接近上限時冰水泵不降階，並逐階升到 60 Hz；
    不再有固定 40 Hz 下限（只在溫濕度有餘裕時才降階）。

回傳：
    無。"""
    sim, room, records = _room_sim(table, scenario="hot", hours=1.0, start_h=8.0, pump_mode=PumpMode.AUTO,
                                   reheat_mode=ReheatMode.OFF)
    tight = [r for r in records if r.fans_running and r.room_k > celsius(26.5)]
    assert tight and max(r.cold_pump_hz for r in tight) == 60.0
    for a, b in zip(records, records[1:]):
        if a.fans_running and a.room_k > celsius(26.5):
            assert b.cold_pump_hz >= a.cold_pump_hz or b.cold_pump_hz == 0.0


def test_room_model_rejects_heating(table: CycleTable) -> None:
    """房間模型只支援冷房。

回傳：
    無。"""
    room = RoomModel(SCENARIOS["mild"])
    with pytest.raises(ValueError, match="只支援冷房"):
        HeatPumpSimulation(table, settings=default_settings(OperationMode.HEATING), room=room)


# ---- 比較框架 ----


def _result(key: str, energy: float, t_kh: float, rh_h: float, pulldown: float | None = 600.0) -> StrategyResult:
    """測試用結果。

參數：
    key: 策略代碼。
    energy: 修正後 kWh。
    t_kh: 溫度超標。
    rh_h: RH 高側超標。
    pulldown: 達標時間。

回傳：
    StrategyResult。"""
    return StrategyResult("hot", key, key, energy, energy, 0.0, 0, 0, 0, 0, 0, 0, 0, 0, t_kh, rh_h, 0.0,
                          celsius(26.5), celsius(25.5), 0.6, pulldown, 0, 0, 0, None, None, celsius(7.0))


def test_reference_is_more_comfortable_baseline_and_best_respects_comfort() -> None:
    """舒適基準取兩個基準候選中舒適度較好者；最佳策略只從舒適度不劣者中選最低用電。

回傳：
    無。"""
    rows = [
        _result("base", 45.0, 9.5, 0.0),
        _result("reheat_off", 38.0, 0.3, 0.0),
        _result("pump40", 30.0, 0.6, 0.0),  # 最省但室溫超標變差
        _result("combo", 32.0, 0.3, 0.5),
        _result("slow", 31.0, 0.3, 0.0, pulldown=900.0),  # 達標變慢
    ]
    assert reference_result(rows).strategy == "reheat_off"
    assert best_strategy(rows).strategy == "combo"
    assert not rows[2].comfort_ok(rows[1]) and not rows[4].comfort_ok(rows[1], ComfortTolerance())


def test_absolute_threshold_and_validity_gate_the_ranking() -> None:
    """與基準一樣差不算達標：全部超過絕對門檻時沒有 ⭐，只有條件式排名；數值檢查失敗者不列入。

回傳：
    無。"""
    hot = [_result("base", 45.0, 9.5, 0.0), _result("reheat_off", 38.0, 0.8, 0.0), _result("combo", 33.0, 0.8, 0.0)]
    assert best_strategy(hot) is None
    assert best_relative_only(hot).strategy == "combo"
    from dataclasses import replace as dc_replace

    broken = dc_replace(_result("combo", 30.0, 0.3, 0.0), coil_check_failures=3)
    ok = [_result("reheat_off", 38.0, 0.3, 0.0), broken]
    assert best_strategy(ok).strategy == "reheat_off"
    unconverged = dc_replace(_result("combo", 30.0, 0.3, 0.0), periodic=False)
    assert not unconverged.valid


def test_single_strategies_inherit_reference_reheat() -> None:
    """單一策略疊在舒適基準的再熱方式上；組合與基準不受影響。

回傳：
    無。"""
    by_key = {s.key: s for s in STRATEGIES}
    pump = by_key["pump40"].layered_on(by_key["base"])
    assert pump.reheat_mode is ReheatMode.FIXED and pump.settings["cold_pump_hz"] == 40.0
    assert by_key["pump40"].layered_on(by_key["reheat_off"]).reheat_mode is ReheatMode.OFF
    assert by_key["combo"].layered_on(by_key["base"]).reheat_mode is ReheatMode.DEMAND
    assert Strategy("x", "x").layered_on(by_key["reheat_off"]).reheat_mode is ReheatMode.FIXED


def test_reference_counts_over_drying_as_discomfort() -> None:
    """兩個基準候選溫度都不超標時，過度除濕（RH < 50 %）較多者不當舒適基準。

回傳：
    無。"""
    from dataclasses import replace as dc_replace

    base = dc_replace(_result("base", 31.0, 0.0, 0.0), humidity_low_pct_h=31.2)
    off = dc_replace(_result("reheat_off", 26.2, 0.0, 0.0), humidity_low_pct_h=3.5)
    assert reference_result([base, off]).strategy == "reheat_off"


# ---- 第三輪（§8.12.8）：協調除濕與低濕側門檻 ----


def test_absolute_threshold_rejects_over_drying() -> None:
    """絕對門檻含低濕側：RH<50 % 超標 > 5 %·h 或最低 RH < 45 % 不算達標（D5 的 46 %／全程低於帶即被擋）。

回傳：
    無。"""
    ok = replace(_result("a", 30.0, 0.0, 0.0), min_rh=0.52)
    assert ok.absolute_ok()
    assert not replace(ok, humidity_low_pct_h=20.0).absolute_ok()
    assert not replace(ok, min_rh=0.44).absolute_ok()
    base = replace(ok, humidity_low_pct_h=1.0)
    assert not replace(ok, humidity_low_pct_h=3.0).comfort_ok(base)


def test_coordinated_dehumidification_enters_and_exits() -> None:
    """協調除濕：含濕量高於上限進入除濕狀態（送風機全開、依室溫補熱、冰水降到下限）；
    含濕量回到目標帶中間（約 55 %RH）才退出，退出後不再熱；非協調模式不會進入除濕狀態。

回傳：
    無。"""
    c = IndoorControlParameters()
    room = RoomModel(SCENARIOS["humid"], reheat_mode=ReheatMode.COORDINATED, chw_reset=True,
                     initial_k=celsius(25.8), initial_rh=0.68)
    room._indoor.chw_setpoint_k = celsius(9.0)
    room.update_fans(8 * 3600.0, frozenset({"A", "B"}), True)
    assert room.dehum_mode and room.fans_on == frozenset({"A", "B"})
    assert room.reheat_request_w(8 * 3600.0, 5000.0) == pytest.approx(c.reheat_gain_w_k * (c.reheat_target_k - celsius(25.8)))
    room.update_chw_setpoint(8 * 3600.0, True)
    assert room.chw_setpoint_k == pytest.approx(c.chw_min_k)
    # 濕度降到 56 %（仍高於退出門檻）：維持除濕
    room.state = replace(room.state, humidity_ratio=psy.humidity_ratio(celsius(26.0), 0.565))
    room.update_fans(8 * 3600.0 + c.dehum_min_s, frozenset({"A", "B"}), True)
    assert room.dehum_mode
    # 降到 54 %：退出，不再熱
    room.state = replace(room.state, humidity_ratio=psy.humidity_ratio(celsius(26.0), 0.54))
    room.update_fans(8 * 3600.0 + 2 * c.dehum_min_s, frozenset({"A", "B"}), True)
    assert not room.dehum_mode
    assert room.reheat_request_w(8 * 3600.0 + 2 * c.dehum_min_s, 5000.0) == 0.0
    demand = RoomModel(SCENARIOS["humid"], reheat_mode=ReheatMode.DEMAND, initial_k=celsius(25.8), initial_rh=0.68)
    demand.update_fans(8 * 3600.0, frozenset({"A", "B"}), True)
    assert not demand.dehum_mode
