"""空調負荷分析：新風負荷、加濕負荷、風量與冷量換算。

本模組只負責表單、單位換算與結果呈現；計算委派給 `AirLoadService`。新風過程標示在
濕空氣線圖上；加濕只標示入口與設計目標兩點（不連線），因為加濕計算是水量與蒸汽需求
估算，不是蒸汽加濕的熱力過程模擬。熱量符號：正值為冷卻（從空氣移除熱）、負值為加熱。
"""

from __future__ import annotations

import flet as ft

from application.air_loads import AirLoadService
from application.models import (
    AirStateInput,
    HumidificationRequest,
    OutdoorAirLoadRequest,
    StateAirflowCapacityRequest,
)
from chart.psychrometric import ChartMarker, PsychrometricChartData, build_psychrometric_chart_data
from domain.psychrometrics.loads import (
    STANDARD_AIR_CP_J_KGK,
    STANDARD_AIR_DENSITY_KG_M3,
    SensibleLatentSplit,
)
from domain.state_points import AirStatePoint, StateSource

from ...ui.components.psychrometric_chart_panel import PsychrometricChartPanel
from ...ui.theme import TOKENS
from ..unit.UnitConverter import UnitConverter
from .base_analysis_module import BaseAnalysisModule
from .result_formatting import ResultFormatter

METHOD_STANDARD = "standard"
METHOD_STATE = "state"
KNOWN_AIRFLOW = "airflow"
KNOWN_CAPACITY = "capacity"
SIGN_NOTE = "正值為冷卻、負值為加熱"


class AirLoadModule(BaseAnalysisModule):
    """空調側負荷的分析模組。"""

    def __init__(self, unit_converter: UnitConverter, page: ft.Page, air_load_service: AirLoadService) -> None:
        """建立三種空調負荷分析的表單與共用線圖。

參數：
    unit_converter: 共用單位轉換器。
    page: Flet 頁面。
    air_load_service: 空調負荷 application service。

回傳：
    無。"""
        super().__init__(unit_converter, page, air_load_service=air_load_service)
        self.loads = air_load_service
        self.chart_panel = PsychrometricChartPanel(placeholder="執行分析後，過程會標示在濕空氣線圖上")
        self._chart_cache: dict[float, PsychrometricChartData] = {}
        self.last_states: dict[str, tuple[AirStatePoint, ...]] = {}
        self.outdoor_ui = self._build_form("oa", [
            ("外氣", [("oa_out_tdb", "外氣乾球溫度", "35", "T", "°C"),
                      ("oa_out_rh", "外氣相對濕度", "60", "RH", "%"),
                      ("oa_flow", "新風量（外氣狀態）", "1000", "VolumeFlow", "m³/h")]),
            ("室內設計條件", [("oa_room_tdb", "室內乾球溫度", "26", "T", "°C"),
                              ("oa_room_rh", "室內相對濕度", "50", "RH", "%")]),
        ])
        self.humid_ui = self._build_form("hum", [
            ("加濕前空氣", [("hum_in_tdb", "入口乾球溫度", "22", "T", "°C"),
                            ("hum_in_rh", "入口相對濕度", "20", "RH", "%"),
                            ("hum_flow", "風量（入口狀態）", "1000", "VolumeFlow", "m³/h")]),
            ("設計目標（用來取得目標濕度比）", [("hum_target_tdb", "目標乾球溫度", "22", "T", "°C"),
                          ("hum_target_rh", "目標相對濕度", "45", "RH", "%")]),
        ])
        self.capacity_ui = self._build_capacity_ui()
        self.bind_independent_unit_sync(list(self.all_entries))
        self._refresh_capacity_rows()

    # ======================================================
    # 註冊
    # ======================================================
    def get_analysis_definitions(self) -> dict:
        """回報此模組提供的空調負荷分析。

回傳：
    以分析名稱為鍵的註冊定義。"""
        return {
            "新風負荷": {
                "analysis_id": "airside.outdoor_air_load",
                "ui": self.outdoor_ui,
                "calc_func": self.calculate_outdoor_air,
                "result_chart": self.chart_panel,
                "state_points": lambda: self.last_states.get("outdoor", ()),
            },
            "加濕負荷": {
                "analysis_id": "airside.humidification",
                "ui": self.humid_ui,
                "calc_func": self.calculate_humidification,
                "result_chart": self.chart_panel,
                "state_points": lambda: self.last_states.get("humidification", ()),
            },
            "風量與冷量換算": {
                "analysis_id": "airside.airflow_capacity",
                "ui": self.capacity_ui,
                "calc_func": self.calculate_airflow_capacity,
                "state_points": lambda: self.last_states.get("capacity", ()),
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

    @staticmethod
    def _segmented(options: list[tuple[str, str]], on_change) -> ft.SegmentedButton:
        """建立單選分段按鈕。

參數：
    options: (值, 顯示文字) 清單；第一項為預設。
    on_change: 變更處理器。

回傳：
    SegmentedButton。"""
        return ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[ft.Segment(value=value, label=ft.Text(label)) for value, label in options],
            selected=[options[0][0]],
            on_change=on_change,
        )

    def _build_capacity_ui(self) -> ft.Container:
        """建立風量與冷量換算表單：計算方式（標準空氣快算／狀態精算）與已知條件（風量／冷量）。

回傳：
    預設隱藏的表單容器。"""
        # 分段按鈕位於窄輸入欄，使用短標籤；欄名說明完整意思，避免文字折行。
        self.cap_method = self._segmented(
            [(METHOD_STANDARD, "快算"), (METHOD_STATE, "精算")], self.on_capacity_mode_change)
        self.cap_known = self._segmented(
            [(KNOWN_AIRFLOW, "風量"), (KNOWN_CAPACITY, "冷量")], self.on_capacity_mode_change)
        self.cap_standard_note = ft.Text(
            f"標準空氣近似：ρ = {STANDARD_AIR_DENSITY_KG_M3} kg/m³、cp = {STANDARD_AIR_CP_J_KGK / 1000:.3f} kJ/(kg·K)；"
            "只計顯熱。需要潛熱或非標準狀態時請用狀態精算。",
            size=TOKENS.caption, color=TOKENS.text_muted,
        )
        rows = [
            ("cap_alt", "海拔高度（決定大氣壓力）", "0", "L", "m"),
            ("cap_in_tdb", "進風乾球溫度", "26", "T", "°C"),
            ("cap_in_rh", "進風相對濕度", "50", "RH", "%"),
            ("cap_out_tdb", "出風乾球溫度", "13", "T", "°C"),
            ("cap_out_rh", "出風相對濕度", "90", "RH", "%"),
            ("cap_dt", "進出風溫差 ΔT", "10", "DeltaT", "K"),
            ("cap_flow", "風量", "1000", "VolumeFlow", "m³/h"),
            ("cap_load", "顯熱容量（大小）", "5", "Power", "kW"),
        ]
        controls: list[ft.Control] = [
            ft.Column([ft.Text("計算方式（快算：標準空氣；精算：濕空氣狀態）", size=TOKENS.body, weight=ft.FontWeight.W_500,
                               color=TOKENS.text_primary), self.cap_method], spacing=6),
            ft.Column([ft.Text("已知條件（由風量求冷量，或由冷量求風量）", size=TOKENS.body, weight=ft.FontWeight.W_500,
                               color=TOKENS.text_primary), self.cap_known], spacing=6),
            self.cap_standard_note,
        ]
        for key, label, default, prop_code, unit in rows:
            controls.append(self.create_input_row(key, label, default, prop_code, unit)["ui_row"])
        return ft.Container(content=ft.Column(controls, spacing=12), visible=False)

    @property
    def capacity_method(self) -> str:
        """目前的計算方式。

回傳：
    ``standard`` 或 ``state``。"""
        return METHOD_STATE if METHOD_STATE in self.cap_method.selected else METHOD_STANDARD

    @property
    def capacity_known(self) -> str:
        """目前的已知條件。

回傳：
    ``airflow`` 或 ``capacity``。"""
        return KNOWN_CAPACITY if KNOWN_CAPACITY in self.cap_known.selected else KNOWN_AIRFLOW

    def _refresh_capacity_rows(self) -> None:
        """依計算方式與已知條件顯示對應輸入列。

回傳：
    無。"""
        state_mode = self.capacity_method == METHOD_STATE
        known_airflow = self.capacity_known == KNOWN_AIRFLOW
        for key in ("cap_alt", "cap_in_tdb", "cap_in_rh", "cap_out_tdb", "cap_out_rh"):
            self.all_entries[key]["ui_row"].visible = state_mode
        self.all_entries["cap_dt"]["ui_row"].visible = not state_mode
        self.all_entries["cap_flow"]["ui_row"].visible = known_airflow
        self.all_entries["cap_load"]["ui_row"].visible = not known_airflow
        self.all_entries["cap_flow"]["label_control"].value = "風量（進風狀態）" if state_mode else "風量"
        # 容量輸入一律取大小（正值）；精算結果的全熱／顯熱／潛熱才帶冷卻（正）／加熱（負）符號。
        self.all_entries["cap_load"]["label_control"].value = "全熱容量（取大小）" if state_mode else "顯熱容量（大小）"
        self.cap_standard_note.visible = not state_mode
        self._update_controls(self.capacity_ui)

    def on_capacity_mode_change(self, _event: ft.ControlEvent | None) -> None:
        """切換計算方式或已知條件。

參數：
    _event: Flet 事件。

回傳：
    無。"""
        self._refresh_capacity_rows()

    def _air_state(self, tdb_key: str, rh_key: str) -> AirStateInput:
        """讀取乾球溫度與 RH 欄位組成空氣狀態。

參數：
    tdb_key: 乾球溫度欄位鍵。
    rh_key: 相對濕度欄位鍵。

回傳：
    AirStateInput。"""
        return AirStateInput(self.read_si(tdb_key), relative_humidity=self.read_si(rh_key))

    # ======================================================
    # 圖表與狀態點
    # ======================================================
    def _plot(self, altitude_m: float, markers: list[ChartMarker], *, connect: bool = True) -> None:
        """在共用圖表上標示狀態點；connect 為 True 時畫出由第一點到最後一點的過程線。

參數：
    altitude_m: 海拔（m）。
    markers: 狀態點（依過程順序）。
    connect: 是否以連線表示過程；只比較狀態、不代表過程軌跡時為 False。

回傳：
    無。"""
        key = round(altitude_m, 3)
        if key not in self._chart_cache:
            self._chart_cache[key] = build_psychrometric_chart_data(self.loads.psychrometrics, altitude_m)
        self.chart_panel.draw(self._chart_cache[key], markers=markers, paths=[markers] if connect else [])
        self.chart_panel.refresh()

    @staticmethod
    def _points(*states: tuple[str, dict]) -> tuple[AirStatePoint, ...]:
        """把濕空氣狀態轉成可保存的狀態點。

參數：
    states: (顯示名稱, 狀態 dict)。

回傳：
    AirStatePoint tuple。"""
        return tuple(AirStatePoint.from_state_mapping(state, source=StateSource.AIR_PROCESS, label=label)
                     for label, state in states)

    # ======================================================
    # 計算
    # ======================================================
    @staticmethod
    def _add_split(formatter: ResultFormatter, split: SensibleLatentSplit, prefix: str) -> None:
        """加入全熱、顯熱、潛熱與顯熱比。

參數：
    formatter: 結果格式化器。
    split: 負荷分解。
    prefix: 名稱前綴，例如「負荷」或「量」。

回傳：
    無。"""
        formatter.add(f"全熱{prefix}", "Power", split.total_w, 3)
        formatter.add(f"顯熱{prefix}", "Power", split.sensible_w, 3)
        formatter.add(f"潛熱{prefix}", "Power", split.latent_w, 3)
        if split.total_w:
            formatter.add_text("顯熱比 SHR", f"{split.sensible_w / split.total_w:.3f}")

    def calculate_outdoor_air(self, use_imperial: bool) -> str:
        """計算新風負荷並標示外氣到室內的過程。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        self.last_states.pop("outdoor", None)
        altitude = self.read_si("oa_alt")
        result = self.loads.outdoor_air(OutdoorAirLoadRequest(
            altitude, self._air_state("oa_out_tdb", "oa_out_rh"), self._air_state("oa_room_tdb", "oa_room_rh"),
            self.read_si("oa_flow"),
        ))
        self._plot(altitude, [ChartMarker.from_state("O 外氣", result.outdoor),
                              ChartMarker.from_state("R 室內", result.room)])
        self.last_states["outdoor"] = self._points(("外氣", result.outdoor), ("室內設計", result.room))

        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section(f"新風負荷（{SIGN_NOTE}）")
        self._add_split(formatter, result.load, "負荷")
        formatter.section("新風量")
        formatter.add("新風量（外氣狀態）", "VolumeFlow", result.outdoor_volume_flow_m3_s, 1)
        formatter.add("乾空氣質量流率", "MassFlow", result.dry_air_mass_flow_kg_s, 4)
        formatter.add("外氣比焓", "H", float(result.outdoor["H"]), 2)
        formatter.add("室內比焓", "H", float(result.room["H"]), 2)
        return formatter.text()

    def calculate_humidification(self, use_imperial: bool) -> str:
        """計算加濕水量與蒸汽需求，並在線圖上標示入口與設計目標（不連線）。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        self.last_states.pop("humidification", None)
        altitude = self.read_si("hum_alt")
        result = self.loads.humidification(HumidificationRequest(
            altitude, self._air_state("hum_in_tdb", "hum_in_rh"), self._air_state("hum_target_tdb", "hum_target_rh"),
            self.read_si("hum_flow"),
        ))
        # 目標是設計狀態，不是蒸汽噴入後的出口；只標示兩點，不畫過程線。
        self._plot(altitude, [ChartMarker.from_state("1 入口", result.inlet),
                              ChartMarker.from_state("2 設計目標", result.target)], connect=False)
        self.last_states["humidification"] = self._points(("加濕前", result.inlet), ("加濕目標", result.target))

        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section("加濕水量／蒸汽需求估算")
        mass_unit = "lbm" if use_imperial else "kg"
        water_per_hour = self.unit_converter.convert_from_si("MassFlow", result.water_kg_s, f"{mass_unit}/s") * 3600
        formatter.add_text("加濕水量", f"{water_per_hour:.2f} {mass_unit}/h")
        formatter.add("蒸汽加濕熱量", "Power", result.steam_heat_w, 3)
        if not result.required:
            formatter.lines.append("目標濕度比不高於入口，不需加濕。")
        formatter.section("計算依據")
        formatter.add("入口濕度比", "W", float(result.inlet["W"]), 2)
        formatter.add("目標濕度比", "W", float(result.target["W"]), 2)
        formatter.add("乾空氣質量流率", "MassFlow", result.dry_air_mass_flow_kg_s, 4)
        formatter.add("水蒸發潛熱 h_fg（當地大氣壓力）", "H", result.steam_latent_heat_j_kg, 1)
        formatter.lines.append("蒸汽加濕熱量為產生常壓飽和蒸汽所需熱量的下限，不含給水預熱與設備損失；"
                               "滴濾、噴霧等等焓加濕不適用。")
        formatter.lines.append("目標狀態是設計目標，只用來取得目標濕度比；本計算不以蒸汽能量平衡預測實際出口乾球溫度，"
                               "線圖上的入口與設計目標兩點僅供比較，不代表實際蒸汽加濕過程的軌跡。")
        return formatter.text()

    def calculate_airflow_capacity(self, use_imperial: bool) -> str:
        """依計算方式與已知條件，換算風量與冷量。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        self.last_states.pop("capacity", None)
        formatter = ResultFormatter(self.unit_converter, use_imperial)
        known_airflow = self.capacity_known == KNOWN_AIRFLOW
        if self.capacity_method == METHOD_STANDARD:
            delta_t = self.read_si("cap_dt")
            result = (self.loads.standard_air_capacity(self.read_si("cap_flow"), delta_t) if known_airflow
                      else self.loads.standard_air_airflow(self.read_si("cap_load"), delta_t))
            formatter.section("標準空氣快算（近似）")
            formatter.add("顯熱容量（大小）", "Power", result.sensible_capacity_w, 3)
            formatter.add("風量", "VolumeFlow", result.volume_flow_m3_s, 1)
            formatter.add("溫差 ΔT", "DeltaT", result.temperature_difference_k, 1)
            formatter.lines.append(
                f"以標準空氣 ρ = {result.density_kg_m3} kg/m³、cp = {result.cp_j_kgk / 1000:.3f} kJ/(kg·K) 計算，只含顯熱；"
                "容量為大小，不區分冷卻或加熱。"
            )
            return formatter.text()

        altitude = self.read_si("cap_alt")
        result = self.loads.state_airflow_capacity(StateAirflowCapacityRequest(
            altitude, self._air_state("cap_in_tdb", "cap_in_rh"), self._air_state("cap_out_tdb", "cap_out_rh"),
            entering_volume_flow_m3_s=self.read_si("cap_flow") if known_airflow else None,
            total_capacity_w=None if known_airflow else self.read_si("cap_load"),
        ))
        self.last_states["capacity"] = self._points(("進風", result.entering), ("出風", result.leaving))
        formatter.section(f"冷量（{SIGN_NOTE}）")
        self._add_split(formatter, result.load, "量")
        formatter.section("風量")
        formatter.add("風量（進風狀態）", "VolumeFlow", result.entering_volume_flow_m3_s, 1)
        formatter.add("乾空氣質量流率", "MassFlow", result.dry_air_mass_flow_kg_s, 4)
        return formatter.text()
