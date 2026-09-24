"""空氣處理過程分析：混合、顯熱加熱／冷卻、冷卻除濕與送風量估算。

本模組只負責表單、單位換算與結果呈現；計算委派給 `AirProcessService`，
線圖曲線來自 `chart.psychrometric`，並在同一個 FigurePanel 上標示過程。
"""

from __future__ import annotations

import flet as ft

from application.air_processes import AirProcessService
from application.models import (
    AirStateInput,
    AirStreamInput,
    CoolingCoilRequest,
    MixingRequest,
    SensibleProcessRequest,
    SupplyAirflowRequest,
)
from chart.psychrometric import PsychrometricChartData, build_psychrometric_chart_data

from ...ui.components.figure_panel import FigurePanel
from ..unit.UnitConverter import UnitConverter
from ..unit.thermo_draw.psychrometric_plot import ChartMarker, draw_psychrometric_chart
from .base_analysis_module import BaseAnalysisModule
from .result_formatting import ResultFormatter


class PsyProcessModule(BaseAnalysisModule):
    """空氣處理過程的分析模組。"""

    def __init__(self, unit_converter: UnitConverter, page: ft.Page,
                 air_process_service: AirProcessService) -> None:
        """建立四種空氣處理分析的表單與共用線圖。

參數：
    unit_converter: 共用單位轉換器。
    page: Flet 頁面。
    air_process_service: 空氣處理 application service。

回傳：
    無。"""
        super().__init__(unit_converter, page, air_process_service=air_process_service)
        self.air = air_process_service
        self.chart_panel = FigurePanel(placeholder="執行分析後，過程會標示在濕空氣線圖上")
        self._chart_cache: dict[float, PsychrometricChartData] = {}
        self.mixing_ui = self._build_form("mix", [
            ("氣流 A（例如外氣）", [("mix_a_tdb", "乾球溫度", "35", "T", "°C"),
                                   ("mix_a_rh", "相對濕度", "60", "RH", "%"),
                                   ("mix_a_flow", "風量", "1000", "VolumeFlow", "m³/h")]),
            ("氣流 B（例如回風）", [("mix_b_tdb", "乾球溫度", "26", "T", "°C"),
                                   ("mix_b_rh", "相對濕度", "50", "RH", "%"),
                                   ("mix_b_flow", "風量", "3000", "VolumeFlow", "m³/h")]),
        ])
        self.sensible_ui = self._build_form("sen", [
            ("入口空氣", [("sen_in_tdb", "入口乾球溫度", "15", "T", "°C"),
                          ("sen_in_rh", "入口相對濕度", "60", "RH", "%"),
                          ("sen_flow", "風量（入口狀態）", "2000", "VolumeFlow", "m³/h")]),
            ("出口條件", [("sen_out_tdb", "出口乾球溫度", "30", "T", "°C")]),
        ])
        self.coil_ui = self._build_form("coil", [
            ("盤管入口", [("coil_in_tdb", "入口乾球溫度", "27", "T", "°C"),
                          ("coil_in_rh", "入口相對濕度", "50", "RH", "%"),
                          ("coil_flow", "風量（入口狀態）", "3000", "VolumeFlow", "m³/h")]),
            ("盤管出口", [("coil_out_tdb", "出口乾球溫度", "13", "T", "°C"),
                          ("coil_out_rh", "出口相對濕度", "95", "RH", "%")]),
        ])
        self.supply_ui = self._build_form("sup", [
            ("室內設計條件", [("sup_room_tdb", "室內乾球溫度", "26", "T", "°C"),
                              ("sup_room_rh", "室內相對濕度", "50", "RH", "%"),
                              ("sup_load", "室內顯熱負荷", "10", "Power", "kW")]),
            ("送風條件", [("sup_supply_tdb", "送風乾球溫度", "15", "T", "°C")]),
        ])
        self.bind_independent_unit_sync(list(self.all_entries))

    # ======================================================
    # 註冊
    # ======================================================
    def get_analysis_definitions(self) -> dict:
        """回報此模組提供的空氣處理分析，並附上共用的濕空氣線圖。

回傳：
    以分析名稱為鍵的註冊定義。"""
        return {
            "兩股氣流混合": {
                "analysis_id": "psychrometrics.mixing",
                "ui": self.mixing_ui,
                "calc_func": self.calculate_mixing,
                "result_chart": self.chart_panel,
            },
            "顯熱加熱／冷卻": {
                "analysis_id": "psychrometrics.sensible",
                "ui": self.sensible_ui,
                "calc_func": self.calculate_sensible,
                "result_chart": self.chart_panel,
            },
            "冷卻除濕盤管": {
                "analysis_id": "psychrometrics.cooling_coil",
                "ui": self.coil_ui,
                "calc_func": self.calculate_cooling_coil,
                "result_chart": self.chart_panel,
            },
            "送風量估算": {
                "analysis_id": "psychrometrics.supply_airflow",
                "ui": self.supply_ui,
                "calc_func": self.calculate_supply_airflow,
                "result_chart": self.chart_panel,
            },
        }

    # ======================================================
    # 表單
    # ======================================================
    def _build_form(self, prefix: str, groups: list[tuple[str, list[tuple[str, str, str, str, str]]]]
                    ) -> ft.Container:
        """建立含海拔欄位與分組輸入列的表單容器。

參數：
    prefix: 此表單海拔欄位的識別鍵前綴。
    groups: (小節名稱, [(key, 欄名, 預設值, 性質代碼, 預設單位), ...]) 清單。

回傳：
    預設隱藏的表單容器。"""
        controls: list[ft.Control] = [
            self.create_input_row(f"{prefix}_alt", "海拔高度（決定大氣壓力）", "0", "L", "m")["ui_row"]
        ]
        for title, rows in groups:
            controls.append(self.section_label(title))
            for key, label, default, prop_code, unit in rows:
                controls.append(self.create_input_row(key, label, default, prop_code, unit)["ui_row"])
        return ft.Container(content=ft.Column(controls, spacing=12), visible=False)

    def _air_state(self, tdb_key: str, rh_key: str) -> AirStateInput:
        """讀取乾球溫度與 RH 欄位組成空氣狀態。

參數：
    tdb_key: 乾球溫度欄位鍵。
    rh_key: 相對濕度欄位鍵。

回傳：
    AirStateInput。"""
        return AirStateInput(self.read_si(tdb_key), relative_humidity=self.read_si(rh_key))

    # ======================================================
    # 圖表
    # ======================================================
    def _chart_data(self, altitude_m: float) -> PsychrometricChartData:
        """回傳指定海拔的線圖資料；同一海拔重複使用快取。

參數：
    altitude_m: 海拔（m）。

回傳：
    PsychrometricChartData。"""
        key = round(altitude_m, 3)
        if key not in self._chart_cache:
            self._chart_cache[key] = build_psychrometric_chart_data(self.air.psychrometrics, altitude_m)
        return self._chart_cache[key]

    def _plot(self, altitude_m: float, markers: list[ChartMarker], paths: list[list[ChartMarker]]) -> None:
        """在共用圖表上畫出過程。

參數：
    altitude_m: 海拔（m）。
    markers: 狀態點。
    paths: 過程線。

回傳：
    無。"""
        draw_psychrometric_chart(self.chart_panel.figure, self._chart_data(altitude_m),
                                 markers=markers, paths=paths)
        self.chart_panel.refresh()

    # ======================================================
    # 計算
    # ======================================================
    def calculate_mixing(self, use_imperial: bool) -> str:
        """計算兩股氣流混合並標示混合線。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        altitude = self.read_si("mix_alt")
        stream_a = AirStreamInput(self._air_state("mix_a_tdb", "mix_a_rh"), self.read_si("mix_a_flow"))
        stream_b = AirStreamInput(self._air_state("mix_b_tdb", "mix_b_rh"), self.read_si("mix_b_flow"))
        result = self.air.mix(MixingRequest(altitude, (stream_a, stream_b)))
        state_a = self.air.resolve_state(stream_a.state, altitude)
        state_b = self.air.resolve_state(stream_b.state, altitude)
        a, b = ChartMarker.from_state("A", state_a), ChartMarker.from_state("B", state_b)
        mixed = ChartMarker.from_state("M 混合", result.state)
        self._plot(altitude, [a, b, mixed], [[a, b]])

        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section("混合後狀態").add_air_state(result.state)
        formatter.section("流量")
        formatter.add("混合後風量", "VolumeFlow", result.volume_flow_m3_s, 1)
        formatter.add("乾空氣質量流率", "MassFlow", result.dry_air_mass_flow_kg_s, 4)
        formatter.add_text("氣流 A 質量比例", f"{result.mass_fractions[0] * 100:.1f} %")
        return formatter.text()

    def calculate_sensible(self, use_imperial: bool) -> str:
        """計算顯熱加熱或冷卻並標示過程線。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        altitude = self.read_si("sen_alt")
        result = self.air.sensible(SensibleProcessRequest(
            altitude, self._air_state("sen_in_tdb", "sen_in_rh"),
            self.read_si("sen_out_tdb"), self.read_si("sen_flow"),
        ))
        inlet, outlet = ChartMarker.from_state("1 入口", result.inlet), ChartMarker.from_state("2 出口", result.outlet)
        self._plot(altitude, [inlet, outlet], [[inlet, outlet]])

        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section("熱量")
        process = "加熱量" if result.heat_rate_w >= 0 else "冷卻量（顯熱）"
        formatter.add(process, "Power", abs(result.heat_rate_w), 3)
        formatter.add("乾空氣質量流率", "MassFlow", result.dry_air_mass_flow_kg_s, 4)
        formatter.section("出口狀態").add_air_state(result.outlet)
        return formatter.text()

    def calculate_cooling_coil(self, use_imperial: bool) -> str:
        """計算冷卻除濕盤管負荷並標示過程線。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        altitude = self.read_si("coil_alt")
        result = self.air.cooling_coil(CoolingCoilRequest(
            altitude,
            self._air_state("coil_in_tdb", "coil_in_rh"),
            self._air_state("coil_out_tdb", "coil_out_rh"),
            self.read_si("coil_flow"),
        ))
        inlet, outlet = ChartMarker.from_state("1 入口", result.inlet), ChartMarker.from_state("2 出口", result.outlet)
        self._plot(altitude, [inlet, outlet], [[inlet, outlet]])

        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section("盤管負荷")
        formatter.add("全熱負荷", "Power", result.total_load_w, 3)
        formatter.add("顯熱負荷", "Power", result.sensible_load_w, 3)
        formatter.add("潛熱負荷", "Power", result.latent_load_w, 3)
        formatter.add_text("顯熱比 SHR", f"{result.sensible_heat_ratio:.3f}")
        mass_unit = "lbm" if use_imperial else "kg"
        condensate_per_hour = self.unit_converter.convert_from_si(
            "MassFlow", result.condensate_kg_s, f"{mass_unit}/s") * 3600
        formatter.add_text("冷凝水量", f"{condensate_per_hour:.2f} {mass_unit}/h")
        formatter.section("出口狀態").add_air_state(result.outlet)
        return formatter.text()

    def calculate_supply_airflow(self, use_imperial: bool) -> str:
        """依顯熱負荷估算送風量並標示室內與送風狀態。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        altitude = self.read_si("sup_alt")
        result = self.air.supply_airflow(SupplyAirflowRequest(
            altitude, self._air_state("sup_room_tdb", "sup_room_rh"),
            self.read_si("sup_supply_tdb"), self.read_si("sup_load"),
        ))
        room, supply = ChartMarker.from_state("R 室內", result.room), ChartMarker.from_state("S 送風", result.supply)
        self._plot(altitude, [room, supply], [[supply, room]])

        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section("送風量")
        formatter.add("所需送風量", "VolumeFlow", result.supply_volume_flow_m3_s, 1)
        formatter.add("乾空氣質量流率", "MassFlow", result.dry_air_mass_flow_kg_s, 4)
        formatter.add("送風溫差 ΔT", "DeltaT", result.temperature_difference_k, 1)
        formatter.section("送風狀態").add_air_state(result.supply)
        return formatter.text()
