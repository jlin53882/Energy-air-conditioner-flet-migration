"""以 Matplotlib 繪製濕空氣線圖與處理過程（Flet 圖表轉接器）。

曲線資料來自 `chart.psychrometric.build_psychrometric_chart_data`；本模組只負責呈現，
圖面固定使用 °C 與 g/kg 乾空氣。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from matplotlib.figure import Figure

from chart.psychrometric import PsychrometricChartData

from . import coolprop_utils  # noqa: F401  # 套用共用的中文字型設定

PROCESS_COLORS = ("#1B5FAA", "#C2620F", "#0F9D9A", "#6D4BC4")
GUIDE_COLOR = "#C2410C"


@dataclass(frozen=True)
class ChartMarker:
    """線圖上的一個狀態點。"""

    label: str
    dry_bulb_c: float
    humidity_ratio: float

    @classmethod
    def from_state(cls, label: str, state: Mapping[str, Any]) -> "ChartMarker":
        """由濕空氣服務回傳的狀態建立標記。

參數：
    label: 標記文字。
    state: 含 Tdb（K）與 W（kg/kg）的狀態。

回傳：
    ChartMarker。"""
        return cls(label, float(state["Tdb"]) - 273.15, float(state["W"]))


@dataclass(frozen=True)
class ChartGuide:
    """由狀態點延伸出的輔助線（例如到露點或濕球溫度），終點以空心圓與標籤標示。"""

    start: ChartMarker
    end: ChartMarker


def draw_psychrometric_chart(
    figure: Figure,
    data: PsychrometricChartData,
    *,
    markers: Sequence[ChartMarker] = (),
    paths: Sequence[Sequence[ChartMarker]] = (),
    guides: Sequence[ChartGuide] = (),
    title: str | None = None,
) -> None:
    """在既有 figure 上重畫濕空氣線圖、狀態點與過程線。

參數：
    figure: 要重畫的 Matplotlib figure（會先清除）。
    data: 線圖曲線資料。
    markers: 要標示的狀態點。
    paths: 過程線，每條為依序連接的狀態點。
    guides: 輔助線；終點標籤取自 end.label。
    title: 選用標題；None 時顯示大氣壓力與海拔，空字串時不顯示標題與圖例說明。

回傳：
    無。"""
    figure.clear()
    axes = figure.add_subplot(111)
    for curve in data.relative_humidity_lines:
        axes.plot(curve.dry_bulb_c, [w * 1000 for w in curve.humidity_ratio],
                  color="#9AA9BA", linewidth=0.7)
        if curve.dry_bulb_c:
            # 碰到上緣的曲線改標在線段 85% 位置，避免標籤擠在圖框頂端。
            last = len(curve.dry_bulb_c) - 1
            index = last if curve.humidity_ratio[-1] < 0.95 * data.humidity_ratio_max else int(last * 0.85)
            axes.annotate(curve.label, (curve.dry_bulb_c[index], curve.humidity_ratio[index] * 1000),
                          fontsize=7, color="#6B7C8F", xytext=(3, -2), textcoords="offset points")
    for curve in data.enthalpy_lines:
        axes.plot(curve.dry_bulb_c, [w * 1000 for w in curve.humidity_ratio],
                  color="#C9B08A", linewidth=0.6, linestyle="--")
        axes.annotate(curve.label.split()[0], (curve.dry_bulb_c[-1], curve.humidity_ratio[-1] * 1000),
                      fontsize=6, color="#A0845C", xytext=(-8, 3), textcoords="offset points")
    saturation = data.saturation
    axes.plot(saturation.dry_bulb_c, [w * 1000 for w in saturation.humidity_ratio],
              color="#1B3A5C", linewidth=1.8, label="飽和線 (100%)")

    for index, path in enumerate(paths):
        color = PROCESS_COLORS[index % len(PROCESS_COLORS)]
        axes.plot([point.dry_bulb_c for point in path],
                  [point.humidity_ratio * 1000 for point in path],
                  color=color, linewidth=2.2)
    for guide in guides:
        axes.plot([guide.start.dry_bulb_c, guide.end.dry_bulb_c],
                  [guide.start.humidity_ratio * 1000, guide.end.humidity_ratio * 1000],
                  color=GUIDE_COLOR, linewidth=1.0, linestyle="--")
        axes.plot(guide.end.dry_bulb_c, guide.end.humidity_ratio * 1000, "o",
                  markerfacecolor="white", markeredgecolor=GUIDE_COLOR, markersize=5, zorder=5)
        axes.annotate(guide.end.label, (guide.end.dry_bulb_c, guide.end.humidity_ratio * 1000),
                      xytext=(-6, 5), textcoords="offset points", fontsize=8, color=GUIDE_COLOR,
                      ha="right")
    for marker in markers:
        axes.plot(marker.dry_bulb_c, marker.humidity_ratio * 1000, "o",
                  color="#C0362C", markersize=7, zorder=5)
        axes.annotate(marker.label, (marker.dry_bulb_c, marker.humidity_ratio * 1000),
                      xytext=(6, 6), textcoords="offset points", fontsize=9,
                      color="#C0362C", fontweight="bold")

    axes.set_xlim(*data.dry_bulb_range_c)
    axes.set_ylim(0, data.humidity_ratio_max * 1000)
    axes.yaxis.tick_right()
    axes.yaxis.set_label_position("right")
    axes.set_xlabel("乾球溫度 (°C)")
    axes.set_ylabel("濕度比 W (g/kg 乾空氣)")
    axes.grid(True, color="#E4E9F0", linewidth=0.6)
    if title is None:
        title = f"濕空氣線圖（大氣壓力 {data.pressure_pa / 1000:.2f} kPa，海拔 {data.altitude_m:g} m）"
    if title:
        axes.set_title(title, fontsize=11)
        axes.text(0.01, 0.98, "虛線：等焓線 (kJ/kg)", transform=axes.transAxes, fontsize=7,
                  color="#A0845C", va="top")
    figure.tight_layout()
