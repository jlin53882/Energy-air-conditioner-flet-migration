# ui_components/analysis_modules/hvac_compressor_module.py
# (已擴充 - 包含所有壓縮機相關計算)

# --- 導入 UI 框架 ---
import flet as ft 

# --- 導入核心服務與基底類別 ---
# 導入所有分析模組的基礎類別，提供通用結構與服務容器
from .base_analysis_module import BaseAnalysisModule 
from ...ui.theme import TOKENS, style_text_field
# 導入 HVAC 系統級分析器，處理計算邏輯
from ..unit.HVACAnalyzer import HVACAnalyzer
# 導入單位轉換器，處理國際單位制與英制之間的轉換
from ..unit.UnitConverter import UnitConverter
# 導入熱力學狀態計算器，用於計算冷媒的熱力學屬性
from ..unit.ThermoStateCalculator import ThermoStateCalculator
from application.analysis_services import CompressionRatioService
from application.models import CompressionRatioRequest
from application.property_queries import PropertyQueryService
from domain.thermodynamics.fluid_policy import resolve_reference_state_policy

# CompressorModule 繼承自 BaseAnalysisModule，專門處理壓縮機相關的 UI 與邏輯
class CompressorModule(BaseAnalysisModule):
    
    # 構造函數：使用「依賴注入 (Dependency Injection)」接收所有必要的服務物件
    def __init__(self, 
                 unit_converter: UnitConverter,      # 接收單位轉換服務
                 page: ft.Page,                      # 接收 Flet 頁面物件
                 analyzer: HVACAnalyzer,             # 接收 HVAC 分析器服務
                 state_calculator: ThermoStateCalculator,
                 compression_ratio_service: CompressionRatioService | None = None,
                 property_query_service: PropertyQueryService | None = None): # 接收熱力學狀態計算服務
        
        # 呼叫基類的構造函數，將所有服務傳入，通常會將它們儲存在 self.services 字典中
        super().__init__(unit_converter, page, analyzer=analyzer,state_calculator=state_calculator) 
        
        
        # 從基類的服務容器中取出並儲存 HVAC 分析器 (analyzer)
        self.analyzer: HVACAnalyzer = self.services.get("analyzer")
        
        # 從服務容器中取出並儲存熱力學狀態計算器 (state_calculator)
        # 這樣就能在類別的其他方法中，方便地調用其熱力學計算功能
        self.state_calculator: ThermoStateCalculator = self.services.get("state_calculator")
        self.compression_ratio_service = compression_ratio_service or CompressionRatioService()
        self.reference_state_provider = property_query_service
        
        # --- 建立此模組所需的所有 UI 元件 (每個方法負責一個計算區塊) ---
        # 透過多個私有方法建立 UI，確保程式碼的模組化與可維護性
        self._build_cr_ui()              # 建立壓縮比 （壓縮比） 相關 UI
        self._build_ex_dest_ui()         # 建立火用破壞 相關 UI
        self._build_ex_eff_loss_ui()     # 建立火用效率損失 相關 UI
        self._build_ex_eff_ratio_ui()    # 建立火用效率比 相關 UI
        self._build_isen_eff_ui()        # 建立等熵效率 相關 UI
        self._build_ref_cap_ui()         # 建立製冷能力 (Refrigeration Capacity) 相關 UI
        self._build_rev_work_ui()        # 建立可逆功 （可逆功） 相關 UI
        self._build_vol_eff_ui()         # 建立容積效率 (Volumetric Efficiency) 相關 UI
        self._build_work_ui()            # 建立壓縮功 (Work) 相關 UI
        self._build_work_q_ui()          # 建立功與熱量 （功與熱量） 相關 UI
        self._build_comp_example_ui()    # 建立一個綜合計算範例的 UI
        
        # --- 建立單位同步機制 ---
        # 設置 UI 輸入欄位和輸出結果與 UnitConverter 之間的單位同步邏輯
        self._setup_unit_sync()
        
        # --- 初始化 CR UI 的狀態 ---
        # 確保模組加載後，壓力輸入的類型（如表壓/絕對壓力）處於一個預設的穩定狀態
        self.on_pressure_type_change(None)

    def get_analysis_definitions(self) -> dict:
        """
        回報此模組提供的 *所有* 功能。
        AnalysisTab 將會自動讀取這個字典來建立下拉選單。
        """
        return {
            "壓縮比 (CR)": {
                "analysis_id": "compressor.compression_ratio",
                "ui": self.cr_ui_container,
                "calc_func": self.calculate_cr
            },
            "壓縮機功 (W_in)": {
                "analysis_id": "compressor.work",
                "ui": self.work_ui_container,
                "calc_func": self.calculate_work
            },
            "壓縮機等熵效率 (η_isen)": {
                "analysis_id": "compressor.isentropic_efficiency",
                "ui": self.isen_eff_ui_container,
                "calc_func": self.calculate_isen_eff
            },
            "系統冷凍能力 (Q_L_dot)蒸發器": {
                "analysis_id": "compressor.refrigeration_capacity",
                "ui": self.ref_cap_ui_container,
                "calc_func": self.calculate_ref_cap
            },
            "壓縮機功 (考慮熱傳 Q_dot)": {
                "analysis_id": "compressor.work_heat_transfer",
                "ui": self.work_q_ui_container,
                "calc_func": self.calculate_work_q
            },
            "壓縮機可逆功 (W_rev_dot)": {
                "analysis_id": "compressor.reversible_work",
                "ui": self.rev_work_ui_container,
                "calc_func": self.calculate_rev_work
            },
            "壓縮機㶲破壞 Ex_dest": {
                "analysis_id": "compressor.exergy_destruction",
                "ui": self.ex_dest_ui_container,
                "calc_func": self.calculate_ex_dest
            },
            "壓縮機容積效率 (η_vol)": {
                "analysis_id": "compressor.volumetric_efficiency",
                "ui": self.vol_eff_ui_container,
                "calc_func": self.calculate_vol_eff
            },
            "壓縮機效能損失 (實際 W_in 損失)": {
                "analysis_id": "compressor.exergy_efficiency_loss",
                "ui": self.ex_eff_loss_ui_container,
                "calc_func": self.calculate_ex_eff_loss
            },
            "壓縮機㶲效率 (η_ex)": {
                "analysis_id": "compressor.exergy_efficiency_ratio",
                "ui": self.ex_eff_ratio_ui_container,
                "calc_func": self.calculate_ex_eff_ratio
            },
            "壓縮機綜合分析範例": {
                "analysis_id": "compressor.combined_example",
                "ui": self.comp_example_ui_container,
                "calc_func": self.calculate_comp_example
            },


            # 您未來可以繼續在這裡新增...
        }

    # --- 1. 壓縮比 (CR) [已存在] ---
    def _build_cr_ui(self):
        self.cr_pressure_type_toggle = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value="Gauge", label=ft.Text("錶壓力 (Gauge)")),
                ft.Segment(value="Absolute", label=ft.Text("絕對壓力 (Absolute)")),
            ],
            selected=["Absolute"],
            on_change=self.on_pressure_type_change,
        )
        self.create_input_row("cr_atm_p", "大氣壓力 (Atm. Pressure)", "101.325", "P", "kPa")
        self.create_input_row("cr_pe", "入口壓力 (Inlet Pressor)", "", "P", "MPa")
        self.create_input_row("cr_pc", "出口壓力 (Outlet Pressor)", "", "P", "MPa")
        
        self.cr_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Column(
                        [
                            ft.Text("壓力類型", size=TOKENS.body, weight=ft.FontWeight.W_500,
                                    color=TOKENS.text_primary),
                            self.cr_pressure_type_toggle,
                        ],
                        spacing=6,
                    ),
                    self.all_entries["cr_atm_p"]["ui_row"],
                    self.all_entries["cr_pe"]["ui_row"],
                    self.all_entries["cr_pc"]["ui_row"],
                ], spacing=15,
            ), visible=False
        )

    def calculate_cr(self, use_imperial: bool) -> str:
        pe_val = float(self.all_entries["cr_pe"]["val"].value)
        pe_unit = self.all_entries["cr_pe"]["unit"].value
        pc_val = float(self.all_entries["cr_pc"]["val"].value)
        pc_unit = self.all_entries["cr_pc"]["unit"].value
        
        pe_pa = self.unit_converter.convert_to_si("P", pe_val, pe_unit) 
        pc_pa = self.unit_converter.convert_to_si("P", pc_val, pc_unit)

        atm_p_si = 0.0
        if "Gauge" in self.cr_pressure_type_toggle.selected:
            atm_p_val = float(self.all_entries["cr_atm_p"]["val"].value)
            atm_p_unit = self.all_entries["cr_atm_p"]["unit"].value
            atm_p_si = self.unit_converter.convert_to_si("P", atm_p_val, atm_p_unit)
        
        pe_abs_pa = pe_pa + atm_p_si
        pc_abs_pa = pc_pa + atm_p_si
        
        cr = self.compression_ratio_service.calculate(
            CompressionRatioRequest(pe_abs_pa, pc_abs_pa)
        )
        return f"壓縮比 (CR): {cr:.4f} (無單位)"
    
    def on_pressure_type_change(self, e):
        is_gauge = "Gauge" in self.cr_pressure_type_toggle.selected
        self.all_entries["cr_atm_p"]["ui_row"].visible = is_gauge
        try:
            self.cr_ui_container.update()
        except RuntimeError:
            # Flet 1 在控制項附加到 Page 之前會拒絕更新。
            pass

    # --- 2. 壓縮機功 (W_in) [修正版] ---
    def _build_work_ui(self):
        self.create_input_row("win_h1", "入口焓值 (Inlet Enthalpy)", "400", "H", "kJ/kg")
        self.create_input_row("win_h2", "出口焓值 (Outlet Enthalpy)", "450", "H", "kJ/kg")
        self.create_input_row("win_m_dot", "質量流率 (Mass Flow Rate)", "0.1", "MassFlow", "kg/s")

        self.work_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["win_h1"]["ui_row"],
                    self.all_entries["win_h2"]["ui_row"],
                    self.all_entries["win_m_dot"]["ui_row"],
                ], spacing=15,
            ), visible=False
        )

    def calculate_work(self, use_imperial: bool) -> str:
        # 1. 取得 UI 值
        h1_val = float(self.all_entries["win_h1"]["val"].value)
        h1_unit = self.all_entries["win_h1"]["unit"].value
        h2_val = float(self.all_entries["win_h2"]["val"].value)
        h2_unit = self.all_entries["win_h2"]["unit"].value
        m_dot_val = float(self.all_entries["win_m_dot"]["val"].value)
        m_dot_unit = self.all_entries["win_m_dot"]["unit"].value
        
        # 2. 轉換為 SI (J/kg, kg/s)
        h1_si = self.unit_converter.convert_to_si("H", h1_val, h1_unit)
        h2_si = self.unit_converter.convert_to_si("H", h2_val, h2_unit)
        m_dot_si = self.unit_converter.convert_to_si("MassFlow", m_dot_val, m_dot_unit)
        
        # 3. [BUG FIX] 準備呼叫 Analyzer 的參數 (Analyzer 期望 kJ/kg)
        h1_kj = h1_si / 1000.0
        h2_kj = h2_si / 1000.0
        
        # 4. 呼叫 Analyzer (返回 kW)
        power_kw = self.analyzer.calculate_compressor_work(m_dot_si, h1_kj, h2_kj)
        
        # 5. 將結果 (kW) 轉回 SI (W) 以便 formatter 處理
        power_si_w = power_kw * 1000.0

        # 6. 格式化輸出
        unit = self.unit_converter.imperial_units["Power"] if use_imperial else self.unit_converter.default_units["Power"]
        val = self.unit_converter.convert_from_si("Power", power_si_w, unit)
        
        return f"壓縮機功 (W_in): {val:.4f} {unit}"

    # --- 3. 壓縮機等熵效率 [新] ---
    def _build_isen_eff_ui(self):
        self.create_input_row("isen_h1", "入口焓值 (Inlet Enthalpy, h1)", "400", "H", "kJ/kg")
        self.create_input_row("isen_h2", "實際出口焓值 (Actual Outlet Enthalpy, h2)", "450", "H", "kJ/kg")
        self.create_input_row("isen_h2s", "等熵出口焓值 (Isentropic Outlet Enthalpy, h2s)", "430", "H", "kJ/kg")

        self.isen_eff_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["isen_h1"]["ui_row"],
                    self.all_entries["isen_h2"]["ui_row"],
                    self.all_entries["isen_h2s"]["ui_row"],
                ], spacing=15,
            ), visible=False
        )
        
    def calculate_isen_eff(self, use_imperial: bool) -> str:
        h1_val = float(self.all_entries["isen_h1"]["val"].value)
        h1_unit = self.all_entries["isen_h1"]["unit"].value
        h2_val = float(self.all_entries["isen_h2"]["val"].value)
        h2_unit = self.all_entries["isen_h2"]["unit"].value
        h2s_val = float(self.all_entries["isen_h2s"]["val"].value)
        h2s_unit = self.all_entries["isen_h2s"]["unit"].value
        
        # 轉換為 SI (J/kg)。
        h1_si = self.unit_converter.convert_to_si("H", h1_val, h1_unit)
        h2_si = self.unit_converter.convert_to_si("H", h2_val, h2_unit)
        h2s_si = self.unit_converter.convert_to_si("H", h2s_val, h2s_unit)
        
        # 由於是比率，J/kg 或 kJ/kg 皆可，Analyzer 函式會處理
        efficiency = self.analyzer.calculate_isentropic_efficiency(h1_si, h2_si, h2s_si)
        
        return f"等熵效率 (Isentropic Efficiency): {efficiency * 100:.2f} %"

    # --- 4. 冷凍能力 (系統) [新] ---
    def _build_ref_cap_ui(self):
        # 根據公式 (3.10) 建立 5 個輸入
        self.create_input_row("ref_v_dot", "壓縮機的容積排氣量 (Volume_dot)", "0.01", "VolumeFlow", "m^3/s")
        # 使用 "Eff" (效率) 作為無單位效率的代理，單位是 %，會自動轉為 0-1
        self.create_input_row("ref_eta_vol", "壓縮機容積效率 (η_vol)", "80", "Eff", "%")
        self.create_input_row("ref_rho1", "冷媒在壓縮機入口處的密度 (ρ1)", "1.2", "D", "kg/m^3")
        self.create_input_row("ref_h1", "蒸發器出口焓值 (Evap Outlet, h1)", "400", "H", "kJ/kg")
        self.create_input_row("ref_h4", "蒸發器入口焓值 (Evap Inlet, h4)", "250", "H", "kJ/kg")

        self.ref_cap_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["ref_v_dot"]["ui_row"],
                    self.all_entries["ref_eta_vol"]["ui_row"],
                    self.all_entries["ref_rho1"]["ui_row"],
                    self.all_entries["ref_h1"]["ui_row"],
                    self.all_entries["ref_h4"]["ui_row"],
                ], spacing=15,
            ), visible=False
        )

    def calculate_ref_cap(self, use_imperial: bool) -> str:
        # 1. 讀取所有 5 個 UI 的值
        v_dot_val = float(self.all_entries["ref_v_dot"]["val"].value)
        v_dot_unit = self.all_entries["ref_v_dot"]["unit"].value
        
        eta_vol_val = float(self.all_entries["ref_eta_vol"]["val"].value)
        eta_vol_unit = self.all_entries["ref_eta_vol"]["unit"].value
        
        rho1_val = float(self.all_entries["ref_rho1"]["val"].value)
        rho1_unit = self.all_entries["ref_rho1"]["unit"].value
        
        h1_val = float(self.all_entries["ref_h1"]["val"].value)
        h1_unit = self.all_entries["ref_h1"]["unit"].value
        
        h4_val = float(self.all_entries["ref_h4"]["val"].value)
        h4_unit = self.all_entries["ref_h4"]["unit"].value
        
        # 2. 將所有值轉換為 Analyzer 函式所需的單位
        # Analyzer 期望: m^3/s, 0-1 ratio, kg/m^3, kJ/kg, kJ/kg
        
        v_dot_si = self.unit_converter.convert_to_si("VolumeFlow", v_dot_val, v_dot_unit) # m^3/s
        eta_vol_si = self.unit_converter.convert_to_si("Eff", eta_vol_val, eta_vol_unit)    # 0-1 比率（例如 80% -> 0.8）
        rho1_si = self.unit_converter.convert_to_si("D", rho1_val, rho1_unit)       # kg/m^3
        h1_si_j = self.unit_converter.convert_to_si("H", h1_val, h1_unit)                 # J/kg
        h4_si_j = self.unit_converter.convert_to_si("H", h4_val, h4_unit)                 # J/kg
        
        # 3. 準備 Analyzer 參數 (它期望 kJ/kg)
        h1_kj = h1_si_j / 1000.0
        h4_kj = h4_si_j / 1000.0

        
        # 4. 呼叫新的 Analyzer 函式 (返回 kW)
        power_kw = self.analyzer.calculate_refrigeration_capacity(
            Vdot_displacement_rate=v_dot_si,
            eta_vol_efficiency=eta_vol_si,
            rho1_inlet_density=rho1_si,
            h1_evaporator_exit_enthalpy=h1_kj,
            h4_evaporator_inlet_enthalpy=h4_kj
        )
        
        # 5. 轉回 SI (W) 以便 formatter 處理
        power_si_w = power_kw * 1000.0
        
        # 6. 格式化輸出
        unit = self.unit_converter.imperial_units["Power"] if use_imperial else self.unit_converter.default_units["Power"]
        val = self.unit_converter.convert_from_si("Power", power_si_w, unit)
        
        return f"冷凍能力 (Refrigeration Capacity): {val:.4f} {unit}"

    # --- 5. 壓縮機功 (含熱傳) [新] ---
    def _build_work_q_ui(self):
        self.create_input_row("wq_m_dot", "質量流率 (Mass Flow Rate)", "0.1", "MassFlow", "kg/s")
        self.create_input_row("wq_h1", "入口焓值 (Inlet Enthalpy, h1)", "400", "H", "kJ/kg")
        self.create_input_row("wq_h2", "出口焓值 (Outlet Enthalpy, h2)", "450", "H", "kJ/kg")
        self.create_input_row("wq_q_out", "傳出熱量 (Heat Out, Q_out)", "2", "Power", "kW")

        self.work_q_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["wq_m_dot"]["ui_row"],
                    self.all_entries["wq_h1"]["ui_row"],
                    self.all_entries["wq_h2"]["ui_row"],
                    self.all_entries["wq_q_out"]["ui_row"],
                ], spacing=15,
            ), visible=False
        )

    def calculate_work_q(self, use_imperial: bool) -> str:
        m_dot_val = float(self.all_entries["wq_m_dot"]["val"].value)
        m_dot_unit = self.all_entries["wq_m_dot"]["unit"].value
        h1_val = float(self.all_entries["wq_h1"]["val"].value)
        h1_unit = self.all_entries["wq_h1"]["unit"].value
        h2_val = float(self.all_entries["wq_h2"]["val"].value)
        h2_unit = self.all_entries["wq_h2"]["unit"].value
        q_out_val = float(self.all_entries["wq_q_out"]["val"].value)
        q_out_unit = self.all_entries["wq_q_out"]["unit"].value

        m_dot_si = self.unit_converter.convert_to_si("MassFlow", m_dot_val, m_dot_unit)
        h1_si = self.unit_converter.convert_to_si("H", h1_val, h1_unit)
        h2_si = self.unit_converter.convert_to_si("H", h2_val, h2_unit)
        q_out_si_w = self.unit_converter.convert_to_si("Power", q_out_val, q_out_unit)

        # 準備 Analyzer 參數 (kJ/kg 和 kW)
        h1_kj = h1_si / 1000.0
        h2_kj = h2_si / 1000.0
        q_out_kw = q_out_si_w / 1000.0
        
        # 呼叫 (返回 kW)
        power_kw = self.analyzer.calculate_compressor_work_heat_transfer(m_dot_si, h1_kj, h2_kj, q_out_kw)
        
        # 轉回 SI (W)
        power_si_w = power_kw * 1000.0
        
        unit = self.unit_converter.imperial_units["Power"] if use_imperial else self.unit_converter.default_units["Power"]
        val = self.unit_converter.convert_from_si("Power", power_si_w, unit)
        
        return f"壓縮機功 (含熱傳): {val:.4f} {unit}"

    # --- 6. 壓縮機可逆功 [新] ---
    def _build_rev_work_ui(self):
        self.create_input_row("rev_m_dot", "質量流率 (Mass Flow Rate)", "0.1", "MassFlow", "kg/s")
        self.create_input_row("rev_h1", "入口焓值 (Inlet Enthalpy, h1)", "400", "H", "kJ/kg")
        self.create_input_row("rev_h2", "出口焓值 (Outlet Enthalpy, h2)", "450", "H", "kJ/kg")
        self.create_input_row("rev_s1", "入口熵 (Inlet Entropy, s1)", "1.7", "S", "kJ/(kg·K)")
        self.create_input_row("rev_s2", "出口熵 (Outlet Entropy, s2)", "1.8", "S", "kJ/(kg·K)")
        self.create_input_row("rev_t0", "死狀態溫度 (Dead State T0)", "25", "T", "°C")

        self.rev_work_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["rev_m_dot"]["ui_row"],
                    self.all_entries["rev_h1"]["ui_row"],
                    self.all_entries["rev_h2"]["ui_row"],
                    self.all_entries["rev_s1"]["ui_row"],
                    self.all_entries["rev_s2"]["ui_row"],
                    self.all_entries["rev_t0"]["ui_row"],
                ], spacing=15,
            ), visible=False
        )

    def calculate_rev_work(self, use_imperial: bool) -> str:
        m_dot_val = float(self.all_entries["rev_m_dot"]["val"].value)
        m_dot_unit = self.all_entries["rev_m_dot"]["unit"].value
        h1_val = float(self.all_entries["rev_h1"]["val"].value)
        h1_unit = self.all_entries["rev_h1"]["unit"].value
        h2_val = float(self.all_entries["rev_h2"]["val"].value)
        h2_unit = self.all_entries["rev_h2"]["unit"].value
        s1_val = float(self.all_entries["rev_s1"]["val"].value)
        s1_unit = self.all_entries["rev_s1"]["unit"].value
        s2_val = float(self.all_entries["rev_s2"]["val"].value)
        s2_unit = self.all_entries["rev_s2"]["unit"].value
        t0_val = float(self.all_entries["rev_t0"]["val"].value)
        t0_unit = self.all_entries["rev_t0"]["unit"].value

        m_dot_si = self.unit_converter.convert_to_si("MassFlow", m_dot_val, m_dot_unit)
        h1_si = self.unit_converter.convert_to_si("H", h1_val, h1_unit)
        h2_si = self.unit_converter.convert_to_si("H", h2_val, h2_unit)
        s1_si = self.unit_converter.convert_to_si("S", s1_val, s1_unit)
        s2_si = self.unit_converter.convert_to_si("S", s2_val, s2_unit)
        t0_k = self.unit_converter.convert_to_si("T", t0_val, t0_unit) # 絕對溫度 (K)
        #print("m_dot_si:", m_dot_si)
        #print("h1_si:", h1_si)
        #print("h2_si:", h2_si)
        #print("s1_si:", s1_si)
        #print("s2_si:", s2_si)
        #print("t0_k:", t0_k)



        # 準備 Analyzer 參數 (kJ/kg, kJ/(kg·K))
        h1_kj = h1_si / 1000.0
        h2_kj = h2_si / 1000.0
        s1_kj = s1_si / 1000.0
        s2_kj = s2_si / 1000.0
        
        # 呼叫 (返回 kW)
        power_kw = self.analyzer.calculate_compressor_reversible_work(m_dot_si, h1_kj, h2_kj, s1_kj, s2_kj, t0_k)
        
        # 轉回 SI (W)
        power_si_w = power_kw * 1000.0
        
        unit = self.unit_converter.imperial_units["Power"] if use_imperial else self.unit_converter.default_units["Power"]
        val = self.unit_converter.convert_from_si("Power", power_si_w, unit)
        
        return f"可逆功 (Reversible Work): {val:.4f} {unit}"

    # --- 7. 壓縮機㶲破壞 [新] ---
    def _build_ex_dest_ui(self):
        self.create_input_row("exd_t0", "死狀態溫度 (Dead State T0)", "25", "T", "°C")
        self.create_input_row("exd_h0", "入口焓值 (Dead Enthalpy, h0)", "400", "H", "kJ/kg")
        self.create_input_row("exd_s0", "入口熵 (Dead Entropy, s0)", "1.7", "S", "kJ/(kg·K)")
        self.create_input_row("exd_h1", "入口焓值 (Inlet Enthalpy, h1)", "400", "H", "kJ/kg")
        self.create_input_row("exd_h2", "出口焓值 (Outlet Enthalpy, h2)", "450", "H", "kJ/kg")
        self.create_input_row("exd_s1", "入口熵 (Inlet Entropy, s1)", "1.7", "S", "kJ/(kg·K)")
        self.create_input_row("exd_s2", "出口熵 (Outlet Entropy, s2)", "1.8", "S", "kJ/(kg·K)")
        self.create_input_row("exd_m_dot", "質量流率 (Mass Flow Rate)", "0.1", "MassFlow", "kg/s")

        self.ex_dest_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["exd_t0"]["ui_row"],
                    self.all_entries["exd_h0"]["ui_row"],
                    self.all_entries["exd_s0"]["ui_row"],
                    self.all_entries["exd_h1"]["ui_row"],
                    self.all_entries["exd_h2"]["ui_row"],
                    self.all_entries["exd_s1"]["ui_row"],
                    self.all_entries["exd_s2"]["ui_row"],
                    self.all_entries["exd_m_dot"]["ui_row"],
                ], spacing=15,
            ), visible=False
        )

    def calculate_ex_dest(self, use_imperial: bool) -> str:
        t0_val = float(self.all_entries["exd_t0"]["val"].value)
        t0_unit = self.all_entries["exd_t0"]["unit"].value
        h1_val = float(self.all_entries["exd_h1"]["val"].value)
        h1_unit = self.all_entries["exd_h1"]["unit"].value
        h2_val = float(self.all_entries["exd_h2"]["val"].value)
        h2_unit = self.all_entries["exd_h2"]["unit"].value
        h0_val = float(self.all_entries["exd_h0"]["val"].value)
        h0_unit = self.all_entries["exd_h0"]["unit"].value
        s0_val = float(self.all_entries["exd_s0"]["val"].value)
        s0_unit = self.all_entries["exd_s0"]["unit"].value
        s1_val = float(self.all_entries["exd_s1"]["val"].value)
        s1_unit = self.all_entries["exd_s1"]["unit"].value
        s2_val = float(self.all_entries["exd_s2"]["val"].value)
        s2_unit = self.all_entries["exd_s2"]["unit"].value
        m_dot_val = float(self.all_entries["exd_m_dot"]["val"].value)
        m_dot_unit = self.all_entries["exd_m_dot"]["unit"].value

        t0_k = self.unit_converter.convert_to_si("T", t0_val, t0_unit)
        s0_si = self.unit_converter.convert_to_si("S", s0_val, s0_unit)
        h0_si = self.unit_converter.convert_to_si("H", h0_val, h0_unit)
        s1_si = self.unit_converter.convert_to_si("S", s1_val, s1_unit)
        s2_si = self.unit_converter.convert_to_si("S", s2_val, s2_unit)
        h1_si = self.unit_converter.convert_to_si("H", h1_val, h1_unit)
        h2_si = self.unit_converter.convert_to_si("H", h2_val, h2_unit)
        m_dot_si = self.unit_converter.convert_to_si("MassFlow", m_dot_val, m_dot_unit)

        # 準備 Analyzer 參數 (kJ/(kg·K))
        s1_kj = s1_si / 1000.0
        s2_kj = s2_si / 1000.0
        h1_kj = h1_si / 1000.0
        h2_kj = h2_si / 1000.0
        h0_kj= h0_si / 1000.0
        s0_kj= s0_si / 1000.0
        
        # 呼叫 (返回 kW)
        power_kw = self.analyzer.calculate_compressor_exerpy_destruction(m_dot_si,h1_kj,h2_kj,s1_kj, s2_kj,t0_k,h0_kj,s0_kj)
        # 轉回 SI (W)
        power_si_w = power_kw * 1000.0
        
        unit = self.unit_converter.imperial_units["Power"] if use_imperial else self.unit_converter.default_units["Power"]
        val = self.unit_converter.convert_from_si("Power", power_si_w, unit)
        
        return f"㶲破壞率 (Exergy Destruction): {val:.4f} {unit}"
    


    # --- 8. 容積效率 [新] ---
    def _build_vol_eff_ui(self):
        # 這裡使用 've_' 作為前綴
        self.create_input_row("ve_r_clearance", "餘隙容積比 (Clearance Ratio, R)", "0.05", "Ratio", "—")
        self.create_input_row("ve_v1", "入口比容 (v1)", "0.05", "SpecVolume", "m³/kg")
        self.create_input_row("ve_v2", "出口比容 (v2)", "0.005", "SpecVolume", "m³/kg")

        self.vol_eff_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["ve_r_clearance"]["ui_row"],
                    self.all_entries["ve_v1"]["ui_row"],
                    self.all_entries["ve_v2"]["ui_row"],
                ], spacing=15,
            ), visible=False
        )

    def calculate_vol_eff(self, use_imperial: bool) -> str:
        r_val = float(self.all_entries["ve_r_clearance"]["val"].value)
        # 餘隙容積比 (R) 是無單位的，無需轉換

        v1_val = float(self.all_entries["ve_v1"]["val"].value)
        v1_unit = self.all_entries["ve_v1"]["unit"].value
        v2_val = float(self.all_entries["ve_v2"]["val"].value)
        v2_unit = self.all_entries["ve_v2"]["unit"].value

        # 轉換為 SI 單位 (m³/kg)
        v1_si = self.unit_converter.convert_to_si("SpecVolume", v1_val, v1_unit)
        v2_si = self.unit_converter.convert_to_si("SpecVolume", v2_val, v2_unit)

        # 呼叫計算函式
        # 這裡假設 calculate_volumetric_efficiency 是 Analyzer 類別的方法或已作為 helper function 導入
        volumetric_efficiency = self.analyzer.calculate_volumetric_efficiency(
            r_val, v1_si, v2_si
        )

        # 容積效率是一個無單位比率，回傳百分比形式
        efficiency_percent = volumetric_efficiency * 100.0

        return f"容積效率 (Volumetric Efficiency): {efficiency_percent:.4f} %"


    # --- 9. 壓縮機㶲效率 (損失法) [新] ---
    def _build_ex_eff_loss_ui(self):
        # 由於參數與 ex_dest 相同，為了區分，使用 'eel_' 作為前綴，但內容沿用 ex_dest 的輸入
        self.create_input_row("eel_t0", "死狀態溫度 (Dead State T0)", "25", "T", "°C")
        self.create_input_row("eel_h0", "入口焓值 (Dead Enthalpy, h0)", "400", "H", "kJ/kg")
        self.create_input_row("eel_s0", "入口熵 (Dead Entropy, s0)", "1.7", "S", "kJ/(kg·K)")
        self.create_input_row("eel_h1", "入口焓值 (Inlet Enthalpy, h1)", "400", "H", "kJ/kg")
        self.create_input_row("eel_h2", "出口焓值 (Outlet Enthalpy, h2)", "450", "H", "kJ/kg")
        self.create_input_row("eel_s1", "入口熵 (Inlet Entropy, s1)", "1.7", "S", "kJ/(kg·K)")
        self.create_input_row("eel_s2", "出口熵 (Outlet Entropy, s2)", "1.8", "S", "kJ/(kg·K)")
        self.create_input_row("eel_m_dot", "質量流率 (Mass Flow Rate)", "0.1", "MassFlow", "kg/s")

        self.ex_eff_loss_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["eel_t0"]["ui_row"],
                    self.all_entries["eel_h0"]["ui_row"],
                    self.all_entries["eel_s0"]["ui_row"],
                    self.all_entries["eel_h1"]["ui_row"],
                    self.all_entries["eel_h2"]["ui_row"],
                    self.all_entries["eel_s1"]["ui_row"],
                    self.all_entries["eel_s2"]["ui_row"],
                    self.all_entries["eel_m_dot"]["ui_row"],
                ], spacing=15,
            ), visible=False
        )

    def calculate_ex_eff_loss(self, use_imperial: bool) -> str:
        # 提取值
        t0_val = float(self.all_entries["eel_t0"]["val"].value)
        t0_unit = self.all_entries["eel_t0"]["unit"].value
        h1_val = float(self.all_entries["eel_h1"]["val"].value)
        h1_unit = self.all_entries["eel_h1"]["unit"].value
        h2_val = float(self.all_entries["eel_h2"]["val"].value)
        h2_unit = self.all_entries["eel_h2"]["unit"].value
        h0_val = float(self.all_entries["eel_h0"]["val"].value)
        h0_unit = self.all_entries["eel_h0"]["unit"].value
        s0_val = float(self.all_entries["eel_s0"]["val"].value)
        s0_unit = self.all_entries["eel_s0"]["unit"].value
        s1_val = float(self.all_entries["eel_s1"]["val"].value)
        s1_unit = self.all_entries["eel_s1"]["unit"].value
        s2_val = float(self.all_entries["eel_s2"]["val"].value)
        s2_unit = self.all_entries["eel_s2"]["unit"].value
        m_dot_val = float(self.all_entries["eel_m_dot"]["val"].value)
        m_dot_unit = self.all_entries["eel_m_dot"]["unit"].value

        # 轉換為 SI 單位
        t0_k = self.unit_converter.convert_to_si("T", t0_val, t0_unit)
        s0_si = self.unit_converter.convert_to_si("S", s0_val, s0_unit)
        h0_si = self.unit_converter.convert_to_si("H", h0_val, h0_unit)
        s1_si = self.unit_converter.convert_to_si("S", s1_val, s1_unit)
        s2_si = self.unit_converter.convert_to_si("S", s2_val, s2_unit)
        h1_si = self.unit_converter.convert_to_si("H", h1_val, h1_unit)
        h2_si = self.unit_converter.convert_to_si("H", h2_val, h2_unit)
        m_dot_si = self.unit_converter.convert_to_si("MassFlow", m_dot_val, m_dot_unit)

        # 準備 Analyzer 參數 (kJ/(kg·K)) - 保持與範例一致
        s1_kj = s1_si / 1000.0
        s2_kj = s2_si / 1000.0
        h1_kj = h1_si / 1000.0
        h2_kj = h2_si / 1000.0
        h0_kj= h0_si / 1000.0
        s0_kj= s0_si / 1000.0

        # 呼叫 (返回效率，無單位)
        # 這裡假設 calculate_compressor_exergetic_efficiency_loss 是 Analyzer 類別的方法
        efficiency = self.analyzer.calculate_compressor_exergetic_efficiency_loss(
            m_dot_si, h1_kj, h2_kj, s1_kj, s2_kj, t0_k, h0_kj, s0_kj
        )

        # 效率是無單位比率，回傳百分比形式
        efficiency_percent = efficiency * 100.0

        return f"㶲效率 (損失法): {efficiency_percent:.4f} %"


    # --- 10. 壓縮機㶲效率 (可逆功法) [新] ---
    def _build_ex_eff_ratio_ui(self):
        # 由於參數與 ex_dest 相同，為了區分，使用 'eer_' 作為前綴，但內容沿用 ex_dest 的輸入
        self.create_input_row("eer_t0", "死狀態溫度 (Dead State T0)", "25", "T", "°C")
        self.create_input_row("eer_h0", "入口焓值 (Dead Enthalpy, h0)", "400", "H", "kJ/kg")
        self.create_input_row("eer_s0", "入口熵 (Dead Entropy, s0)", "1.7", "S", "kJ/(kg·K)")
        self.create_input_row("eer_h1", "入口焓值 (Inlet Enthalpy, h1)", "400", "H", "kJ/kg")
        self.create_input_row("eer_h2", "出口焓值 (Outlet Enthalpy, h2)", "450", "H", "kJ/kg")
        self.create_input_row("eer_s1", "入口熵 (Inlet Entropy, s1)", "1.7", "S", "kJ/(kg·K)")
        self.create_input_row("eer_s2", "出口熵 (Outlet Entropy, s2)", "1.8", "S", "kJ/(kg·K)")
        self.create_input_row("eer_m_dot", "質量流率 (Mass Flow Rate)", "0.1", "MassFlow", "kg/s")

        self.ex_eff_ratio_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["eer_t0"]["ui_row"],
                    self.all_entries["eer_h0"]["ui_row"],
                    self.all_entries["eer_s0"]["ui_row"],
                    self.all_entries["eer_h1"]["ui_row"],
                    self.all_entries["eer_h2"]["ui_row"],
                    self.all_entries["eer_s1"]["ui_row"],
                    self.all_entries["eer_s2"]["ui_row"],
                    self.all_entries["eer_m_dot"]["ui_row"],
                ], spacing=15,
            ), visible=False
        )

    def calculate_ex_eff_ratio(self, use_imperial: bool) -> str:
        # 提取值 (與 calculate_ex_eff_loss 相同)
        t0_val = float(self.all_entries["eer_t0"]["val"].value)
        t0_unit = self.all_entries["eer_t0"]["unit"].value
        h1_val = float(self.all_entries["eer_h1"]["val"].value)
        h1_unit = self.all_entries["eer_h1"]["unit"].value
        h2_val = float(self.all_entries["eer_h2"]["val"].value)
        h2_unit = self.all_entries["eer_h2"]["unit"].value
        h0_val = float(self.all_entries["eer_h0"]["val"].value)
        h0_unit = self.all_entries["eer_h0"]["unit"].value
        s0_val = float(self.all_entries["eer_s0"]["val"].value)
        s0_unit = self.all_entries["eer_s0"]["unit"].value
        s1_val = float(self.all_entries["eer_s1"]["val"].value)
        s1_unit = self.all_entries["eer_s1"]["unit"].value
        s2_val = float(self.all_entries["eer_s2"]["val"].value)
        s2_unit = self.all_entries["eer_s2"]["unit"].value
        m_dot_val = float(self.all_entries["eer_m_dot"]["val"].value)
        m_dot_unit = self.all_entries["eer_m_dot"]["unit"].value

        # 轉換為 SI 單位
        t0_k = self.unit_converter.convert_to_si("T", t0_val, t0_unit)
        s0_si = self.unit_converter.convert_to_si("S", s0_val, s0_unit)
        h0_si = self.unit_converter.convert_to_si("H", h0_val, h0_unit)
        s1_si = self.unit_converter.convert_to_si("S", s1_val, s1_unit)
        s2_si = self.unit_converter.convert_to_si("S", s2_val, s2_unit)
        h1_si = self.unit_converter.convert_to_si("H", h1_val, h1_unit)
        h2_si = self.unit_converter.convert_to_si("H", h2_val, h2_unit)
        m_dot_si = self.unit_converter.convert_to_si("MassFlow", m_dot_val, m_dot_unit)

        # 準備 Analyzer 參數 (kJ/(kg·K)) - 保持與範例一致
        s1_kj = s1_si / 1000.0
        s2_kj = s2_si / 1000.0
        h1_kj = h1_si / 1000.0
        h2_kj = h2_si / 1000.0
        h0_kj= h0_si / 1000.0
        s0_kj= s0_si / 1000.0

        # 呼叫 (返回效率，無單位)
        # 這裡假設 calculate_compressor_exergetic_efficiency_ratio 是 Analyzer 類別的方法
        efficiency = self.analyzer.calculate_compressor_exergetic_efficiency_ratio(
            m_dot_si, h1_kj, h2_kj, s1_kj, s2_kj, t0_k, h0_kj, s0_kj
        )

        # 效率是無單位比率，回傳百分比形式
        efficiency_percent = efficiency * 100.0

        return f"㶲效率 (可逆功法): {efficiency_percent:.4f} %"    
    
    # --- 11. 壓縮機 例題內容 [新] ---
    def _build_comp_example_ui(self):
        # 使用 'ce_' （壓縮機範例） 作為前綴

        # 輸入參數
        self.create_input_row("ce_r", "容積效率參數 R (Clearance Ratio)", "0.05", "Ratio", "—")
        self.create_input_row("ce_p1", "入口壓力 (P1)", "100", "P", "kPa")
        self.create_input_row("ce_t1", "入口溫度 (T1)", "280", "T", "K")
        self.create_input_row("ce_p2", "出口壓力 (P2)", "500", "P", "kPa")
        self.create_input_row("ce_t2", "出口溫度 (T2)", "380", "T", "K")
        self.create_input_row("ce_p0", "死狀態壓力 (P0)", "101.325", "P", "kPa")
        self.create_input_row("ce_t0", "死狀態溫度 (T0)", "298.15", "T", "K") # 25°C
        self.create_input_row("ce_v1_dot", "入口體積流率 (V1_dot)", "0.01", "VolumeFlow", "m³/s")

        self.ce_substance_tf = style_text_field(ft.TextField(
            value="R134a",  # 預設值
            expand=True,
            height=TOKENS.input_height,
            hint_text="輸入如 R134a, Air, Water...",
            prefix_icon=ft.Icons.PROPANE_TANK_OUTLINED,
            text_align=ft.TextAlign.LEFT,
        ))
        # 與 create_input_row 相同的「框外欄名 + 欄位」結構，讓整張表單對齊。
        self.ce_substance_row = ft.Column(
            [
                ft.Text("工作流體 (Substance)", size=TOKENS.body, weight=ft.FontWeight.W_500,
                        color=TOKENS.text_primary),
                self.ce_substance_tf,
            ],
            spacing=6,
        )

        self.comp_example_ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["ce_r"]["ui_row"],
                    self.all_entries["ce_p1"]["ui_row"],
                    self.all_entries["ce_t1"]["ui_row"],
                    self.all_entries["ce_p2"]["ui_row"],
                    self.all_entries["ce_t2"]["ui_row"],
                    self.all_entries["ce_p0"]["ui_row"],
                    self.all_entries["ce_t0"]["ui_row"],
                    self.all_entries["ce_v1_dot"]["ui_row"],
                    self.ce_substance_row, # 新增物質選擇
                ], spacing=15,
            ), visible=False
    )

    def _reference_state_for(self, fluid: str) -> str:
        """回傳應用程式針對壓縮機流體要求的 policy。

參數：
    fluid (str): 函數輸入值。

回傳：
    str：函數計算或處理後的結果。"""
        if self.reference_state_provider is None:
            requested_policy = "ASHRAE"
        else:
            requested_policy = self.reference_state_provider.requested_reference_state(fluid)
        return resolve_reference_state_policy(fluid, requested_policy)

    def calculate_comp_example(self, use_imperial: bool) -> str:
        # 1. 獲取並轉換輸入值
        r_val = float(self.all_entries["ce_r"]["val"].value)

        p1_val = float(self.all_entries["ce_p1"]["val"].value)
        p1_unit = self.all_entries["ce_p1"]["unit"].value
        p2_val = float(self.all_entries["ce_p2"]["val"].value)
        p2_unit = self.all_entries["ce_p2"]["unit"].value
        p0_val = float(self.all_entries["ce_p0"]["val"].value)
        p0_unit = self.all_entries["ce_p0"]["unit"].value

        t1_val = float(self.all_entries["ce_t1"]["val"].value)
        t1_unit = self.all_entries["ce_t1"]["unit"].value
        t2_val = float(self.all_entries["ce_t2"]["val"].value)
        t2_unit = self.all_entries["ce_t2"]["unit"].value
        t0_val = float(self.all_entries["ce_t0"]["val"].value)
        t0_unit = self.all_entries["ce_t0"]["unit"].value

        v1_dot_val = float(self.all_entries["ce_v1_dot"]["val"].value)
        v1_dot_unit = self.all_entries["ce_v1_dot"]["unit"].value

        substance = self.ce_substance_tf.value # 獲取流體名稱

        # 轉換為 CoolProp 期望的 SI 單位
        # 假設 CoolProp 期望 P 為 Pa, T 為 K, V_dot 為 m³/s
        p1_si = self.unit_converter.convert_to_si("P", p1_val, p1_unit)
        p2_si = self.unit_converter.convert_to_si("P", p2_val, p2_unit)
        p0_si = self.unit_converter.convert_to_si("P", p0_val, p0_unit)
        
        t1_k = self.unit_converter.convert_to_si("T", t1_val, t1_unit)
        t2_k = self.unit_converter.convert_to_si("T", t2_val, t2_unit)
        t0_k = self.unit_converter.convert_to_si("T", t0_val, t0_unit)
        
        # 3. 讀取由 application 擁有的要求 policy，而不是 facade 快取。
        current_ref = self._reference_state_for(substance)

        v1_dot_si = self.unit_converter.convert_to_si("VolumeFlow", v1_dot_val, v1_dot_unit)

        # 4. 呼叫主要的計算函式 (假設此函式已被整合到 self.analyzer 中)
        # 這裡假設您的 self.analyzer 類別有一個方法來執行這個完整流程
        try:
            # eff_vol, win_si, eff_isen, ex_dest_si, eff_comp_ex
            results = self.analyzer.calculate_compressor_example(
                r_val, p1_si, t1_k, p2_si, t2_k, p0_si, t0_k, v1_dot_si, substance,ref_state_code=current_ref
            )
            """
            print("r_val", r_val)
            print("p1_si", p1_si)
            print("t1_k", t1_k)
            print("p2_si", p2_si)
            print("t2_k", t2_k)
            print("p0_si", p0_si)
            print("t0_k", t0_k)
            print("v1_dot_si", v1_dot_si)
            print("substance", substance)
            """
        except Exception as e:
            return f"計算錯誤: {e}"

        # 1. 將回傳的結果解包，並明確標示單位是 kW
        Eff_vol, Win_kW, Eff_isen, Ex_destruction_flow_kW, EFF_comp_ex = results
        # 2. [!! 關鍵修正 !!]
        # 將 kW 轉回 W，以符合 unit_converter 對 SI 基本單位的預期
        Win_si = Win_kW * 1000.0
        Ex_destruction_flow_si = Ex_destruction_flow_kW * 1000.0

        # 3. 單位轉換和結果格式化

        # 功/破壞率 (Win_si, Ex_destruction_flow_si)
        # 轉換回使用者指定的單位 (W -> kW, BTU/h, etc.)
        power_unit = self.unit_converter.imperial_units["Power"] if use_imperial else self.unit_converter.default_units["Power"]
        #print(f"power_unit: {power_unit}")
        win_display = self.unit_converter.convert_from_si("Power", Win_si, power_unit)
        #print(f"win_display: {win_display}")
        ex_dest_display = self.unit_converter.convert_from_si("Power", Ex_destruction_flow_si, power_unit)
        #print(f"ex_dest_display: {ex_dest_display}")


        # 效率和比率 (Eff_vol, Eff_isen, EFF_comp_ex) - 顯示為百分比
        eff_vol_percent = Eff_vol * 100.0
        eff_isen_percent = Eff_isen * 100.0
        eff_comp_ex_percent = EFF_comp_ex * 100.0

        # 4. 構建輸出字串
        result_lines = [
            "--- 壓縮機例題結果 ---",
            f"容積效率 (Eff_vol): {eff_vol_percent:.2f} %",
            f"等熵效率 (Eff_isen): {eff_isen_percent:.2f} %",
            f"壓縮機輸入功 (Win): {win_display:.4f} {power_unit}",
            f"㶲破壞率 (Ex_destruction_flow): {ex_dest_display:.4f} {power_unit}",
            f"㶲效率 (EFF_comp_ex): {eff_comp_ex_percent:.2f} %",
        ]

        return "\n".join(result_lines)
    
    # --- 12. 單位同步 (此模組共用) [已擴充] ---
    def _setup_unit_sync(self):
        # 壓力 (P)
        cr_sync_group = ["cr_pe", "cr_pc", "cr_atm_p","ce_p1", "ce_p2", "ce_p0"]
        self.all_entries["cr_pe"]["unit"].on_select = self._create_unit_sync_handler("P", cr_sync_group)
        self.all_entries["cr_pc"]["unit"].on_select = self._create_unit_sync_handler("P", cr_sync_group)
        self.all_entries["cr_atm_p"]["unit"].on_select = self._create_unit_sync_handler("P", cr_sync_group)
        self.all_entries["ce_p1"]["unit"].on_select = self._create_unit_sync_handler("P", cr_sync_group)
        self.all_entries["ce_p2"]["unit"].on_select = self._create_unit_sync_handler("P", cr_sync_group)
        self.all_entries["ce_p0"]["unit"].on_select = self._create_unit_sync_handler("P", cr_sync_group)

        
        # 焓 (H)
        h_sync_group = ["win_h1", "win_h2", "isen_h1", "isen_h2", "isen_h2s", "ref_h1", "ref_h4", "wq_h1", "wq_h2", "rev_h1", "rev_h2"]
        for key in h_sync_group:
            if key in self.all_entries:
                self.all_entries[key]["unit"].on_select = self._create_unit_sync_handler("H", h_sync_group)

        # 質量流率 (MassFlow)
        m_dot_sync_group = ["win_m_dot", "ref_m_dot", "wq_m_dot", "rev_m_dot", "exd_m_dot"]
        for key in m_dot_sync_group:
             if key in self.all_entries:
                self.all_entries[key]["unit"].on_select = self._create_unit_sync_handler("MassFlow", m_dot_sync_group)

        # 熵 (S)
        s_sync_group = ["rev_s1", "rev_s2", "exd_s1", "exd_s2"]
        for key in s_sync_group:
            if key in self.all_entries:
                self.all_entries[key]["unit"].on_select = self._create_unit_sync_handler("S", s_sync_group)

        # 溫度 (T)
        t_sync_group = ["rev_t0", "exd_t0","ce_t1", "ce_t2", "ce_t0"]
        for key in t_sync_group:
            if key in self.all_entries:
                self.all_entries[key]["unit"].on_select = self._create_unit_sync_handler("T", t_sync_group)
        
         # 體積流率 (VolumeFlow)
        # * 新增 ce_v1_dot *
        v_dot_sync_group = ["ref_v_dot", "ce_v1_dot"]
        for key in v_dot_sync_group:
            if key in self.all_entries:
                self.all_entries[key]["unit"].on_select = self._create_unit_sync_handler("VolumeFlow", v_dot_sync_group)

        # 功率 (Power)
        self.all_entries["wq_q_out"]["unit"].on_select = self._create_unit_sync_handler("Power", ["wq_q_out"])

        # --- 新增 "冷凍能力" 的單位同步 ---
        self.all_entries["ref_v_dot"]["unit"].on_select = self._create_unit_sync_handler("VolumeFlow", ["ref_v_dot"])
        self.all_entries["ref_rho1"]["unit"].on_select = self._create_unit_sync_handler("D", ["ref_rho1"])

        # "ref_eta_vol" (效率) 使用 "RH" 代理，單位下拉選單被禁用，無需同步


    # --- 13. 由 AnalysisTab 呼叫的特定方法 (不變) ---
    def update_atm_pressure_default(self, use_imperial: bool):
        """由 AnalysisTab 呼叫，用於更新大氣壓力預設值

參數：
    use_imperial (bool): 函數輸入值。

回傳：
    無。"""
        atm_p_controls = self.all_entries["cr_atm_p"]
        atm_p_si_base = 101325.0
        
        if use_imperial:
            new_unit = self.unit_converter.imperial_units["P"]
            new_val = self.unit_converter.convert_from_si("P", atm_p_si_base, new_unit)
        else:
            new_unit = "kPa"
            new_val = self.unit_converter.convert_from_si("P", atm_p_si_base, new_unit)
        
        atm_p_controls["val"].value = f"{new_val:.5g}"
        atm_p_controls["unit"].value = new_unit
        self._last_units["cr_atm_p"] = new_unit
        
        if self.cr_ui_container.parent: # 安全檢查
            self.cr_ui_container.update()