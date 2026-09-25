"""以 Flet 原生折線圖（flet_charts.LineChart）呈現濕空氣線圖。

曲線資料來自 `chart.psychrometric.build_psychrometric_chart_data`，標註點與輔助線
使用 `ChartMarker`／`ChartGuide`；本元件只負責呈現，圖面固定使用 °C 與 g/kg 乾空氣。
文字由介面本身繪製，因此不依賴系統的中文字型，顏色也與工作區主題一致。
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
            label=ft.Text(str(value), size=TOKENS.overline, color=TOKENS.text_muted,
                          font_family=TOKENS.mono_font),
        )
        for value in values
    ]


def _curve_series(curve: ChartCurve, *, color: str, width: float,
                  dash: list[int] | None = None) -> fch.LineChartData:
    """把一條曲線轉成不顯示提示框的折線。

參數：
    curve: 曲線資料（y 為 kg/kg）。
    color: 線條顏色。
    width: 線寬。
    dash: 選用的虛線樣式。

回傳：
    LineChartData。"""
    return fch.LineChartData(
        points=[
            fch.LineChartDataPoint(x, w * 1000, show_tooltip=False)
            for x, w in zip(curve.dry_bulb_c, curve.humidity_ratio)
        ],
        color=color,
        stroke_width=width,
        dash_pattern=dash,
        curved=True,
        prevent_curve_over_shooting=True,
    )


def _point(marker: ChartMarker, shape: fch.ChartCirclePoint | None) -> fch.LineChartDataPoint:
    """建立帶提示文字的標註點。

參數：
    marker: 標註點。
    shape: 點的外觀；None 表示不畫點。

回傳：
    LineChartDataPoint。"""
    return fch.LineChartDataPoint(
        marker.dry_bulb_c,
        marker.humidity_ratio * 1000,
        point=shape if shape is not None else False,
        tooltip=f"{marker.label}\n{marker.dry_bulb_c:.1f} °C · {marker.humidity_ratio * 1000:.2f} g/kg",
    )


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
            interactive=True,
            tooltip=fch.LineChartTooltip(bgcolor=TOKENS.text_primary, max_width=220),
        )
        self.chart_box = ft.Container(content=self.chart, height=height, visible=False,
                                      padding=ft.Padding.only(top=8, right=4))
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
            label_size=24,
            title=ft.Text("乾球溫度 (°C)", size=TOKENS.caption, color=TOKENS.text_secondary),
            title_size=20,
        )
        self.chart.right_axis = fch.ChartAxis(
            labels=_axis_labels(0, w_max, y_step),
            label_size=32,
            title=ft.Text("濕度比 (g/kg)", size=TOKENS.caption, color=TOKENS.text_secondary),
            title_size=20,
        )
        self.chart.left_axis = fch.ChartAxis(show_labels=False, label_size=0)
        self.chart.top_axis = fch.ChartAxis(show_labels=False, label_size=0)

        rh_labels = "／".join(curve.label for curve in data.relative_humidity_lines)
        legend: list[ft.Control] = [_legend_item(_dot(True, TOKENS.highlight), marker.label)
                                    for marker in self.markers]
        legend += [_legend_item(_dot(False, TOKENS.highlight), guide.end.label) for guide in self.guides]
        legend += [
            _legend_item(_line(SATURATION_COLOR), "飽和線 100%"),
            _legend_item(_line(RH_LINE_COLOR), f"等相對濕度 {rh_labels}" if rh_labels else "等相對濕度"),
            _legend_item(_line(ENTHALPY_LINE_COLOR, dashed=True), "等焓線"),
        ]
        self.legend.controls = legend
        self.placeholder.visible = False
        self.chart_box.visible = True

    def refresh(self) -> None:
        """在已掛載頁面時重繪。

回傳：
    無。"""
        try:
            self.update()
        except RuntimeError:
            pass
