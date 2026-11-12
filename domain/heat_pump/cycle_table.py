"""以 (蒸發溫度, 冷凝溫度) 網格預先計算冷媒狀態，模擬時以內插取值。

動態模擬每個時間步要求解上百次循環；直接查詢狀態服務太慢，因此啟動時透過
:class:`~domain.refrigeration.states.ThermodynamicStateProvider` 建表，之後只做內插。

表內容（單位質量，canonical SI）：
- 只依蒸發溫度 Te：蒸發壓力 pe、吸氣焓 h1、吸氣熵 s1、吸氣密度 ρ1。
- 只依冷凝溫度 Tc：冷凝壓力 pc、液管焓 h3。
- 依 (Te, Tc)：等熵排氣焓 h2s、實際排氣溫度 Td（以建表時的總效率計算）。
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from domain.refrigeration.states import ThermodynamicStateProvider, query_state

from .parameters import CycleSettings, celsius


@dataclass(frozen=True)
class CycleProperties:
    """某 (Te, Tc) 的單位質量循環性質。"""

    evaporating_pressure_pa: float
    condensing_pressure_pa: float
    suction_enthalpy_j_kg: float
    suction_density_kg_m3: float
    discharge_enthalpy_j_kg: float
    liquid_enthalpy_j_kg: float
    discharge_temperature_k: float


def _grid(start: float, stop: float, step: float) -> list[float]:
    """產生含兩端的等距網格。

參數：
    start: 起點。
    stop: 終點。
    step: 間距。

回傳：
    網格點。"""
    count = int(round((stop - start) / step))
    return [start + i * step for i in range(count + 1)]


def _locate(grid: Sequence[float], value: float) -> tuple[int, float]:
    """找出 value 所在區間與內插權重（超出範圍時夾在端點）。

參數：
    grid: 遞增網格。
    value: 查詢值。

回傳：
    (左端索引, 權重 0–1)。"""
    if value <= grid[0]:
        return 0, 0.0
    if value >= grid[-1]:
        return len(grid) - 2, 1.0
    index = bisect_right(grid, value) - 1
    return index, (value - grid[index]) / (grid[index + 1] - grid[index])


def _lerp(values: Sequence[float], index: int, weight: float) -> float:
    """一維線性內插。

參數：
    values: 數值。
    index: 左端索引。
    weight: 權重。

回傳：
    內插值。"""
    return values[index] + (values[index + 1] - values[index]) * weight


class CycleTable:
    """R410A 等冷媒的循環性質表。"""

    def __init__(
        self,
        settings: CycleSettings,
        overall_efficiency: float,
        evaporating_grid_k: Sequence[float],
        condensing_grid_k: Sequence[float],
        suction: Sequence[tuple[float, float, float, float]],
        condensing: Sequence[tuple[float, float]],
        discharge: Sequence[Sequence[tuple[float, float]]],
    ) -> None:
        """以已計算的網格資料建立表（一般請用 :meth:`build`）。

參數：
    settings: 循環設定。
    overall_efficiency: 建表時使用的壓縮機總效率。
    evaporating_grid_k: 蒸發溫度網格。
    condensing_grid_k: 冷凝溫度網格。
    suction: 每個 Te 的 (pe, h1, s1, ρ1)。
    condensing: 每個 Tc 的 (pc, h3)。
    discharge: [Te][Tc] 的 (h2s, Td)。

回傳：
    無。"""
        self.settings = settings
        self.overall_efficiency = overall_efficiency
        self.evaporating_grid_k = list(evaporating_grid_k)
        self.condensing_grid_k = list(condensing_grid_k)
        self._suction = [tuple(row) for row in suction]
        self._condensing = [tuple(row) for row in condensing]
        self._discharge = [[tuple(cell) for cell in row] for row in discharge]

    @property
    def evaporating_range_k(self) -> tuple[float, float]:
        """蒸發溫度適用範圍。

回傳：
            (下限, 上限) K。"""
        return self.evaporating_grid_k[0], self.evaporating_grid_k[-1]

    @property
    def condensing_range_k(self) -> tuple[float, float]:
        """冷凝溫度適用範圍。

回傳：
            (下限, 上限) K。"""
        return self.condensing_grid_k[0], self.condensing_grid_k[-1]

    @classmethod
    def build(
        cls,
        provider: ThermodynamicStateProvider,
        settings: CycleSettings | None = None,
        overall_efficiency: float = 0.66,
        evaporating_range_k: tuple[float, float] = (celsius(-30.0), celsius(20.0)),
        condensing_range_k: tuple[float, float] = (celsius(10.0), celsius(70.0)),
        step_k: float = 1.0,
    ) -> CycleTable:
        """透過狀態服務建表。

參數：
    provider: canonical SI 狀態服務。
    settings: 循環設定（冷媒、過熱度、過冷度、reference state）。
    overall_efficiency: 壓縮機總效率，用於排氣溫度。
    evaporating_range_k: 蒸發溫度範圍。
    condensing_range_k: 冷凝溫度範圍。
    step_k: 網格間距。

回傳：
    CycleTable。

引發：
    ValueError：參數不合理時。"""
        settings = settings or CycleSettings()
        if not 0 < overall_efficiency <= 1:
            raise ValueError("壓縮機總效率必須介於 0 與 1 之間。")
        if step_k <= 0:
            raise ValueError("網格間距必須大於 0。")
        if settings.superheat_k < 0 or settings.subcooling_k < 0:
            raise ValueError("過熱度與過冷度不得為負。")
        if evaporating_range_k[1] >= condensing_range_k[1]:
            raise ValueError("冷凝溫度範圍上限必須高於蒸發溫度範圍上限。")
        fluid = settings.fluid
        ref = settings.reference_state

        def state(known, description):
            return query_state(provider, fluid, known, ref, description)

        te_grid = _grid(*evaporating_range_k, step_k)
        tc_grid = _grid(*condensing_range_k, step_k)
        suction = []
        for te in te_grid:
            pe = float(state([("T", te), ("Q", 1.0)], "蒸發壓力")["P"])
            if settings.superheat_k > 0:
                s1 = state([("T", te + settings.superheat_k), ("P", pe)], "壓縮機吸氣狀態")
            else:
                s1 = state([("P", pe), ("Q", 1.0)], "壓縮機吸氣狀態")
            suction.append((pe, float(s1["H"]), float(s1["S"]), float(s1["D"])))
        condensing = []
        for tc in tc_grid:
            pc = float(state([("T", tc), ("Q", 0.0)], "冷凝壓力")["P"])
            if settings.subcooling_k > 0:
                s3 = state([("T", tc - settings.subcooling_k), ("P", pc)], "冷凝器出口狀態")
            else:
                s3 = state([("P", pc), ("Q", 0.0)], "冷凝器出口狀態")
            condensing.append((pc, float(s3["H"])))
        discharge = []
        for te, (_pe, h1, s1, _rho) in zip(te_grid, suction):
            row = []
            for tc, (pc, _h3) in zip(tc_grid, condensing):
                if tc <= te:
                    row.append((math.nan, math.nan))
                    continue
                h2s = float(state([("P", pc), ("S", s1)], "等熵排氣狀態")["H"])
                h2 = h1 + (h2s - h1) / overall_efficiency
                td = float(state([("P", pc), ("H", h2)], "排氣狀態")["T"])
                row.append((h2s, td))
            discharge.append(row)
        return cls(settings, overall_efficiency, te_grid, tc_grid, suction, condensing, discharge)

    def properties(self, evaporating_k: float, condensing_k: float) -> CycleProperties:
        """以內插取得 (Te, Tc) 的循環性質。超出表範圍時夾在邊界。

參數：
    evaporating_k: 蒸發溫度。
    condensing_k: 冷凝溫度。

回傳：
    CycleProperties。

引發：
    ValueError：冷凝溫度不高於蒸發溫度時。"""
        if condensing_k <= evaporating_k:
            raise ValueError("冷凝溫度必須高於蒸發溫度。")
        i, wi = _locate(self.evaporating_grid_k, evaporating_k)
        j, wj = _locate(self.condensing_grid_k, condensing_k)
        pe = _lerp([row[0] for row in self._suction[i : i + 2]], 0, wi)
        h1 = _lerp([row[1] for row in self._suction[i : i + 2]], 0, wi)
        rho1 = _lerp([row[3] for row in self._suction[i : i + 2]], 0, wi)
        pc = _lerp([row[0] for row in self._condensing[j : j + 2]], 0, wj)
        h3 = _lerp([row[1] for row in self._condensing[j : j + 2]], 0, wj)
        h2s = self._bilinear(i, wi, j, wj, 0)
        td = self._bilinear(i, wi, j, wj, 1)
        h2 = h1 + (h2s - h1) / self.overall_efficiency
        return CycleProperties(pe, pc, h1, rho1, h2, h3, td)

    def _bilinear(self, i: int, wi: float, j: int, wj: float, k: int) -> float:
        """二維雙線性內插；鄰點缺值（Tc ≤ Te）時退回可用的鄰點。

參數：
    i: Te 左端索引。
    wi: Te 權重。
    j: Tc 左端索引。
    wj: Tc 權重。
    k: 欄位（0 = h2s，1 = Td）。

回傳：
    內插值。

引發：
    ValueError：周圍四點皆無資料時。"""
        corners = (
            (self._discharge[i][j][k], (1 - wi) * (1 - wj)),
            (self._discharge[i][j + 1][k], (1 - wi) * wj),
            (self._discharge[i + 1][j][k], wi * (1 - wj)),
            (self._discharge[i + 1][j + 1][k], wi * wj),
        )
        valid = [(value, weight) for value, weight in corners if not math.isnan(value)]
        if not valid:
            raise ValueError("冷凝溫度與蒸發溫度太接近，超出性質表範圍。")
        total = sum(weight for _value, weight in valid)
        if total <= 0:
            return sum(value for value, _weight in valid) / len(valid)
        return sum(value * weight for value, weight in valid) / total
