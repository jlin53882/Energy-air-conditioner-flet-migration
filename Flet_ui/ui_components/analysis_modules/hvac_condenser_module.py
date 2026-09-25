# ui_components/analysis_modules/hvac_evaporator_module.py

import flet as ft
from application.models import CondenserExergyRequest
from application.refrigeration import RefrigerationService

from ...ui.theme import TOKENS
from .base_analysis_module import BaseAnalysisModule
from .result_formatting import ResultFormatter
from ..unit.HVACAnalyzer import HVACAnalyzer
from ..unit.UnitConverter import UnitConverter
from ..unit.ThermoStateCalculator import ThermoStateCalculator

# 傳熱邊界溫度的兩種設定：熱直接排到環境（T_b = T0），或指定放熱對象溫度。
BOUNDARY_AMBIENT = "ambient"
BOUNDARY_CUSTOM = "custom"


class CondenserModule(BaseAnalysisModule):
    def __init__(self, unit_converter: UnitConverter, page: ft.Page, analyzer: HVACAnalyzer,
                 state_calculator: ThermoStateCalculator,
                 refrigeration_service: RefrigerationService | None = None):
        super().__init__(unit_converter, page, analyzer=analyzer,
                         state_calculator=state_calculator)
        
        self.analyzer: HVACAnalyzer = self.services.get("analyzer")
        self.state_calculator: ThermoStateCalculator = self.services.get("state_calculator")
        # Exergy 分析需要冷凍 application service；只有新版工作區注入時才註冊，
        # 舊版 AnalysisTab 的分析清單維持不變。
        self.refrigeration = refrigeration_service

        self._build_qc_ui()
        self._setup_unit_sync()
        self.exergy_ui = self._build_exergy_ui() if refrigeration_service is not None else None
        
        
    def get_analysis_definitions(self) -> dict:
        definitions = {
            "冷凝器交換率 (Qcon)": {
                "analysis_id": "condenser.heat_rate",
                "ui": self.qc_ui_container,
                "calc_func": self.calculate_qe
            },
        }
        if self.exergy_ui is not None:
            definitions["冷凝器 Exergy 分析"] = {
                "analysis_id": "condenser.exergy",
                "ui": self.exergy_ui,
                "calc_func": self.calculate_exergy,
            }
        return definitions

    # --- 1. 冷凝器交換率 (Qcon) 相關 ---
    def _build_qc_ui(self):
        self.create_input_row("qc_h1", "入口焓值 (Inlet Enthalpy, h1)", "400", "H", "kJ/kg")
        self.create_input_row("qc_h2", "出口焓值 (Outlet Enthalpy, h2)", "200", "H", "kJ/kg")
        self.create_input_row("qc_m_dot", "質量流率 (Mass Flow Rate)", "0.1", "MassFlow", "kg/s")

        self.qc_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["qc_h1"]["ui_row"],
                    self.all_entries["qc_h2"]["ui_row"],
                    self.all_entries["qc_m_dot"]["ui_row"],
                ],
                spacing=15,
            ),
            visible=False
        )
        
    def calculate_qe(self, use_imperial: bool) -> str:
        h1_val = self.read_float("qc_h1")
        h1_unit = self.all_entries["qc_h1"]["unit"].value
        h2_val = self.read_float("qc_h2")
        h2_unit = self.all_entries["qc_h2"]["unit"].value
        m_dot_val = self.read_float("qc_m_dot")
        m_dot_unit = self.all_entries["qc_m_dot"]["unit"].value
        
        h1_si = self.unit_converter.convert_to_si("H", h1_val, h1_unit)
        h2_si = self.unit_converter.convert_to_si("H", h2_val, h2_unit)
        m_dot_si = self.unit_converter.convert_to_si("MassFlow", m_dot_val, m_dot_unit)
        #單位轉換
        h1=h1_si/1000 # j/kg-> kj/kg
        h2=h2_si/1000 # j/kg-> kj/kg
        #函數 內容都是輸出kW
        qc_si_w = self.analyzer.calculate_condenser_heat_rate(m_dot_si,h1, h2)
        qc_si_w = qc_si_w*1000 #kW*1000 -> W
        
        unit = self.unit_converter.imperial_units["Power"] if use_imperial else self.unit_converter.default_units["Power"]
        val = self.unit_converter.convert_from_si("Power", qc_si_w, unit)
        
        return f"冷凝器交換率 (Qcon): {val:.4f} {unit}"

    # --- 2. 單位同步 ---
    def _setup_unit_sync(self):
        qc_h_sync_group = ["qc_h1", "qc_h2"]
        self.all_entries["qc_h1"]["unit"].on_select = self._create_unit_sync_handler("H", qc_h_sync_group)
        self.all_entries["qc_h2"]["unit"].on_select = self._create_unit_sync_handler("H", qc_h_sync_group)
        
        self.all_entries["qc_m_dot"]["unit"].on_select = self._create_unit_sync_handler("MassFlow", ["qc_m_dot"])    # --- 3. 冷凝器 Exergy 分析 ---
    def _build_exergy_ui(self) -> ft.Container:
        """建立冷凝器 Exergy 分析表單。

回傳：
    預設隱藏的表單容器。"""
        self.create_text_row("cx_fluid", "冷媒", "R134a", "例如 R134a、R32、R410A")
        self.cx_boundary = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value=BOUNDARY_AMBIENT, label=ft.Text("排到環境 (T0)")),
                ft.Segment(value=BOUNDARY_CUSTOM, label=ft.Text("指定放熱對象溫度")),
            ],
            selected=[BOUNDARY_AMBIENT],
            on_change=self.on_boundary_change,
        )
        rows = [
            ("cx_p", "冷凝壓力（絕對）", "1000", "P", "kPa"),
            ("cx_t_in", "冷媒入口溫度", "60", "T", "°C"),
            ("cx_t_out", "冷媒出口溫度", "35", "T", "°C"),
            ("cx_m_dot", "冷媒質量流率", "0.05", "MassFlow", "kg/s"),
            ("cx_t0", "死狀態（環境）溫度 T0", "25", "T", "°C"),
            ("cx_t_b", "放熱對象溫度 T_b", "35", "T", "°C"),
        ]
        for key, label, default, prop_code, unit in rows:
            self.create_input_row(key, label, default, prop_code, unit)
        self.bind_independent_unit_sync([key for key, *_ in rows])
        controls: list[ft.Control] = [
            self.text_entries["cx_fluid"]["ui_row"],
            self.section_label("冷媒狀態（忽略冷凝器壓降）"),
            self.all_entries["cx_p"]["ui_row"],
            self.all_entries["cx_t_in"]["ui_row"],
            self.all_entries["cx_t_out"]["ui_row"],
            self.all_entries["cx_m_dot"]["ui_row"],
            self.section_label("Exergy 分析基準"),
            self.all_entries["cx_t0"]["ui_row"],
            ft.Column([
                ft.Text("傳熱邊界溫度", size=TOKENS.body, weight=ft.FontWeight.W_500,
                        color=TOKENS.text_primary),
                self.cx_boundary,
                ft.Text("熱直接排到環境時邊界溫度等於 T0，熱不帶走 Exergy（η = 0）；熱被回收利用時"
                        "（例如加熱熱水），請指定放熱對象溫度，需介於 T0 與冷媒平均放熱溫度之間。",
                        size=TOKENS.caption, color=TOKENS.text_muted),
            ], spacing=6),
            self.all_entries["cx_t_b"]["ui_row"],
        ]
        self.all_entries["cx_t_b"]["ui_row"].visible = False
        return ft.Container(content=ft.Column(controls, spacing=12), visible=False)

    def _boundary_is_custom(self) -> bool:
        """回傳是否使用指定的放熱對象溫度。

回傳：
    True 表示使用指定溫度；False 表示熱排到環境。"""
        return BOUNDARY_CUSTOM in self.cx_boundary.selected

    def on_boundary_change(self, _event: ft.ControlEvent | None) -> None:
        """切換傳熱邊界設定時，只在指定溫度模式顯示放熱對象溫度欄位。

參數：
    _event: Flet 變更事件；此處不需讀取內容。

回傳：
    無。"""
        self.all_entries["cx_t_b"]["ui_row"].visible = self._boundary_is_custom()
        try:
            self.exergy_ui.update()
        except RuntimeError:
            # Flet 1 在控制項附加到 Page 之前會拒絕更新。
            pass

    def calculate_exergy(self, use_imperial: bool) -> str:
        """計算冷凝器的能量、熵與㶲平衡。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        dead_state_k = self.read_si("cx_t0")
        boundary_k = self.read_si("cx_t_b") if self._boundary_is_custom() else dead_state_k
        result = self.refrigeration.analyze_condenser_exergy(CondenserExergyRequest(
            fluid=self.read_text("cx_fluid"),
            pressure_pa=self.read_si("cx_p"),
            inlet_temperature_k=self.read_si("cx_t_in"),
            outlet_temperature_k=self.read_si("cx_t_out"),
            mass_flow_kg_s=self.read_si("cx_m_dot"),
            dead_state_temperature_k=dead_state_k,
            boundary_temperature_k=boundary_k,
        ))
        balance = result.balance
        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section("Exergy 平衡")
        formatter.add("Exergy 破壞率 X_dest", "Power", balance.exergy_destruction_w, 3)
        formatter.add_text("Exergy 效率 η", f"{balance.exergy_efficiency * 100:.1f} %")
        formatter.add("放熱量 Q_H", "Power", balance.heat_rejection_w, 3)
        formatter.add("冷媒 Exergy 減少量", "Power", balance.exergy_decrease_w, 3)
        formatter.add("熱帶走的 Exergy Ex_Q", "Power", balance.heat_exergy_w, 3)
        formatter.add("熵產生率 S_gen", "EntropyFlow", balance.entropy_generation_w_k, 5)
        formatter.section("溫度")
        formatter.add_text("傳熱邊界", "指定放熱對象溫度" if self._boundary_is_custom() else "排到環境（T_b = T0）")
        formatter.add("傳熱邊界溫度 T_b", "T", result.boundary_temperature_k, 2)
        formatter.add("冷媒平均放熱溫度", "T", balance.mean_heat_rejection_temperature_k, 2)
        formatter.add("露點（飽和蒸氣）", "T", result.dew_point_k, 2)
        formatter.add("泡點（飽和液體）", "T", result.bubble_point_k, 2)
        formatter.add("死狀態溫度 T0", "T", result.dead_state_temperature_k, 2)
        formatter.section("冷媒狀態")
        formatter.add("入口比焓 h1", "H", result.inlet.enthalpy_j_kg, 2)
        formatter.add("出口比焓 h2", "H", result.outlet.enthalpy_j_kg, 2)
        formatter.add("入口比熵 s1", "S", result.inlet.entropy_j_kgk, 4)
        formatter.add("出口比熵 s2", "S", result.outlet.entropy_j_kgk, 4)
        return formatter.text()
