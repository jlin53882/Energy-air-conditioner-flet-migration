"""熱泵動態模擬頁的呈現邏輯（不依賴 Flet，可單獨測試）。

- 系統示意圖的幾何：元件位置、冷媒管與水管的折線（邏輯座標 1000 × 560）。
- 由 :class:`~domain.heat_pump.StepRecord` 推導每條管路的狀態、電磁閥開關與元件運轉。
- 水溫配色、流動點位置與數值格式化。

示意圖是簡化的邏輯流路（依 ``docs/simulation-model.md`` §2.1 的電磁閥狀態表），
不是實際配管圖；電磁閥位置只標示其控制的支路。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from domain.heat_pump import OperationMode, RefrigerantMode, StepRecord

CANVAS_WIDTH = 1000
CANVAS_HEIGHT = 560

Point = tuple[float, float]


class LineState(str, Enum):
    """管路狀態（決定顏色）。"""

    DISCHARGE = "discharge"
    LIQUID = "liquid"
    TWO_PHASE = "two_phase"
    SUCTION = "suction"
    WATER = "water"
    IDLE = "idle"


LINE_COLORS: dict[LineState, str] = {
    LineState.DISCHARGE: "#C2410C",
    LineState.LIQUID: "#E8945A",
    LineState.TWO_PHASE: "#6BA8D6",
    LineState.SUCTION: "#1F4E89",
    LineState.WATER: "#3A8F8A",
    LineState.IDLE: "#CDCDC4",
}

LINE_LABELS: dict[LineState, str] = {
    LineState.DISCHARGE: "高壓氣（排氣）",
    LineState.LIQUID: "高壓液",
    LineState.TWO_PHASE: "低壓兩相",
    LineState.SUCTION: "低壓氣（吸氣）",
    LineState.WATER: "水路",
    LineState.IDLE: "未使用",
}


@dataclass(frozen=True)
class Pipe:
    """一條管路：識別碼、折線與（冷媒管）在運轉時的狀態。"""

    key: str
    points: tuple[Point, ...]
    refrigerant_state: LineState | None = None


@dataclass(frozen=True)
class Box:
    """矩形元件。"""

    key: str
    label: str
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> Point:
        """中心點。

回傳：
            (x, y)。"""
        return self.x + self.width / 2, self.y + self.height / 2


# ---- 元件位置 ----
COLD_TANK = Box("cold_tank", "冰水桶", 40, 230, 120, 230)
HOT_TANK = Box("hot_tank", "熱水桶", 200, 230, 120, 230)
FAN_A = Box("fan_a", "送風機 A", 40, 40, 120, 60)
FAN_B = Box("fan_b", "送風機 B", 200, 40, 120, 60)
CONDENSER = Box("condenser", "板式冷凝器", 430, 120, 70, 110)
EVAPORATOR = Box("evaporator", "板式蒸發器", 430, 380, 70, 110)
OUTDOOR = Box("outdoor", "室外換熱器", 790, 220, 170, 120)
COMPRESSOR_CENTER: Point = (650, 100)
COMPRESSOR_RADIUS = 38
EXPANSION_VALVE: Point = (650, 470)
OUTDOOR_FAN_CENTER: Point = (875, 280)
COLD_PUMP: Point = (250, 530)
HOT_PUMP: Point = (380, 200)
FAN_PUMP: Point = (220, 120)

BOXES = (COLD_TANK, HOT_TANK, FAN_A, FAN_B, CONDENSER, EVAPORATOR, OUTDOOR)

# ---- 冷媒管（運轉時的狀態） ----
REFRIGERANT_PIPES: tuple[Pipe, ...] = (
    Pipe("dis_main", ((650, 62), (650, 30)), LineState.DISCHARGE),
    Pipe("dis_hx2", ((650, 30), (560, 30), (560, 140), (500, 140)), LineState.DISCHARGE),
    Pipe("dis_out", ((650, 30), (840, 30), (840, 220)), LineState.DISCHARGE),
    Pipe("liq_hx2", ((500, 210), (580, 210), (580, 470), (632, 470)), LineState.LIQUID),
    Pipe("liq_out", ((790, 300), (740, 300), (740, 440), (600, 440), (600, 470), (632, 470)), LineState.LIQUID),
    Pipe("lp_hx1", ((650, 488), (650, 520), (520, 520), (520, 470), (500, 470)), LineState.TWO_PHASE),
    Pipe("lp_out", ((650, 488), (650, 520), (900, 520), (900, 340)), LineState.TWO_PHASE),
    Pipe("suc_hx1", ((500, 400), (610, 400), (610, 160), (650, 160), (650, 138)), LineState.SUCTION),
    Pipe("suc_out", ((805, 220), (805, 160), (650, 160), (650, 138)), LineState.SUCTION),
)

ACTIVE_PIPES: dict[RefrigerantMode, frozenset[str]] = {
    RefrigerantMode.DUAL: frozenset({"dis_main", "dis_hx2", "liq_hx2", "lp_hx1", "suc_hx1"}),
    RefrigerantMode.SMART_COOLING: frozenset({"dis_main", "dis_out", "liq_out", "lp_hx1", "suc_hx1"}),
    RefrigerantMode.SMART_HEATING: frozenset({"dis_main", "dis_hx2", "liq_hx2", "lp_out", "suc_out"}),
}

# ---- 水管（方向即流向） ----
HOT_SUPPLY = Pipe("hot_supply", ((320, 260), (380, 260), (380, 140), (430, 140)))
HOT_RETURN = Pipe("hot_return", ((430, 210), (350, 210), (350, 300), (320, 300)))
COLD_SUPPLY = Pipe("cold_supply", ((70, 460), (70, 530), (410, 530), (410, 470), (430, 470)))
COLD_RETURN = Pipe("cold_return", ((430, 400), (390, 400), (390, 512), (130, 512), (130, 460)))
FAN_LOOP_COLD = Pipe("fan_loop_cold", ((140, 230), (140, 120)))
FAN_LOOP_HOT = Pipe("fan_loop_hot", ((300, 230), (300, 120)))
FAN_HEADER = Pipe("fan_header", ((140, 100), (140, 120), (300, 120), (300, 100)))

# ---- 電磁閥位置（只標示所控制的支路） ----
VALVE_POSITIONS: dict[int, Point] = {
    1: (650, 46),
    8: (560, 80),
    9: (840, 120),
    6: (740, 370),
    7: (612, 470),
    10: (585, 520),
    11: (900, 430),
    2: (790, 548),
    3: (825, 548),
    4: (860, 548),
    5: (895, 548),
}

# 電磁閥標籤相對位置（預設在右上）
VALVE_LABEL_OFFSETS: dict[int, Point] = {1: (-30.0, 0.0), 7: (-2.0, -20.0), 10: (0.0, 18.0)}


@dataclass(frozen=True)
class SchematicState:
    """某一步的示意圖狀態。"""

    pipe_states: dict[str, LineState]
    valves_open: frozenset[int]
    compressor_on: bool
    outdoor_fan_on: bool
    fans_on: frozenset[str]
    fan_loop_tank: str
    cold_color: str
    hot_color: str


def schematic_state(record: StepRecord) -> SchematicState:
    """由記錄推導示意圖狀態。停機時冷媒管全部顯示為未使用，電磁閥維持模式設定。

參數：
    record: 時間步記錄。

回傳：
    SchematicState。"""
    active = ACTIVE_PIPES[record.mode] if record.compressor_on else frozenset()
    states = {
        pipe.key: (pipe.refrigerant_state if pipe.key in active else LineState.IDLE)
        for pipe in REFRIGERANT_PIPES
    }
    outdoor_used = record.mode is not RefrigerantMode.DUAL
    return SchematicState(
        pipe_states=states,
        valves_open=record.valves_open,
        compressor_on=record.compressor_on,
        outdoor_fan_on=record.compressor_on and outdoor_used,
        fans_on=record.fans,
        fan_loop_tank="cold_tank" if record.operation is OperationMode.COOLING else "hot_tank",
        cold_color=water_color(record.cold_water_k),
        hot_color=water_color(record.hot_water_k),
    )


_COLOR_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (5.0, (0x1F, 0x4E, 0x89)),
    (15.0, (0x6B, 0xA8, 0xD6)),
    (27.0, (0xE9, 0xE4, 0xD8)),
    (38.0, (0xE8, 0x94, 0x5A)),
    (50.0, (0xC2, 0x41, 0x0C)),
)


def water_color(temperature_k: float) -> str:
    """水溫配色：5 °C 深藍 → 27 °C 米白 → 50 °C 橘紅（線性內插）。

參數：
    temperature_k: 水溫。

回傳：
    #RRGGBB。"""
    t = temperature_k - 273.15
    stops = _COLOR_STOPS
    if t <= stops[0][0]:
        rgb = stops[0][1]
    elif t >= stops[-1][0]:
        rgb = stops[-1][1]
    else:
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                w = (t - t0) / (t1 - t0)
                rgb = tuple(round(a + (b - a) * w) for a, b in zip(c0, c1))
                break
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def polyline_length(points: Sequence[Point]) -> float:
    """折線長度。

參數：
    points: 折線點。

回傳：
    長度。"""
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def point_along(points: Sequence[Point], distance: float) -> Point:
    """沿折線距離起點 distance 的位置（超出時循環）。

參數：
    points: 折線點。
    distance: 距離。

回傳：
    (x, y)。"""
    total = polyline_length(points)
    if total <= 0:
        return points[0]
    remaining = distance % total
    for a, b in zip(points, points[1:]):
        segment = math.dist(a, b)
        if remaining <= segment:
            w = remaining / segment if segment else 0.0
            return a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w
        remaining -= segment
    return points[-1]


def flow_dots(points: Sequence[Point], phase: float, spacing: float = 40.0) -> list[Point]:
    """沿折線等距的流動點；phase 每增加 spacing，點前進一格。

參數：
    points: 折線點。
    phase: 相位（距離）。
    spacing: 點間距。

回傳：
    點位置。"""
    total = polyline_length(points)
    if total <= 0:
        return []
    count = max(1, int(total // spacing))
    offset = phase % spacing
    return [point_along(points, offset + i * spacing) for i in range(count) if offset + i * spacing <= total]


# ---- 數值格式化 ----


def format_temperature(value_k: float | None) -> str:
    """K → °C 文字。

參數：
    value_k: 溫度。

回傳：
    文字（無值時為「—」）。"""
    return "—" if value_k is None else f"{value_k - 273.15:.1f}"


def format_power(value_w: float | None) -> str:
    """W → kW 文字。

參數：
    value_w: 功率。

回傳：
    文字。"""
    return "—" if value_w is None else f"{value_w / 1000:.2f}"


def format_pressure(value_pa: float | None) -> str:
    """Pa → bar（絕對）文字。

參數：
    value_pa: 壓力。

回傳：
    文字。"""
    return "—" if value_pa is None else f"{value_pa / 1e5:.2f}"


def format_clock(seconds: float) -> str:
    """模擬時間 hh:mm:ss。

參數：
    seconds: 秒。

回傳：
    文字。"""
    total = int(round(seconds))
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


MODE_SHORT_LABELS: dict[RefrigerantMode, str] = {
    RefrigerantMode.DUAL: "雙效",
    RefrigerantMode.SMART_COOLING: "智慧冷房",
    RefrigerantMode.SMART_HEATING: "智慧暖房",
}

MODE_LABELS: dict[RefrigerantMode, str] = {
    RefrigerantMode.DUAL: "雙效",
    RefrigerantMode.SMART_COOLING: "智慧冷房（室外冷凝）",
    RefrigerantMode.SMART_HEATING: "智慧暖房（室外吸熱）",
}

WARNING_LABELS: dict[str, str] = {
    "high_pressure": "高壓接近上限",
    "hp_limiting": "高壓限頻中",
    "frost": "結霜風險",
    "tripped": "安全停機（需復歸）",
}


def instant_cop(record: StepRecord) -> float | None:
    """瞬時系統 COP（送風機負荷 ÷ 總耗電）。

參數：
    record: 時間步記錄。

回傳：
    COP；無耗電時為 None。"""
    total = record.total_power_w
    return record.fan_coil_load_w / total if total > 0 else None


@dataclass(frozen=True)
class PhCycle:
    """P-h 圖上的循環四點（h kJ/kg、P kPa）。"""

    points: tuple[tuple[float, float], ...]


def ph_cycle(record: StepRecord) -> PhCycle | None:
    """由記錄取得 P-h 循環（1 吸氣 → 2 排氣 → 3 液管 → 4 蒸發器入口 → 1）。

參數：
    record: 時間步記錄。

回傳：
    PhCycle；停機時為 None。"""
    if not record.compressor_on or record.suction_enthalpy_j_kg is None:
        return None
    pe = record.evaporating_pressure_pa / 1000
    pc = record.condensing_pressure_pa / 1000
    h1 = record.suction_enthalpy_j_kg / 1000
    h2 = record.discharge_enthalpy_j_kg / 1000
    h3 = record.liquid_enthalpy_j_kg / 1000
    return PhCycle(((h1, pe), (h2, pc), (h3, pc), (h3, pe), (h1, pe)))


def downsample(values: Sequence, limit: int) -> list:
    """等間隔抽樣到最多 limit 筆（保留最後一筆）。

參數：
    values: 資料。
    limit: 上限。

回傳：
    抽樣後資料。"""
    if len(values) <= limit:
        return list(values)
    stride = math.ceil(len(values) / limit)
    sampled = list(values[::stride])
    if sampled[-1] is not values[-1]:
        sampled.append(values[-1])
    return sampled
