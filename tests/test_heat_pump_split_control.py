"""冷房目標分離控制與控制診斷（``docs/simulation-model.md`` §8.12）。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from domain.heat_pump import (
    CoolingControlMode,
    CycleTable,
    HeatPumpParameters,
    HeatPumpSimulation,
    OperationMode,
    PidController,
    celsius,
    default_settings,
)
from domain.heat_pump.comparison import max_in_window, run_lengths_s
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter

HOUR = 3600.0
_RUNS: dict = {}


@pytest.fixture(scope="module")
def table() -> CycleTable:
    """模組共用的性質表。

回傳：
    CycleTable。"""
    return CycleTable.build(ThermodynamicStateService(CanonicalUnitConverter()))


def _run(table: CycleTable, mode: CoolingControlMode, fans: frozenset[str], hours: float = 3.0):
    """冷房 3 h（起始 30／30 °C），相同參數只算一次。

參數：
    table: 性質表。
    mode: 冷房控制架構。
    fans: 送風機。
    hours: 時數。

回傳：
    (模擬器, 記錄)。"""
    key = (mode, tuple(sorted(fans)), hours)
    if key not in _RUNS:
        params = HeatPumpParameters()
        params = replace(params, control=replace(params.control, cooling_control_mode=mode))
        settings = replace(default_settings(OperationMode.COOLING), fans=fans)
        sim = HeatPumpSimulation(table, params, settings, initial_cold_k=celsius(30.0), initial_hot_k=celsius(30.0))
        _RUNS[key] = (sim, sim.run(hours * HOUR))
    return _RUNS[key]


# ---- PID 單元 ----


def test_directional_anti_windup_unwinds_when_saturated_high() -> None:
    """輸出超上限且誤差反向時：舊做法（條件式）不積分，方向性抗飽和會讓積分退回。

回傳：
    無。"""
    legacy = PidController(kp=10.0, ti_s=100.0, td_s=0.0, out_min=30.0, out_max=60.0, bias=30.0, integral=40.0)
    split = PidController(kp=10.0, ti_s=100.0, td_s=0.0, out_min=30.0, out_max=60.0, bias=30.0, integral=40.0,
                          directional_anti_windup=True)
    legacy.update(-0.5, 10.0)
    split.update(-0.5, 10.0)
    assert legacy.integral == 40.0
    assert split.integral < 30.0 + 1e-9  # 先夾到上限 − bias = 30，再退回


def test_directional_anti_windup_clamps_integral_to_dynamic_limit() -> None:
    """限頻上限降低時，積分不超過「上限 − bias」，並受下限保護。

回傳：
    無。"""
    pid = PidController(kp=10.0, ti_s=50.0, td_s=0.0, out_min=0.0, out_max=60.0, bias=30.0,
                        directional_anti_windup=True, integral_min=-5.0)
    for _ in range(100):
        pid.update(0.5, 10.0, out_max=40.0)
    assert pid.integral <= 10.0 + 1e-9
    for _ in range(200):
        pid.update(-0.5, 10.0)
    assert pid.integral == pytest.approx(-5.0)


def test_derivative_on_measurement_ignores_setpoint_step() -> None:
    """目標值階躍（冰水重設）時，對量測值微分不產生突跳；對誤差微分會。

回傳：
    無。"""
    kwargs = dict(kp=10.0, ti_s=0.0, td_s=30.0, out_min=0.0, out_max=200.0, bias=30.0)
    on_error = PidController(**kwargs)
    on_pv = PidController(**kwargs, derivative_on_measurement=True)
    pv = celsius(9.0)
    for target in (celsius(7.0), celsius(7.0), celsius(10.0)):
        a = on_error.update(pv - target, 5.0)
        b = on_pv.update(pv - target, 5.0, measurement=pv)
    assert b == pytest.approx(20.0)  # 量測值不變 → 微分 0；誤差 −1 K → 30 − 10
    assert a < b - 50.0 or a == 0.0  # 對誤差微分：3 K 階躍造成大幅負向突跳（夾到下限 0）


def test_rolling_window_and_run_lengths() -> None:
    """滾動一小時最多啟動次數（雙指標）與連續運轉時間（不含被截斷的段）。

回傳：
    無。"""
    assert max_in_window([]) == 0
    assert max_in_window([0.0, 100.0, 3599.0, 3600.0, 7300.0]) == 3
    assert max_in_window([0.0, 3600.0, 7200.0]) == 1

    class R:
        def __init__(self, on: bool) -> None:
            self.compressor_on = on
            self.dt_s = 10.0

    pattern = [True, True, False, True, True, True, False, False, True]
    assert run_lengths_s([R(on) for on in pattern]) == [30.0]


# ---- 模擬 ----


def test_legacy_mode_is_default_and_unchanged(table: CycleTable) -> None:
    """預設為 LEGACY：PID 目標 = 停機點 7 °C，桶溫 ≤ 7 °C 立即停機。

回傳：
    無。"""
    assert HeatPumpParameters().control.cooling_control_mode is CoolingControlMode.LEGACY
    sim, records = _run(table, CoolingControlMode.LEGACY, frozenset({"A", "B"}))
    assert all(r.chw_target_k == pytest.approx(celsius(7.0)) for r in records)
    stops = [e for e in sim.events if e.code == "stop"]
    assert stops
    for event in stops:
        before = next(r for r in reversed(records) if r.time_s < event.time_s)
        assert before.cold_water_k <= celsius(7.0) + 0.3


def test_split_mode_modulates_instead_of_cycling_with_both_fans(table: CycleTable) -> None:
    """A+B（負荷介於最低與最高能力之間）：目標分離後連續運轉、桶溫貼近 7.5 °C、PID 出現負誤差並降載，
    系統 COP 高於 LEGACY。

回傳：
    無。"""
    sim_l, legacy = _run(table, CoolingControlMode.LEGACY, frozenset({"A", "B"}))
    sim_s, split = _run(table, CoolingControlMode.SPLIT, frozenset({"A", "B"}))
    late = [r for r in split if r.time_s >= HOUR]
    assert all(r.chw_target_k == pytest.approx(celsius(7.5)) for r in late)
    assert sum(1 for e in sim_s.events if e.code == "start" and e.time_s >= HOUR) < sum(
        1 for e in sim_l.events if e.code == "start" and e.time_s >= HOUR)
    assert all(celsius(6.9) < r.cold_water_k < celsius(8.1) for r in late)
    running = [r for r in late if r.compressor_on]
    assert any(r.frequency_hz < 60.0 for r in running)
    assert any(r.cold_water_k < celsius(7.5) and r.pid_request_hz < 60.0 for r in running)

    def cop(records):
        load = sum(r.fan_coil_load_w * r.dt_s for r in records if r.time_s >= HOUR)
        power = sum(r.total_power_w * r.dt_s for r in records if r.time_s >= HOUR)
        return load / power

    assert cop(split) > cop(legacy)


def test_split_mode_stops_only_at_minimum_step_after_hold(table: CycleTable) -> None:
    """負荷低於最低能力（只開 A）：一般停機前一定已在最低階；重啟仍需 ≥ 8 °C；不觸發防凍停機。

回傳：
    無。"""
    sim, records = _run(table, CoolingControlMode.SPLIT, frozenset({"A"}))
    control = sim.params.control
    stops = [e for e in sim.events if e.code == "stop" and e.time_s > HOUR]
    assert stops and not any(e.code == "freeze_stop" for e in sim.events)
    for event in stops:
        before = next(r for r in reversed(records) if r.time_s < event.time_s)
        backstop = before.cold_water_k <= celsius(7.0) - control.cooling_stop_backstop_k + 0.05
        assert before.frequency_hz == 30.0 or backstop
    starts = [e for e in sim.events if e.code == "start"]
    restart_temps = [next(r for r in records if r.time_s + r.dt_s >= e.time_s).cold_water_k for e in starts]
    assert restart_temps and all(t >= celsius(8.0) - 0.05 for t in restart_temps)


def test_startup_loss_ramps_capacity_and_costs_tau_seconds(table: CycleTable) -> None:
    """啟停損失：重啟後冷量以 1 − e^(−t/τ) 爬升、耗電全額；每次啟動累計損失 τ 秒的滿載冷量；
    模擬起點即運轉時不扣。

回傳：
    無。"""
    params = HeatPumpParameters()
    params = replace(params, control=replace(params.control, startup_capacity_tau_s=60.0))
    settings = replace(default_settings(OperationMode.COOLING), fans=frozenset({"A"}))
    sim = HeatPumpSimulation(table, params, settings, initial_cold_k=celsius(30.0), initial_hot_k=celsius(30.0))
    base = HeatPumpSimulation(table, HeatPumpParameters(), settings, initial_cold_k=celsius(30.0),
                              initial_hot_k=celsius(30.0))
    assert sim.step().cooling_w == pytest.approx(base.step().cooling_w)  # 模擬起點即運轉：不扣
    records = sim.run(HOUR)
    start = next(e for e in sim.events if e.code == "start")
    first = next(r for r in records if r.time_s >= start.time_s - 1e-9)
    later = next(r for r in records if r.time_s >= start.time_s + 120.0)
    assert first.compressor_on and first.cooling_w < 0.1 * later.cooling_w
    assert first.compressor_power_w > 0.8 * later.compressor_power_w

    # 積分損失：固定運轉點逐步推進，Σ(1 − factor)·dt = τ。
    perf = sim._solver.solve(sim._conditions(60.0))
    sim._ctrl.on_since_s = sim.time_s
    lost = 0.0
    t = sim.time_s
    for _ in range(200):
        lost += (1.0 - sim._apply_startup_loss(perf, 5.0).cooling_w / perf.cooling_w) * 5.0
        sim.time_s += 5.0
    sim.time_s = t
    assert lost == pytest.approx(60.0, rel=1e-3)
