"""冷凍循環分析：蒸氣壓縮循環（含 P-h 圖）與過熱度／過冷度判讀。

計算委派給 `RefrigerationService`；P-h 圖沿用既有 `generate_thermo_diagram`，
以與循環計算相同的 reference-state policy（Auto）繪製。
"""

from __future__ import annotations

import flet as ft

from application.models import RefrigerationCycleRequest, SuperheatCheckRequest
from application.refrigeration import RefrigerationService
from domain.refrigeration.saturation import REGION_SUBCOOLED, REGION_SUPERHEATED

from ...ui.components.figure_panel import FigurePanel
from ...ui.theme import TOKENS
from ..unit.UnitConverter import (
    ABSOLUTE_TO_GAUGE_UNIT,
    GAUGE_PRESSURE,
    GAUGE_TO_ABSOLUTE_UNIT,
    UnitConverter,
)
from ..unit.thermo_draw.coolprop_utils import generate_thermo_diagram
from .base_analysis_module import BaseAnalysisModule
from .result_formatting import ResultFormatter

REGION_LABELS = {
    REGION_SUPERHEATED: "過熱蒸氣",
    REGION_SUBCOOLED: "過冷液體",
}
CYCLE_STATE_LABELS = {
    "1": "1 壓縮機入口",
    "2": "2 壓縮機出口（排氣）",
    "3": "3 冷凝器出口",
    "4": "4 蒸發器入口",
}


class RefrigerationCycleModule(BaseAnalysisModule):
    """冷凍循環相關分析。"""

    def __init__(self, unit_converter: UnitConverter, page: ft.Page,
                 refrigeration_service: RefrigerationService) -> None:
        """建立循環與過熱度判讀表單。

參數：
    unit_converter: 共用單位轉換器。
    page: Flet 頁面。
    refrigeration_service: 冷凍 application service。

回傳：
    無。"""
        super().__init__(unit_converter, page, refrigeration_service=refrigeration_service)
        self.refrigeration = refrigeration_service
        self.chart_panel = FigurePanel(height=520, placeholder="執行分析後在 P-h 圖上繪製循環")
        self.cycle_ui = self._build_cycle_ui()
        self.superheat_ui = self._build_superheat_ui()
        self.bind_independent_unit_sync(list(self.all_entries))
        self.on_pressure_type_change(None)

    def get_analysis_definitions(self) -> dict:
        """回報冷凍循環分析。

回傳：
    以分析名稱為鍵的註冊定義。"""
        return {
            "蒸氣壓縮冷凍循環": {
                "analysis_id": "cycle.vapor_compression",
                "ui": self.cycle_ui,
                "calc_func": self.calculate_cycle,
                "result_chart": self.chart_panel,
            },
            "過熱度／過冷度判讀": {
                "analysis_id": "cycle.superheat_subcooling",
                "ui": self.superheat_ui,
                "calc_func": self.calculate_superheat,
            },
        }

    # ======================================================
    # 表單
    # ======================================================
    def _build_cycle_ui(self) -> ft.Container:
        """建立蒸氣壓縮循環表單。

回傳：
    預設隱藏的表單容器。"""
        self.create_text_row("cyc_fluid", "冷媒", "R32", "例如 R32、R410A、R134a、R290")
        rows = [
            ("cyc_te", "蒸發溫度（飽和）", "5", "T", "°C"),
            ("cyc_tc", "冷凝溫度（飽和）", "45", "T", "°C"),
            ("cyc_sh", "過熱度", "5", "DeltaT", "K"),
            ("cyc_sc", "過冷度", "5", "DeltaT", "K"),
            ("cyc_eta", "壓縮機等熵效率", "70", "Eff", "%"),
            ("cyc_capacity", "冷凍能力", "10", "Power", "kW"),
        ]
        controls: list[ft.Control] = [
            self.section_label("冷媒與飽和溫度"),
            self.text_entries["cyc_fluid"]["ui_row"],
        ]
        for index, (key, label, default, prop_code, unit) in enumerate(rows):
            if index == 2:
                controls.append(self.section_label("過熱、過冷與壓縮機"))
            if index == 5:
                controls.append(self.section_label("系統容量"))
            controls.append(self.create_input_row(key, label, default, prop_code, unit)["ui_row"])
        return ft.Container(content=ft.Column(controls, spacing=12), visible=False)

    def _build_superheat_ui(self) -> ft.Container:
        """建立過熱度／過冷度判讀表單（支援錶壓力輸入）。

回傳：
    預設隱藏的表單容器。"""
        self.create_text_row("sh_fluid", "冷媒", "R32", "例如 R32、R410A、R134a")
        self.sh_pressure_type = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value="Gauge", label=ft.Text("錶壓力 (Gauge)")),
                ft.Segment(value="Absolute", label=ft.Text("絕對壓力 (Absolute)")),
            ],
            selected=["Gauge"],
            on_change=self.on_pressure_type_change,
        )
        controls: list[ft.Control] = [
            self.text_entries["sh_fluid"]["ui_row"],
            self.section_label("現場量測"),
            ft.Column([
                ft.Text("壓力類型", size=TOKENS.body, weight=ft.FontWeight.W_500,
                        color=TOKENS.text_primary),
                self.sh_pressure_type,
            ], spacing=6),
            # 預設為錶壓力模式，因此量測壓力以錶壓單位（kPag、psig…）輸入。
            self.create_input_row("sh_p", "量測壓力", "900", GAUGE_PRESSURE, "kPag")["ui_row"],
            self.create_input_row("sh_atm", "大氣壓力（錶壓換算用）", "101.325", "P", "kPa")["ui_row"],
            self.create_input_row("sh_t", "量測管溫", "20", "T", "°C")["ui_row"],
        ]
        return ft.Container(content=ft.Column(controls, spacing=12), visible=False)

    def _pressure_is_gauge(self) -> bool:
        """回傳目前是否為錶壓力模式。

回傳：
    True 表示錶壓力模式。"""
        return "Gauge" in self.sh_pressure_type.selected

    def on_pressure_type_change(self, _event: ft.ControlEvent | None) -> None:
        """切換錶壓力／絕對壓力：量測壓力改用對應語意的單位，並維持相同的實際壓力。

錶壓力模式使用錶壓單位（kPag、psig…）並顯示大氣壓力欄位；絕對壓力模式使用
絕對單位（kPa、psia…）。切換時以「錶壓 + 大氣壓力 = 絕對壓力」換算數值，
讓欄位代表的實際絕對壓力不變；量測壓力空白或無法解析時只切換單位。
大氣壓力無法解析而無法換算時，維持原模式並在大氣壓力欄位提示。

參數：
    _event: Flet 事件；初始化時為 None。

回傳：
    無。"""
        to_gauge = self._pressure_is_gauge()
        entry = self.all_entries["sh_p"]
        target_prop = GAUGE_PRESSURE if to_gauge else "P"
        if entry["prop_code"] != target_prop and not self._convert_pressure_mode(to_gauge):
            self.sh_pressure_type.selected = ["Absolute" if to_gauge else "Gauge"]
        self.all_entries["sh_atm"]["ui_row"].visible = self._pressure_is_gauge()
        try:
            self.superheat_ui.update()
        except RuntimeError:
            pass

    def _convert_pressure_mode(self, to_gauge: bool) -> bool:
        """把量測壓力欄位換成另一種壓力語意，數值換算為相同的實際壓力。

參數：
    to_gauge: True 表示由絕對壓力改為錶壓力。

回傳：
    True 表示已切換；大氣壓力無效而無法換算時回傳 False（不做任何變更）。"""
        entry = self.all_entries["sh_p"]
        atm_entry = self.all_entries["sh_atm"]
        old_unit = entry["unit"].value
        new_unit = ABSOLUTE_TO_GAUGE_UNIT[old_unit] if to_gauge else GAUGE_TO_ABSOLUTE_UNIT[old_unit]
        new_prop = GAUGE_PRESSURE if to_gauge else "P"
        try:
            value = float((entry["val"].value or "").strip())
        except ValueError:
            value = None
        if value is not None:
            try:
                atmospheric_pa = self.read_si("sh_atm")
                if atmospheric_pa <= 0:
                    raise ValueError("大氣壓力必須大於 0。")
            except ValueError:
                atm_entry["val"].error_text = "請輸入有效的大氣壓力，才能在錶壓與絕對壓力間換算"
                return False
            current_si = self.unit_converter.convert_to_si(entry["prop_code"], value, old_unit)
            absolute_pa = current_si if to_gauge else current_si + atmospheric_pa
            new_si = absolute_pa - atmospheric_pa if to_gauge else absolute_pa
            entry["val"].value = f"{self.unit_converter.convert_from_si(new_prop, new_si, new_unit):.7g}"
        atm_entry["val"].error_text = None
        self.retarget_input_row("sh_p", new_prop, new_unit)
        return True

    # ======================================================
    # 計算
    # ======================================================
    def calculate_cycle(self, use_imperial: bool) -> str:
        """求解蒸氣壓縮循環並在 P-h 圖上繪製。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        fluid = self.read_text("cyc_fluid")
        result = self.refrigeration.solve_cycle(RefrigerationCycleRequest(
            fluid=fluid,
            evaporating_temperature_k=self.read_si("cyc_te"),
            condensing_temperature_k=self.read_si("cyc_tc"),
            superheat_k=self.read_si("cyc_sh"),
            subcooling_k=self.read_si("cyc_sc"),
            isentropic_efficiency=self.read_si("cyc_eta"),
            refrigeration_capacity_w=self.read_si("cyc_capacity"),
        ))
        self._plot_cycle(result)

        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section("性能")
        formatter.add_text("冷房 COP", f"{result.cop_cooling:.2f}")
        formatter.add_text("暖房 COP（熱泵）", f"{result.cop_heating:.2f}")
        formatter.add_text("壓縮比", f"{result.pressure_ratio:.2f}")
        formatter.add("冷凍效果 q_L", "H", result.refrigerating_effect_j_kg)
        formatter.add("壓縮功 w", "H", result.compressor_work_j_kg)
        formatter.add("冷凝放熱 q_H", "H", result.heat_rejection_j_kg)
        formatter.section("系統")
        formatter.add("冷媒質量流率", "MassFlow", result.mass_flow_kg_s, 4)
        formatter.add("壓縮機功率", "Power", result.compressor_power_w, 3)
        formatter.add("冷凝器放熱量", "Power", result.heat_rejection_w, 3)
        formatter.add("吸入體積流量", "VolumeFlow", result.suction_volume_flow_m3_s, 2)
        formatter.section("壓力（絕對）")
        formatter.add("蒸發壓力", "P", result.evaporating_pressure_pa)
        formatter.add("冷凝壓力", "P", result.condensing_pressure_pa)
        formatter.section("狀態點溫度")
        for key, label in CYCLE_STATE_LABELS.items():
            formatter.add(label, "T", result.states[key].temperature_k, 1)
        formatter.section("狀態點比焓")
        for key, label in CYCLE_STATE_LABELS.items():
            formatter.add(label, "H", result.states[key].enthalpy_j_kg, 1)
        return formatter.text()

    def _plot_cycle(self, result) -> None:
        """以既有熱力圖繪製函式在 P-h 圖上畫出 1→2→3→4→1 循環。

參數：
    result: VaporCompressionResult。

回傳：
    無。"""
        points = []
        for index, state in enumerate(result.cycle_path):
            is_closing_point = index == len(result.cycle_path) - 1
            points.append({
                "input_type": "P-h",
                "P_Pa": state.pressure_pa,
                "H_J_kg": state.enthalpy_j_kg,
                "label": "" if is_closing_point else state.key,
            })
        generate_thermo_diagram(
            fluid=result.fluid,
            diagram="P-h",
            state_points_si=points,
            unit_converter=self.unit_converter,
            connect_points=True,
            input_mode="Cycle",
            ref_state="Auto",
            target_P_unit="MPa",
            figure=self.chart_panel.figure,
        )
        self.chart_panel.refresh()

    def calculate_superheat(self, use_imperial: bool) -> str:
        """依量測壓力與管溫判讀過熱度或過冷度。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        # 錶壓力只在通道層處理：application／domain 一律收到絕對壓力 Pa。
        pressure = self.read_si("sh_p")
        if self.all_entries["sh_p"]["prop_code"] == GAUGE_PRESSURE:
            pressure = self.unit_converter.gauge_to_absolute_pa(pressure, self.read_si("sh_atm"))
        result = self.refrigeration.check_superheat(SuperheatCheckRequest(
            fluid=self.read_text("sh_fluid"),
            pressure_pa=pressure,
            measured_temperature_k=self.read_si("sh_t"),
        ))
        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section("判讀")
        formatter.add_text("狀態", REGION_LABELS.get(result.region, "兩相（飽和區）"))
        if result.superheat_k is not None:
            formatter.add("過熱度", "DeltaT", result.superheat_k, 1)
        if result.subcooling_k is not None:
            formatter.add("過冷度", "DeltaT", result.subcooling_k, 1)
        formatter.section("飽和溫度")
        formatter.add("露點（飽和蒸氣）", "T", result.dew_point_k, 1)
        formatter.add("泡點（飽和液體）", "T", result.bubble_point_k, 1)
        formatter.add("溫度滑移", "DeltaT", result.temperature_glide_k, 2)
        formatter.add("絕對壓力", "P", result.pressure_pa)
        return formatter.text()
