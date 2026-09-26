# ui_components/analysis_modules/hvac_evaporator_module.py

from collections.abc import Callable

import flet as ft
from application.models import CondenserExergyRequest
from application.refrigeration import RefrigerationService
from domain.refrigeration import coolant_mean_temperature_k

from ...ui.theme import TOKENS
from .base_analysis_module import BaseAnalysisModule
from .result_formatting import ResultFormatter
from ..unit.HVACAnalyzer import HVACAnalyzer
from ..unit.UnitConverter import UnitConverter
from ..unit.ThermoStateCalculator import ThermoStateCalculator

# 等效傳熱邊界溫度的兩種設定：分析邊界涵蓋到整體排熱至環境（T_b = T0），
# 或指定熱量穿越所選控制邊界時的等效傳熱邊界溫度。
BOUNDARY_AMBIENT = "ambient"
BOUNDARY_CUSTOM = "custom"
# 指定模式下 T_b 的來源：直接輸入，或由冷卻介質進出口溫度計算熱力學平均溫度。
BOUNDARY_SOURCE_DIRECT = "direct"
BOUNDARY_SOURCE_COOLANT = "coolant"


class CondenserModule(BaseAnalysisModule):
    def __init__(self, unit_converter: UnitConverter, page: ft.Page, analyzer: HVACAnalyzer,
                 state_calculator: ThermoStateCalculator,
                 refrigeration_service: RefrigerationService,
                 pressure_from_altitude: Callable[[float], float] | None = None):
        super().__init__(unit_converter, page, analyzer=analyzer,
                         state_calculator=state_calculator,
                         pressure_from_altitude=pressure_from_altitude)
        
        self.analyzer: HVACAnalyzer = self.services.get("analyzer")
        self.state_calculator: ThermoStateCalculator = self.services.get("state_calculator")
        # Exergy 分析使用冷凍 application service。
        self.refrigeration = refrigeration_service

        self._build_qc_ui()
        self._setup_unit_sync()
        self.exergy_ui = self._build_exergy_ui()
        self.last_exergy_result = None
        
        
    def get_analysis_definitions(self) -> dict:
        return {
            "冷凝器交換率 (Qcon)": {
                "analysis_id": "condenser.heat_rate",
                "ui": self.qc_ui_container,
                "calc_func": self.calculate_qe
            },
            "冷凝器 Exergy 分析": {
                "analysis_id": "condenser.exergy",
                "ui": self.exergy_ui,
                "calc_func": self.calculate_exergy,
                "state_points": lambda: (
                    (self.last_exergy_result.inlet, self.last_exergy_result.outlet)
                    if self.last_exergy_result else ()
                ),
            },
        }

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
        reference_state_row, self.cx_ref_state = self.create_reference_state_row()
        self.cx_pressure_type = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value="Gauge", label=ft.Text("錶壓力 (Gauge)")),
                ft.Segment(value="Absolute", label=ft.Text("絕對壓力 (Absolute)")),
            ],
            selected=["Absolute"],
            on_change=self.on_pressure_type_change,
        )
        self.cx_boundary = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value=BOUNDARY_AMBIENT, label=ft.Text("整體排熱至環境")),
                ft.Segment(value=BOUNDARY_CUSTOM, label=ft.Text("指定等效傳熱邊界溫度")),
            ],
            selected=[BOUNDARY_AMBIENT],
            # 不顯示勾選圖示，讓選項文字在窄欄中不必折成多行；選取狀態仍以底色表示。
            show_selected_icon=False,
            on_change=self.on_boundary_change,
        )
        self.cx_boundary_source = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value=BOUNDARY_SOURCE_DIRECT, label=ft.Text("直接輸入 T_b")),
                ft.Segment(value=BOUNDARY_SOURCE_COOLANT, label=ft.Text("由冷卻介質溫度計算")),
            ],
            selected=[BOUNDARY_SOURCE_DIRECT],
            show_selected_icon=False,
            on_change=self.on_boundary_change,
            visible=False,
        )
        # 說明文字預設收起，點標題右側的「?」才展開，避免表單過長。
        self.cx_boundary_help_button = ft.IconButton(
            ft.Icons.HELP_OUTLINE,
            icon_size=18,
            icon_color=TOKENS.text_secondary,
            tooltip="什麼是等效傳熱邊界溫度？",
            on_click=self.toggle_boundary_help,
        )
        self.cx_boundary_help = ft.Container(
            content=ft.Column([
                ft.Text("T_b 是熱量穿越所選控制邊界 (control boundary) 時的等效溫度，不一定等於外氣或"
                        "熱水的 bulk temperature。", size=TOKENS.caption, color=TOKENS.text_secondary),
                ft.Text("• 整體排熱至環境：分析邊界涵蓋冷凝器直到最終向環境排熱的整體系統，T_b = T0，"
                        "熱不帶走 Exergy（η = 0）。", size=TOKENS.caption, color=TOKENS.text_secondary),
                ft.Text("• 指定等效傳熱邊界溫度：只分析冷凝器本體時，輸入該邊界對應的等效溫度，"
                        "需介於 T0 與冷媒平均放熱溫度之間。", size=TOKENS.caption, color=TOKENS.text_secondary),
                ft.Text("• 由冷卻介質溫度計算：輸入冷卻水、熱回收熱水或空冷空氣的進出口溫度，以"
                        "T_b = (T_出 − T_入) / ln(T_出 / T_入)（絕對溫度）計算，此時 η 即熱交換器的"
                        " Exergy 效率。適用於無相變的冷卻介質，不適用於蒸發式冷凝器。",
                        size=TOKENS.caption, color=TOKENS.text_secondary),
            ], spacing=4),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor=TOKENS.surface_variant,
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
            visible=False,
        )
        rows = [
            ("cx_p", "冷凝壓力", "1000", "P", "kPa"),
            ("cx_t_in", "冷媒入口溫度", "60", "T", "°C"),
            ("cx_t_out", "冷媒出口溫度", "35", "T", "°C"),
            ("cx_m_dot", "冷媒質量流率", "0.05", "MassFlow", "kg/s"),
            ("cx_t0", "死狀態（環境）溫度 T0", "25", "T", "°C"),
            ("cx_t_b", "等效傳熱邊界溫度 T_b", "35", "T", "°C"),
            ("cx_c_in", "冷卻介質入口溫度", "30", "T", "°C"),
            ("cx_c_out", "冷卻介質出口溫度", "35", "T", "°C"),
        ]
        for key, label, default, prop_code, unit in rows:
            self.create_input_row(key, label, default, prop_code, unit)
        self.bind_independent_unit_sync([key for key, *_ in rows])
        atmosphere_rows = self.create_atmosphere_rows("cx_alt", "cx_atm")
        controls: list[ft.Control] = [
            self.text_entries["cx_fluid"]["ui_row"],
            reference_state_row,
            self.section_label("冷媒狀態（忽略冷凝器壓降）"),
            ft.Column([
                ft.Text("壓力類型", size=TOKENS.body, weight=ft.FontWeight.W_500,
                        color=TOKENS.text_primary),
                self.cx_pressure_type,
            ], spacing=6),
            *atmosphere_rows,
            self.all_entries["cx_p"]["ui_row"],
            self.all_entries["cx_t_in"]["ui_row"],
            self.all_entries["cx_t_out"]["ui_row"],
            self.all_entries["cx_m_dot"]["ui_row"],
            self.section_label("Exergy 分析基準"),
            self.all_entries["cx_t0"]["ui_row"],
            ft.Column([
                ft.Row([
                    ft.Text("等效傳熱邊界溫度", size=TOKENS.body, weight=ft.FontWeight.W_500,
                            color=TOKENS.text_primary, expand=True),
                    self.cx_boundary_help_button,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.cx_boundary_help,
                self.cx_boundary,
            ], spacing=6),
            self.cx_boundary_source,
            self.all_entries["cx_t_b"]["ui_row"],
            self.all_entries["cx_c_in"]["ui_row"],
            self.all_entries["cx_c_out"]["ui_row"],
        ]
        self._refresh_boundary_rows()
        container = ft.Container(content=ft.Column(controls, spacing=12), visible=False)
        self.apply_pressure_basis(self.cx_pressure_type, ["cx_p"], "cx_alt", "cx_atm")
        return container

    def on_pressure_type_change(self, _event: ft.ControlEvent | None) -> None:
        """切換冷凝壓力的錶壓力／絕對壓力，數值換算為同一個實際壓力。

錶壓力模式使用錶壓單位並顯示海拔與大氣壓力欄位；大氣壓力無法解析時維持原模式並
提示（換算規則見 ``BaseAnalysisModule.switch_pressure_basis``）。

參數：
    _event: Flet 變更事件；此處不需讀取內容。

回傳：
    無。"""
        self.apply_pressure_basis(self.cx_pressure_type, ["cx_p"], "cx_alt", "cx_atm", self.exergy_ui)

    def toggle_boundary_help(self, _event: ft.ControlEvent | None) -> None:
        """展開或收起等效傳熱邊界溫度的說明。

參數：
    _event: Flet 點擊事件；此處不需讀取內容。

回傳：
    無。"""
        self.cx_boundary_help.visible = not self.cx_boundary_help.visible
        try:
            self.cx_boundary_help.update()
        except RuntimeError:
            # Flet 1 在控制項附加到 Page 之前會拒絕更新。
            pass

    def _boundary_is_custom(self) -> bool:
        """回傳是否使用指定的等效傳熱邊界溫度。

回傳：
    True 表示使用指定溫度；False 表示分析邊界涵蓋到整體排熱至環境（T_b = T0）。"""
        return BOUNDARY_CUSTOM in self.cx_boundary.selected

    def _boundary_from_coolant(self) -> bool:
        """回傳指定模式下是否由冷卻介質進出口溫度計算 T_b。

回傳：
    True 表示由冷卻介質溫度計算；False 表示直接輸入 T_b。"""
        return BOUNDARY_SOURCE_COOLANT in self.cx_boundary_source.selected

    def _refresh_boundary_rows(self) -> None:
        """依傳熱邊界設定顯示對應的欄位：指定模式才顯示來源選項，再依來源顯示 T_b 或冷卻介質溫度。

回傳：
    無。"""
        custom = self._boundary_is_custom()
        from_coolant = custom and self._boundary_from_coolant()
        self.cx_boundary_source.visible = custom
        self.all_entries["cx_t_b"]["ui_row"].visible = custom and not from_coolant
        self.all_entries["cx_c_in"]["ui_row"].visible = from_coolant
        self.all_entries["cx_c_out"]["ui_row"].visible = from_coolant

    def on_boundary_change(self, _event: ft.ControlEvent | None) -> None:
        """切換傳熱邊界設定或 T_b 來源時，更新顯示的欄位。

參數：
    _event: Flet 變更事件；此處不需讀取內容。

回傳：
    無。"""
        self._refresh_boundary_rows()
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
        self.last_exergy_result = None
        dead_state_k = self.read_si("cx_t0")
        from_coolant = self._boundary_is_custom() and self._boundary_from_coolant()
        if not self._boundary_is_custom():
            boundary_k, boundary_label = dead_state_k, "整體排熱至環境（T_b = T0）"
        elif from_coolant:
            boundary_k = coolant_mean_temperature_k(self.read_si("cx_c_in"), self.read_si("cx_c_out"))
            boundary_label = "由冷卻介質溫度計算"
        else:
            boundary_k, boundary_label = self.read_si("cx_t_b"), "指定等效傳熱邊界溫度"
        result = self.refrigeration.analyze_condenser_exergy(CondenserExergyRequest(
            fluid=self.read_text("cx_fluid"),
            pressure_pa=self.read_absolute_pressure_pa("cx_p", "cx_atm"),
            inlet_temperature_k=self.read_si("cx_t_in"),
            outlet_temperature_k=self.read_si("cx_t_out"),
            mass_flow_kg_s=self.read_si("cx_m_dot"),
            dead_state_temperature_k=dead_state_k,
            boundary_temperature_k=boundary_k,
            reference_state=self.cx_ref_state.value,
        ))
        self.last_exergy_result = result
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
        formatter.add_text("傳熱邊界", boundary_label)
        formatter.add("等效傳熱邊界溫度 T_b", "T", result.boundary_temperature_k, 2)
        if from_coolant:
            formatter.add("冷卻介質入口溫度", "T", self.read_si("cx_c_in"), 2)
            formatter.add("冷卻介質出口溫度", "T", self.read_si("cx_c_out"), 2)
        formatter.add("冷媒平均放熱溫度", "T", balance.mean_heat_rejection_temperature_k, 2)
        formatter.add("露點（飽和蒸氣）", "T", result.dew_point_k, 2)
        formatter.add("泡點（飽和液體）", "T", result.bubble_point_k, 2)
        formatter.add("死狀態溫度 T0", "T", result.dead_state_temperature_k, 2)
        formatter.section("冷媒狀態")
        formatter.add("冷凝壓力（絕對）", "P", result.pressure_pa, 2)
        formatter.add("入口比焓 h1", "H", result.inlet.enthalpy_j_kg, 2)
        formatter.add("出口比焓 h2", "H", result.outlet.enthalpy_j_kg, 2)
        formatter.add("入口比熵 s1", "S", result.inlet.entropy_j_kgk, 4)
        formatter.add("出口比熵 s2", "S", result.outlet.entropy_j_kgk, 4)
        return formatter.text()
