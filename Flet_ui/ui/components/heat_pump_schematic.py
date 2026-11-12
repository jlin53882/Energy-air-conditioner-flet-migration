"""熱泵系統示意圖（Flet canvas，向量繪製）。

幾何、配色與狀態推導在 :mod:`Flet_ui.ui.heat_pump_presentation`；本元件只負責繪製：
依冷媒溫度上色並帶光暈的管路、流動點、旋轉的壓縮機與風扇、圓柱水桶、板式換熱器、
室外機、黃銅膨脹閥、電磁閥，以及狀態點數值框。所有座標以邏輯座標 1000 × 640 繪製，
最後依可用寬度等比縮放。
"""

from __future__ import annotations

import math

import flet as ft
import flet.canvas as cv

from domain.heat_pump import StepRecord

from ..heat_pump_presentation import (
    CALLOUT_BOXES,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    COLD_PUMP,
    COLD_RETURN,
    COLD_SUPPLY,
    COLD_TANK,
    COMPRESSOR,
    COMPRESSOR_CENTER,
    CONDENSER,
    EVAPORATOR,
    EXPANSION_VALVE,
    FAN_A,
    FAN_B,
    FAN_DROP_B,
    FAN_DROPS,
    FAN_HEADER,
    FAN_LOOP_COLD,
    FAN_LOOP_HOT,
    FAN_PUMP,
    HOT_PUMP,
    HOT_RETURN,
    HOT_SUPPLY,
    HOT_TANK,
    IDLE_LINE_COLOR,
    OUTDOOR,
    OUTDOOR_FAN_CENTER,
    REFRIGERANT_PIPES,
    VALVE_LABEL_OFFSETS,
    VALVE_ORIENTATION,
    VALVE_POSITIONS,
    Box,
    LineState,
    SchematicState,
    flow_dots,
    format_temperature,
    schematic_state,
)
from ..theme import TOKENS

_CENTER = ft.Alignment(0.0, 0.0)
_LEFT = ft.Alignment(-1.0, 0.0)
CALLOUT_BG = "#27302D"
STEEL = ("#7C8784", "#D9DEDB", "#8E9996")
BRASS = ("#A8761D", "#F0CB6E", "#B98722")


def _alpha(color: str, opacity: float) -> str:
    """加上透明度。

參數：
    color: #RRGGBB。
    opacity: 0–1。

回傳：
    Flet 顏色字串。"""
    return ft.Colors.with_opacity(opacity, color)


def _mix(color: str, other: str, weight: float) -> str:
    """兩色混合。

參數：
    color: 原色 #RRGGBB。
    other: 混入色 #RRGGBB。
    weight: other 的比例。

回傳：
    #RRGGBB。"""
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#{:02X}{:02X}{:02X}".format(*(round(x + (y - x) * weight) for x, y in zip(a, b)))


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


def _gradient(begin, end, colors: list[str]) -> ft.Paint:
    """線性漸層填色。

參數：
    begin: 起點。
    end: 終點。
    colors: 顏色。

回傳：
    Paint。"""
    return ft.Paint(style=ft.PaintingStyle.FILL, gradient=ft.PaintLinearGradient(begin=begin, end=end, colors=colors))


def _label(x: float, y: float, text: str, size: float = 11, color: str | None = None, bold: bool = False,
           alignment: ft.Alignment = _CENTER) -> cv.Text:
    """文字。

參數：
    x: x。
    y: y。
    text: 文字。
    size: 字級。
    color: 顏色。
    bold: 粗體。
    alignment: 對齊點。

回傳：
    cv.Text。"""
    return cv.Text(x, y, text, alignment=alignment,
                   text_align=ft.TextAlign.CENTER if alignment is _CENTER else ft.TextAlign.LEFT,
                   style=ft.TextStyle(size=size, color=color or TOKENS.text_secondary,
                                      weight=ft.FontWeight.W_600 if bold else ft.FontWeight.W_400))


def _polyline(points, paint: ft.Paint) -> cv.Path:
    """折線。

參數：
    points: 點。
    paint: 畫筆。

回傳：
    cv.Path。"""
    return cv.Path([cv.Path.MoveTo(*points[0])] + [cv.Path.LineTo(*p) for p in points[1:]], paint=paint)


def _polygon(points, paint: ft.Paint) -> cv.Path:
    """封閉多邊形。

參數：
    points: 頂點。
    paint: 畫筆。

回傳：
    cv.Path。"""
    return cv.Path([cv.Path.MoveTo(*points[0])] + [cv.Path.LineTo(*p) for p in points[1:]] + [cv.Path.Close()],
                   paint=paint)


def _rotor(center, radius: float, angle: float, color: str, blades: int = 3, width: float = 2.5) -> list[cv.Shape]:
    """旋轉葉片。

參數：
    center: 中心。
    radius: 半徑。
    angle: 角度（rad）。
    color: 顏色。
    blades: 葉片數。
    width: 線寬。

回傳：
    shapes。"""
    cx, cy = center
    return [cv.Line(cx, cy, cx + radius * math.cos(angle + 2 * math.pi * i / blades),
                    cy + radius * math.sin(angle + 2 * math.pi * i / blades), paint=_stroke(color, width))
            for i in range(blades)]


# ---- 縮放 ----


def _scale_point(point, k: float):
    """縮放座標點。

參數：
    point: (x, y) 或 Offset。
    k: 比例。

回傳：
    (x, y)。"""
    if point is None:
        return None
    x, y = (point.x, point.y) if hasattr(point, "x") else point
    return (x * k, y * k)


def _scale_paint(paint: ft.Paint, k: float) -> ft.Paint:
    """縮放線寬、虛線與漸層座標。

參數：
    paint: 畫筆。
    k: 比例。

回傳：
    新畫筆。"""
    gradient = paint.gradient
    if isinstance(gradient, ft.PaintLinearGradient):
        gradient = ft.PaintLinearGradient(begin=_scale_point(gradient.begin, k), end=_scale_point(gradient.end, k),
                                          colors=gradient.colors, color_stops=gradient.color_stops)
    stroke = paint.style is ft.PaintingStyle.STROKE
    return ft.Paint(
        color=paint.color, style=paint.style, gradient=gradient,
        stroke_width=max(0.8, (paint.stroke_width or 1.0) * k) if stroke else paint.stroke_width,
        stroke_cap=paint.stroke_cap, stroke_join=paint.stroke_join,
        stroke_dash_pattern=[d * k for d in paint.stroke_dash_pattern] if paint.stroke_dash_pattern else None,
    )


def _scale_element(element, k: float):
    """縮放路徑元素。

參數：
    element: Path 元素。
    k: 比例。

回傳：
    新元素。"""
    if isinstance(element, (cv.Path.MoveTo, cv.Path.LineTo)):
        return type(element)(element.x * k, element.y * k)
    if isinstance(element, cv.Path.QuadraticTo):
        return cv.Path.QuadraticTo(element.cp1x * k, element.cp1y * k, element.x * k, element.y * k)
    return element


def scale_shapes(shapes: list[cv.Shape], k: float) -> list[cv.Shape]:
    """把邏輯座標的 shape 依比例縮放。

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
            radius = shape.border_radius * k if isinstance(shape.border_radius, (int, float)) else shape.border_radius
            out.append(cv.Rect(shape.x * k, shape.y * k, shape.width * k, shape.height * k, border_radius=radius,
                               paint=_scale_paint(shape.paint, k)))
        elif isinstance(shape, cv.Oval):
            out.append(cv.Oval(shape.x * k, shape.y * k, shape.width * k, shape.height * k,
                               paint=_scale_paint(shape.paint, k)))
        elif isinstance(shape, cv.Circle):
            out.append(cv.Circle(shape.x * k, shape.y * k, shape.radius * k, paint=_scale_paint(shape.paint, k)))
        elif isinstance(shape, cv.Path):
            out.append(cv.Path([_scale_element(e, k) for e in shape.elements], paint=_scale_paint(shape.paint, k)))
        elif isinstance(shape, cv.Text):
            style = shape.style
            out.append(cv.Text(shape.x * k, shape.y * k, shape.value, alignment=shape.alignment,
                               text_align=shape.text_align,
                               style=ft.TextStyle(size=max(8.0, (style.size or 11) * k), color=style.color,
                                                  weight=style.weight) if style else None))
        else:
            out.append(shape)
    return out


# ---- 元件 ----


def _tank(box: Box, color: str, temperature_k: float | None) -> list[cv.Shape]:
    """圓柱水桶（含保溫外框、水面波紋與水溫）。

參數：
    box: 位置。
    color: 水色。
    temperature_k: 水溫。

回傳：
    shapes。"""
    x, y, w, h = box.x, box.y, box.width, box.height
    dark = _mix(color, "#000000", 0.28)
    light = _mix(color, "#FFFFFF", 0.35)
    shapes: list[cv.Shape] = [
        cv.Oval(x - 6, y + h - 14, w + 12, 28, paint=_fill(_alpha("#000000", 0.08))),
        cv.Rect(x - 5, y - 5, w + 10, h + 10, border_radius=20, paint=_fill("#E9E7DF")),
        cv.Rect(x - 5, y - 5, w + 10, h + 10, border_radius=20, paint=_stroke("#C9C6BA", 1.2)),
        cv.Rect(x, y, w, h, border_radius=16, paint=_gradient((x, y), (x + w, y), [dark, color, light, color, dark])),
        cv.Oval(x, y - 8, w, 18, paint=_fill(light)),
        cv.Oval(x, y - 8, w, 18, paint=_stroke(_alpha("#FFFFFF", 0.6), 1.2)),
    ]
    wave = [cv.Path.MoveTo(x + 8, y + 26)]
    for i in range(4):
        x0 = x + 8 + i * (w - 16) / 4
        wave.append(cv.Path.QuadraticTo(x0 + (w - 16) / 8, y + 20 if i % 2 == 0 else y + 32, x0 + (w - 16) / 4, y + 26))
    shapes.append(cv.Path(wave, paint=_stroke(_alpha("#FFFFFF", 0.55), 2)))
    if temperature_k is not None:
        shapes.append(_label(x + w / 2, y + h / 2, f"{format_temperature(temperature_k)} °C", 22, "#FFFFFF", True))
    shapes.append(_label(x + w / 2, y - 22, box.label, 12, TOKENS.text_primary, True))
    return shapes


def _plate_exchanger(box: Box, accent: str | None, refrigerant_side: str) -> list[cv.Shape]:
    """板式換熱器（板片堆疊、夾緊螺桿與接管口）。

參數：
    box: 位置。
    accent: 運轉時的冷媒顏色（None 為停用）。
    refrigerant_side: 冷媒接管所在側（"left" 或 "right"）。

回傳：
    shapes。"""
    x, y, w, h = box.x, box.y, box.width, box.height
    base = accent or "#B9BDB8"
    top = _mix(base, "#FFFFFF", 0.55)
    bottom = _mix(base, "#FFFFFF", 0.2)
    shapes: list[cv.Shape] = [
        cv.Rect(x - 6, y - 6, w + 12, 10, border_radius=3, paint=_gradient((x, y), (x + w, y), list(STEEL))),
        cv.Rect(x - 6, y + h - 4, w + 12, 10, border_radius=3, paint=_gradient((x, y), (x + w, y), list(STEEL))),
        cv.Rect(x, y, w, h, border_radius=5, paint=_gradient((x, y), (x, y + h), [top, bottom])),
    ]
    for i in range(1, 9):
        px = x + w * i / 9
        shapes.append(cv.Line(px, y + 6, px, y + h - 6, paint=_stroke(_alpha(_mix(base, "#000000", 0.35), 0.55), 1.2)))
    shapes.append(cv.Rect(x, y, w, h, border_radius=5, paint=_stroke(_mix(base, "#000000", 0.35), 1.4)))
    for bx in (x - 2, x + w + 2):
        shapes.append(cv.Line(bx, y - 4, bx, y + h + 4, paint=_stroke("#6B7471", 2)))
    ref_x = x if refrigerant_side == "left" else x + w
    water_x = x + w if refrigerant_side == "left" else x
    for px, py in ((ref_x, y + 20), (ref_x, y + h - 15), (water_x, y + 20), (water_x, y + h - 20)):
        shapes.append(cv.Circle(px, py, 5, paint=_fill("#E9ECEA")))
        shapes.append(cv.Circle(px, py, 5, paint=_stroke("#6B7471", 1.5)))
    shapes.append(_label(x + w / 2, y - 20, box.label, 11, TOKENS.text_primary, True))
    return shapes


def _compressor(running: bool, angle: float, frequency_hz: float | None, power_w: float | None) -> list[cv.Shape]:
    """壓縮機（金屬機殼、上蓋、接線盒、轉子視窗、機腳）。

參數：
    running: 是否運轉。
    angle: 轉子角度。
    frequency_hz: 頻率。
    power_w: 耗電。

回傳：
    shapes。"""
    b = COMPRESSOR
    cx, cy = COMPRESSOR_CENTER
    shapes: list[cv.Shape] = [cv.Oval(b.x - 12, b.y + b.height - 4, b.width + 24, 16, paint=_fill(_alpha("#000000", 0.12)))]
    if running:
        shapes.append(cv.Circle(cx, cy, 58, paint=_fill(_alpha(TOKENS.primary, 0.08))))
        shapes.append(cv.Circle(cx, cy, 52, paint=_stroke(_alpha(TOKENS.primary, 0.25), 3)))
    shapes += [
        cv.Rect(b.x + 6, b.y + b.height - 4, 16, 10, border_radius=2, paint=_fill("#4B5350")),
        cv.Rect(b.x + b.width - 22, b.y + b.height - 4, 16, 10, border_radius=2, paint=_fill("#4B5350")),
        cv.Rect(b.x, b.y, b.width, b.height, border_radius=18,
                paint=_gradient((b.x, b.y), (b.x + b.width, b.y), list(STEEL))),
        cv.Oval(b.x, b.y - 10, b.width, 24, paint=_gradient((b.x, b.y), (b.x + b.width, b.y), list(STEEL))),
        cv.Oval(b.x, b.y - 10, b.width, 24, paint=_stroke("#6B7471", 1)),
        cv.Rect(b.x + b.width - 26, b.y - 16, 18, 12, border_radius=2, paint=_fill("#3E4643")),
        cv.Rect(b.x, b.y, b.width, b.height, border_radius=18, paint=_stroke("#5E6764", 1.2)),
        cv.Circle(cx, cy + 4, 21, paint=_fill("#2E3532")),
        cv.Circle(cx, cy + 4, 21, paint=_stroke(TOKENS.primary if running else "#5E6764", 2.5)),
    ]
    shapes += _rotor((cx, cy + 4), 16, angle if running else 0.0, "#9FD3CF" if running else "#6B7471", 3, 3)
    shapes.append(cv.Circle(cx, cy + 4, 4, paint=_fill("#D9DEDB")))
    shapes.append(_label(b.x - 52, b.y + 18, "壓縮機", 12, TOKENS.text_primary, True))
    shapes.append(_label(b.x - 52, b.y + 34, "INV", 10, TOKENS.text_muted, True))
    text = f"{frequency_hz:.1f} Hz · {power_w / 1000:.2f} kW" if running and frequency_hz and power_w is not None else "停機"
    shapes.append(_label(cx, b.y + b.height + 18, text, 11, TOKENS.primary if running else TOKENS.text_muted, True))
    return shapes


def _outdoor_unit(role: str | None, accent: str | None, angle: float, outdoor_k: float | None) -> list[cv.Shape]:
    """室外換熱器（機殼、盤管鰭片、風扇網罩與葉片）。

參數：
    role: "condenser"、"evaporator" 或 None。
    accent: 盤管顏色。
    angle: 葉片角度。
    outdoor_k: 外氣溫度。

回傳：
    shapes。"""
    b = OUTDOOR
    coil = accent or "#B9BDB8"
    shapes: list[cv.Shape] = [
        cv.Rect(b.x, b.y, b.width, b.height, border_radius=10,
                paint=_gradient((b.x, b.y), (b.x, b.y + b.height), ["#F6F6F2", "#D9D9D1"])),
        cv.Rect(b.x, b.y, b.width, b.height, border_radius=10, paint=_stroke("#B5B5AB", 1.4)),
    ]
    for i in range(12):
        fx = b.x + 10 + i * 7
        shapes.append(cv.Line(fx, b.y + 10, fx, b.y + b.height - 10, paint=_stroke("#C3C3BA", 1)))
    for j in range(5):
        ty = b.y + 16 + j * 15
        shapes.append(cv.Line(b.x + 8, ty, b.x + 92, ty, paint=_stroke(coil, 3)))
    cx, cy = OUTDOOR_FAN_CENTER
    shapes.append(cv.Circle(cx, cy, 40, paint=_fill("#2F3633")))
    shapes += _rotor((cx, cy), 34, angle * 1.6 if role else 0.0, "#AEB6B3" if role else "#6B7471", 3, 9)
    for r in (40, 30, 20):
        shapes.append(cv.Circle(cx, cy, r, paint=_stroke(_alpha("#FFFFFF", 0.35), 1)))
    shapes.append(cv.Circle(cx, cy, 6, paint=_fill("#D9DEDB")))
    text = "室外換熱器"
    if outdoor_k is not None:
        text += f" · 外氣 {format_temperature(outdoor_k)} °C"
    shapes.append(_label(b.x + b.width / 2, b.y + b.height + 13, text, 11, TOKENS.text_primary, True))
    return shapes


def _expansion_valve() -> list[cv.Shape]:
    """黃銅電子膨脹閥（垂直流向）。

回傳：
    shapes。"""
    x, y = EXPANSION_VALVE
    paint = _gradient((x - 10, y), (x + 10, y), list(BRASS))
    return [
        _polygon(((x - 11, y - 15), (x + 11, y - 15), (x, y)), paint),
        _polygon(((x - 11, y + 15), (x + 11, y + 15), (x, y)), paint),
        cv.Rect(x, y - 3, 18, 6, paint=_gradient((x, y - 3), (x, y + 3), list(BRASS))),
        cv.Circle(x + 22, y, 7, paint=_gradient((x + 15, y), (x + 29, y), list(BRASS))),
        cv.Circle(x + 22, y, 7, paint=_stroke("#8A6418", 1)),
        _label(x - 30, y, "EXV", 10, TOKENS.text_secondary, True),
    ]


def _fan_coil(box: Box, on: bool, active_loop: bool, load_w: float | None, angle: float) -> list[cv.Shape]:
    """吊隱式送風機（出風格柵與風扇）。

參數：
    box: 位置。
    on: 是否開啟。
    active_loop: 是否有供水。
    load_w: 個別負荷。
    angle: 葉片角度。

回傳：
    shapes。"""
    x, y, w, h = box.x, box.y, box.width, box.height
    shapes: list[cv.Shape] = [
        cv.Rect(x, y, w, h, border_radius=8,
                paint=_gradient((x, y), (x, y + h), ["#FFFFFF", "#E7E7E0"] if on else ["#F4F4F0", "#ECECE6"])),
        cv.Rect(x, y, w, h, border_radius=8, paint=_stroke("#C3C3BA" if not on else TOKENS.primary, 1.4)),
    ]
    for i in range(4):
        gy = y + 14 + i * 9
        shapes.append(cv.Line(x + 10, gy, x + 52, gy, paint=_stroke("#B5B5AB", 1.5)))
    fan_center = (x + w - 26, y + h / 2)
    shapes.append(cv.Circle(*fan_center, 18, paint=_fill("#2F3633" if on else "#BDBDB4")))
    shapes += _rotor(fan_center, 15, angle * 2 if on and active_loop else 0.0, "#AEB6B3", 3, 5)
    text = box.label if not on else f"{box.label[-1]} · {load_w / 1000:.2f} kW" if load_w is not None else box.label
    shapes.append(_label(x + 34, y + h + 12, text, 10, TOKENS.text_primary if on else TOKENS.text_muted, True))
    return shapes


def _pump(center, color: str, angle: float) -> list[cv.Shape]:
    """水泵。

參數：
    center: 位置。
    color: 環顏色。
    angle: 葉輪角度。

回傳：
    shapes。"""
    return [cv.Circle(*center, 13, paint=_fill("#FFFFFF")), cv.Circle(*center, 13, paint=_stroke(color, 2.5))] + \
        _rotor(center, 9, angle * 2, color, 3, 2)


def _valve(number: int, is_open: bool) -> list[cv.Shape]:
    """電磁閥（蝶形閥體，開啟時發綠光）。

參數：
    number: 閥號。
    is_open: 是否開啟。

回傳：
    shapes。"""
    x, y = VALVE_POSITIONS[number]
    vertical = VALVE_ORIENTATION[number] == "v"
    color = TOKENS.success if is_open else "#A9ADA8"
    fill = _fill(color if is_open else "#FFFFFF")
    if vertical:
        tri_a, tri_b = ((x - 7, y - 9), (x + 7, y - 9), (x, y)), ((x - 7, y + 9), (x + 7, y + 9), (x, y))
    else:
        tri_a, tri_b = ((x - 9, y - 7), (x - 9, y + 7), (x, y)), ((x + 9, y - 7), (x + 9, y + 7), (x, y))
    shapes: list[cv.Shape] = []
    if is_open:
        shapes.append(cv.Circle(x, y, 13, paint=_fill(_alpha(TOKENS.success, 0.18))))
    shapes += [_polygon(tri_a, fill), _polygon(tri_b, fill), _polygon(tri_a, _stroke(color, 1.4)),
               _polygon(tri_b, _stroke(color, 1.4))]
    if number in VALVE_LABEL_OFFSETS:
        dx, dy = VALVE_LABEL_OFFSETS[number]
        shapes.append(_label(x + dx, y + dy, f"SV{number}", 9, TOKENS.success if is_open else TOKENS.text_muted, True))
    return shapes


def _callout(key: str, title: str, lines: tuple[str, ...], accent: str, anchor) -> list[cv.Shape]:
    """深色狀態點數值框與引線。

參數：
    key: 位置鍵。
    title: 標題。
    lines: 內容。
    accent: 色條。
    anchor: 引線端點。

回傳：
    shapes。"""
    (x, y), w, h = CALLOUT_BOXES[key]
    edge_x = x if anchor[0] < x else x + w if anchor[0] > x + w else anchor[0]
    edge_y = y + h / 2 if edge_x in (x, x + w) else (y if anchor[1] < y else y + h)
    shapes: list[cv.Shape] = [
        cv.Line(edge_x, edge_y, anchor[0], anchor[1], paint=_stroke(_alpha(CALLOUT_BG, 0.55), 1.2, [3, 3])),
        cv.Circle(anchor[0], anchor[1], 3.5, paint=_fill(CALLOUT_BG)),
        cv.Rect(x + 2, y + 3, w, h, border_radius=8, paint=_fill(_alpha("#000000", 0.12))),
        cv.Rect(x, y, w, h, border_radius=8, paint=_fill(_alpha(CALLOUT_BG, 0.94))),
        cv.Rect(x, y, 5, h, border_radius=3, paint=_fill(accent)),
        _label(x + 13, y + 12, title, 11, "#C9D2CE", True, _LEFT),
    ]
    for i, line in enumerate(line for line in lines if line):
        shapes.append(_label(x + 13, y + 29 + i * 16, line, 13 if i == 0 else 11.5, "#FFFFFF", i == 0, _LEFT))
    return shapes


class HeatPumpSchematic(ft.Container):
    """可動的系統示意圖。"""

    def __init__(self) -> None:
        """建立畫布（未有資料前只畫元件）。

回傳：
    無。"""
        self.zoom = 1.0
        self.canvas = cv.Canvas(shapes=[], height=CANVAS_HEIGHT, on_resize=self._on_resize, resize_interval=100)
        super().__init__(
            content=ft.Column([self.canvas], horizontal_alignment=ft.CrossAxisAlignment.STRETCH, spacing=0),
            gradient=ft.LinearGradient(begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1),
                                       colors=["#FAFAF7", "#EFEFE9"]),
            border_radius=TOKENS.radius_md,
            padding=TOKENS.spacing_sm,
        )
        self.state: SchematicState | None = None
        self._last: tuple = (None, 0.0, 0.0, 0.0, None)
        self.render(None, 0.0, 0.0, 0.0)

    def _on_resize(self, event: cv.CanvasResizeEvent) -> None:
        """依可用寬度縮放（最大 1.3 倍）。

參數：
            event: 尺寸事件。

回傳：
            無。"""
        if not event.width:
            return
        zoom = min(1.3, event.width / CANVAS_WIDTH)
        if abs(zoom - self.zoom) < 0.01:
            return
        self.zoom = zoom
        self.canvas.height = CANVAS_HEIGHT * zoom
        self.render(*self._last)
        try:
            self.update()
        except RuntimeError:
            pass

    def render(self, record: StepRecord | None, refrigerant_phase: float, water_phase: float, rotor_angle: float,
               outdoor_k: float | None = None) -> SchematicState | None:
        """依記錄重繪。

參數：
    record: 最新時間步記錄（None 表示尚未開始）。
    refrigerant_phase: 冷媒流動點相位。
    water_phase: 水流動點相位。
    rotor_angle: 旋轉元件角度。
    outdoor_k: 外氣溫度（顯示用）。

回傳：
    使用的 SchematicState。"""
        self._last = (record, refrigerant_phase, water_phase, rotor_angle, outdoor_k)
        state = schematic_state(record) if record is not None else None
        self.state = state
        shapes: list[cv.Shape] = []
        shapes += self._water(state, record, water_phase, rotor_angle)
        shapes += self._refrigerant_lines(state)
        shapes += self._components(state, record, rotor_angle, outdoor_k)
        shapes += self._refrigerant_dots(state, refrigerant_phase)
        shapes += self._callouts(state)
        self.canvas.shapes = scale_shapes(shapes, self.zoom)
        return state

    # ---- 各層 ----

    def _water(self, state, record, phase: float, angle: float) -> list[cv.Shape]:
        """水路、水泵與進出水溫。

參數：
            state: 示意圖狀態。
            record: 記錄。
            phase: 流動相位。
            angle: 葉輪角度。

回傳：
            shapes。"""
        shapes: list[cv.Shape] = []
        started = state is not None
        cold = state.cold_color if started else "#9DB4C8"
        hot = state.hot_color if started else "#D9B9A3"
        fan_tank = state.fan_loop_tank if started else None
        fan_color = cold if fan_tank == "cold_tank" else hot
        fans_on = started and bool(state.fans_on)
        pipes = [
            (COLD_SUPPLY, cold, started), (COLD_RETURN, cold, started),
            (HOT_SUPPLY, hot, started), (HOT_RETURN, hot, started),
            (FAN_HEADER, fan_color, fans_on), (FAN_DROPS, fan_color, fans_on and "A" in state.fans_on),
            (FAN_DROP_B, fan_color, fans_on and "B" in state.fans_on),
            (FAN_LOOP_COLD, cold, fans_on and fan_tank == "cold_tank"),
            (FAN_LOOP_HOT, hot, fans_on and fan_tank == "hot_tank"),
        ]
        for pipe, color, active in pipes:
            if active:
                shapes.append(_polyline(pipe.points, _stroke(_mix(color, "#000000", 0.25), 7)))
                shapes.append(_polyline(pipe.points, _stroke(color, 4.5)))
                shapes += [cv.Circle(x, y, 2.6, paint=_fill(_alpha("#FFFFFF", 0.9)))
                           for x, y in flow_dots(pipe.points, phase, 30)]
            else:
                shapes.append(_polyline(pipe.points, _stroke(IDLE_LINE_COLOR, 2, [5, 5])))
        shapes += _pump(COLD_PUMP, cold, angle if started else 0.0)
        shapes += _pump(HOT_PUMP, hot, angle if started else 0.0)
        shapes += _pump(FAN_PUMP, fan_color if fans_on else IDLE_LINE_COLOR, angle if fans_on else 0.0)
        if record is not None:
            room = "冷房" if fan_tank == "cold_tank" else "暖房"
            shapes.append(_label(380, 14, f"送風機水路（{room}，冰水泵）", 10, TOKENS.text_muted))
            for water_in, water_out, x in ((record.evaporator_water_in_k, record.evaporator_water_out_k, 210),
                                           (record.condenser_water_in_k, record.condenser_water_out_k, 790)):
                if water_in is not None:
                    shapes.append(_label(x, 306, f"出 {format_temperature(water_out)} °C", 10, TOKENS.text_secondary, True))
                    shapes.append(_label(x, 446, f"進 {format_temperature(water_in)} °C", 10, TOKENS.text_secondary, True))
        return shapes

    def _refrigerant_lines(self, state) -> list[cv.Shape]:
        """冷媒管：未使用者為虛線，運轉中依溫度上色並帶光暈（未使用者先畫）。

參數：
            state: 示意圖狀態。

回傳：
            shapes。"""
        shapes: list[cv.Shape] = []

        def is_active(pipe) -> bool:
            return state is not None and state.pipe_states[pipe.key] is not LineState.IDLE

        for pipe in sorted(REFRIGERANT_PIPES, key=is_active):
            if not is_active(pipe):
                shapes.append(_polyline(pipe.points, _stroke(IDLE_LINE_COLOR, 2.5, [6, 6])))
                continue
            color = state.pipe_colors[pipe.key]
            shapes += [
                _polyline(pipe.points, _stroke(_alpha(color, 0.12), 16)),
                _polyline(pipe.points, _stroke(_alpha(color, 0.25), 10)),
                _polyline(pipe.points, _stroke(_mix(color, "#000000", 0.15), 6)),
                _polyline(pipe.points, _stroke(_mix(color, "#FFFFFF", 0.25), 2.5)),
            ]
        return shapes

    def _refrigerant_dots(self, state, phase: float) -> list[cv.Shape]:
        """冷媒流動點。

參數：
            state: 示意圖狀態。
            phase: 相位。

回傳：
            shapes。"""
        if state is None:
            return []
        shapes: list[cv.Shape] = []
        for pipe in REFRIGERANT_PIPES:
            if state.pipe_states[pipe.key] is LineState.IDLE:
                continue
            for x, y in flow_dots(pipe.points, phase, 28):
                shapes.append(cv.Circle(x, y, 4.5, paint=_fill(_alpha("#FFFFFF", 0.35))))
                shapes.append(cv.Circle(x, y, 2.6, paint=_fill("#FFFFFF")))
        return shapes

    def _components(self, state, record, angle: float, outdoor_k: float | None) -> list[cv.Shape]:
        """元件。

參數：
            state: 示意圖狀態。
            record: 記錄。
            angle: 角度。
            outdoor_k: 外氣溫度。

回傳：
            shapes。"""
        running = state is not None and state.compressor_on
        colors = state.pipe_colors if state else {}
        evaporating = colors.get("lp_hx1") if state and state.pipe_states["lp_hx1"] is not LineState.IDLE else None
        condensing = colors.get("dis_hx2") if state and state.pipe_states["dis_hx2"] is not LineState.IDLE else None
        role = state.outdoor_role if state else None
        outdoor_accent = None
        if role == "condenser":
            outdoor_accent = colors.get("dis_out")
        elif role == "evaporator":
            outdoor_accent = colors.get("lp_out")
        shapes: list[cv.Shape] = []
        shapes += _tank(COLD_TANK, state.cold_color if state else "#6BA8D6", record.cold_water_k if record else None)
        shapes += _tank(HOT_TANK, state.hot_color if state else "#E8945A", record.hot_water_k if record else None)
        shapes += _plate_exchanger(EVAPORATOR, evaporating, "right")
        shapes += _plate_exchanger(CONDENSER, condensing, "left")
        shapes += _outdoor_unit(role, outdoor_accent, angle, outdoor_k)
        shapes += _compressor(running, angle, record.frequency_hz if record else None,
                              record.compressor_power_w if record else None)
        shapes += _expansion_valve()
        fan_tank_active = state is not None
        share = {}
        if record is not None and record.fans:
            ua = {"A": 3_516.0, "B": 5_274.0}
            total = sum(ua[name] for name in record.fans)
            share = {name: record.fan_coil_load_w * ua[name] / total for name in record.fans}
        for box, name in ((FAN_A, "A"), (FAN_B, "B")):
            on = state is not None and name in state.fans_on
            shapes += _fan_coil(box, on, fan_tank_active, share.get(name), angle)
        open_valves = state.valves_open if state else frozenset()
        for number in VALVE_POSITIONS:
            shapes += _valve(number, number in open_valves)
        shapes.append(_label(105, 597, "SV2–5（串／並聯，未使用）", 9, TOKENS.text_muted))
        return shapes

    def _callouts(self, state) -> list[cv.Shape]:
        """狀態點數值框；引線指向目前運轉中的支路。

參數：
            state: 示意圖狀態。

回傳：
            shapes。"""
        if state is None:
            return []
        active = {key for key, value in state.pipe_states.items() if value is not LineState.IDLE}
        anchors = {
            "suction": (420.0, 175.0) if "suc_out" in active else (345.0, 175.0),
            "discharge": (560.0, 150.0) if "dis_out" in active else (660.0, 150.0),
            "liquid": (650.0, 440.0),
            "expansion": (650.0, 520.0),
            "outdoor": (380.0, 545.0),
        }
        shapes: list[cv.Shape] = []
        for item in state.callouts:
            shapes += _callout(item.key, item.title, item.lines, item.accent, anchors[item.key])
        return shapes
