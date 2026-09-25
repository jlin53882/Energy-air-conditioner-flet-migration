# ui_components/analysis_modules/hvac_evaporator_module.py

import flet as ft
from .base_analysis_module import BaseAnalysisModule
from ..unit.HVACAnalyzer import HVACAnalyzer
from ..unit.UnitConverter import UnitConverter

class EvaporatorModule(BaseAnalysisModule):
    def __init__(self, unit_converter: UnitConverter, page: ft.Page, analyzer: HVACAnalyzer):
        super().__init__(unit_converter, page, analyzer=analyzer)
        
        self.analyzer: HVACAnalyzer = self.services.get("analyzer")
        
        self._build_qe_ui()
        self._setup_unit_sync()
        
    def get_analysis_definitions(self) -> dict:
        return {
            "蒸發器熱交換率 (Qe)": {
                "analysis_id": "evaporator.heat_rate",
                "ui": self.qe_ui_container,
                "calc_func": self.calculate_qe
            }
            # 未來可在此處新增 "蒸發器 LMTD" 等...
        }

    # --- 1. 蒸發器熱交換率 (Qe) 相關 ---
    def _build_qe_ui(self):
        self.create_input_row("qe_h1", "入口焓值 (Inlet Enthalpy, h1)", "200", "H", "kJ/kg")
        self.create_input_row("qe_h2", "出口焓值 (Outlet Enthalpy, h2)", "400", "H", "kJ/kg")
        self.create_input_row("qe_m_dot", "質量流率 (Mass Flow Rate)", "0.1", "MassFlow", "kg/s")

        self.qe_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["qe_h1"]["ui_row"],
                    self.all_entries["qe_h2"]["ui_row"],
                    self.all_entries["qe_m_dot"]["ui_row"],
                ],
                spacing=15,
            ),
            visible=False
        )
        
    def calculate_qe(self, use_imperial: bool) -> str:
        h1_val = self.read_float("qe_h1")
        h1_unit = self.all_entries["qe_h1"]["unit"].value
        h2_val = self.read_float("qe_h2")
        h2_unit = self.all_entries["qe_h2"]["unit"].value
        m_dot_val = self.read_float("qe_m_dot")
        m_dot_unit = self.all_entries["qe_m_dot"]["unit"].value
        h1_si = self.unit_converter.convert_to_si("H", h1_val, h1_unit)
        h2_si = self.unit_converter.convert_to_si("H", h2_val, h2_unit)
        #單位轉換
        h1=h1_si/1000 # j/kg-> kj/kg
        h2=h2_si/1000 # j/kg-> kj/kg
        m_dot_si = self.unit_converter.convert_to_si("MassFlow", m_dot_val, m_dot_unit)
        #函數 內容都是輸出kW
        qe_si_w = self.analyzer.calculate_evaporator_heat_rate(m_dot_si,h1, h2) 
        qe_si_w = qe_si_w*1000 #kW*1000 -> W

        unit = self.unit_converter.imperial_units["Power"] if use_imperial else self.unit_converter.default_units["Power"]
        val = self.unit_converter.convert_from_si("Power", qe_si_w, unit)
        
        return f"蒸發器熱交換率 (Qe): {val:.4f} {unit}"

    # --- 2. 單位同步 ---
    def _setup_unit_sync(self):
        qe_h_sync_group = ["qe_h1", "qe_h2"]
        self.all_entries["qe_h1"]["unit"].on_select = self._create_unit_sync_handler("H", qe_h_sync_group)
        self.all_entries["qe_h2"]["unit"].on_select = self._create_unit_sync_handler("H", qe_h_sync_group)
        
        self.all_entries["qe_m_dot"]["unit"].on_select = self._create_unit_sync_handler("MassFlow", ["qe_m_dot"])