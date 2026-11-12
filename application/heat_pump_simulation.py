"""熱泵動態模擬的 application service。

負責建立（並快取）冷媒性質表、產生模擬 session，以及提供 P-h 圖的飽和線。
建表約需數秒，UI 應在背景執行緒呼叫 :meth:`HeatPumpSimulationService.prepare`。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from domain.heat_pump import (
    CycleTable,
    HeatPumpParameters,
    HeatPumpSimulation,
    OperationMode,
    SimulationSettings,
    celsius,
    default_settings,
)
from domain.refrigeration.states import ThermodynamicStateProvider, query_state


@dataclass(frozen=True)
class SaturationDome:
    """P-h 與 T-s 圖飽和線（canonical SI；焓、熵的 reference state 與模擬相同）。

    ``liquid``／``vapor`` 為 (h, P)；``liquid_ts``／``vapor_ts`` 為 (s, T)。
    """

    liquid: tuple[tuple[float, float], ...]
    vapor: tuple[tuple[float, float], ...]
    reference_state: str
    liquid_ts: tuple[tuple[float, float], ...] = ()
    vapor_ts: tuple[tuple[float, float], ...] = ()


class HeatPumpSimulationService:
    """建立熱泵模擬 session；性質表與飽和線只計算一次。"""

    def __init__(self, state_provider: ThermodynamicStateProvider, params: HeatPumpParameters | None = None) -> None:
        """以狀態服務建立 service。

參數：
    state_provider: canonical SI 狀態服務。
    params: 系統參數（預設為規格值）。

回傳：
    無。"""
        self._provider = state_provider
        self.params = params or HeatPumpParameters()
        self._lock = threading.Lock()
        self._table: CycleTable | None = None
        self._dome: SaturationDome | None = None

    @property
    def is_ready(self) -> bool:
        """性質表是否已建立。

回傳：
            bool。"""
        return self._table is not None and self._dome is not None

    def prepare(self) -> None:
        """建立性質表與飽和線（可重複呼叫；執行緒安全）。

回傳：
    無。"""
        self.table()
        self.saturation_dome()

    def table(self) -> CycleTable:
        """取得（必要時建立）性質表。

回傳：
    CycleTable。"""
        with self._lock:
            if self._table is None:
                self._table = CycleTable.build(
                    self._provider, self.params.cycle, self.params.compressor.overall_efficiency
                )
            return self._table

    def saturation_dome(self, low_k: float = celsius(-30.0), high_k: float = celsius(68.0), step_k: float = 2.0) -> SaturationDome:
        """取得（必要時計算）飽和液線與飽和蒸氣線（P-h 與 T-s）。

參數：
    low_k: 最低飽和溫度。
    high_k: 最高飽和溫度。
    step_k: 溫度間距。

回傳：
    SaturationDome。"""
        with self._lock:
            if self._dome is None:
                cycle = self.params.cycle
                liquid, vapor, liquid_ts, vapor_ts = [], [], [], []
                count = int(round((high_k - low_k) / step_k))
                for i in range(count + 1):
                    t = low_k + i * step_k
                    for quality, target, target_ts in ((0.0, liquid, liquid_ts), (1.0, vapor, vapor_ts)):
                        state = query_state(
                            self._provider, cycle.fluid, [("T", t), ("Q", quality)], cycle.reference_state, "飽和狀態"
                        )
                        target.append((float(state["H"]), float(state["P"])))
                        target_ts.append((float(state["S"]), t))
                self._dome = SaturationDome(
                    tuple(liquid), tuple(vapor), cycle.reference_state, tuple(liquid_ts), tuple(vapor_ts)
                )
            return self._dome

    def new_session(
        self,
        settings: SimulationSettings | None = None,
        initial_cold_k: float = celsius(30.0),
        initial_hot_k: float = celsius(30.0),
    ) -> HeatPumpSimulation:
        """建立新的模擬 session。

參數：
    settings: 初始設定（預設冷房）。
    initial_cold_k: 冰水桶初始溫度。
    initial_hot_k: 熱水桶初始溫度。

回傳：
    HeatPumpSimulation。"""
        return HeatPumpSimulation(
            self.table(),
            self.params,
            settings or default_settings(OperationMode.COOLING),
            initial_cold_k=initial_cold_k,
            initial_hot_k=initial_hot_k,
        )
