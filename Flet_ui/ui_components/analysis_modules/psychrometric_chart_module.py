"""濕空氣線圖：在指定海拔的線圖上標示多個狀態點並列出其性質。"""

from __future__ import annotations

import flet as ft

from application.air_processes import AirProcessService
from application.models import AirStateInput
from chart.psychrometric import build_psychrometric_chart_data

from ...ui.components.figure_panel import FigurePanel
from ...ui.theme import TOKENS
from ..unit.UnitConverter import UnitConverter
from ..unit.thermo_draw.psychrometric_plot import ChartMarker, draw_psychrometric_chart
from .base_analysis_module import BaseAnalysisModule
from .result_formatting import ResultFormatter

MAX_POINTS = 8


class PsychrometricChartModule(BaseAnalysisModule):
    """濕空氣線圖與多狀態點標示。"""

    def __init__(self, unit_converter: UnitConverter, page: ft.Page,
                 air_process_service: AirProcessService) -> None:
        """建立線圖設定表單與圖表面板。

參數：
    unit_converter: 共用單位轉換器。
    page: Flet 頁面。
    air_process_service: 提供濕空氣狀態計算的 application service。

回傳：
    無。"""
        super().__init__(unit_converter, page, air_process_service=air_process_service)
        self.air = air_process_service
        self.chart_panel = FigurePanel(height=560, placeholder="按下「執行分析」繪製濕空氣線圖")
        self.connect_points_cb = ft.Checkbox(label="依序連接狀態點（表示處理過程）", value=True,
                                             active_color=TOKENS.primary)
        altitude_row = self.create_input_row("pc_alt", "海拔高度（決定大氣壓力）", "0", "L", "m")["ui_row"]
        tdb_row = self.create_input_row("pc_tdb", "乾球溫度（逗號分隔多點）", "35, 26, 13", "T", "°C")["ui_row"]
        rh_row = self.create_input_row("pc_rh", "相對濕度（與乾球溫度一一對應）", "60, 50, 95", "RH", "%")["ui_row"]
        for key in ("pc_tdb", "pc_rh"):
            self.all_entries[key]["val"].keyboard_type = ft.KeyboardType.TEXT
        self.bind_independent_unit_sync(["pc_alt"])
        self.bind_multi_value_unit_sync(["pc_tdb"])
        self.chart_ui = ft.Container(
            content=ft.Column(
                [
                    altitude_row,
                    self.section_label(f"狀態點（最多 {MAX_POINTS} 點）"),
                    tdb_row,
                    rh_row,
                    self.connect_points_cb,
                ],
                spacing=12,
            ),
            visible=False,
        )

    def get_analysis_definitions(self) -> dict:
        """回報濕空氣線圖分析。

回傳：
    以分析名稱為鍵的註冊定義。"""
        return {
            "濕空氣線圖": {
                "analysis_id": "psychrometric_chart.plot",
                "ui": self.chart_ui,
                "calc_func": self.calculate_chart,
                "result_chart": self.chart_panel,
                "result_chart_first": True,
            },
        }

    def calculate_chart(self, use_imperial: bool) -> str:
        """計算各狀態點、繪製線圖並列出性質。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。

引發：
    ValueError：點數不一致或超過上限時。"""
        altitude = self.read_si("pc_alt")
        temperatures = self.read_si_list("pc_tdb")
        humidities = self.read_si_list("pc_rh")
        if len(temperatures) != len(humidities):
            raise ValueError(f"乾球溫度（{len(temperatures)} 筆）與相對濕度（{len(humidities)} 筆）的數量必須相同。")
        if len(temperatures) > MAX_POINTS:
            raise ValueError(f"最多只能標示 {MAX_POINTS} 個狀態點。")
        states = [
            self.air.resolve_state(AirStateInput(tdb, relative_humidity=rh), altitude)
            for tdb, rh in zip(temperatures, humidities)
        ]
        markers = [ChartMarker.from_state(str(index), state) for index, state in enumerate(states, 1)]
        paths = [markers] if self.connect_points_cb.value and len(markers) > 1 else []
        draw_psychrometric_chart(
            self.chart_panel.figure,
            build_psychrometric_chart_data(self.air.psychrometrics, altitude),
            markers=markers,
            paths=paths,
        )
        self.chart_panel.refresh()

        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section("大氣條件")
        formatter.add("大氣壓力", "P", self.air.psychrometrics.calculate_pressure_from_altitude(altitude), 3)
        for index, state in enumerate(states, 1):
            formatter.section(f"狀態點 {index}").add_air_state(state)
        return formatter.text()
