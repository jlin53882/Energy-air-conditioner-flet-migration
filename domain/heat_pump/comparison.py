"""節能策略比較：相同日負載與舒適度條件下比較全系統用電（``docs/simulation-model.md`` §8.7）。

做法：
- 每個策略從相同初始狀態（室內 29 °C／65 %RH、冰水桶 12 °C、熱水桶 30 °C、0 時）連跑兩天，
  第一天量「達標時間」，第二天統計用電與舒適度（第一天消除房間與水桶熱容的初值差）。
- 第二天開始與結束的水桶與房間儲能差，以當次的主機冷房 COP 換算成電能修正。
- 只在舒適度指標不比**舒適基準**差（容許值見 ``ComfortTolerance``）的策略中選用電最低者。
  舒適基準取「現行預設（固定 20 % 再熱）」與「現行預設但再熱關閉」中舒適度較好者：高溫情境固定再熱
  會把室溫推高到帶外，高濕低負載情境不再熱則會過冷，兩者都不能單獨當作參考（§8.7）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from .cycle_table import CycleTable
from .parameters import FULL_ELECTRICAL, HeatPumpParameters, celsius
from .room import HOUR_S, DailyScenario, IndoorControlParameters, ReheatMode, RoomModel, RoomParameters
from .simulation import (
    FrequencyMode,
    HeatPumpSimulation,
    OperationMode,
    PumpMode,
    SimulationSettings,
    StepRecord,
    default_settings,
)

DAY_S = 24 * HOUR_S


@dataclass(frozen=True)
class Strategy:
    """一組控制策略（相對於預設設定的覆寫）。"""

    key: str
    name: str
    settings: dict = field(default_factory=dict)
    reheat_mode: ReheatMode = ReheatMode.FIXED
    reheat_fraction: float = 0.2
    chw_reset: bool = False
    # 單一策略的再熱方式沿用該情境的舒適基準（見 ``layered_on``），才是同條件比較。
    inherit_reheat: bool = False

    def layered_on(self, reference: Strategy) -> Strategy:
        """把單一策略疊在舒適基準的再熱方式上。

參數：
    reference: 舒適基準策略。

回傳：
    Strategy（``inherit_reheat`` 為假時原樣回傳）。"""
        if not self.inherit_reheat:
            return self
        return replace(self, reheat_mode=reference.reheat_mode, reheat_fraction=reference.reheat_fraction)


STRATEGIES: tuple[Strategy, ...] = (
    Strategy("base", "現行預設：水泵 60 Hz、冰水 7 °C、固定 20 % 再熱、壓縮機 PID"),
    Strategy("reheat_off", "現行預設但再熱關閉", reheat_mode=ReheatMode.OFF),
    Strategy("reheat_demand", "按需再熱", reheat_mode=ReheatMode.DEMAND),
    Strategy("pump50", "水泵 50 Hz", {"cold_pump_hz": 50.0, "hot_pump_hz": 50.0}, inherit_reheat=True),
    Strategy("pump40", "水泵 40 Hz", {"cold_pump_hz": 40.0, "hot_pump_hz": 40.0}, inherit_reheat=True),
    Strategy("pump_auto", "水泵依需求調速（含舒適度保護）", {"pump_mode": PumpMode.AUTO}, inherit_reheat=True),
    Strategy("chw_reset", "冰水溫度重設 7–10 °C", chw_reset=True, inherit_reheat=True),
    Strategy("idle_pump_off", "非必要迴路停泵", {"idle_pump_off": True}, inherit_reheat=True),
    Strategy("comp_fixed60", "壓縮機固定 60 Hz 啟停", {"frequency_mode": FrequencyMode.MANUAL,
                                                     "manual_frequency_hz": 60.0}, inherit_reheat=True),
    Strategy("combo", "組合：水泵自動＋冰水重設＋按需再熱＋停泵",
             {"pump_mode": PumpMode.AUTO, "idle_pump_off": True}, reheat_mode=ReheatMode.DEMAND, chw_reset=True),
)


@dataclass(frozen=True)
class ComfortTolerance:
    """「不比基準差」的容許值。"""

    temperature_kh: float = 0.1
    humidity_high_pct_h: float = 1.0
    pulldown_s: float = 60.0


@dataclass(frozen=True)
class StrategyResult:
    """單一策略、單一情境的結果（第二天統計，除達標時間外）。"""

    scenario: str
    strategy: str
    name: str
    energy_kwh: float
    corrected_energy_kwh: float
    storage_correction_kwh: float
    compressor_kwh: float
    pump_kwh: float
    fan_kwh: float
    outdoor_fan_kwh: float
    other_kwh: float
    sensible_kwh: float
    latent_kwh: float
    reheat_kwh: float
    temperature_exceed_kh: float
    humidity_high_pct_h: float
    humidity_low_pct_h: float
    max_temperature_k: float
    min_temperature_k: float
    max_rh: float
    pulldown_s: float | None
    compressor_starts: int
    fan_switches: int
    protection_events: int
    chiller_cop: float | None
    system_cop: float | None
    mean_chw_setpoint_k: float

    def comfort_ok(self, base: StrategyResult, tol: ComfortTolerance | None = None) -> bool:
        """舒適度是否不比基準差（溫度超標、濕度高側超標、達標時間）。

參數：
    base: 基準結果。
    tol: 容許值。

回傳：
    bool。"""
        tol = tol or ComfortTolerance()
        if self.temperature_exceed_kh > base.temperature_exceed_kh + tol.temperature_kh:
            return False
        if self.humidity_high_pct_h > base.humidity_high_pct_h + tol.humidity_high_pct_h:
            return False
        if base.pulldown_s is not None and (self.pulldown_s is None or self.pulldown_s > base.pulldown_s + tol.pulldown_s):
            return False
        return True


def _pulldown_s(records: list[StepRecord], control: IndoorControlParameters, start_s: float) -> float | None:
    """達標時間：自系統啟用起，室溫進入設定帶且 RH ≤ 上限並維持 5 min 所需時間。

參數：
    records: 第一天記錄。
    control: 室內控制器參數。
    start_s: 系統啟用時刻。

回傳：
    s；當天未達標為 None。"""
    held = 0.0
    for r in records:
        if r.time_s < start_s or r.room_k is None or r.room_rh is None:
            continue
        ok = abs(r.room_k - control.setpoint_k) <= control.band_k and r.room_rh <= control.rh_high
        held = held + r.dt_s if ok else 0.0
        if held >= 300.0:
            return r.time_s + r.dt_s - 300.0 - start_s
    return None


def evaluate(records: list[StepRecord], events: list, scenario_key: str, strategy: Strategy, room: RoomModel,
             params: HeatPumpParameters, day_start_s: float, pulldown_s: float | None,
             start_state: tuple[float, float, float]) -> StrategyResult:
    """彙整第二天的指標。

參數：
    records: 第二天記錄。
    events: 全部事件。
    scenario_key: 情境代碼。
    strategy: 策略。
    room: 房間模型（取參數）。
    params: 系統參數。
    day_start_s: 第二天起始時刻。
    pulldown_s: 第一天的達標時間。
    start_state: 第二天開始時的（冰水桶 K, 熱水桶 K, 室溫 K）。

回傳：
    StrategyResult。"""
    c = room.control
    kwh = 1.0 / 3.6e6
    occ = [r for r in records if r.occupied]
    energy = sum(r.total_power_w * r.dt_s for r in records) * kwh
    compressor = sum(r.compressor_power_w * r.dt_s for r in records) * kwh
    pumps = sum(r.pump_power_w * r.dt_s for r in records) * kwh
    fans = sum(r.fan_power_w * r.dt_s for r in records) * kwh
    outdoor = sum(r.outdoor_fan_power_w * r.dt_s for r in records) * kwh
    other = sum(r.standby_power_w * r.dt_s for r in records) * kwh
    evap = sum(r.cooling_w * r.dt_s for r in records if r.mode.value != "smart_heating") * kwh
    chiller_cop = evap / compressor if compressor > 0 else None
    # 儲能修正：第二天結束比開始「欠」的冷量（冰水桶、房間變暖為正）以主機冷房 COP 換成電能。
    end = records[-1]
    cold_c = params.cold_tank.heat_capacity_j_k
    owed_j = cold_c * (end.cold_water_k - start_state[0]) + room.params.heat_capacity_j_k * (end.room_k - start_state[2])
    correction = owed_j * kwh / chiller_cop if chiller_cop else 0.0
    upper, lower = c.setpoint_k + c.band_k, c.setpoint_k - c.band_k
    t_exceed = sum((max(0.0, r.room_k - upper) + max(0.0, lower - r.room_k)) * r.dt_s for r in occ) / HOUR_S
    rh_high = sum(max(0.0, r.room_rh - c.rh_high) * 100 * r.dt_s for r in occ) / HOUR_S
    rh_low = sum(max(0.0, c.rh_low - r.room_rh) * 100 * r.dt_s for r in occ) / HOUR_S
    end_s = day_start_s + DAY_S
    in_day = [e for e in events if day_start_s <= e.time_s < end_s]
    fan_switches = sum(1 for a, b in zip(records, records[1:]) if a.fans_running != b.fans_running)
    fan_coil = sum(r.fan_coil_load_w * r.dt_s for r in records) * kwh
    return StrategyResult(
        scenario=scenario_key, strategy=strategy.key, name=strategy.name,
        energy_kwh=energy, corrected_energy_kwh=energy + correction, storage_correction_kwh=correction,
        compressor_kwh=compressor, pump_kwh=pumps, fan_kwh=fans, outdoor_fan_kwh=outdoor, other_kwh=other,
        sensible_kwh=sum(r.coil_sensible_w * r.dt_s for r in records) * kwh,
        latent_kwh=sum(r.coil_latent_w * r.dt_s for r in records) * kwh,
        reheat_kwh=sum(r.reheat_w * r.dt_s for r in records) * kwh,
        temperature_exceed_kh=t_exceed, humidity_high_pct_h=rh_high, humidity_low_pct_h=rh_low,
        max_temperature_k=max(r.room_k for r in occ), min_temperature_k=min(r.room_k for r in occ),
        max_rh=max(r.room_rh for r in occ), pulldown_s=pulldown_s,
        compressor_starts=sum(1 for e in in_day if e.code == "start"),
        fan_switches=fan_switches,
        protection_events=sum(1 for e in in_day if e.code in {"trip", "freeze_stop", "hp_preempt"}),
        chiller_cop=chiller_cop,
        system_cop=fan_coil / (energy + correction) if energy + correction > 0 else None,
        mean_chw_setpoint_k=sum(r.chw_setpoint_k * r.dt_s for r in occ) / sum(r.dt_s for r in occ),
    )


def run_strategy(table: CycleTable, scenario_key: str, scenario: DailyScenario, strategy: Strategy,
                 params: HeatPumpParameters | None = None, room_params: RoomParameters | None = None,
                 control: IndoorControlParameters | None = None, fans: frozenset[str] = frozenset({"A", "B"}),
                 dt_s: float = 5.0, progress: Callable[[float], None] | None = None) -> StrategyResult:
    """執行一個策略兩天並回傳第二天的結果。

參數：
    table: 性質表。
    scenario_key: 情境代碼。
    scenario: 日負載情境。
    strategy: 策略。
    params: 系統參數（預設為 ``FULL_ELECTRICAL`` 全系統耗電口徑）。
    room_params: 房間參數。
    control: 室內控制器參數。
    fans: 可用送風機。
    dt_s: 時間步長。
    progress: 進度回呼（0–1）。

回傳：
    StrategyResult。"""
    params = params or replace(HeatPumpParameters(), electrical=FULL_ELECTRICAL)
    room = RoomModel(scenario, room_params, control, reheat_mode=strategy.reheat_mode,
                     reheat_fraction=strategy.reheat_fraction, chw_reset=strategy.chw_reset,
                     initial_k=celsius(29.0), initial_rh=0.65)
    settings: SimulationSettings = replace(default_settings(OperationMode.COOLING), fans=fans, **strategy.settings)
    sim = HeatPumpSimulation(table, params, settings, initial_cold_k=celsius(12.0), initial_hot_k=celsius(30.0),
                             room=room, start_time_s=0.0)
    day1 = sim.run(DAY_S, dt_s)
    if progress:
        progress(0.5)
    start_state = (sim.cold_water_k, sim.hot_water_k, room.state.temperature_k)
    day2 = sim.run(DAY_S, dt_s)
    if progress:
        progress(1.0)
    enable_s = (scenario.occupied_hours[0] - scenario.precool_h) * HOUR_S
    pulldown = _pulldown_s(day1, room.control, enable_s)
    return evaluate(day2, sim.events, scenario_key, strategy, room, params, DAY_S, pulldown, start_state)


REFERENCE_CANDIDATES = ("base", "reheat_off")


def comfort_score(result: StrategyResult) -> float:
    """舒適度綜合分數（溫度超標 K·h ＋ RH 高側超標 %·h ÷ 10；越小越好），用來挑舒適基準。

參數：
    result: 結果。

回傳：
    分數。"""
    return result.temperature_exceed_kh + result.humidity_high_pct_h / 10.0


def reference_result(results: list[StrategyResult]) -> StrategyResult | None:
    """舒適基準：「現行預設」與「現行預設但再熱關閉」兩者中舒適度較好者（依情境而定）。

參數：
    results: 同一情境的結果。

回傳：
    StrategyResult；兩者都沒有時為 None。"""
    candidates = [r for r in results if r.strategy in REFERENCE_CANDIDATES]
    return min(candidates, key=comfort_score) if candidates else None


def best_strategy(results: list[StrategyResult], tol: ComfortTolerance | None = None) -> StrategyResult | None:
    """舒適度不比舒適基準差的策略中，修正後用電最低者（舒適基準本身也是候選）。

參數：
    results: 同一情境的結果（須含 ``base`` 或 ``reheat_off``）。
    tol: 容許值。

回傳：
    StrategyResult；沒有舒適基準時為 None。"""
    base = reference_result(results)
    if base is None:
        return None
    candidates = [r for r in results if r.comfort_ok(base, tol)]
    return min(candidates, key=lambda r: r.corrected_energy_kwh)


__all__ = [
    "DAY_S",
    "REFERENCE_CANDIDATES",
    "STRATEGIES",
    "ComfortTolerance",
    "Strategy",
    "StrategyResult",
    "best_strategy",
    "comfort_score",
    "reference_result",
    "evaluate",
    "run_strategy",
]
