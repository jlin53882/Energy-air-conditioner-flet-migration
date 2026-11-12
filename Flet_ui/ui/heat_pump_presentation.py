"""熱泵動態模擬頁的呈現邏輯（不依賴 Flet，可單獨測試）。

- 系統示意圖的幾何（邏輯座標 1000 × 640）：「左冷右熱」版面——左側冰水桶與板式蒸發器、
  右側熱水桶與板式冷凝器、上方壓縮機與送風機、下方室外換熱器。
- 由 :class:`~domain.heat_pump.StepRecord` 推導每條管路的狀態與依冷媒溫度的顏色、
  電磁閥開關、元件運轉與狀態點數值框。
- 水溫／冷媒溫度配色、流動點位置、P-h／T-s 循環與數值格式化。

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
CANVAS_HEIGHT = 640

Point = tuple[float, float]


class LineState(str, Enum):
    """管路狀態。"""

    DISCHARGE = "discharge"
    LIQUID = "liquid"
    TWO_PHASE = "two_phase"
    SUCTION = "suction"
    WATER = "water"
    IDLE = "idle"


LINE_LABELS: dict[LineState, str] = {
    LineState.DISCHARGE: "高壓氣（排氣）",
    LineState.LIQUID: "高壓液",
    LineState.TWO_PHASE: "低壓兩相",
    LineState.SUCTION: "低壓氣（吸氣）",
    LineState.WATER: "水路",
    LineState.IDLE: "未使用",
}

WATER_LINE_COLOR = "#3A8F8A"
IDLE_LINE_COLOR = "#CDCDC4"


@dataclass(frozen=True)
class Pipe:
    """一條管路：識別碼、折線（方向即流向）與運轉時的冷媒狀態。"""

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
COLD_TANK = Box("cold_tank", "冰水桶 160 L", 40, 290, 130, 230)
HOT_TANK = Box("hot_tank", "熱水桶 160 L", 830, 290, 130, 230)
EVAPORATOR = Box("evaporator", "板式蒸發器", 250, 300, 70, 140)
CONDENSER = Box("condenser", "板式冷凝器", 680, 300, 70, 140)
OUTDOOR = Box("outdoor", "室外換熱器", 380, 500, 220, 90)
FAN_A = Box("fan_a", "送風機 A", 200, 45, 120, 55)
FAN_B = Box("fan_b", "送風機 B", 680, 45, 120, 55)
COMPRESSOR = Box("compressor", "壓縮機", 465, 62, 70, 86)
COMPRESSOR_CENTER: Point = (500.0, 110.0)
EXPANSION_VALVE: Point = (650.0, 470.0)
OUTDOOR_FAN_CENTER: Point = (525.0, 545.0)
COLD_PUMP: Point = (210.0, 420.0)
HOT_PUMP: Point = (790.0, 420.0)
FAN_PUMP: Point = (150.0, 28.0)

BOXES = (COLD_TANK, HOT_TANK, EVAPORATOR, CONDENSER, OUTDOOR, FAN_A, FAN_B)

# ---- 冷媒管 ----
REFRIGERANT_PIPES: tuple[Pipe, ...] = (
    Pipe("dis_main", ((535, 90), (560, 90)), LineState.DISCHARGE),
    Pipe("dis_hx2", ((560, 90), (660, 90), (660, 320), (680, 320)), LineState.DISCHARGE),
    Pipe("dis_out", ((560, 90), (560, 500)), LineState.DISCHARGE),
    Pipe("liq_hx2", ((680, 410), (650, 410), (650, 455)), LineState.LIQUID),
    Pipe("liq_out", ((590, 500), (590, 410), (650, 410), (650, 455)), LineState.LIQUID),
    Pipe("lp_hx1", ((650, 485), (650, 615), (335, 615), (335, 425), (320, 425)), LineState.TWO_PHASE),
    Pipe("lp_out", ((650, 485), (650, 560), (600, 560)), LineState.TWO_PHASE),
    Pipe("suc_hx1", ((320, 315), (345, 315), (345, 135), (420, 135), (465, 135)), LineState.SUCTION),
    Pipe("suc_out", ((420, 500), (420, 135), (465, 135)), LineState.SUCTION),
)

ACTIVE_PIPES: dict[RefrigerantMode, frozenset[str]] = {
    RefrigerantMode.DUAL: frozenset({"dis_main", "dis_hx2", "liq_hx2", "lp_hx1", "suc_hx1"}),
    RefrigerantMode.SMART_COOLING: frozenset({"dis_main", "dis_out", "liq_out", "lp_hx1", "suc_hx1"}),
    RefrigerantMode.SMART_HEATING: frozenset({"dis_main", "dis_hx2", "liq_hx2", "lp_out", "suc_out"}),
}

# ---- 水管（方向即流向） ----
COLD_SUPPLY = Pipe("cold_supply", ((170, 420), (250, 420)))
COLD_RETURN = Pipe("cold_return", ((250, 320), (170, 320)))
HOT_SUPPLY = Pipe("hot_supply", ((830, 420), (750, 420)))
HOT_RETURN = Pipe("hot_return", ((750, 320), (830, 320)))
FAN_HEADER = Pipe("fan_header", ((60, 28), (940, 28)))
FAN_DROPS = Pipe("fan_drops", ((260, 28), (260, 45)))
FAN_DROP_B = Pipe("fan_drop_b", ((740, 28), (740, 45)))
FAN_LOOP_COLD = Pipe("fan_loop_cold", ((60, 282), (60, 28)))
FAN_LOOP_HOT = Pipe("fan_loop_hot", ((940, 282), (940, 28)))

# ---- 電磁閥：位置與方向（h 水平管、v 垂直管） ----
VALVE_POSITIONS: dict[int, Point] = {
    1: (548, 90),
    8: (660, 205),
    9: (560, 300),
    6: (590, 455),
    7: (650, 432),
    10: (480, 615),
    11: (625, 560),
    2: (60, 615),
    3: (90, 615),
    4: (120, 615),
    5: (150, 615),
}
VALVE_ORIENTATION: dict[int, str] = {1: "h", 8: "v", 9: "v", 6: "v", 7: "v", 10: "h", 11: "h",
                                     2: "h", 3: "h", 4: "h", 5: "h"}
VALVE_LABEL_OFFSETS: dict[int, Point] = {
    1: (0.0, -16.0), 8: (-24.0, 0.0), 9: (-24.0, 0.0), 6: (-24.0, 0.0), 7: (24.0, 0.0),
    10: (0.0, 15.0), 11: (0.0, 15.0),
}

# ---- 狀態點數值框：(左上角, 寬, 高) ----
CALLOUT_BOXES: dict[str, tuple[Point, float, float]] = {
    "suction": ((180.0, 140.0), 155.0, 58.0),
    "discharge": ((685.0, 118.0), 160.0, 58.0),
    "liquid": ((688.0, 458.0), 138.0, 54.0),
    "expansion": ((688.0, 522.0), 138.0, 54.0),
    "outdoor": ((185.0, 528.0), 160.0, 44.0),
}

# ---- 冷媒溫度配色 ----
_TEMPERATURE_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (-10.0, (0x1E, 0x4F, 0xD8)),
    (8.0, (0x2F, 0x8F, 0xE8)),
    (20.0, (0x52, 0xBE, 0xE8)),
    (35.0, (0xF2, 0xA3, 0x3A)),
    (60.0, (0xE8, 0x59, 0x0C)),
    (95.0, (0xC8, 0x1E, 0x1E)),
)

_WATER_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (5.0, (0x1F, 0x4E, 0x89)),
    (15.0, (0x6B, 0xA8, 0xD6)),
    (27.0, (0xE9, 0xE4, 0xD8)),
    (38.0, (0xE8, 0x94, 0x5A)),
    (50.0, (0xC2, 0x41, 0x0C)),
)


def _interpolate(stops, value_c: float) -> str:
    """色階內插。

參數：
    stops: (°C, RGB) 色階。
    value_c: 溫度 °C。

回傳：
    #RRGGBB。"""
    if value_c <= stops[0][0]:
        rgb = stops[0][1]
    elif value_c >= stops[-1][0]:
        rgb = stops[-1][1]
    else:
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= value_c <= t1:
                w = (value_c - t0) / (t1 - t0)
                rgb = tuple(round(a + (b - a) * w) for a, b in zip(c0, c1))
                break
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def refrigerant_color(temperature_k: float) -> str:
    """冷媒管配色：−10 °C 深藍 → 20 °C 淺藍 → 35 °C 琥珀 → 95 °C 紅。

參數：
    temperature_k: 冷媒溫度。

回傳：
    #RRGGBB。"""
    return _interpolate(_TEMPERATURE_STOPS, temperature_k - 273.15)


def water_color(temperature_k: float) -> str:
    """水溫配色：5 °C 深藍 → 27 °C 米白 → 50 °C 橘紅。

參數：
    temperature_k: 水溫。

回傳：
    #RRGGBB。"""
    return _interpolate(_WATER_STOPS, temperature_k - 273.15)


TEMPERATURE_LEGEND: tuple[tuple[float, str], ...] = tuple(
    (t, "#{:02X}{:02X}{:02X}".format(*rgb)) for t, rgb in _TEMPERATURE_STOPS
)


@dataclass(frozen=True)
class Callout:
    """狀態點數值框。"""

    key: str
    title: str
    lines: tuple[str, ...]
    accent: str


@dataclass(frozen=True)
class SchematicState:
    """某一步的示意圖狀態。"""

    pipe_states: dict[str, LineState]
    pipe_colors: dict[str, str]
    valves_open: frozenset[int]
    compressor_on: bool
    outdoor_role: str | None
    fans_on: frozenset[str]
    fan_loop_tank: str
    cold_color: str
    hot_color: str
    callouts: tuple[Callout, ...]


def _pipe_temperature(record: StepRecord, state: LineState) -> float | None:
    """各段冷媒溫度：排氣 Td、液管 Tc − SC、兩相 Te、吸氣 Te + SH。

參數：
    record: 記錄。
    state: 管路狀態。

回傳：
    K；停機時為 None。"""
    return {
        LineState.DISCHARGE: record.discharge_k,
        LineState.LIQUID: record.liquid_temperature_k,
        LineState.TWO_PHASE: record.evaporating_k,
        LineState.SUCTION: record.suction_temperature_k,
    }.get(state)


def _c(value_k: float | None) -> str:
    """K → 「x.x °C」。

參數：
    value_k: 溫度。

回傳：
    文字。"""
    return "—" if value_k is None else f"{value_k - 273.15:.1f} °C"


def callouts(record: StepRecord) -> tuple[Callout, ...]:
    """狀態點數值框（停機時不顯示）。

參數：
    record: 記錄。

回傳：
    Callout。"""
    if not record.compressor_on:
        return ()
    pe = record.evaporating_pressure_pa / 1e5
    pc = record.condensing_pressure_pa / 1e5
    superheat = record.suction_temperature_k - record.evaporating_k
    subcooling = record.condensing_k - record.liquid_temperature_k
    items = [
        Callout("suction", "① 吸氣", (f"Te {_c(record.evaporating_k)}", f"{pe:.2f} bar · SH {superheat:.1f} K"),
                refrigerant_color(record.suction_temperature_k)),
        Callout("discharge", "② 排氣", (f"Td {_c(record.discharge_k)}", f"{pc:.2f} bar · Tc {_c(record.condensing_k)}"),
                refrigerant_color(record.discharge_k)),
        Callout("liquid", "③ 液管", (f"{_c(record.liquid_temperature_k)}", f"過冷 SC {subcooling:.1f} K"),
                refrigerant_color(record.liquid_temperature_k)),
        Callout("expansion", "④ 膨脹後", (f"{_c(record.evaporating_k)}", f"{pe:.2f} bar"),
                refrigerant_color(record.evaporating_k)),
    ]
    if record.mode is not RefrigerantMode.DUAL:
        role = "冷凝放熱" if record.mode is RefrigerantMode.SMART_COOLING else "蒸發吸熱"
        items.append(Callout("outdoor", "室外換熱器", (f"{role} {record.outdoor_heat_w / 1000:.2f} kW", ""),
                             "#5E6764"))
    return tuple(items)


def schematic_state(record: StepRecord) -> SchematicState:
    """由記錄推導示意圖狀態。停機時冷媒管全部顯示為未使用，電磁閥維持模式設定。

參數：
    record: 時間步記錄。

回傳：
    SchematicState。"""
    active = ACTIVE_PIPES[record.mode] if record.compressor_on else frozenset()
    states: dict[str, LineState] = {}
    colors: dict[str, str] = {}
    for pipe in REFRIGERANT_PIPES:
        line_state = pipe.refrigerant_state if pipe.key in active else LineState.IDLE
        states[pipe.key] = line_state
        temperature = _pipe_temperature(record, line_state) if line_state is not LineState.IDLE else None
        colors[pipe.key] = refrigerant_color(temperature) if temperature is not None else IDLE_LINE_COLOR
    role = None
    if record.compressor_on and record.mode is RefrigerantMode.SMART_COOLING:
        role = "condenser"
    elif record.compressor_on and record.mode is RefrigerantMode.SMART_HEATING:
        role = "evaporator"
    return SchematicState(
        pipe_states=states,
        pipe_colors=colors,
        valves_open=record.valves_open,
        compressor_on=record.compressor_on,
        outdoor_role=role,
        fans_on=record.fans,
        fan_loop_tank="cold_tank" if record.operation is OperationMode.COOLING else "hot_tank",
        cold_color=water_color(record.cold_water_k),
        hot_color=water_color(record.hot_water_k),
        callouts=callouts(record),
    )


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
class CyclePath:
    """熱力圖上的循環路徑與四個狀態點（1 吸氣、2 排氣、3 液管、4 膨脹後）。"""

    points: tuple[tuple[float, float], ...]
    markers: tuple[tuple[float, float], ...] = ()


def ph_cycle(record: StepRecord) -> CyclePath | None:
    """P-h 循環（h kJ/kg、P kPa）。

參數：
    record: 時間步記錄。

回傳：
    CyclePath；停機時為 None。"""
    if not record.compressor_on or record.suction_enthalpy_j_kg is None:
        return None
    pe = record.evaporating_pressure_pa / 1000
    pc = record.condensing_pressure_pa / 1000
    h1 = record.suction_enthalpy_j_kg / 1000
    h2 = record.discharge_enthalpy_j_kg / 1000
    h3 = record.liquid_enthalpy_j_kg / 1000
    return CyclePath(((h1, pe), (h2, pc), (h3, pc), (h3, pe), (h1, pe)), ((h1, pe), (h2, pc), (h3, pc), (h3, pe)))


PhCycle = CyclePath


def _entropy_at(curve: Sequence[tuple[float, float]], temperature_k: float) -> float | None:
    """在飽和線 (s, T) 上依溫度內插熵。

參數：
    curve: 依溫度遞增的 (s J/(kg·K), T K)。
    temperature_k: 溫度。

回傳：
    J/(kg·K)；超出範圍時為 None。"""
    for (s0, t0), (s1, t1) in zip(curve, curve[1:]):
        if t0 <= temperature_k <= t1:
            w = (temperature_k - t0) / (t1 - t0) if t1 != t0 else 0.0
            return s0 + (s1 - s0) * w
    return None


def ts_cycle(
    record: StepRecord,
    liquid_ts: Sequence[tuple[float, float]] = (),
    vapor_ts: Sequence[tuple[float, float]] = (),
) -> CyclePath | None:
    """T-s 循環（s kJ/(kg·K)、T °C）。

給了飽和線時，冷凝段走 ② → 飽和蒸氣(Tc) → 飽和液(Tc) → ③，蒸發段走 ④ → 飽和蒸氣(Te) → ①；
沒有飽和線時只連四個狀態點。

參數：
    record: 時間步記錄。
    liquid_ts: 飽和液線 (s, T)。
    vapor_ts: 飽和蒸氣線 (s, T)。

回傳：
    CyclePath；停機或缺熵值時為 None。"""
    if not record.compressor_on or record.suction_entropy_j_kg_k is None:
        return None
    te, tc = record.evaporating_k, record.condensing_k
    p1 = (record.suction_entropy_j_kg_k, record.suction_temperature_k)
    p2 = (record.discharge_entropy_j_kg_k, record.discharge_k)
    p3 = (record.liquid_entropy_j_kg_k, record.liquid_temperature_k)
    p4 = (record.evaporator_inlet_entropy_j_kg_k, te)
    sg_c, sf_c, sg_e = _entropy_at(vapor_ts, tc), _entropy_at(liquid_ts, tc), _entropy_at(vapor_ts, te)
    path = [p1, p2]
    if sg_c is not None and sf_c is not None:
        path += [(sg_c, tc), (sf_c, tc)]
    path += [p3, p4]
    if sg_e is not None:
        path.append((sg_e, te))
    path.append(p1)

    def convert(points):
        return tuple((s / 1000, t - 273.15) for s, t in points)

    return CyclePath(convert(path), convert((p1, p2, p3, p4)))


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
