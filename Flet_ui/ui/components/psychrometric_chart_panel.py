"""以 Flet 原生折線圖（flet_charts.LineChart）呈現濕空氣線圖。

曲線資料來自 `chart.psychrometric.build_psychrometric_chart_data`，標註點與輔助線
使用 `ChartMarker`／`ChartGuide`；本元件只負責呈現，圖面固定使用 °C 與 g/kg 乾空氣。
文字由介面本身繪製，因此不依賴系統的中文字型，顏色也與工作區主題一致。

圖表不回應滑鼠：背景參考線橫跨整張圖，滑鼠經過時套件會在每條線上各標出一個點，
而且只要同時碰到背景線，標註點的提示框也不會出現。因此所有說明文字都直接畫在
圖上：狀態點名稱、濕球／露點輔助線的讀值、每條等相對濕度線與等焓線的數值。

原生折線圖沒有「在資料座標放文字」的功能，本元件在圖表上疊一層標籤，並依圖表
回報的實際尺寸（``on_size_change``）把資料座標換算成畫面位置；換算所需的軸線
保留寬度與圖表設定共用同一組常數。
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import flet as ft
import flet_charts as fch

from chart.psychrometric import ChartCurve, ChartGuide, ChartMarker, PsychrometricChartData

from ..theme import TOKENS

SATURATION_COLOR = TOKENS.primary
RH_LINE_COLOR = "#A9BDBA"
ENTHALPY_LINE_COLOR = "#D9CBB2"
PROCESS_COLORS = (TOKENS.primary, "#6B7F3A", "#7A5C99", "#8A5A2B")
RH_LABEL_COLOR = "#5E7A76"
ENTHALPY_LABEL_COLOR = "#9C8155"

# 軸線保留寬度（像素）：圖表設定與標籤座標換算共用，確保標籤對準資料點。
BOTTOM_LABEL_SIZE = 24
BOTTOM_TITLE_SIZE = 22
RIGHT_LABEL_SIZE = 34
RIGHT_TITLE_SIZE = 22


def _axis_step(span: float) -> int:
    """依座標範圍決定刻度間距，讓刻度數量維持在 6–10 個左右。

參數：
    span: 座標範圍長度。

回傳：
    刻度間距。"""
    return 5 if span <= 50 else 10


def _axis_labels(low: float, high: float, step: int) -> list[fch.ChartAxisLabel]:
    """建立等距的座標刻度標籤。

參數：
    low: 座標下限。
    high: 座標上限。
    step: 刻度間距。

回傳：
    刻度標籤清單。"""
    first = math.ceil(low / step) * step
    values = range(int(first), int(math.floor(high)) + 1, step)
    return [
        fch.ChartAxisLabel(
            value=value,
            label=ft.Text(str(value), size=TOKENS.caption, color=TOKENS.text_secondary,
                          font_family=TOKENS.mono_font),
        )
        for value in values
    ]


def _estimate_text_width(text: str, size: float) -> float:
    """估算等寬字型文字的像素寬度（全形字約為半形字的兩倍）。

參數：
    text: 文字內容。
    size: 字級。

回傳：
    估計寬度（像素）。"""
    return sum(size * (1.0 if ord(char) > 0x2E80 else 0.62) for char in text)


def _overlaps(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
    """判斷兩個 (左, 上, 右, 下) 矩形是否重疊。

參數：
    first: 第一個矩形。
    second: 第二個矩形。

回傳：
    是否重疊。"""
    return not (first[2] <= second[0] or second[2] <= first[0] or first[3] <= second[1] or second[3] <= first[1])


def _curve_series(curve: ChartCurve, *, color: str, width: float,
                  dash: list[int] | None = None) -> fch.LineChartData:
    """把一條背景參考曲線轉成折線。

以直線段連接計算取樣點（每條曲線預設 61 點，已足夠平滑），不使用 Bézier
平滑，避免畫面在取樣點之間呈現不屬於濕空氣計算結果的曲線形狀。

參數：
    curve: 曲線資料（y 為 kg/kg）。
    color: 線條顏色。
    width: 線寬。
    dash: 選用的虛線樣式。

回傳：
    LineChartData。"""
    return fch.LineChartData(
        points=[
            fch.LineChartDataPoint(x, w * 1000)
            for x, w in zip(curve.dry_bulb_c, curve.humidity_ratio)
        ],
        color=color,
        stroke_width=width,
        dash_pattern=dash,
        curved=False,
    )


def _point(marker: ChartMarker, shape: fch.ChartCirclePoint | None) -> fch.LineChartDataPoint:
    """建立標註點。

參數：
    marker: 標註點。
    shape: 點的外觀；None 表示不畫點。

回傳：
    LineChartDataPoint。"""
    return fch.LineChartDataPoint(
        marker.dry_bulb_c,
        marker.humidity_ratio * 1000,
        point=shape if shape is not None else False,
    )


def marker_caption(marker: ChartMarker) -> str:
    """回傳圖例使用的標註點文字：名稱與座標（乾球溫度、濕度比）。

參數：
    marker: 標註點。

回傳：
    例如「1 入口  25.0 °C · 11.20 g/kg」。"""
    return f"{marker.label}  {marker.dry_bulb_c:.1f} °C · {marker.humidity_ratio * 1000:.2f} g/kg"


def _legend_item(swatch: ft.Control, text: str) -> ft.Row:
    """建立一個圖例項目。

參數：
    swatch: 圖例符號。
    text: 圖例文字。

回傳：
    圖例列。"""
    return ft.Row(
        [swatch, ft.Text(text, size=TOKENS.caption, color=TOKENS.text_secondary,
                         font_family=TOKENS.mono_font)],
        spacing=6,
        tight=True,
    )


def _dot(filled: bool, color: str) -> ft.Container:
    """建立圓點圖例符號。

參數：
    filled: 是否為實心。
    color: 顏色。

回傳：
    圓點容器。"""
    return ft.Container(
        width=9, height=9,
        bgcolor=color if filled else TOKENS.surface,
        border=None if filled else ft.Border.all(1.5, color),
        border_radius=ft.BorderRadius.all(5),
    )


def _line(color: str, dashed: bool = False) -> ft.Control:
    """建立線條圖例符號。

參數：
    color: 顏色。
    dashed: 是否為虛線。

回傳：
    線條控制項。"""
    if not dashed:
        return ft.Container(width=16, height=2, bgcolor=color)
    return ft.Row([ft.Container(width=5, height=2, bgcolor=color) for _ in range(3)], spacing=2, tight=True)


class PsychrometricChartPanel(ft.Column):
    """可重複重畫的原生濕空氣線圖，附標註點圖例。"""

    def __init__(self, *, height: int = 420, placeholder: str = "計算後顯示濕空氣線圖") -> None:
        """建立空白線圖。

參數：
    height: 圖表高度（像素）。
    placeholder: 尚未繪圖時顯示的提示文字。

回傳：
    無。"""
        self.chart = fch.LineChart(
            expand=True,
            interactive=False,
            on_size_change=self._on_chart_resize,
        )
        # 疊在圖表上的文字標籤；位置在得知圖表尺寸後才計算。
        self.label_layer = ft.Stack(expand=True)
        self.chart_box = ft.Container(
            content=ft.Stack([self.chart, self.label_layer], expand=True),
            height=height,
            visible=False,
            padding=ft.Padding.only(top=8, right=4),
        )
        self.chart_size: tuple[float, float] | None = None
        self.data: PsychrometricChartData | None = None
        self.placed_labels: list[str] = []
        self.placeholder = ft.Container(
            content=ft.Text(placeholder, size=TOKENS.body, color=TOKENS.text_muted),
            height=height,
            alignment=ft.Alignment.CENTER,
            bgcolor=TOKENS.surface_variant,
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
        )
        self.legend = ft.Row(spacing=TOKENS.spacing_md, run_spacing=6, wrap=True)
        self.markers: list[ChartMarker] = []
        self.guides: list[ChartGuide] = []
        super().__init__([self.placeholder, self.chart_box, self.legend], spacing=TOKENS.spacing_sm)

    def draw(
        self,
        data: PsychrometricChartData,
        *,
        markers: Sequence[ChartMarker] = (),
        paths: Sequence[Sequence[ChartMarker]] = (),
        guides: Sequence[ChartGuide] = (),
    ) -> None:
        """以新的曲線資料、狀態點、過程線與輔助線重畫線圖。

參數：
    data: 線圖曲線資料。
    markers: 要標示的狀態點（實心點）。
    paths: 過程線，每條為依序連接的狀態點。
    guides: 輔助線（虛線，終點為空心點，例如到濕球溫度與露點）。

回傳：
    無。"""
        self.data = data
        self.markers = list(markers)
        self.guides = list(guides)
        series: list[fch.LineChartData] = []
        for curve in data.enthalpy_lines:
            series.append(_curve_series(curve, color=ENTHALPY_LINE_COLOR, width=0.8, dash=[4, 4]))
        for curve in data.relative_humidity_lines:
            series.append(_curve_series(curve, color=RH_LINE_COLOR, width=1.0))
        series.append(_curve_series(data.saturation, color=SATURATION_COLOR, width=2.2))

        for index, path in enumerate(paths):
            series.append(fch.LineChartData(
                points=[_point(point, fch.ChartCirclePoint(color=PROCESS_COLORS[index % len(PROCESS_COLORS)],
                                                           radius=3.5))
                        for point in path],
                color=PROCESS_COLORS[index % len(PROCESS_COLORS)],
                stroke_width=2.5,
            ))
        hollow = fch.ChartCirclePoint(color=TOKENS.surface, radius=4, stroke_color=TOKENS.highlight,
                                      stroke_width=1.5)
        for guide in self.guides:
            series.append(fch.LineChartData(
                points=[_point(guide.start, None), _point(guide.end, hollow)],
                color=TOKENS.highlight,
                stroke_width=1.2,
                dash_pattern=[4, 3],
            ))
        filled = fch.ChartCirclePoint(color=TOKENS.highlight, radius=5.5, stroke_color=TOKENS.surface,
                                      stroke_width=1.5)
        for marker in self.markers:
            series.append(fch.LineChartData(points=[_point(marker, filled)], color=TOKENS.highlight,
                                            stroke_width=0))

        low_c, high_c = data.dry_bulb_range_c
        w_max = data.humidity_ratio_max * 1000
        x_step, y_step = _axis_step(high_c - low_c), _axis_step(w_max)
        self.chart.data_series = series
        self.chart.min_x, self.chart.max_x = low_c, high_c
        self.chart.min_y, self.chart.max_y = 0, w_max
        self.chart.horizontal_grid_lines = fch.ChartGridLines(interval=y_step, color=TOKENS.border, width=0.6)
        self.chart.vertical_grid_lines = fch.ChartGridLines(interval=x_step, color=TOKENS.border, width=0.6)
        self.chart.border = ft.Border.all(1, TOKENS.border_strong)
        self.chart.bottom_axis = fch.ChartAxis(
            labels=_axis_labels(low_c, high_c, x_step),
            label_size=BOTTOM_LABEL_SIZE,
            title=ft.Text("乾球溫度 (°C)", size=TOKENS.caption + 1, color=TOKENS.text_secondary),
            title_size=BOTTOM_TITLE_SIZE,
        )
        self.chart.right_axis = fch.ChartAxis(
            labels=_axis_labels(0, w_max, y_step),
            label_size=RIGHT_LABEL_SIZE,
            title=ft.Text("濕度比 (g/kg)", size=TOKENS.caption + 1, color=TOKENS.text_secondary),
            title_size=RIGHT_TITLE_SIZE,
        )
        self.chart.left_axis = fch.ChartAxis(show_labels=False, label_size=0)
        self.chart.top_axis = fch.ChartAxis(show_labels=False, label_size=0)

        rh_labels = "／".join(curve.label for curve in data.relative_humidity_lines)
        legend: list[ft.Control] = [_legend_item(_dot(True, TOKENS.highlight), marker_caption(marker))
                                    for marker in self.markers]
        legend += [
            _legend_item(_line(SATURATION_COLOR), "飽和線 100%"),
            _legend_item(_line(RH_LINE_COLOR), f"等相對濕度 {rh_labels}" if rh_labels else "等相對濕度"),
            _legend_item(_line(ENTHALPY_LINE_COLOR, dashed=True), "等焓線"),
        ]
        self.legend.controls = legend
        self.placeholder.visible = False
        self.chart_box.visible = True
        self.layout_labels()

    def _on_chart_resize(self, event) -> None:
        """圖表尺寸改變時重新放置標籤。

參數：
    event: 含 width／height 的尺寸事件。

回傳：
    無。"""
        self.chart_size = (float(event.width), float(event.height))
        self.layout_labels()
        try:
            self.label_layer.update()
        except RuntimeError:
            pass

    def to_screen(self, dry_bulb_c: float, humidity_ratio_g_kg: float) -> tuple[float, float] | None:
        """把資料座標換成標籤圖層中的像素位置；尚未得知圖表尺寸時回傳 None。

參數：
    dry_bulb_c: 乾球溫度（°C）。
    humidity_ratio_g_kg: 濕度比（g/kg）。

回傳：
    (x, y) 像素位置，或 None。"""
        if self.chart_size is None or self.data is None:
            return None
        width, height = self.chart_size
        plot_width = width - RIGHT_LABEL_SIZE - RIGHT_TITLE_SIZE
        plot_height = height - BOTTOM_LABEL_SIZE - BOTTOM_TITLE_SIZE
        low_c, high_c = self.data.dry_bulb_range_c
        w_max = self.data.humidity_ratio_max * 1000
        x = (dry_bulb_c - low_c) / (high_c - low_c) * plot_width
        y = (1 - humidity_ratio_g_kg / w_max) * plot_height
        return x, y

    def layout_labels(self) -> None:
        """依目前尺寸重建圖上的文字標籤。

依重要性放置：狀態點名稱、輔助線讀值（濕球／露點）、飽和線、等相對濕度線、
等焓線。放置前先估算文字範圍，依序嘗試候選位置，取第一個不與已放置標籤重疊者。
狀態點與濕球／露點為必要標籤：所有候選位置都重疊時仍放在第一個候選位置，
不會消失；曲線數值為次要標籤，所有候選位置都重疊時略過，避免曲線密集處擁擠。

回傳：
    無。"""
        self.label_layer.controls = []
        self.placed_labels: list[str] = []
        if self.chart_size is None or self.data is None:
            return
        width = self.chart_size[0]
        plot_width = width - RIGHT_LABEL_SIZE - RIGHT_TITLE_SIZE
        occupied: list[tuple[float, float, float, float]] = []
        labels: list[ft.Control] = []

        def place(content: ft.Control, text: str, size: float, x: float, y: float, *,
                  candidates: Sequence[tuple[float, float, bool]], padding: float = 0,
                  mandatory: bool = False) -> None:
            """把文字放在 (x, y) 附近第一個不與已放置標籤重疊的候選位置。

參數：
    content: 要放置的控制項。
    text: 文字內容（用於估算寬度）。
    size: 字級。
    x: 像素 x。
    y: 像素 y。
    candidates: 依偏好排序的 (dx, dy, align_right)：dx 為往外的水平距離、
        dy 為垂直位移，align_right 為 True 表示文字右緣對齊錨點、往左延伸。
    padding: 控制項左右內距。
    mandatory: 必要標籤在所有候選位置都重疊時仍放在第一個候選位置；
        次要標籤則略過。

回傳：
    無。"""
            text_width = _estimate_text_width(text, size) + 2 * padding
            boxes = []
            for dx, dy, align_right in candidates:
                left = x - dx - text_width if align_right else x + dx
                boxes.append((left, y + dy, left + text_width, y + dy + size * 1.4))
            box = next((box for box in boxes if not any(_overlaps(box, other) for other in occupied)), None)
            if box is None:
                if not mandatory:
                    return
                box = boxes[0]
            occupied.append(box)
            self.placed_labels.append(text)
            labels.append(ft.Container(content, left=box[0], top=box[1]))

        def curve_label(value: str, color: str, x: float, y: float, *, at_right_edge: bool) -> None:
            """放置曲線數值：右緣結束的曲線標在端點左上，上緣結束的標在端點左下。

參數：
    value: 顯示文字。
    color: 顏色。
    x: 端點像素 x。
    y: 端點像素 y。
    at_right_edge: 曲線是否在圖框右緣結束。

回傳：
    無。"""
            size = TOKENS.overline
            text = ft.Text(value, size=size, color=color, font_family=TOKENS.mono_font)
            place(text, value, size, x, y, candidates=[(3, -15 if at_right_edge else 3, True)])

        # 1. 狀態點名稱（必要）：優先標在點的右下方，位於右半部時優先往左延伸，
        #    避免超出圖框；與其他標籤重疊時依序改到上方或另一側。
        for marker in self.markers:
            point = self.to_screen(marker.dry_bulb_c, marker.humidity_ratio * 1000)
            if point is None:
                continue
            size = TOKENS.caption + 1
            badge = ft.Container(
                content=ft.Text(marker.label, size=size, color=TOKENS.highlight,
                                weight=ft.FontWeight.W_700, font_family=TOKENS.mono_font),
                bgcolor=ft.Colors.with_opacity(0.85, TOKENS.surface),
                padding=ft.Padding.symmetric(horizontal=4, vertical=1),
                border_radius=ft.BorderRadius.all(4),
            )
            toward_left = point[0] > plot_width / 2
            above = -(size * 1.4 + 6)
            place(badge, marker.label, size, *point, padding=4, mandatory=True, candidates=[
                (8, 6, toward_left), (8, above, toward_left),
                (8, 6, not toward_left), (8, above, not toward_left),
            ])
        # 2. 輔助線終點（必要）：濕球溫度、露點讀值優先標在點的左上方，
        #    重疊時依序改到右上、左下、右下。
        for guide in self.guides:
            point = self.to_screen(guide.end.dry_bulb_c, guide.end.humidity_ratio * 1000)
            if point:
                size = TOKENS.caption
                text = ft.Text(guide.end.label, size=size, color=TOKENS.highlight,
                               weight=ft.FontWeight.W_600, font_family=TOKENS.mono_font)
                place(text, guide.end.label, size, *point, mandatory=True, candidates=[
                    (6, -20, True), (6, -20, False), (6, 6, True), (6, 6, False),
                ])
        # 3–4. 飽和線與等相對濕度線：數值標在線的末端（圖框右緣或上緣）。
        for curve in (self.data.saturation, *reversed(self.data.relative_humidity_lines)):
            if not curve.dry_bulb_c:
                continue
            point = self.to_screen(curve.dry_bulb_c[-1], curve.humidity_ratio[-1] * 1000)
            if point is None:
                continue
            color = SATURATION_COLOR if curve is self.data.saturation else RH_LABEL_COLOR
            curve_label(curve.label, color, *point, at_right_edge=point[0] >= plot_width - 2)
        # 5. 等焓線：數值標在靠近飽和線的一端（線圖慣例的焓值刻度）。
        for curve in self.data.enthalpy_lines:
            if not curve.dry_bulb_c:
                continue
            point = self.to_screen(curve.dry_bulb_c[-1], curve.humidity_ratio[-1] * 1000)
            if point and 0 <= point[0] <= plot_width:
                value = curve.label.split()[0]
                size = TOKENS.overline
                text = ft.Text(value, size=size, color=ENTHALPY_LABEL_COLOR, font_family=TOKENS.mono_font)
                place(text, value, size, *point, candidates=[(4, -16, True)])
        self.label_layer.controls = labels

    def refresh(self) -> None:
        """在已掛載頁面時重繪。

回傳：
    無。"""
        try:
            self.update()
        except RuntimeError:
            pass
