"""濕空氣性質的結果畫面：關鍵數值、焓濕圖、完整性質表與可展開的計算過程。

只負責呈現 `PsychrometricService` 回傳的中立狀態，不做任何濕空氣計算；
圖表曲線來自 `chart.psychrometric`，數值格式與單位由 `ResultFormatter` 決定。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import flet as ft

from chart.psychrometric import PsychrometricChartData, build_psychrometric_chart_data
from domain.psychrometrics.service import PsychrometricService

from ...ui.components.figure_panel import FigurePanel
from ...ui.components.kpi_tile import KpiTile
from ...ui.components.property_table import PropertyGroup, PropertyRow, PropertyTable
from ...ui.theme import TOKENS
from ..unit.UnitConverter import UnitConverter
from ..unit.thermo_draw.psychrometric_plot import ChartGuide, ChartMarker, draw_psychrometric_chart
from .result_formatting import ResultFormatter

KNOWN_WET_BULB = "twb"
KNOWN_RELATIVE_HUMIDITY = "rh"
# 焓濕圖只保留少量等 RH 線，讓狀態點與輔助線清楚可讀。
CHART_RH_LEVELS = (0.3, 0.5, 0.7)


def chart_axes_for(state: Mapping[str, Any]) -> tuple[tuple[float, float], float]:
    """依狀態點決定焓濕圖座標範圍：預設 0–35 °C、0–30 g/kg，必要時放大以容納狀態點。

參數：
    state: 中立濕空氣狀態。

回傳：
    (乾球溫度範圍 °C, 濕度比上限 kg/kg)。"""
    tdb_c = float(state["Tdb"]) - 273.15
    tdp_c = float(state["Tdp"]) - 273.15
    low = min(0.0, math.floor((tdp_c - 5.0) / 5.0) * 5.0)
    high = max(35.0, math.ceil((tdb_c + 5.0) / 5.0) * 5.0)
    w_max = max(0.030, math.ceil(float(state["W"]) * 1.4 / 0.005) * 0.005)
    return (low, high), w_max


def _card(title: str, content: ft.Control, trailing: ft.Control | None = None) -> ft.Container:
    """建立結果畫面中的白底區塊。

參數：
    title: 區塊標題。
    content: 區塊內容。
    trailing: 選用的標題列右側控制項。

回傳：
    區塊容器。"""
    header: list[ft.Control] = [
        ft.Text(title, size=TOKENS.body + 1, weight=ft.FontWeight.W_600, color=TOKENS.text_primary,
                expand=True)
    ]
    if trailing is not None:
        header.append(trailing)
    return ft.Container(
        content=ft.Column([ft.Row(header, vertical_alignment=ft.CrossAxisAlignment.CENTER), content],
                          spacing=TOKENS.spacing_sm + 4),
        padding=TOKENS.spacing_lg - 4,
        bgcolor=TOKENS.surface,
        border=ft.Border.all(1, TOKENS.border),
        border_radius=ft.BorderRadius.all(TOKENS.radius_md),
    )


class PsychrometricResultView(ft.Column):
    """濕空氣性質計算的結構化結果畫面。"""

    def __init__(self, unit_converter: UnitConverter, psychrometrics: PsychrometricService) -> None:
        """建立空白的結果畫面。

參數：
    unit_converter: 共用單位轉換器。
    psychrometrics: 用於產生焓濕圖曲線的濕空氣服務。

回傳：
    無。"""
        self.unit_converter = unit_converter
        self.psychrometrics = psychrometrics
        self._chart_cache: dict[tuple, PsychrometricChartData] = {}
        kpi_col = {"xs": 6, "xl": 3}
        self.kpis = {
            "RH": KpiTile("相對濕度 RH", col=kpi_col),
            "Tdp": KpiTile("露點溫度 Tdp", col=kpi_col),
            "H": KpiTile("焓值 h", col=kpi_col),
            "W": KpiTile("濕度比 W", col=kpi_col),
        }
        self.chart_panel = FigurePanel(height=420, placeholder="計算後顯示焓濕圖")
        self.property_table = PropertyTable()
        self.process_table = PropertyTable()
        self.process_body = ft.Container(content=self.process_table, visible=False)
        self.process_icon = ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=TOKENS.text_secondary)
        self.process_toggle = ft.Container(
            content=ft.Row(
                [
                    self.process_icon,
                    ft.Text("顯示計算過程", size=TOKENS.body, weight=ft.FontWeight.W_600,
                            color=TOKENS.text_primary),
                    ft.Text("飽和壓力、飽和濕度比等中間值", size=TOKENS.caption,
                            color=TOKENS.text_muted),
                ],
                spacing=TOKENS.spacing_sm,
            ),
            on_click=self.toggle_process,
            ink=True,
            padding=ft.Padding.symmetric(vertical=4),
        )
        legend = ft.Row(
            [
                ft.Container(width=8, height=8, bgcolor="#C0362C",
                             border_radius=ft.BorderRadius.all(4)),
                ft.Text("目前狀態點", size=TOKENS.caption, color=TOKENS.text_secondary),
            ],
            spacing=6,
            tight=True,
        )
        super().__init__(
            [
                ft.ResponsiveRow(list(self.kpis.values()), spacing=TOKENS.spacing_sm,
                                 run_spacing=TOKENS.spacing_sm),
                # 寬螢幕時焓濕圖與完整性質表並排，較窄時上下排列。
                ft.ResponsiveRow(
                    [
                        ft.Container(_card("焓濕圖", self.chart_panel, legend), col={"xs": 12, "xl": 7}),
                        ft.Container(_card("完整性質", self.property_table), col={"xs": 12, "xl": 5}),
                    ],
                    spacing=TOKENS.spacing_md,
                    run_spacing=TOKENS.spacing_md,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Container(
                    content=ft.Column([self.process_toggle, self.process_body],
                                      spacing=TOKENS.spacing_sm),
                    padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_lg - 4,
                                                 vertical=TOKENS.spacing_sm + 4),
                    bgcolor=TOKENS.surface,
                    border=ft.Border.all(1, TOKENS.border),
                    border_radius=ft.BorderRadius.all(TOKENS.radius_md),
                ),
            ],
            spacing=TOKENS.spacing_md,
        )

    def toggle_process(self, _event: ft.ControlEvent | None) -> None:
        """展開或收合計算過程。

參數：
    _event: Flet 點擊事件；此處不需讀取內容。

回傳：
    無。"""
        self.process_body.visible = not self.process_body.visible
        self.process_icon.icon = ft.Icons.EXPAND_MORE if self.process_body.visible else ft.Icons.CHEVRON_RIGHT
        try:
            self.update()
        except RuntimeError:
            pass

    def show(self, state: Mapping[str, Any], *, known_input: str, use_imperial: bool) -> None:
        """以新的計算結果更新關鍵數值、焓濕圖與性質表。

參數：
    state: PsychrometricService 回傳的中立狀態。
    known_input: 使用者提供的第二個已知條件（KNOWN_WET_BULB 或 KNOWN_RELATIVE_HUMIDITY）。
    use_imperial: 是否以英制輸出。

回傳：
    無。"""
        fmt = ResultFormatter(self.unit_converter, use_imperial)
        self.kpis["RH"].set_value(f"{state['RH'] * 100:.1f}", "%")
        self.kpis["Tdp"].set_value(*fmt.parts("T", state["Tdp"], 2))
        # 關鍵數值卡空間有限，乾空氣基準 (DA) 只標在完整性質表中。
        self.kpis["H"].set_value(*fmt.parts("H", state["H"], 2))
        self.kpis["W"].set_value(*fmt.parts("W", state["W"], 2))
        self.property_table.set_groups(self._property_groups(state, known_input, fmt))
        self.process_table.set_groups(self._process_groups(state, fmt))
        self._draw_chart(state)

    def _property_groups(self, state: Mapping[str, Any], known_input: str,
                         fmt: ResultFormatter) -> list[PropertyGroup]:
        """組成「輸入值／計算結果」兩組性質。

參數：
    state: 中立狀態。
    known_input: 第二個已知條件種類。
    fmt: 結果格式化器。

回傳：
    性質分組。"""
        def row(label: str, code: str, key: str, digits: int = 2, suffix: str = "") -> PropertyRow:
            """建立一列帶單位的性質。

參數：
    label: 名稱。
    code: 性質代碼。
    key: 狀態鍵。
    digits: 小數位數。
    suffix: 單位後綴。

回傳：
    PropertyRow。"""
            value, unit = fmt.parts(code, state[key], digits)
            return PropertyRow(label, value, unit + suffix)

        wet_bulb = row("濕球溫度", "T", "Twb")
        humidity = PropertyRow("相對濕度", f"{state['RH'] * 100:.2f}", "%")
        known, derived = (wet_bulb, humidity) if known_input == KNOWN_WET_BULB else (humidity, wet_bulb)
        return [
            PropertyGroup("輸入值", [
                row("乾球溫度", "T", "Tdb"),
                known,
                row("海拔高度", "L", "Altitude", 1),
                row("大氣壓力", "P", "P", 3),
            ], highlighted=True),
            PropertyGroup("計算結果", [
                row("露點溫度", "T", "Tdp"),
                derived,
                row("濕度比", "W", "W", 2, "(DA)"),
                row("焓值", "H", "H", 2, "(DA)"),
                row("比容", "V", "V", 4, "(DA)"),
                row("水蒸氣分壓", "P", "Pw", 3),
            ]),
        ]

    @staticmethod
    def _process_groups(state: Mapping[str, Any], fmt: ResultFormatter) -> list[PropertyGroup]:
        """組成計算過程的中間值。

參數：
    state: 中立狀態。
    fmt: 結果格式化器。

回傳：
    性質分組。"""
        def row(label: str, code: str, key: str, digits: int) -> PropertyRow:
            """建立一列中間值。

參數：
    label: 名稱。
    code: 性質代碼。
    key: 狀態鍵。
    digits: 小數位數。

回傳：
    PropertyRow。"""
            value, unit = fmt.parts(code, state[key], digits)
            return PropertyRow(label, value, unit)

        return [
            PropertyGroup("飽和水蒸氣分壓", [
                row("乾球溫度下 Pws(Tdb)", "P", "Pws_db", 4),
                row("濕球溫度下 Pws(Twb)", "P", "Pws_wd", 4),
            ]),
            PropertyGroup("飽和濕度比", [
                row("乾球溫度下 Ws(Tdb)", "W", "Ws", 3),
                row("濕球溫度下 Ws(Twb)", "W", "Wss", 3),
            ]),
        ]

    def _chart_data(self, altitude_m: float, dry_bulb_range: tuple[float, float],
                    humidity_ratio_max: float) -> PsychrometricChartData:
        """取得（並快取）指定座標的焓濕圖曲線資料。

參數：
    altitude_m: 海拔（m）。
    dry_bulb_range: 乾球溫度範圍（°C）。
    humidity_ratio_max: 濕度比上限（kg/kg）。

回傳：
    PsychrometricChartData。"""
        key = (round(altitude_m, 3), dry_bulb_range, round(humidity_ratio_max, 4))
        if key not in self._chart_cache:
            self._chart_cache[key] = build_psychrometric_chart_data(
                self.psychrometrics, altitude_m,
                dry_bulb_range_c=dry_bulb_range,
                humidity_ratio_max=humidity_ratio_max,
                rh_levels=CHART_RH_LEVELS,
            )
        return self._chart_cache[key]

    def _draw_chart(self, state: Mapping[str, Any]) -> None:
        """畫出狀態點以及到露點、濕球溫度的輔助線。

參數：
    state: 中立狀態。

回傳：
    無。"""
        dry_bulb_range, humidity_ratio_max = chart_axes_for(state)
        data = self._chart_data(float(state["Altitude"]), dry_bulb_range, humidity_ratio_max)
        tdb_c = float(state["Tdb"]) - 273.15
        point = ChartMarker(f"{tdb_c:.1f} °C / {state['RH'] * 100:.1f}%", tdb_c, float(state["W"]))
        dew_point = ChartMarker(f"Tdp {float(state['Tdp']) - 273.15:.1f}",
                                float(state["Tdp"]) - 273.15, float(state["W"]))
        wet_bulb = ChartMarker(f"Twb {float(state['Twb']) - 273.15:.1f}",
                               float(state["Twb"]) - 273.15, float(state["Wss"]))
        draw_psychrometric_chart(
            self.chart_panel.figure, data,
            markers=[point],
            guides=[ChartGuide(point, wet_bulb), ChartGuide(point, dew_point)],
            title="",
        )
        self.chart_panel.refresh()
