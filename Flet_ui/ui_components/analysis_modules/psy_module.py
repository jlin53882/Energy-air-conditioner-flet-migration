# ui_components/analysis_modules/psy_module.py

import flet as ft
from .base_analysis_module import BaseAnalysisModule
from ..unit.PsychrometricCalculator import PsychrometricCalculator
from ..unit.UnitConverter import UnitConverter

class PsyModule(BaseAnalysisModule):
    def __init__(self, unit_converter: UnitConverter, page: ft.Page, psy_calculator: PsychrometricCalculator):
        super().__init__(unit_converter, page, psy_calculator=psy_calculator)
        
        self.psy_calculator: PsychrometricCalculator = self.services.get("psy_calculator")
        
        # --- 建立 UI ---
        self._build_ui_components()
        self._setup_unit_sync()
        
        # --- 建立 UI 容器 ---
        # 兩種模式共用 *同一個* UI 容器實例
        self.ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.all_entries["psy_alt"]["ui_row"],
                    self.all_entries["psy_tdb"]["ui_row"],
                    self.all_entries["psy_twb"]["ui_row"],
                    self.all_entries["psy_rh"]["ui_row"],
                ],
                spacing=15,
            ),
            visible=False
        )

    def get_analysis_definitions(self) -> dict:
        """回報此模組提供的 *兩種* 濕空氣計算模式"""
        return {
            "濕空氣性質 (已知乾濕球)": {
                "analysis_id": "psychrometrics.tdb_twb",
                "ui": self.ui_container,
                "calc_func": self.calculate_psy,
                "calculation_mode": "psychrometric"
            },
            "濕空氣性質 (已知乾球與相對濕度)": {
                "analysis_id": "psychrometrics.tdb_rh",
                "ui": self.ui_container,
                "calc_func": self.calculate_psy,
                "calculation_mode": "psychrometric"
            }
        }
        
    def _build_ui_components(self):
        """僅建立元件"""
        self.create_input_row("psy_alt", "高度 (Altitude)", "0", "L", "m")
        self.create_input_row("psy_tdb", "乾球溫度 (Dry-Bulb)", "25", "T", "°C")
        self.create_input_row("psy_twb", "濕球溫度 (Wet-Bulb)", "20", "T", "°C")
        self.create_input_row("psy_rh", "相對濕度 (Rel. Humidity)", "50", "RH", "%")

    def _setup_unit_sync(self):
        """設定單位同步"""
        psy_t_sync_group = ["psy_tdb", "psy_twb"]
        self.all_entries["psy_tdb"]["unit"].on_change = self._create_unit_sync_handler("T", psy_t_sync_group)
        self.all_entries["psy_twb"]["unit"].on_change = self._create_unit_sync_handler("T", psy_t_sync_group)
        self.all_entries["psy_alt"]["unit"].on_change = self._create_unit_sync_handler("L", ["psy_alt"])

    def configure_ui_for_mode(self, mode_name: str):
        """
        由 AnalysisTab 呼叫，配置 UI 顯示模式。
        這是一個 *特定* 方法，僅供 PsyModule 使用。
        """
        if mode_name == "濕空氣性質 (已知乾濕球)":
            self.all_entries["psy_twb"]["ui_row"].visible = True
            self.all_entries["psy_rh"]["ui_row"].visible = False
        elif mode_name == "濕空氣性質 (已知乾球與相對濕度)":
            self.all_entries["psy_twb"]["ui_row"].visible = False
            self.all_entries["psy_rh"]["ui_row"].visible = True
        
        # Flet raises RuntimeError when ``page`` is read before attachment;
        # construction-time tests and headless callers legitimately hit that path.
        try:
            attached_page = self.ui_container.page
        except RuntimeError:
            attached_page = None
        if attached_page:
            self.ui_container.update()

    def calculate_psy(self, use_imperial: bool, mode_name: str) -> str:
        """
        實作濕空氣計算。
        注意：此函式需要額外的 'mode_name' 參數。
        """
        # 1. 讀取通用值和單位
        alt_val = float(self.all_entries["psy_alt"]["val"].value)
        alt_unit = self.all_entries["psy_alt"]["unit"].value
        tdb_val = float(self.all_entries["psy_tdb"]["val"].value)
        tdb_unit = self.all_entries["psy_tdb"]["unit"].value

        # 2. 轉換為 SI (m 和 K)
        alt_m = self.unit_converter.convert_to_si("L", alt_val, alt_unit)
        tdb_k = self.unit_converter.convert_to_si("T", tdb_val, tdb_unit)

        psy_results = {}
        
        # 3. 根據傳入的 mode_name 決定計算路徑
        if mode_name == "濕空氣性質 (已知乾濕球)":
            twb_val = float(self.all_entries["psy_twb"]["val"].value)
            twb_unit = self.all_entries["psy_twb"]["unit"].value
            twb_k = self.unit_converter.convert_to_si("T", twb_val, twb_unit)
            psy_results = self.psy_calculator.calculate_from_tdb_twb(tdb_k, twb_k, alt_m)

        elif mode_name == "濕空氣性質 (已知乾球與相對濕度)":
            rh_val = float(self.all_entries["psy_rh"]["val"].value)
            rh_si = self.unit_converter.convert_to_si("RH", rh_val, "%") 
            psy_results = self.psy_calculator.calculate_from_tdb_rh(tdb_k, rh_si, alt_m)

        # 4. 格式化輸出
        if psy_results:
            result_lines = self._format_psy_results(psy_results, use_imperial)
            return "\n".join(result_lines)
        else:
            return "計算失敗。"

    def _format_psy_results(self, si_results, use_imperial):
        """
        輔助方法：將濕空氣的 *大型* SI 結果字典
        格式化為您指定的詳細字串列表，並支援 SI/Imperial 轉換。
        (此函式從舊的 analysis_tab.py 完整搬移過來)
        """
        lines = []
        
        # 1. 決定目標單位
        if use_imperial:
            l_unit = self.unit_converter.imperial_units["L"]
            p_unit = self.unit_converter.imperial_units["P"]
            t_unit = self.unit_converter.imperial_units["T"]
            w_unit = self.unit_converter.imperial_units["W"]
            h_unit = self.unit_converter.imperial_units["H"]
            v_unit = self.unit_converter.imperial_units["V"]
        else:
            l_unit = self.unit_converter.default_units["L"]
            p_unit = "Pa"     
            t_unit = self.unit_converter.default_units["T"]
            w_unit = "kg/kg"  
            h_unit = self.unit_converter.default_units["H"]
            v_unit = self.unit_converter.default_units["V"]

        # 2. 獲取所有 SI 基礎單位數值 (省略... 如同您原始碼)
        alt_si = si_results['Altitude']
        p_si = si_results['P']
        tdb_si = si_results['Tdb']
        twb_si = si_results['Twb']
        tdp_si = si_results['Tdp']
        rh_si = si_results['RH']
        w_si = si_results['W']
        h_si = si_results['H']
        v_si = si_results['V']
        pw_si = si_results['Pw']
        pws_db_si = si_results['Pws_db']
        pws_wd_si = si_results['Pws_wd']
        ws_si = si_results['Ws']
        wss_si = si_results['Wss']

        # 3. 將所有數值轉換為目標顯示單位 (省略... 如同您原始碼)
        alt_val = self.unit_converter.convert_from_si("L", alt_si, l_unit)
        p_val = self.unit_converter.convert_from_si("P", p_si, p_unit)
        tdb_val = self.unit_converter.convert_from_si("T", tdb_si, t_unit)
        twb_val = self.unit_converter.convert_from_si("T", twb_si, t_unit)
        tdp_val = self.unit_converter.convert_from_si("T", tdp_si, t_unit)
        w_val = self.unit_converter.convert_from_si("W", w_si, w_unit)
        h_val = self.unit_converter.convert_from_si("H", h_si, h_unit)
        v_val = self.unit_converter.convert_from_si("V", v_si, v_unit)
        pw_val = self.unit_converter.convert_from_si("P", pw_si, p_unit)
        pws_db_val = self.unit_converter.convert_from_si("P", pws_db_si, p_unit)
        pws_wd_val = self.unit_converter.convert_from_si("P", pws_wd_si, p_unit)
        ws_val = self.unit_converter.convert_from_si("W", ws_si, w_unit)
        wss_val = self.unit_converter.convert_from_si("W", wss_si, w_unit)
        
        # 4. 依照您要求的格式，建立字串列表 (省略... 如同您原始碼)
        title_width = 48
        lines.append("--- 主要性質 ---")
        lines.append(f"{'海拔高度 (Altitude)':<{title_width}}: {alt_val:.2f} {l_unit}")
        lines.append(f"{'大氣壓力 (Atmospheric Pressure)':<{title_width}}: {p_val:.4f} {p_unit}")
        lines.append(f"{'乾球溫度 (Dry-Bulb Temperature)':<{title_width}}: {tdb_val:.2f} {t_unit}")
        lines.append(f"{'計算濕球溫度 (Calculated Wet-Bulb Temp)':<{title_width}}: {twb_val:.2f} {t_unit}")
        lines.append(f"{'露點溫度 (Dew Point Temperature)':<{title_width}}: {tdp_val:.2f} {t_unit}")
        lines.append(f"{'相對濕度 (Relative Humidity)':<{title_width}}: {rh_si:.2f} %") 
        lines.append(f"{'濕度比 (Humidity Ratio)':<{title_width}}: {w_val:.6f} {w_unit}")
        lines.append(f"{'濕空氣之焓值 (Enthalpy)':<{title_width}}: {h_val:.4f} {h_unit}")
        lines.append(f"{'濕空氣之比容 (Specific Volume)':<{title_width}}: {v_val:.4f} {v_unit}")
        lines.append("\n--- 中間過程壓力值 ---")
        lines.append(f"{'水蒸氣分壓 (Vapor Pressure)':<{title_width}}: {pw_val:.4f} {p_unit}")
        lines.append(f"{'飽和狀態之水蒸氣分壓 (Saturation Pressure at Tdb)':<{title_width}}: {pws_db_val:.4f} {p_unit}")
        lines.append(f"{'濕球溫度下，飽和狀態之水蒸氣分壓 (Saturation Pressure at Twb)':<{title_width}}: {pws_wd_val:.4f} {p_unit}")
        lines.append("\n--- 中間過程濕度比 ---")
        lines.append(f"{'飽和濕空氣之濕度比 (Saturation Humidity Ratio at Tdb)':<{title_width}}: {ws_val:.6f} {w_unit}")
        lines.append(f"{'濕球溫度下，飽和狀態之濕度比 (Saturation Humidity Ratio at Twb)':<{title_width}}: {wss_val:.6f} {w_unit}")
        
        return lines