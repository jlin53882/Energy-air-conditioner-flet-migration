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
    best_strategy,
    reference_result,
)
from domain.heat_pump.parameters import FULL_ELECTRICAL, HeatPumpParameters
from domain.heat_pump.room import DEFAULT_COILS, SCENARIOS, IndoorControlParameters, ReheatMode, RoomModel
from domain.heat_pump.wet_coil import coil_performance, counterflow_effectiveness, water_side_ua
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
    """盤管 B 對表 8.1.1 每一點的空氣側冷量誤差 ≤ 6 %（擬合點）。

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
    assert water_side_ua(COIL_B, 0.31) == pytest.approx(COIL_B.water_side_ua_w_k * 0.5 ** 0.5)


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
    """空氣側焓降 = 水側得熱；進水高於露點時為乾盤管（潛冷 0）；無水量時無熱傳。

回傳：
    無。"""
    w = psy.humidity_ratio(celsius(27.0), 0.6)
    r = coil_performance(COIL_B, celsius(27.0), w, celsius(7.0), 0.62)
    air_side = COIL_B.air_flow_kg_s * (psy.enthalpy_j_kg(celsius(27.0), w)
                                       - psy.enthalpy_j_kg(r.air_out_k, r.air_out_humidity_ratio))
    assert air_side == pytest.approx(r.total_w, rel=0.03)
    assert r.total_w == pytest.approx(0.62 * 4186 * (r.water_out_k - celsius(7.0)), rel=1e-6)
    dry_w = psy.humidity_ratio(celsius(26.0), 0.3)
    dry = coil_performance(COIL_B, celsius(26.0), dry_w, celsius(14.0), 0.62)
    assert not dry.wet and dry.latent_w == 0.0 and dry.total_w > 0
    assert coil_performance(COIL_B, celsius(27.0), w, celsius(7.0), 0.0).total_w == 0.0


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


def test_scenario_schedule_and_profiles() -> None:
    """外氣 14 時最高；日照 07–18 時；午休人數減半；空調 07:30 啟用。

回傳：
    無。"""
    sc = SCENARIOS["hot"]
    assert sc.outdoor_k(14 * 3600) - K == pytest.approx(35.0)
    assert sc.outdoor_k(2 * 3600) - K == pytest.approx(28.0)
    assert sc.solar_w(3 * 3600) == 0.0 and sc.solar_w(12.5 * 3600) == pytest.approx(1200.0)
    assert sc.people_count(12.5 * 3600) == 3 and sc.people_count(9 * 3600) == 6
    assert not sc.system_enabled(7.4 * 3600) and sc.system_enabled(7.5 * 3600)
    assert sc.occupied(24 * 3600 + 9 * 3600)


def test_fan_staging_keeps_one_fan_when_humid() -> None:
    """室溫低於下限時關送風機，但濕度高於上限時至少保留一台（B）。

回傳：
    無。"""
    control = IndoorControlParameters()
    dry = RoomModel(SCENARIOS["mild"], initial_k=celsius(25.0), initial_rh=0.5)
    dry.update_fans(0.0, frozenset({"A", "B"}), True)
    assert dry.fans_on == frozenset()
    humid = RoomModel(SCENARIOS["mild"], initial_k=celsius(25.0), initial_rh=0.7)
    humid.update_fans(0.0, frozenset({"A", "B"}), True)
    assert humid.fans_on == frozenset({"B"})
    hot = RoomModel(SCENARIOS["mild"], initial_k=control.stage2_on_k + 0.1)
    hot.update_fans(0.0, frozenset({"A", "B"}), True)
    assert hot.fans_on == frozenset({"A", "B"})
    hot.update_fans(1.0, frozenset({"A", "B"}), False)
    assert hot.fans_on == frozenset()


def test_chw_reset_moves_setpoint_with_humidity() -> None:
    """冰水重設：乾且不熱時每 5 min 升 0.5 K（上限 10 °C）；濕度偏高時降。

回傳：
    無。"""
    room = RoomModel(SCENARIOS["mild"], chw_reset=True, initial_k=celsius(26.0), initial_rh=0.5)
    for i in range(10):
        room.update_chw_setpoint(i * 300.0, True)
    assert room.chw_setpoint_k == pytest.approx(celsius(10.0))
    room.state.humidity_ratio = psy.humidity_ratio(celsius(26.0), 0.65)
    room.update_chw_setpoint(4000.0, True)
    assert room.chw_setpoint_k == pytest.approx(celsius(9.5))
    fixed = RoomModel(SCENARIOS["mild"], chw_reset=False)
    assert fixed.update_chw_setpoint(0.0, True) == pytest.approx(celsius(7.0))


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
    _, _, records = _room_sim(table, scenario="mild", hours=3.0, start_h=8.0, chw_reset=True,
                              reheat_mode=ReheatMode.OFF)
    assert max(r.chw_setpoint_k for r in records) > celsius(7.4)
    later = [r for r in records if r.time_s > 9.5 * 3600]
    assert min(r.cold_water_k for r in later) > celsius(7.2)


def test_auto_pump_respects_comfort_floor(table: CycleTable) -> None:
    """水泵自動（房間模型）：送風機運轉時冰水泵不低於 40 Hz。

回傳：
    無。"""
    _, _, records = _room_sim(table, scenario="mild", hours=2.0, start_h=8.0, pump_mode=PumpMode.AUTO,
                              reheat_mode=ReheatMode.OFF)
    assert all(r.cold_pump_hz >= 40.0 for r in records if r.fans_running and r.cold_pump_hz > 0)


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
