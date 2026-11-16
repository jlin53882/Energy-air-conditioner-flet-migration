"""多元取熱雙效熱泵的時間步進模擬（``docs/simulation-model.md`` §2–§5）。

每個時間步：
1. 依目前模式與頻率求解運轉點（Te、Tc、能力、耗電）。
2. 以顯式 Euler 更新冰水桶與熱水桶溫度。
3. 依水溫切換冷媒模式（電磁閥），再更新壓縮機頻率（PID＋階梯量化）與啟停。

壓縮機與兩台水泵都由變頻器在固定階梯（預設 30／40／50／60 Hz）運轉；冷房時熱水桶另供
除濕後再熱盤管。模擬器是可變物件：UI 可在步與步之間調整運轉方式、送風機、頻率模式、
泵浦頻率、再熱比例與環境溫度。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum

from .components import (
    VALVES_OPEN,
    CompressorPerformance,
    OperatingConditions,
    OperatingPointSolver,
    PlateExchanger,
    RefrigerantMode,
    refrigerant_side_resistance,
)
from .control import FrequencyStepper, PidController
from .cycle_table import CycleTable
from .parameters import WATER_CP_J_KG_K, HeatPumpParameters, celsius, gpm_to_kg_s


class OperationMode(str, Enum):
    """使用者選擇的運轉方式：兩台送風機統一接冰水桶（冷房）或熱水桶（暖房）。"""

    COOLING = "cooling"
    HEATING = "heating"


class FrequencyMode(str, Enum):
    """壓縮機頻率控制方式。"""

    AUTO = "auto"
    MANUAL = "manual"


class PumpMode(str, Enum):
    """水泵頻率控制方式。"""

    MANUAL = "manual"
    AUTO = "auto"


OUTDOOR_RANGE_K = (celsius(-10.0), celsius(45.0))
ROOM_RANGE_K = (celsius(10.0), celsius(35.0))

WARNING_HIGH_PRESSURE = "high_pressure"
WARNING_HP_LIMITING = "hp_limiting"
WARNING_FROST = "frost"
WARNING_TRIPPED = "tripped"
WARNING_FREEZE_LIMITING = "freeze_limiting"
WARNING_FREEZE_STOPPED = "freeze_stopped"


@dataclass(frozen=True)
class SimulationSettings:
    """使用者可在執行中調整的設定。"""

    operation: OperationMode = OperationMode.COOLING
    fans: frozenset[str] = frozenset({"A", "B"})
    frequency_mode: FrequencyMode = FrequencyMode.AUTO
    manual_frequency_hz: float = 60.0
    cold_pump_hz: float = 60.0
    hot_pump_hz: float = 60.0
    pump_mode: PumpMode = PumpMode.MANUAL
    reheat_fraction: float = 0.2
    room_k: float = celsius(27.0)
    outdoor_k: float = celsius(30.0)


def default_settings(operation: OperationMode) -> SimulationSettings:
    """依運轉方式回傳預設環境（冷房 27/30 °C、暖房 20/15 °C）。

參數：
    operation: 運轉方式。

回傳：
    SimulationSettings。"""
    if operation is OperationMode.HEATING:
        return SimulationSettings(operation=operation, room_k=celsius(20.0), outdoor_k=celsius(15.0))
    return SimulationSettings(operation=operation)


@dataclass(frozen=True)
class SimulationEvent:
    """模式切換、啟停與保護事件。"""

    time_s: float
    code: str
    message: str


@dataclass(frozen=True)
class StepRecord:
    """單一時間步的記錄（§5）。所有量為 canonical SI。"""

    time_s: float
    dt_s: float
    operation: OperationMode
    mode: RefrigerantMode
    compressor_on: bool
    frequency_hz: float
    frequency_limit_hz: float
    valves_open: frozenset[int]
    fans: frozenset[str]
    cold_water_k: float
    hot_water_k: float
    evaporating_k: float | None
    condensing_k: float | None
    evaporating_pressure_pa: float | None
    condensing_pressure_pa: float | None
    pressure_ratio: float | None
    mass_flow_kg_s: float
    discharge_k: float | None
    suction_enthalpy_j_kg: float | None
    discharge_enthalpy_j_kg: float | None
    liquid_enthalpy_j_kg: float | None
    cooling_w: float
    heating_w: float
    compressor_power_w: float
    fan_coil_load_w: float
    fan_power_w: float
    pump_power_w: float
    cold_tank_loss_w: float
    hot_tank_loss_w: float
    energy_used_j: float
    fan_coil_energy_j: float
    warnings: frozenset[str]
    suction_temperature_k: float | None = None
    liquid_temperature_k: float | None = None
    suction_entropy_j_kg_k: float | None = None
    discharge_entropy_j_kg_k: float | None = None
    liquid_entropy_j_kg_k: float | None = None
    evaporator_inlet_entropy_j_kg_k: float | None = None
    evaporator_water_in_k: float | None = None
    evaporator_water_out_k: float | None = None
    condenser_water_in_k: float | None = None
    condenser_water_out_k: float | None = None
    outdoor_heat_w: float = 0.0
    cold_pump_hz: float = 0.0
    hot_pump_hz: float = 0.0
    cold_pump_gpm: float = 0.0
    hot_pump_gpm: float = 0.0
    cold_pump_power_w: float = 0.0
    hot_pump_power_w: float = 0.0
    reheat_demand_w: float = 0.0
    reheat_w: float = 0.0
    reheat_energy_j: float = 0.0

    @property
    def net_cooling_w(self) -> float:
        """送到室內的淨冷卻量（盤管冷卻 − 再熱）；暖房時為 0。

回傳：
            W。"""
        if self.operation is not OperationMode.COOLING:
            return 0.0
        return max(0.0, self.fan_coil_load_w - self.reheat_w)

    @property
    def total_power_w(self) -> float:
        """壓縮機＋送風機＋水泵。

回傳：
            W。"""
        return self.compressor_power_w + self.fan_power_w + self.pump_power_w

    @property
    def system_cop(self) -> float | None:
        """累計系統 COP（送風機側，含水泵）。

回傳：
            無因次；尚無耗電時為 None。"""
        if self.energy_used_j <= 0:
            return None
        return self.fan_coil_energy_j / self.energy_used_j


@dataclass
class _ControllerState:
    """頻率控制器內部狀態。"""

    compressor_on: bool = True
    frequency_hz: float = 60.0
    frequency_limit_hz: float = 60.0
    freeze_limit_hz: float = 60.0
    freeze_timer_s: float = 0.0
    freeze_stopped: bool = False
    off_since_s: float | None = None
    tripped: bool = False
    cold_pump_hz: float = 60.0
    hot_pump_hz: float = 60.0
    cold_pump_changed_s: float = -1e9
    hot_pump_changed_s: float = -1e9


class HeatPumpSimulation:
    """可逐步推進的熱泵模擬器。"""

    def __init__(
        self,
        table: CycleTable,
        params: HeatPumpParameters | None = None,
        settings: SimulationSettings | None = None,
        initial_cold_k: float = celsius(30.0),
        initial_hot_k: float = celsius(30.0),
    ) -> None:
        """建立模擬器。

參數：
    table: 循環性質表（須以相同冷媒設定與總效率建立）。
    params: 系統參數。
    settings: 初始使用者設定。
    initial_cold_k: 冰水桶初始溫度。
    initial_hot_k: 熱水桶初始溫度。

回傳：
    無。

引發：
    ValueError：性質表與參數不一致時。"""
        self.params = params or HeatPumpParameters()
        if table.settings != self.params.cycle:
            raise ValueError("性質表的循環設定與模擬參數不一致。")
        if abs(table.overall_efficiency - self.params.compressor.overall_efficiency) > 1e-9:
            raise ValueError("性質表的壓縮機總效率與模擬參數不一致。")
        self.table = table
        self._solver = OperatingPointSolver(table, self.params)
        resistance = refrigerant_side_resistance(self.params.refrigerant_side, self.params.geometry)
        self._condenser = PlateExchanger(self.params.condenser, self.params.geometry, resistance)
        self._evaporator = PlateExchanger(self.params.evaporator, self.params.geometry, resistance)
        settings = settings or SimulationSettings()
        self._settings = settings
        self.time_s = 0.0
        self.cold_water_k = initial_cold_k
        self.hot_water_k = initial_hot_k
        self.mode = RefrigerantMode.DUAL
        comp = self.params.compressor
        control = self.params.control
        self._ctrl = _ControllerState(frequency_hz=comp.max_frequency_hz, frequency_limit_hz=comp.max_frequency_hz,
                                      freeze_limit_hz=comp.max_frequency_hz)
        self._pid = PidController(
            kp=control.kp_hz_per_k, ti_s=control.integral_time_s, td_s=control.derivative_time_s,
            out_min=comp.min_frequency_hz, out_max=comp.max_frequency_hz, bias=comp.min_frequency_hz,
            filter_ratio=control.derivative_filter_ratio,
        )
        self._stepper = FrequencyStepper(comp.frequency_steps_hz, control.step_hysteresis_hz, control.step_dwell_s,
                                         current_hz=comp.max_frequency_hz)
        self._mode_since_s = 0.0
        self._guess: tuple[float, float] | None = None
        self._energy_j = 0.0
        self._fan_coil_energy_j = 0.0
        self._reheat_energy_j = 0.0
        self.events: list[SimulationEvent] = []
        self.update_settings(settings)

    @property
    def settings(self) -> SimulationSettings:
        """目前設定。

回傳：
            SimulationSettings。"""
        return self._settings

    @property
    def condenser(self) -> PlateExchanger:
        """板式冷凝器模型。

回傳：
            PlateExchanger。"""
        return self._condenser

    @property
    def evaporator(self) -> PlateExchanger:
        """板式蒸發器模型。

回傳：
            PlateExchanger。"""
        return self._evaporator

    def update_settings(self, settings: SimulationSettings) -> None:
        """套用新的使用者設定（可在執行中呼叫）。

參數：
    settings: 新設定。

回傳：
    無。

引發：
    ValueError：設定不合理時。"""
        compressor = self.params.compressor
        known = {fan.name for fan in self.params.fan_coils}
        if not settings.fans <= known:
            raise ValueError(f"未知的送風機：{sorted(settings.fans - known)}")
        if settings.manual_frequency_hz not in compressor.frequency_steps_hz:
            raise ValueError(f"手動頻率必須是階梯 {self._format_steps(compressor.frequency_steps_hz)} Hz 之一。")
        for value, pump, label in (
            (settings.cold_pump_hz, self.params.cold_pump, "冰水泵"),
            (settings.hot_pump_hz, self.params.hot_pump, "熱水泵"),
        ):
            if value not in pump.frequency_steps_hz:
                raise ValueError(f"{label}頻率必須是階梯 {self._format_steps(pump.frequency_steps_hz)} Hz 之一。")
        if not 0.0 <= settings.reheat_fraction <= self.params.reheat.max_fraction:
            raise ValueError(f"再熱比例必須介於 0～{self.params.reheat.max_fraction:g}。")
        for value, (low, high), label in (
            (settings.outdoor_k, OUTDOOR_RANGE_K, "外氣溫度"),
            (settings.room_k, ROOM_RANGE_K, "室溫"),
        ):
            if not low <= value <= high:
                raise ValueError(f"{label}必須介於 {low - 273.15:g}～{high - 273.15:g} °C。")
        previous = self._settings
        self._settings = settings
        ctrl = self._ctrl
        if previous.operation is not settings.operation:
            self.mode = RefrigerantMode.DUAL
            self._mode_since_s = self.time_s
            self._pid.reset()
            self._event("operation", f"運轉方式切換為{'冷房' if settings.operation is OperationMode.COOLING else '暖房'}")
            self._guess = None
        elif previous.frequency_mode is FrequencyMode.MANUAL and settings.frequency_mode is FrequencyMode.AUTO:
            # 無擾切換：讓 PID 輸出從目前頻率開始。
            self._pid.preset(ctrl.frequency_hz, self._control_error())
        if ctrl.compressor_on and not ctrl.tripped and settings.frequency_mode is FrequencyMode.MANUAL:
            ctrl.frequency_hz = self._stepper.start(settings.manual_frequency_hz, ctrl.frequency_limit_hz, self.time_s)

    @staticmethod
    def _format_steps(steps: tuple[float, ...]) -> str:
        """階梯顯示文字。

參數：
            steps: 階梯。

回傳：
            例如「30／40／50／60」。"""
        return "／".join(f"{step:g}" for step in steps)

    def set_manual_frequency(self, frequency_hz: float) -> None:
        """切換為手動頻率。

參數：
    frequency_hz: 頻率。

回傳：
    無。"""
        self.update_settings(
            replace(self._settings, frequency_mode=FrequencyMode.MANUAL, manual_frequency_hz=frequency_hz)
        )

    def reset_trip(self) -> None:
        """手動復歸安全停機。

回傳：
    無。"""
        if self._ctrl.tripped:
            self._ctrl.tripped = False
            self._event("trip_reset", "安全停機已手動復歸")

    def _event(self, code: str, message: str) -> None:
        """記錄事件。

參數：
    code: 事件代碼。
    message: 說明。

回傳：
    無。"""
        self.events.append(SimulationEvent(self.time_s, code, message))

    def _cold_flow_kg_s(self) -> float:
        """冰水泵目前流量。

回傳：
            kg/s。"""
        return gpm_to_kg_s(self.params.cold_pump.flow_gpm(self._pump_hz()[0]))

    def _hot_flow_kg_s(self) -> float:
        """熱水泵目前流量。

回傳：
            kg/s。"""
        return gpm_to_kg_s(self.params.hot_pump.flow_gpm(self._pump_hz()[1]))

    def _pump_hz(self) -> tuple[float, float]:
        """目前實際的（冰水泵, 熱水泵）頻率：手動取設定值，自動取控制器狀態（§2.4）。

回傳：
            (Hz, Hz)。"""
        ctrl = self._ctrl
        if self._settings.pump_mode is PumpMode.MANUAL:
            ctrl.cold_pump_hz = self._settings.cold_pump_hz
            ctrl.hot_pump_hz = self._settings.hot_pump_hz
        return ctrl.cold_pump_hz, ctrl.hot_pump_hz

    def _next_pump_hz(self, steps: tuple[float, ...], flow_gpm: Callable[[float], float], current: float,
                      delta_t_k: float, target_k: float, changed_s: float) -> float:
        """水側溫差控制：溫差高於目標＋遲滯時升一階；降一階後預測溫差仍不超過目標時降一階。

參數：
    steps: 可用階梯（升冪）。
    flow_gpm: 頻率到流量的函式。
    current: 目前頻率。
    delta_t_k: 目前板式換熱器水側溫差（無熱交換為 0）。
    target_k: 目標溫差。
    changed_s: 上次變階的時間。

回傳：
    下一步頻率（Hz）。"""
        c = self.params.control
        if self.time_s - changed_s < c.pump_step_dwell_s:
            return current
        steps = tuple(sorted(steps))
        index = steps.index(current) if current in steps else len(steps) - 1
        if delta_t_k > target_k + c.pump_hysteresis_k and index < len(steps) - 1:
            return steps[index + 1]
        if index > 0:
            lower = steps[index - 1]
            if delta_t_k * flow_gpm(current) / flow_gpm(lower) <= target_k:
                return lower
        return current

    def _update_pumps(self, perf: CompressorPerformance | None) -> None:
        """自動模式下依板式換熱器水側溫差更新水泵頻率（下一步生效）。

參數：
    perf: 本步運轉點（停機或該換熱器不在流路時溫差視為 0，水泵逐階降到最低）。

回傳：
    無。"""
        if self._settings.pump_mode is not PumpMode.AUTO:
            return
        c = self.params.control
        ctrl = self._ctrl
        cold_dt = hot_dt = 0.0
        if perf is not None:
            if self.mode is not RefrigerantMode.SMART_HEATING:
                cold_dt = perf.cooling_w / (self._cold_flow_kg_s() * WATER_CP_J_KG_K)
            if self.mode is not RefrigerantMode.SMART_COOLING:
                hot_dt = perf.heating_w / (self._hot_flow_kg_s() * WATER_CP_J_KG_K)
        cold = self._next_pump_hz(self.params.cold_pump.frequency_steps_hz, self.params.cold_pump.flow_gpm,
                                  ctrl.cold_pump_hz, cold_dt, c.pump_cold_delta_t_k, ctrl.cold_pump_changed_s)
        hot = self._next_pump_hz(self.params.hot_pump.frequency_steps_hz, self.params.hot_pump.flow_gpm,
                                 ctrl.hot_pump_hz, hot_dt, c.pump_hot_delta_t_k, ctrl.hot_pump_changed_s)
        if cold != ctrl.cold_pump_hz:
            ctrl.cold_pump_hz, ctrl.cold_pump_changed_s = cold, self.time_s
        if hot != ctrl.hot_pump_hz:
            ctrl.hot_pump_hz, ctrl.hot_pump_changed_s = hot, self.time_s

    def _conditions(self, frequency_hz: float) -> OperatingConditions:
        """組合求解條件。

參數：
    frequency_hz: 頻率。

回傳：
    OperatingConditions。"""
        s = self._settings
        return OperatingConditions(
            mode=self.mode,
            cold_water_k=self.cold_water_k,
            hot_water_k=self.hot_water_k,
            outdoor_k=s.outdoor_k,
            frequency_hz=frequency_hz,
            evaporator_conductance_w_k=self._evaporator.conductance(self._cold_flow_kg_s()),
            condenser_conductance_w_k=self._condenser.conductance(self._hot_flow_kg_s()),
            outdoor_ua_w_k=self.params.outdoor_ua_w_k,
        )

    def step(self, dt_s: float = 5.0) -> StepRecord:
        """推進一個時間步。

參數：
    dt_s: 時間步長（0 < dt ≤ 10 s）。

回傳：
    本步開始時運轉點與本步結束後水溫的記錄。

引發：
    ValueError：dt 不合理時。"""
        if not 0 < dt_s <= 10.0:
            raise ValueError("時間步長必須介於 0 與 10 秒之間。")
        p = self.params
        s = self._settings
        ctrl = self._ctrl
        cooling = s.operation is OperationMode.COOLING

        perf: CompressorPerformance | None = None
        warnings: set[str] = set()
        tripped_now = False
        if ctrl.compressor_on and not ctrl.tripped:
            perf = self._solver.solve(self._conditions(ctrl.frequency_hz), self._guess)
            self._guess = (perf.evaporating_k, perf.condensing_k)
            if perf.condensing_k >= p.control.trip_condensing_k or (
                perf.properties.discharge_temperature_k >= p.control.trip_discharge_k
            ):
                ctrl.tripped = True
                ctrl.compressor_on = False
                tripped_now = True
                perf = None
        if ctrl.tripped:
            warnings.add(WARNING_TRIPPED)
        if ctrl.freeze_stopped and not ctrl.compressor_on:
            warnings.add(WARNING_FREEZE_STOPPED)
        if perf is not None:
            if perf.condensing_k >= p.control.warn_high_pressure_k:
                warnings.add(WARNING_HIGH_PRESSURE)
            if perf.evaporating_k < p.control.warn_frost_k:
                warnings.add(WARNING_FROST)

        active_fans = [fan for fan in p.fan_coils if fan.name in s.fans]
        fan_ua = sum(fan.ua_w_k for fan in active_fans)
        fan_power = sum(fan.fan_power_w for fan in active_fans)
        if cooling:
            fan_load = max(0.0, fan_ua * (s.room_k - self.cold_water_k))
        else:
            fan_load = max(0.0, fan_ua * (self.hot_water_k - s.room_k))
        cold_pump_hz, hot_pump_hz = self._pump_hz()
        cold_pump_power = p.cold_pump.power_w(cold_pump_hz)
        hot_pump_power = p.hot_pump.power_w(hot_pump_hz)
        pump_power = cold_pump_power + hot_pump_power
        reheat_demand = reheat = 0.0
        if cooling and fan_ua > 0 and fan_load > 0:
            reheat_demand = s.reheat_fraction * fan_load
            coil_air_k = self.cold_water_k + p.reheat.coil_air_approach_k
            capacity = p.reheat.ua_ratio_to_fan_coil * fan_ua * max(0.0, self.hot_water_k - coil_air_k)
            reheat = min(reheat_demand, capacity)

        q_evap_water = perf.cooling_w if perf is not None and self.mode is not RefrigerantMode.SMART_HEATING else 0.0
        q_cond_water = perf.heating_w if perf is not None and self.mode is not RefrigerantMode.SMART_COOLING else 0.0
        # 板式換熱器進出水溫（進水 = 本步開始時的桶溫）；室外換熱量依模式取冷凝或蒸發側。
        evap_in = cond_in = evap_out = cond_out = None
        outdoor_heat = 0.0
        if perf is not None:
            cold_rate = self._cold_flow_kg_s() * WATER_CP_J_KG_K
            hot_rate = self._hot_flow_kg_s() * WATER_CP_J_KG_K
            if self.mode is not RefrigerantMode.SMART_HEATING:
                evap_in = self.cold_water_k
                evap_out = evap_in - perf.cooling_w / cold_rate
            else:
                outdoor_heat = perf.cooling_w
            if self.mode is not RefrigerantMode.SMART_COOLING:
                cond_in = self.hot_water_k
                cond_out = cond_in + perf.heating_w / hot_rate
            else:
                outdoor_heat = perf.heating_w
        cold_loss = p.cold_tank.loss_ua_w_k * (s.room_k - self.cold_water_k)
        hot_loss = p.hot_tank.loss_ua_w_k * (s.room_k - self.hot_water_k)
        cold_net = (fan_load if cooling else 0.0) - q_evap_water + cold_loss
        hot_net = q_cond_water - (0.0 if cooling else fan_load) - reheat + hot_loss
        self.cold_water_k += cold_net / p.cold_tank.heat_capacity_j_k * dt_s
        self.hot_water_k += hot_net / p.hot_tank.heat_capacity_j_k * dt_s
        compressor_power = perf.power_w if perf is not None else 0.0
        self._energy_j += (compressor_power + fan_power + pump_power) * dt_s
        self._fan_coil_energy_j += fan_load * dt_s
        self._reheat_energy_j += reheat * dt_s

        record = StepRecord(
            time_s=self.time_s,
            dt_s=dt_s,
            operation=s.operation,
            mode=self.mode,
            compressor_on=perf is not None,
            frequency_hz=ctrl.frequency_hz if perf is not None else 0.0,
            frequency_limit_hz=ctrl.frequency_limit_hz,
            valves_open=VALVES_OPEN[self.mode],
            fans=s.fans,
            cold_water_k=self.cold_water_k,
            hot_water_k=self.hot_water_k,
            evaporating_k=perf.evaporating_k if perf else None,
            condensing_k=perf.condensing_k if perf else None,
            evaporating_pressure_pa=perf.properties.evaporating_pressure_pa if perf else None,
            condensing_pressure_pa=perf.properties.condensing_pressure_pa if perf else None,
            pressure_ratio=perf.pressure_ratio if perf else None,
            mass_flow_kg_s=perf.mass_flow_kg_s if perf else 0.0,
            discharge_k=perf.properties.discharge_temperature_k if perf else None,
            suction_enthalpy_j_kg=perf.properties.suction_enthalpy_j_kg if perf else None,
            discharge_enthalpy_j_kg=perf.properties.discharge_enthalpy_j_kg if perf else None,
            liquid_enthalpy_j_kg=perf.properties.liquid_enthalpy_j_kg if perf else None,
            cooling_w=perf.cooling_w if perf else 0.0,
            heating_w=perf.heating_w if perf else 0.0,
            compressor_power_w=compressor_power,
            fan_coil_load_w=fan_load,
            fan_power_w=fan_power,
            pump_power_w=pump_power,
            cold_tank_loss_w=cold_loss,
            hot_tank_loss_w=hot_loss,
            energy_used_j=self._energy_j,
            fan_coil_energy_j=self._fan_coil_energy_j,
            warnings=frozenset(warnings),
            suction_temperature_k=perf.evaporating_k + p.cycle.superheat_k if perf else None,
            liquid_temperature_k=perf.condensing_k - p.cycle.subcooling_k if perf else None,
            suction_entropy_j_kg_k=perf.properties.suction_entropy_j_kg_k if perf else None,
            discharge_entropy_j_kg_k=perf.properties.discharge_entropy_j_kg_k if perf else None,
            liquid_entropy_j_kg_k=perf.properties.liquid_entropy_j_kg_k if perf else None,
            evaporator_inlet_entropy_j_kg_k=perf.properties.evaporator_inlet_entropy_j_kg_k if perf else None,
            evaporator_water_in_k=evap_in,
            evaporator_water_out_k=evap_out,
            condenser_water_in_k=cond_in,
            condenser_water_out_k=cond_out,
            outdoor_heat_w=outdoor_heat,
            cold_pump_hz=cold_pump_hz,
            hot_pump_hz=hot_pump_hz,
            cold_pump_gpm=p.cold_pump.flow_gpm(cold_pump_hz),
            hot_pump_gpm=p.hot_pump.flow_gpm(hot_pump_hz),
            cold_pump_power_w=cold_pump_power,
            hot_pump_power_w=hot_pump_power,
            reheat_demand_w=reheat_demand,
            reheat_w=reheat,
            reheat_energy_j=self._reheat_energy_j,
        )

        self.time_s += dt_s
        if tripped_now:
            ctrl.off_since_s = self.time_s
            self._event("trip", "高壓或排氣溫度過高，安全停機（需手動復歸）")
        self._update_mode()
        self._update_pumps(perf)
        extra_warnings = self._update_compressor(perf, dt_s)
        if extra_warnings:
            record = replace(record, warnings=record.warnings | extra_warnings)
        return record

    def _switch_mode(self, mode: RefrigerantMode, code: str, message: str) -> None:
        """切換冷媒模式並記錄事件。

參數：
    mode: 新模式。
    code: 事件代碼。
    message: 說明。

回傳：
    無。"""
        self.mode = mode
        self._mode_since_s = self.time_s
        self._event(code, message)

    def _update_mode(self) -> None:
        """依水溫切換冷媒模式（§2.2 第 2、4 項）。回切需在智慧模式停留至少 ``mode_return_dwell_s``。

回傳：
    無。"""
        c = self.params.control
        cooling = self._settings.operation is OperationMode.COOLING
        settled = self.time_s - self._mode_since_s >= c.mode_return_dwell_s
        if cooling:
            if self.mode is RefrigerantMode.DUAL and self.hot_water_k >= c.cooling_hot_switch_k:
                self._switch_mode(RefrigerantMode.SMART_COOLING, "smart_cooling",
                                  "熱水達上限：關 SV8、開 SV9，切換智慧冷房")
                self._preempt_high_pressure()
            elif self.mode is RefrigerantMode.SMART_COOLING and self.hot_water_k <= c.cooling_hot_return_k and settled:
                self._switch_mode(RefrigerantMode.DUAL, "dual", "熱水回落：關 SV9、開 SV8，回到雙效")
            elif self.mode is RefrigerantMode.SMART_HEATING:
                self.mode = RefrigerantMode.DUAL
        else:
            if self.mode is RefrigerantMode.DUAL and self.cold_water_k <= c.heating_cold_switch_k:
                self._switch_mode(RefrigerantMode.SMART_HEATING, "smart_heating",
                                  "冰水達下限：關 SV10、開 SV11，切換智慧暖房")
            elif self.mode is RefrigerantMode.DUAL and self._ctrl.freeze_stopped:
                self._switch_mode(RefrigerantMode.SMART_HEATING, "smart_heating",
                                  "冰水出水溫度過低（防凍保護）：關 SV10、開 SV11，改由室外換熱器吸熱")
            elif (self.mode is RefrigerantMode.SMART_HEATING and self.cold_water_k >= c.heating_cold_return_k
                  and settled and self._plate_evaporator_safe(RefrigerantMode.DUAL)):
                self._switch_mode(RefrigerantMode.DUAL, "dual", "冰水回升：關 SV11、開 SV10，回到雙效")
            elif self.mode is RefrigerantMode.SMART_COOLING:
                self.mode = RefrigerantMode.DUAL

    def _preempt_high_pressure(self) -> None:
        """切換到室外冷凝時預先限頻：冷凝溫度會在一步內跳升，事後限頻來不及（§2.3）。

以新模式預測冷凝溫度，由目前階梯逐階往下找第一個冷凝溫度低於限頻起點的階梯（都不行則取最低階）。

回傳：
    無。"""
        ctrl = self._ctrl
        if not ctrl.compressor_on or ctrl.tripped:
            return
        steps = [step for step in sorted(self.params.compressor.frequency_steps_hz, reverse=True)
                 if step <= ctrl.frequency_hz + 1e-9]
        chosen = steps[-1]
        for step in steps:
            perf = self._solver.solve(self._conditions(step), None)
            if perf.condensing_k < self.params.control.hp_limit_start_k:
                chosen = step
                break
        if chosen < ctrl.frequency_hz:
            ctrl.frequency_limit_hz = min(ctrl.frequency_limit_hz, chosen)
            ctrl.frequency_hz = self._stepper.start(chosen, chosen, self.time_s)
            self._event("hp_preempt", f"切換室外冷凝前預先限頻至 {chosen:.0f} Hz")
        self._guess = None

    def _plate_evaporator_safe(self, mode: RefrigerantMode | None = None) -> bool:
        """以最低頻率預測冰水出水溫度，是否不低於防凍保護設定（板式蒸發器不在流路時恆為真）。

參數：
    mode: 要預測的冷媒模式（預設目前模式）。

回傳：
    bool。"""
        mode = mode or self.mode
        if mode is RefrigerantMode.SMART_HEATING:
            return True
        conditions = replace(self._conditions(self.params.compressor.min_frequency_hz), mode=mode)
        predicted = self._solver.solve(conditions, None)
        return self._evaporator_leaving_k(predicted) >= self.params.control.freeze_limit_start_k

    def _evaporator_leaving_k(self, perf: CompressorPerformance) -> float:
        """板式蒸發器出水（冰水）溫度：進水（冰水桶）溫度減去水側取熱量 ÷ 水流熱容率。

參數：
    perf: 運轉點。

回傳：
    出水溫度（K）。"""
        rate = self._cold_flow_kg_s() * WATER_CP_J_KG_K
        return self.cold_water_k - perf.cooling_w / rate

    def _update_compressor(self, perf: CompressorPerformance | None, dt_s: float) -> frozenset[str]:
        """更新高壓與防凍限頻、頻率與啟停（§2.3）。

參數：
    perf: 本步運轉點（停機時為 None）。
    dt_s: 時間步長。

回傳：
    本步額外的警示代碼（高壓限頻、防凍限頻）。"""
        c = self.params.control
        comp = self.params.compressor
        s = self._settings
        ctrl = self._ctrl
        if ctrl.tripped:
            return frozenset()
        cooling = s.operation is OperationMode.COOLING
        controlled = self.cold_water_k if cooling else self.hot_water_k
        error = self._control_error()

        if not ctrl.compressor_on:
            restart = controlled >= c.cooling_restart_k if cooling else controlled <= c.heating_restart_k
            waited = ctrl.off_since_s is None or self.time_s - ctrl.off_since_s >= c.min_off_time_s
            if restart and waited and self._plate_evaporator_safe():
                ctrl.compressor_on = True
                ctrl.freeze_stopped = False
                ctrl.freeze_timer_s = 0.0
                self._pid.reset()
                ctrl.off_since_s = None
                request = (s.manual_frequency_hz if s.frequency_mode is FrequencyMode.MANUAL
                           else max(comp.min_frequency_hz, min(comp.max_frequency_hz, self._pid.output(error))))
                ctrl.frequency_hz = self._stepper.start(
                    request, min(ctrl.frequency_limit_hz, ctrl.freeze_limit_hz), self.time_s)
                self._event("start", "壓縮機重新啟動")
            return frozenset()

        limiting = False
        if perf is not None:
            if perf.condensing_k >= c.hp_limit_start_k:
                ctrl.frequency_limit_hz = max(comp.min_frequency_hz, ctrl.frequency_limit_hz - c.hp_limit_down_hz_per_s * dt_s)
                limiting = True
            elif perf.condensing_k < c.hp_limit_release_k:
                ctrl.frequency_limit_hz = min(comp.max_frequency_hz, ctrl.frequency_limit_hz + c.hp_limit_up_hz_per_s * dt_s)
            else:
                limiting = ctrl.frequency_limit_hz < comp.max_frequency_hz
        freezing = False
        plate_in_use = self.mode is not RefrigerantMode.SMART_HEATING
        if perf is not None and plate_in_use:
            leaving = self._evaporator_leaving_k(perf)
            if leaving < c.freeze_limit_start_k:
                ctrl.freeze_limit_hz = max(comp.min_frequency_hz,
                                           ctrl.freeze_limit_hz - c.freeze_limit_down_hz_per_s * dt_s)
                freezing = True
            elif leaving >= c.freeze_release_k:
                ctrl.freeze_limit_hz = min(comp.max_frequency_hz,
                                           ctrl.freeze_limit_hz + c.freeze_limit_up_hz_per_s * dt_s)
            else:
                freezing = ctrl.freeze_limit_hz < comp.max_frequency_hz
        elif not plate_in_use:
            ctrl.freeze_limit_hz = comp.max_frequency_hz
        limit = min(ctrl.frequency_limit_hz, ctrl.freeze_limit_hz)

        if s.frequency_mode is FrequencyMode.AUTO:
            request = self._pid.update(error, dt_s, out_max=limit)
            ctrl.frequency_hz = self._stepper.update(request, limit, self.time_s)
            at_minimum = ctrl.frequency_hz <= comp.min_frequency_hz + 1e-9
            margin = c.auto_stop_margin_k
            # 冷房：冰水降到設定值（7 °C）即停機（使用者決定）；暖房：最低頻率且熱水超過設定值 + 裕度才停。
            stop = (controlled <= c.cooling_setpoint_k if cooling
                    else at_minimum and controlled >= c.heating_setpoint_k + margin)
        else:
            ctrl.frequency_hz = self._stepper.start(s.manual_frequency_hz, limit, self.time_s)
            stop = controlled <= c.cooling_setpoint_k if cooling else controlled >= c.heating_setpoint_k
        if stop:
            ctrl.compressor_on = False
            ctrl.off_since_s = self.time_s
            self._event("stop", "已達溫度目標，壓縮機停機")
            return frozenset()
        # 防凍停機：已在最低頻率運轉、冰水出水溫度仍低於設定，持續 freeze_stop_delay_s。
        at_floor = perf is not None and perf.frequency_hz <= comp.min_frequency_hz + 1e-9
        if perf is not None and plate_in_use and at_floor and self._evaporator_leaving_k(perf) < c.freeze_limit_start_k:
            ctrl.freeze_timer_s += dt_s
            if ctrl.freeze_timer_s >= c.freeze_stop_delay_s:
                ctrl.compressor_on = False
                ctrl.freeze_stopped = True
                ctrl.freeze_timer_s = 0.0
                ctrl.off_since_s = self.time_s
                self._event("freeze_stop", f"冰水出水溫度低於 {c.freeze_limit_start_k - 273.15:g} °C，防凍保護停機")
                return frozenset()
        else:
            ctrl.freeze_timer_s = 0.0
        warnings: set[str] = set()
        if limiting:
            warnings.add(WARNING_HP_LIMITING)
        if freezing:
            warnings.add(WARNING_FREEZE_LIMITING)
        return frozenset(warnings)

    def _control_error(self) -> float:
        """PID 控制誤差：冷房為冰水 − 目標，暖房為目標 − 熱水（正值表示需要更多能力）。

回傳：
    K。"""
        c = self.params.control
        if self._settings.operation is OperationMode.COOLING:
            return self.cold_water_k - c.cooling_setpoint_k
        return c.heating_setpoint_k - self.hot_water_k

    def run(self, duration_s: float, dt_s: float = 5.0) -> list[StepRecord]:
        """連續推進。

參數：
    duration_s: 模擬時間。
    dt_s: 時間步長。

回傳：
    每一步的記錄。"""
        records = []
        end = self.time_s + duration_s
        while self.time_s < end - 1e-9:
            records.append(self.step(min(dt_s, end - self.time_s)))
        return records


@dataclass(frozen=True)
class SimulationSummary:
    """一段模擬的摘要指標。"""

    duration_s: float
    stops: int
    run_fraction: float
    mean_frequency_hz: float
    mean_fan_coil_load_w: float
    energy_used_j: float
    system_cop: float | None
    max_condensing_k: float | None
    min_evaporating_k: float | None
    warnings: frozenset[str] = field(default_factory=frozenset)
    reheat_energy_j: float = 0.0


def summarize(records: list[StepRecord], events: list[SimulationEvent]) -> SimulationSummary:
    """彙總記錄。

參數：
    records: 連續的時間步記錄。
    events: 事件。

回傳：
    SimulationSummary。

引發：
    ValueError：記錄為空時。"""
    if not records:
        raise ValueError("沒有模擬記錄。")
    start = records[0].time_s
    duration = sum(r.dt_s for r in records)
    running = [r for r in records if r.compressor_on]
    run_time = sum(r.dt_s for r in running)
    energy = records[-1].energy_used_j - (records[0].energy_used_j - records[0].total_power_w * records[0].dt_s)
    fan_energy = sum(r.fan_coil_load_w * r.dt_s for r in records)
    stops = sum(1 for e in events if e.code == "stop" and start < e.time_s <= start + duration)
    warnings: frozenset[str] = frozenset().union(*(r.warnings for r in records))
    condensing = [r.condensing_k for r in running if r.condensing_k is not None]
    evaporating = [r.evaporating_k for r in running if r.evaporating_k is not None]
    return SimulationSummary(
        duration_s=duration,
        stops=stops,
        run_fraction=run_time / duration if duration else 0.0,
        mean_frequency_hz=sum(r.frequency_hz * r.dt_s for r in running) / run_time if running else 0.0,
        mean_fan_coil_load_w=fan_energy / duration if duration else 0.0,
        energy_used_j=energy,
        system_cop=fan_energy / energy if energy > 0 else None,
        max_condensing_k=max(condensing) if condensing else None,
        min_evaporating_k=min(evaporating) if evaporating else None,
        warnings=warnings,
        reheat_energy_j=sum(r.reheat_w * r.dt_s for r in records),
    )
