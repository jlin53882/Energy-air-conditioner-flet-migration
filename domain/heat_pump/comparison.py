"""節能策略比較：相同日負載、通風與舒適度條件下比較全系統用電（``docs/simulation-model.md`` §8.6–§8.7）。

做法：
- 每個策略從相同初始狀態（0 時，室內 29 °C／65 %RH、冰水桶 12 °C、熱水桶 30 °C）開始，第一天量「達標時間」；
  之後**重複同一日工況，直到週期穩態**，以**最後兩天的平均**統計（用電、超標量、啟動次數都是每日平均）。
  兩個水桶在啟停遲滯帶內循環，停機時的相位每天不同，有時形成兩天一循環（例如熱水桶相位決定隔天再熱量），
  所以收斂判定比較「相隔兩天」的狀態：室溫、含濕量接近，水桶溫差在遲滯帶寬度內，且相隔兩天的單日用電差 ≤ 1 %。
  殘留影響以「殘差修正」與「日間變動」兩欄量化，策略間差距小於日間變動時不視為有意義。
  這取代「跑兩天＋以平均 COP 換算儲能差」：COP 換算只能粗估，房間溫差也會改變整天外殼負荷。
  最後一天的殘留儲能差仍以主機 COP 換算列出（診斷用，不計入排名）。
- 舒適度判定分兩層：**絕對門檻**（``AbsoluteComfort``）與**不劣於舒適基準**（``ComfortTolerance``）。
  舒適基準取「現行預設（固定 20 % 再熱）」與「現行預設但再熱關閉」中舒適度較好者。
- 只在兩層都通過、盤管不變量檢查無違反的策略中，選全系統用電最低者；沒有任何策略通過絕對門檻時，明確標示。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from .cycle_table import CycleTable
from .parameters import FULL_ELECTRICAL, HeatPumpParameters, celsius
from .room import (
    DEFAULT_COILS,
    HOUR_S,
    DailyScenario,
    IndoorControlParameters,
    ReheatMode,
    RoomModel,
    RoomParameters,
)
from .simulation import (
    FrequencyMode,
    HeatPumpSimulation,
    OperationMode,
    PumpMode,
    SimulationSettings,
    StepRecord,
    default_settings,
)
from .wet_coil import CoilParameters

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
    Strategy("pump_auto", "水泵最佳化：依需求調速（舒適度餘裕控制）", {"pump_mode": PumpMode.AUTO}, inherit_reheat=True),
    Strategy("chw_reset", "冰水溫度重設 7–10 °C", chw_reset=True, inherit_reheat=True),
    Strategy("idle_pump_off", "非必要迴路停泵", {"idle_pump_off": True}, inherit_reheat=True),
    Strategy("comp_fixed60", "壓縮機固定 60 Hz 啟停", {"frequency_mode": FrequencyMode.MANUAL,
                                                     "manual_frequency_hz": 60.0}, inherit_reheat=True),
    Strategy("combo3", "水泵＋冰水重設＋按需再熱", {"pump_mode": PumpMode.AUTO},
             reheat_mode=ReheatMode.DEMAND, chw_reset=True),
    Strategy("combo", "水泵＋冰水重設＋按需再熱＋停泵",
             {"pump_mode": PumpMode.AUTO, "idle_pump_off": True}, reheat_mode=ReheatMode.DEMAND, chw_reset=True),
)

# Codex 建議的三組核心比較：基準、水泵最佳化、水泵＋冰水重設＋按需再熱。
CORE_STRATEGIES: tuple[str, ...] = ("base", "reheat_off", "pump_auto", "combo3")


@dataclass(frozen=True)
class ComfortTolerance:
    """「不劣於舒適基準」的容許值。"""

    temperature_kh: float = 0.1
    humidity_high_pct_h: float = 1.0
    pulldown_s: float = 60.0


@dataclass(frozen=True)
class AbsoluteComfort:
    """絕對舒適門檻（在室時段，一天；假設值，待業主確認）。與基準一樣差並不算達標。"""

    temperature_kh: float = 0.5
    humidity_high_pct_h: float = 5.0
    max_temperature_k: float = celsius(27.0)
    max_rh: float = 0.65


@dataclass(frozen=True)
class StrategyResult:
    """單一策略、單一情境的結果（週期穩態的最後一天，除達標時間外）。"""

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
    days: int = 2
    periodic: bool = True
    drift_room_k: float = 0.0
    drift_cold_k: float = 0.0
    drift_hot_k: float = 0.0
    coil_check_failures: int = 0
    room_condensed_kg: float = 0.0
    day_to_day_kwh: float = 0.0

    def comfort_ok(self, base: StrategyResult, tol: ComfortTolerance | None = None) -> bool:
        """舒適度是否不劣於基準（溫度超標、濕度高側超標、達標時間）。

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

    def absolute_ok(self, limits: AbsoluteComfort | None = None) -> bool:
        """是否通過絕對舒適門檻。

參數：
    limits: 門檻。

回傳：
    bool。"""
        limits = limits or AbsoluteComfort()
        return (self.temperature_exceed_kh <= limits.temperature_kh
                and self.humidity_high_pct_h <= limits.humidity_high_pct_h
                and self.max_temperature_k <= limits.max_temperature_k
                and self.max_rh <= limits.max_rh)

    @property
    def valid(self) -> bool:
        """數值檢查：盤管不變量無違反、週期穩態收斂、房間無過飽和截斷。

回傳：
            bool。"""
        return self.coil_check_failures == 0 and self.periodic and self.room_condensed_kg < 1e-3


@dataclass(frozen=True)
class _DayState:
    cold_k: float
    hot_k: float
    room_k: float
    room_w: float


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
             start_state: tuple[float, float, float], days: int = 2, periodic: bool = True,
             coil_check_failures: int = 0, window_days: int = 1) -> StrategyResult:
    """彙整統計日的指標。

參數：
    records: 統計日記錄。
    events: 全部事件。
    scenario_key: 情境代碼。
    strategy: 策略。
    room: 房間模型（取參數）。
    params: 系統參數。
    day_start_s: 統計日起始時刻。
    pulldown_s: 第一天的達標時間。
    start_state: 統計日開始時的（冰水桶 K, 熱水桶 K, 室溫 K）。
    days: 模擬天數。
    periodic: 是否達到週期穩態。
    coil_check_failures: 盤管不變量違反次數。
    window_days: 統計窗的天數（累計量除以此值成為每日平均）。

回傳：
    StrategyResult。"""
    c = room.control
    kwh = 1.0 / 3.6e6 / window_days
    occ = [r for r in records if r.occupied]
    energy = sum(r.total_power_w * r.dt_s for r in records) * kwh
    compressor = sum(r.compressor_power_w * r.dt_s for r in records) * kwh
    pumps = sum(r.pump_power_w * r.dt_s for r in records) * kwh
    fans = sum(r.fan_power_w * r.dt_s for r in records) * kwh
    outdoor = sum(r.outdoor_fan_power_w * r.dt_s for r in records) * kwh
    other = sum(r.standby_power_w * r.dt_s for r in records) * kwh
    evap = sum(r.cooling_w * r.dt_s for r in records if r.mode.value != "smart_heating") * kwh
    chiller_cop = evap / compressor if compressor > 0 else None
    end = records[-1]
    owed_j = (params.cold_tank.heat_capacity_j_k * (end.cold_water_k - start_state[0])
              + room.params.heat_capacity_j_k * (end.room_k - start_state[2]))
    correction = owed_j * kwh / chiller_cop if chiller_cop else 0.0
    upper, lower = c.setpoint_k + c.band_k, c.setpoint_k - c.band_k
    per_day_h = HOUR_S * window_days
    t_exceed = sum((max(0.0, r.room_k - upper) + max(0.0, lower - r.room_k)) * r.dt_s for r in occ) / per_day_h
    rh_high = sum(max(0.0, r.room_rh - c.rh_high) * 100 * r.dt_s for r in occ) / per_day_h
    rh_low = sum(max(0.0, c.rh_low - r.room_rh) * 100 * r.dt_s for r in occ) / per_day_h
    end_s = day_start_s + DAY_S * window_days
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
        compressor_starts=round(sum(1 for e in in_day if e.code == "start") / window_days),
        fan_switches=round(fan_switches / window_days),
        protection_events=round(sum(1 for e in in_day if e.code in {"trip", "freeze_stop", "hp_preempt"}) / window_days),
        chiller_cop=chiller_cop,
        system_cop=fan_coil / energy if energy > 0 else None,
        mean_chw_setpoint_k=sum(r.chw_setpoint_k * r.dt_s for r in occ) / sum(r.dt_s for r in occ),
        days=days, periodic=periodic,
        drift_room_k=end.room_k - start_state[2], drift_cold_k=end.cold_water_k - start_state[0],
        drift_hot_k=end.hot_water_k - start_state[1],
        coil_check_failures=coil_check_failures, room_condensed_kg=room.condensed_kg,
    )


@dataclass(frozen=True)
class PeriodicTolerance:
    """週期穩態判定：統計日開始與結束的狀態差，以及相鄰兩天的用電差。

    水桶在啟停遲滯帶內循環（冰水約 1 K、熱水約 2 K 寬），容許值取遲滯帶寬度。
    """

    room_k: float = 0.05
    room_humidity_ratio: float = 5e-5
    cold_tank_k: float = 1.0
    hot_tank_k: float = 2.5
    energy_fraction: float = 0.01
    min_days: int = 4
    max_days: int = 8


def _state(sim: HeatPumpSimulation, room: RoomModel) -> _DayState:
    """目前狀態快照。

參數：
    sim: 模擬器。
    room: 房間。

回傳：
    _DayState。"""
    return _DayState(sim.cold_water_k, sim.hot_water_k, room.state.temperature_k, room.state.humidity_ratio)


def _periodic(a: _DayState, b: _DayState, tol: PeriodicTolerance) -> bool:
    """兩個同時刻狀態是否在容許差內。

參數：
    a: 開始。
    b: 結束。
    tol: 容許值。

回傳：
    bool。"""
    return (abs(a.room_k - b.room_k) <= tol.room_k and abs(a.room_w - b.room_w) <= tol.room_humidity_ratio
            and abs(a.cold_k - b.cold_k) <= tol.cold_tank_k and abs(a.hot_k - b.hot_k) <= tol.hot_tank_k)


def run_strategy(table: CycleTable, scenario_key: str, scenario: DailyScenario, strategy: Strategy,
                 params: HeatPumpParameters | None = None, room_params: RoomParameters | None = None,
                 control: IndoorControlParameters | None = None, fans: frozenset[str] = frozenset({"A", "B"}),
                 dt_s: float = 5.0, progress: Callable[[float], None] | None = None,
                 coils: tuple[CoilParameters, ...] = DEFAULT_COILS,
                 periodic: PeriodicTolerance | None = None) -> StrategyResult:
    """執行一個策略直到週期穩態，回傳最後一天的結果。

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
    progress: 進度回呼（已完成天數）。
    coils: 盤管參數（敏感度分析用）。
    periodic: 週期穩態判定。

回傳：
    StrategyResult。"""
    params = params or replace(HeatPumpParameters(), electrical=FULL_ELECTRICAL)
    periodic = periodic or PeriodicTolerance()
    room = RoomModel(scenario, room_params, control, coils=coils, reheat_mode=strategy.reheat_mode,
                     reheat_fraction=strategy.reheat_fraction, chw_reset=strategy.chw_reset,
                     initial_k=celsius(29.0), initial_rh=0.65)
    settings: SimulationSettings = replace(default_settings(OperationMode.COOLING), fans=fans, **strategy.settings)
    sim = HeatPumpSimulation(table, params, settings, initial_cold_k=celsius(12.0), initial_hot_k=celsius(30.0),
                             room=room, start_time_s=0.0)
    day1 = sim.run(DAY_S, dt_s)
    enable_s = (scenario.occupied_hours[0] - scenario.precool_h) * HOUR_S
    pulldown = _pulldown_s(day1, room.control, enable_s)
    days = 1
    states = [_state(sim, room)]
    day_records: list[list[StepRecord]] = []
    day_starts: list[float] = []
    day_kwh: list[float] = []
    converged = False
    while True:
        day_starts.append(sim.time_s)
        records = sim.run(DAY_S, dt_s)
        day_records = (day_records + [records])[-2:]  # 只保留最後兩天，避免多日記錄佔滿記憶體
        day_kwh.append(sum(r.total_power_w * r.dt_s for r in records) / 3.6e6)
        states.append(_state(sim, room))
        days += 1
        if progress:
            progress(days)
        if len(day_kwh) >= 3:
            # 相隔兩天比較（涵蓋一天與兩天週期）。
            steady_energy = abs(day_kwh[-1] - day_kwh[-3]) <= periodic.energy_fraction * day_kwh[-1]
            converged = steady_energy and _periodic(states[-3], states[-1], periodic)
        if (converged and days >= periodic.min_days) or days >= periodic.max_days:
            break
    failures = sum(sim.coil_check_failures.values())
    window = day_records[-2] + day_records[-1]
    start = states[-3]
    result = evaluate(window, sim.events, scenario_key, strategy, room, params, day_starts[-2], pulldown,
                      (start.cold_k, start.hot_k, start.room_k), days=days, periodic=converged,
                      coil_check_failures=failures, window_days=2)
    return replace(result, day_to_day_kwh=abs(day_kwh[-1] - day_kwh[-2]))


REFERENCE_CANDIDATES = ("base", "reheat_off")


def comfort_score(result: StrategyResult) -> float:
    """舒適度綜合分數（溫度超標 K·h ＋ (RH 高側 ＋ RH 低側超標 %·h) ÷ 10；越小越好），用來挑舒適基準。

過度除濕（RH < 50 %）也算舒適度問題，否則兩個候選溫度都不超標時會選到過乾的那個。

參數：
    result: 結果。

回傳：
    分數。"""
    return result.temperature_exceed_kh + (result.humidity_high_pct_h + result.humidity_low_pct_h) / 10.0


def reference_result(results: list[StrategyResult]) -> StrategyResult | None:
    """舒適基準：「現行預設」與「現行預設但再熱關閉」兩者中舒適度較好者（依情境而定）。

參數：
    results: 同一情境的結果。

回傳：
    StrategyResult；兩者都沒有時為 None。"""
    candidates = [r for r in results if r.strategy in REFERENCE_CANDIDATES]
    return min(candidates, key=comfort_score) if candidates else None


def acceptable(result: StrategyResult, base: StrategyResult, tol: ComfortTolerance | None = None,
               limits: AbsoluteComfort | None = None) -> bool:
    """可列入比較：數值檢查通過、絕對門檻通過、且不劣於舒適基準。

參數：
    result: 結果。
    base: 舒適基準。
    tol: 相對容許值。
    limits: 絕對門檻。

回傳：
    bool。"""
    return result.valid and result.absolute_ok(limits) and (result is base or result.comfort_ok(base, tol))


def best_relative_only(results: list[StrategyResult], tol: ComfortTolerance | None = None) -> StrategyResult | None:
    """**條件式**排名：只要求數值檢查與不劣於舒適基準（不看絕對門檻）。

只在沒有任何策略通過絕對門檻時參考（例如房間負荷超過設備能力，所有方案都會在尖峰超標）；
結果必須標示「絕對門檻未達成」。

參數：
    results: 同一情境的結果。
    tol: 相對容許值。

回傳：
    StrategyResult 或 None。"""
    base = reference_result(results)
    if base is None:
        return None
    candidates = [r for r in results if r.valid and (r is base or r.comfort_ok(base, tol))]
    return min(candidates, key=lambda r: r.energy_kwh) if candidates else None


def best_strategy(results: list[StrategyResult], tol: ComfortTolerance | None = None,
                  limits: AbsoluteComfort | None = None) -> StrategyResult | None:
    """可列入比較的策略中全系統用電最低者。

參數：
    results: 同一情境的結果（須含 ``base`` 或 ``reheat_off``）。
    tol: 相對容許值。
    limits: 絕對門檻。

回傳：
    StrategyResult；沒有舒適基準或沒有任何策略可列入時為 None。"""
    base = reference_result(results)
    if base is None:
        return None
    candidates = [r for r in results if acceptable(r, base, tol, limits)]
    return min(candidates, key=lambda r: r.energy_kwh) if candidates else None


__all__ = [
    "CORE_STRATEGIES",
    "DAY_S",
    "REFERENCE_CANDIDATES",
    "STRATEGIES",
    "AbsoluteComfort",
    "ComfortTolerance",
    "PeriodicTolerance",
    "Strategy",
    "StrategyResult",
    "acceptable",
    "best_relative_only",
    "best_strategy",
    "comfort_score",
    "evaluate",
    "reference_result",
    "run_strategy",
]
