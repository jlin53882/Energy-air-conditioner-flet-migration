"""熱泵系統示意圖（Flet canvas）。

幾何與狀態推導在 :mod:`Flet_ui.ui.heat_pump_presentation`；本元件只負責把它畫出來，
並以流動點、旋轉葉片呈現運轉。每次 :meth:`HeatPumpSchematic.render` 重建整組 shape。
"""

from __future__ import annotations

import math

import flet as ft
import flet.canvas as cv

from domain.heat_pump import StepRecord

from ..heat_pump_presentation import (
    BOXES,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    COLD_RETURN,
    COLD_SUPPLY,
    COLD_PUMP,
    COLD_TANK,
    COMPRESSOR_CENTER,
    COMPRESSOR_RADIUS,
    CONDENSER,
    EVAPORATOR,
    EXPANSION_VALVE,
    FAN_A,
    FAN_B,
    FAN_HEADER,
    FAN_LOOP_COLD,
    FAN_LOOP_HOT,
    FAN_PUMP,
    HOT_RETURN,
    HOT_SUPPLY,
    HOT_PUMP,
    HOT_TANK,
    LINE_COLORS,
    OUTDOOR,
    OUTDOOR_FAN_CENTER,
    REFRIGERANT_PIPES,
    VALVE_LABEL_OFFSETS,
    VALVE_POSITIONS,
    LineState,
    SchematicState,
    flow_dots,
    format_temperature,
    schematic_state,
)
from ..theme import TOKENS

_CENTER = ft.Alignment(0.0, 0.0)


def _stroke(color: str, width: float = 3.0, dash: list[float] | None = None) -> ft.Paint:
    """線條畫筆。

參數：
    color: 顏色。
    width: 線寬。
    dash: 虛線樣式。

回傳：
    Paint。"""
    return ft.Paint(color=color, stroke_width=width, style=ft.PaintingStyle.STROKE,
                    stroke_cap=ft.StrokeCap.ROUND, stroke_join=ft.StrokeJoin.ROUND, stroke_dash_pattern=dash)


def _fill(color: str) -> ft.Paint:
    """填色畫筆。

參數：
    color: 顏色。

回傳：
    Paint。"""
    return ft.Paint(color=color, style=ft.PaintingStyle.FILL)


def _label(x: float, y: float, text: str, size: int = 11, color: str | None = None, bold: bool = False) -> cv.Text:
    """置中文字。

參數：
    x: 中心 x。
    y: 中心 y。
    text: 文字。
    size: 字級。
    color: 顏色。
    bold: 是否粗體。

回傳：
    cv.Text。"""
    return cv.Text(x, y, text, alignment=_CENTER, text_align=ft.TextAlign.CENTER,
                   style=ft.TextStyle(size=size, color=color or TOKENS.text_secondary,
                                      weight=ft.FontWeight.W_600 if bold else ft.FontWeight.W_400))


def _polyline(points, paint: ft.Paint) -> cv.Path:
    """折線。

參數：
    points: 點。
    paint: 畫筆。

回傳：
    cv.Path。"""
    elements = [cv.Path.MoveTo(*points[0])] + [cv.Path.LineTo(*p) for p in points[1:]]
    return cv.Path(elements, paint=paint)


def _scale_paint(paint: ft.Paint, k: float) -> ft.Paint:
    """縮放線寬與虛線。

參數：
    paint: 畫筆。
    k: 比例。

回傳：
    新畫筆。"""
    if paint.style is not ft.PaintingStyle.STROKE:
        return paint
    dash = [d * k for d in paint.stroke_dash_pattern] if paint.stroke_dash_pattern else None
    return ft.Paint(color=paint.color, stroke_width=max(1.0, (paint.stroke_width or 1.0) * k), style=paint.style,
                    stroke_cap=paint.stroke_cap, stroke_join=paint.stroke_join, stroke_dash_pattern=dash)


def scale_shapes(shapes: list[cv.Shape], k: float) -> list[cv.Shape]:
    """把邏輯座標（1000 × 560）的 shape 依比例縮放。

參數：
    shapes: shapes。
    k: 比例。

回傳：
    縮放後的 shapes。"""
    if abs(k - 1.0) < 1e-9:
        return shapes
    out: list[cv.Shape] = []
    for shape in shapes:
        if isinstance(shape, cv.Line):
            out.append(cv.Line(shape.x1 * k, shape.y1 * k, shape.x2 * k, shape.y2 * k, paint=_scale_paint(shape.paint, k)))
        elif isinstance(shape, cv.Rect):
            out.append(cv.Rect(shape.x * k, shape.y * k, shape.width * k, shape.height * k,
                               border_radius=shape.border_radius * k if isinstance(shape.border_radius, (int, float))
                               else shape.border_radius, paint=_scale_paint(shape.paint, k)))
        elif isinstance(shape, cv.Circle):
            out.append(cv.Circle(shape.x * k, shape.y * k, shape.radius * k, paint=_scale_paint(shape.paint, k)))
        elif isinstance(shape, cv.Path):
            elements = [type(e)(e.x * k, e.y * k) for e in shape.elements]
            out.append(cv.Path(elements, paint=_scale_paint(shape.paint, k)))
        elif isinstance(shape, cv.Text):
            style = shape.style
            size = max(8.0, (style.size or 11) * k) if style else None
            out.append(cv.Text(shape.x * k, shape.y * k, shape.value, alignment=shape.alignment,
                               text_align=shape.text_align,
                               style=ft.TextStyle(size=size, color=style.color, weight=style.weight) if style else None))
        else:
            out.append(shape)
    return out


def _rotor(center, radius: float, angle: float, color: str, blades: int = 3) -> list[cv.Shape]:
    """旋轉葉片（壓縮機、風扇、水泵）。

參數：
    center: 中心。
    radius: 半徑。
    angle: 角度（rad）。
    color: 顏色。
    blades: 葉片數。

回傳：
    shapes。"""
    cx, cy = center
    shapes: list[cv.Shape] = []
    for i in range(blades):
        a = angle + 2 * math.pi * i / blades
        shapes.append(cv.Line(cx, cy, cx + radius * math.cos(a), cy + radius * math.sin(a), paint=_stroke(color, 2.5)))
    return shapes


class HeatPumpSchematic(ft.Container):
    """可動的系統示意圖。"""

    def __init__(self) -> None:
        """建立空白畫布（未有資料前只畫元件外框）。

回傳：
    無。"""
        self.zoom = 1.0
        self.canvas = cv.Canvas(shapes=[], height=CANVAS_HEIGHT, on_resize=self._on_resize, resize_interval=100)
        super().__init__(
            content=ft.Column([self.canvas], horizontal_alignment=ft.CrossAxisAlignment.STRETCH, spacing=0),
            bgcolor=TOKENS.surface_variant,
            border_radius=TOKENS.radius_md,
            padding=TOKENS.spacing_sm,
        )
        self.state: SchematicState | None = None
        self._last = (None, 0.0, 0.0, 0.0)
        self.canvas.shapes = self._static_shapes(None, None)

    def _on_resize(self, event: cv.CanvasResizeEvent) -> None:
        """依可用寬度縮放（最大 1.3 倍），高度跟著比例調整。

參數：
            event: 尺寸事件。

回傳：
            無。"""
        if not event.width:
            return
        scale = min(1.3, event.width / CANVAS_WIDTH)
        if abs(scale - self.zoom) < 0.01:
            return
        self.zoom = scale
        self.canvas.height = CANVAS_HEIGHT * scale
        self.render(*self._last)
        try:
            self.update()
        except RuntimeError:
            pass

    def render(self, record: StepRecord | None, refrigerant_phase: float, water_phase: float, rotor_angle: float) -> SchematicState | None:
        """依記錄重繪。

參數：
    record: 最新時間步記錄（None 表示尚未開始）。
    refrigerant_phase: 冷媒流動點相位。
    water_phase: 水流動點相位。
    rotor_angle: 旋轉元件角度。

回傳：
    使用的 SchematicState。"""
        self._last = (record, refrigerant_phase, water_phase, rotor_angle)
        state = schematic_state(record) if record is not None else None
        self.state = state
        shapes = self._static_shapes(state, record)
        shapes += self._pipes(state, refrigerant_phase, water_phase)
        shapes += self._components(state, record, rotor_angle)
        self.canvas.shapes = scale_shapes(shapes, self.zoom)
        return state

    def _static_shapes(self, state: SchematicState | None, record: StepRecord | None) -> list[cv.Shape]:
        """元件外框、水桶填色與標籤。

參數：
    state: 示意圖狀態。
    record: 記錄。

回傳：
    shapes。"""
        shapes: list[cv.Shape] = []
        for box in BOXES:
            fill = TOKENS.surface
            if state is not None and box is COLD_TANK:
                fill = state.cold_color
            elif state is not None and box is HOT_TANK:
                fill = state.hot_color
            shapes.append(cv.Rect(box.x, box.y, box.width, box.height, border_radius=10, paint=_fill(fill)))
            shapes.append(cv.Rect(box.x, box.y, box.width, box.height, border_radius=10,
                                  paint=_stroke(TOKENS.border_strong, 1.5)))
        for box in (CONDENSER, EVAPORATOR):
            for i in range(1, 6):
                x = box.x + box.width * i / 6
                shapes.append(cv.Line(x, box.y + 8, x, box.y + box.height - 8, paint=_stroke(TOKENS.border_strong, 1)))
        for i in range(1, 7):
            y = OUTDOOR.y + OUTDOOR.height * i / 7
            shapes.append(cv.Line(OUTDOOR.x + 8, y, OUTDOOR.x + 40, y, paint=_stroke(TOKENS.border_strong, 1)))
        label_color = TOKENS.text_primary
        shapes += [
            _label(COLD_TANK.center[0], COLD_TANK.y - 12, "冰水桶 160 L", 12, label_color, True),
            _label(HOT_TANK.center[0], HOT_TANK.y - 12, "熱水桶 160 L", 12, label_color, True),
            _label(CONDENSER.center[0], CONDENSER.y - 12, "板式冷凝器", 11, label_color, True),
            _label(EVAPORATOR.center[0], EVAPORATOR.y + EVAPORATOR.height + 12, "板式蒸發器", 11, label_color, True),
            _label(OUTDOOR.center[0], OUTDOOR.y - 12, "室外換熱器", 11, label_color, True),
            _label(COMPRESSOR_CENTER[0] + 70, COMPRESSOR_CENTER[1] + 30, "壓縮機 INV", 11, label_color, True),
            _label(EXPANSION_VALVE[0] + 42, EXPANSION_VALVE[1] - 14, "膨脹閥", 10),
            _label(FAN_A.center[0], FAN_A.center[1], "送風機 A", 11, label_color),
            _label(FAN_B.center[0], FAN_B.center[1], "送風機 B", 11, label_color),
            _label(705, 548, "SV2–5（未使用）", 10, TOKENS.text_muted),
        ]
        if record is not None:
            for box, value in ((COLD_TANK, record.cold_water_k), (HOT_TANK, record.hot_water_k)):
                shapes.append(_label(box.center[0], box.center[1], f"{format_temperature(value)} °C", 20,
                                     TOKENS.text_primary, True))
        return shapes

    def _pipes(self, state: SchematicState | None, refrigerant_phase: float, water_phase: float) -> list[cv.Shape]:
        """冷媒管與水管，以及流動點。

參數：
    state: 示意圖狀態。
    refrigerant_phase: 冷媒相位。
    water_phase: 水相位。

回傳：
    shapes。"""
        shapes: list[cv.Shape] = []
        water = LINE_COLORS[LineState.WATER]
        idle = LINE_COLORS[LineState.IDLE]
        fan_tank = state.fan_loop_tank if state else "cold_tank"
        water_pipes = [
            (HOT_SUPPLY, True),
            (HOT_RETURN, True),
            (COLD_SUPPLY, True),
            (COLD_RETURN, True),
            (FAN_HEADER, state is not None and bool(state.fans_on)),
            (FAN_LOOP_COLD, state is not None and fan_tank == "cold_tank"),
            (FAN_LOOP_HOT, state is not None and fan_tank == "hot_tank"),
        ]
        for pipe, active in water_pipes:
            color = water if active and state is not None else idle
            shapes.append(_polyline(pipe.points, _stroke(color, 3, None if active else [6, 6])))
            if active and state is not None:
                shapes += [cv.Circle(x, y, 3, paint=_fill(TOKENS.surface)) for x, y in flow_dots(pipe.points, water_phase, 36)]
        def is_active(pipe) -> bool:
            return state is not None and state.pipe_states[pipe.key] is not LineState.IDLE

        # 未使用的管先畫，共用管段由運轉中的顏色蓋過。
        for pipe in sorted(REFRIGERANT_PIPES, key=is_active):
            line_state = state.pipe_states[pipe.key] if state else LineState.IDLE
            active = line_state is not LineState.IDLE
            shapes.append(_polyline(pipe.points, _stroke(LINE_COLORS[line_state], 4 if active else 2.5,
                                                          None if active else [6, 6])))
            if active:
                shapes += [cv.Circle(x, y, 3.5, paint=_fill(TOKENS.surface))
                           for x, y in flow_dots(pipe.points, refrigerant_phase, 34)]
        return shapes

    def _components(self, state: SchematicState | None, record: StepRecord | None, angle: float) -> list[cv.Shape]:
        """壓縮機、風扇、水泵、膨脹閥與電磁閥。

參數：
    state: 示意圖狀態。
    record: 記錄。
    angle: 旋轉角度。

回傳：
    shapes。"""
        shapes: list[cv.Shape] = []
        running = state is not None and state.compressor_on
        cx, cy = COMPRESSOR_CENTER
        shapes.append(cv.Circle(cx, cy, COMPRESSOR_RADIUS, paint=_fill(TOKENS.primary_soft if running else TOKENS.surface)))
        shapes.append(cv.Circle(cx, cy, COMPRESSOR_RADIUS, paint=_stroke(TOKENS.primary if running else TOKENS.border_strong, 2.5)))
        shapes += _rotor(COMPRESSOR_CENTER, COMPRESSOR_RADIUS - 8, angle if running else 0.0,
                         TOKENS.primary if running else TOKENS.border_strong)
        freq = f"{record.frequency_hz:.1f} Hz" if record is not None and record.compressor_on else "停機"
        shapes.append(_label(cx + 70, cy + 46, freq, 12, TOKENS.primary if running else TOKENS.text_muted, True))

        fan_on = state is not None and state.outdoor_fan_on
        shapes.append(cv.Circle(*OUTDOOR_FAN_CENTER, 42, paint=_stroke(TOKENS.border_strong, 1.5)))
        shapes += _rotor(OUTDOOR_FAN_CENTER, 38, angle * 1.5 if fan_on else 0.0,
                         TOKENS.primary if fan_on else TOKENS.border_strong, 4)

        for pump in (COLD_PUMP, HOT_PUMP, FAN_PUMP):
            on = state is not None
            shapes.append(cv.Circle(*pump, 12, paint=_fill(TOKENS.surface)))
            shapes.append(cv.Circle(*pump, 12, paint=_stroke(LINE_COLORS[LineState.WATER] if on else TOKENS.border_strong, 2)))
            shapes += _rotor(pump, 9, angle * 2 if on else 0.0,
                             LINE_COLORS[LineState.WATER] if on else TOKENS.border_strong, 2)

        for box, name in ((FAN_A, "A"), (FAN_B, "B")):
            on = state is not None and name in state.fans_on
            center = (box.x + box.width - 18, box.y + 18)
            shapes += _rotor(center, 12, angle * 2 if on else 0.0, TOKENS.primary if on else TOKENS.border_strong, 4)

        ex, ey = EXPANSION_VALVE
        shapes.append(_polyline(((ex - 12, ey - 10), (ex + 12, ey + 10), (ex + 12, ey - 10), (ex - 12, ey + 10),
                                 (ex - 12, ey - 10)), _stroke(TOKENS.text_secondary, 2)))

        open_valves = state.valves_open if state else frozenset()
        for number, (vx, vy) in VALVE_POSITIONS.items():
            is_open = number in open_valves
            color = TOKENS.success if is_open else TOKENS.border_strong
            shapes.append(cv.Rect(vx - 9, vy - 9, 18, 18, border_radius=4,
                                  paint=_fill(color if is_open else TOKENS.surface)))
            shapes.append(cv.Rect(vx - 9, vy - 9, 18, 18, border_radius=4, paint=_stroke(color, 2)))
            if number not in (2, 3, 4, 5):
                dx, dy = VALVE_LABEL_OFFSETS.get(number, (22.0, -14.0))
                shapes.append(_label(vx + dx, vy + dy, f"SV{number}", 10,
                                     TOKENS.success if is_open else TOKENS.text_muted, True))
        return shapes
