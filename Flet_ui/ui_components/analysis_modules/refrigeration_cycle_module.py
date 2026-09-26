"""冷凍循環分析：蒸氣壓縮循環（含 P-h 圖）。

計算委派給 `RefrigerationService`；P-h 圖沿用既有 `generate_thermo_diagram`，
並使用循環結果攜帶的 reference-state policy（求解時實際使用的那一個）繪製，
不在繪圖時重新解析。現場過熱度／過冷度判讀已移到獨立工具
（`superheat_subcooling_module.py`）。
"""

from __future__ import annotations

import flet as ft

from application.models import RefrigerationCycleRequest
from application.refrigeration import RefrigerationService

from ...ui.components.figure_panel import FigurePanel
from ..unit.UnitConverter import UnitConverter
from ..unit.thermo_draw.coolprop_utils import generate_thermo_diagram
from .base_analysis_module import BaseAnalysisModule
from .result_formatting import ResultFormatter

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
        """建立蒸氣壓縮循環表單。

參數：
    unit_converter: 共用單位轉換器。
    page: Flet 頁面。
    refrigeration_service: 冷凍 application service。

回傳：
    無。"""
        super().__init__(unit_converter, page, refrigeration_service=refrigeration_service)
        self.refrigeration = refrigeration_service
        self.last_result = None
        self.chart_panel = FigurePanel(height=520, placeholder="執行分析後在 P-h 圖上繪製循環")
        self.cycle_ui = self._build_cycle_ui()
        self.bind_independent_unit_sync(list(self.all_entries))

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
                "state_points": lambda: tuple(self.last_result.states.values()) if self.last_result else (),
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
        reference_state_row, self.cyc_ref_state = self.create_reference_state_row()
        controls: list[ft.Control] = [
            self.section_label("冷媒與飽和溫度"),
            self.text_entries["cyc_fluid"]["ui_row"],
            reference_state_row,
        ]
        for index, (key, label, default, prop_code, unit) in enumerate(rows):
            if index == 2:
                controls.append(self.section_label("過熱、過冷與壓縮機"))
            if index == 5:
                controls.append(self.section_label("系統容量"))
            controls.append(self.create_input_row(key, label, default, prop_code, unit)["ui_row"])
        return ft.Container(content=ft.Column(controls, spacing=12), visible=False)

    # ======================================================
    # 計算
    # ======================================================
    def calculate_cycle(self, use_imperial: bool) -> str:
        """求解蒸氣壓縮循環並在 P-h 圖上繪製。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        self.last_result = None
        fluid = self.read_text("cyc_fluid")
        result = self.refrigeration.solve_cycle(RefrigerationCycleRequest(
            fluid=fluid,
            evaporating_temperature_k=self.read_si("cyc_te"),
            condensing_temperature_k=self.read_si("cyc_tc"),
            superheat_k=self.read_si("cyc_sh"),
            subcooling_k=self.read_si("cyc_sc"),
            isentropic_efficiency=self.read_si("cyc_eta"),
            refrigeration_capacity_w=self.read_si("cyc_capacity"),
            reference_state=self.cyc_ref_state.value,
        ))
        self.last_result = result
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
            # 與求解使用同一個已解析的 policy，確保圖上焓值與結果一致。
            ref_state=result.reference_state,
            target_P_unit="MPa",
            figure=self.chart_panel.figure,
        )
        self.chart_panel.refresh()
