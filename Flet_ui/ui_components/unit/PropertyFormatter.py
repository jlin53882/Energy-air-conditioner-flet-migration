# PropertyFormatter.py
# 職責：格式化輸出字串。
# 依賴 UnitConverter 將 SI 轉回顯示單位。

from .UnitConverter import UnitConverter

class PropertyFormatter:
    def __init__(self, unit_converter: UnitConverter):
        self.unit_converter = unit_converter
        self.properties = ["P", "T", "H", "S", "D", "Q", "V", "U"]

        self.prop_names = {
            "P": "Pressure (壓力)", 
            "T": "Temperature (溫度)", 
            "H": "Enthalpy (焓)",
            "S": "Entropy (熵)", 
            "D": "Density (密度)", 
            "Q": "Quality (乾度)",
            "V": "Specific Volume (比容)", 
            "U": "Internal Energy (內能)"
        }
        
        # 顯示相關的定義
        self.output_prop_names = {
            "P": "Pressure 壓力 (P)", "T": "Temperature 溫度 (T)", 
            "H": "Enthalpy 焓 (h)", "S": "Entropy 熵 (s)",
            "D": "Density 密度 (ρ)", "Q": "Quality 乾度 (Q)", 
            "V": "Specific Volume 比容 (v)", "U": "Internal Energy 內能 (u)"
        }
        self.display_precision = {
            "P": 4, "T": 4, "H": 6, "S": 6, "D": 6, "Q": 6, "V": 6, "U": 6
        }
        
    def _get_phase_description(self, phase_str):
        """根據 CoolProp 回傳的相態字串，返回更易讀的描述。

參數：
    phase_str (未指定型別): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
        phase_map = {
            'liquid': 'Compressed Liquid (壓縮液)',
            'twophase': 'Two-Phase (Saturated) (兩相飽和區)',
            'supercritical_gas': 'Supercritical Gas (超臨界氣體)',
            'supercritical_liquid': 'Supercritical Liquid (超臨界液體)',
            'supercritical': 'Supercritical (超臨界流體)',
            'gas': 'Superheated Vapor (過熱氣體)',
            'unknown': 'Unknown (未知)',
            'critical_point': 'Critical Point (臨界點)'
        }
        return phase_map.get(phase_str, phase_str.capitalize()) # 預設返回首字大寫的原字串

    def format_specific_properties(self, si_results, use_imperial_units):
        """
        格式化所有比性質 (比性質) 的輸出。
        
        :param si_results: 包含 SI 單位 (K, Pa, J/kg...) 的熱力學狀態字典
        :param use_imperial_units: 布林值，True 表示輸出英制，False 表示輸出公制
        :return: 格式化後的字串
        """
        lines = ["--- 比性質 (Specific Properties) ---"]
        
        # 根據 use_imperial 選擇要使用的單位字典
        target_units = self.unit_converter.imperial_units if use_imperial_units else self.unit_converter.default_units

        # 遍歷所有定義的性質
        for prop_code in self.properties:
            if prop_code in si_results:
                si_value = si_results[prop_code]
                
                # 乾度 (Q) 是特例，它沒有單位且範圍是 0-1
                if prop_code == 'Q':
                    if si_value >= 0 and si_value <= 1:
                        # 僅在兩相區顯示乾度
                        lines.append(f"{self.output_prop_names[prop_code]:<28}: {si_value:.4f} (0-1)")
                    continue # 處理完乾度後跳過後續單位轉換

                # 獲取目標單位 (例如 "MPa" 或 "psia")
                target_unit = target_units.get(prop_code)
                if not target_unit:
                    continue # 如果沒有定義單位 (不應發生)

                # 執行單位轉換
                display_val = self.unit_converter.convert_from_si(prop_code, si_value, target_unit)
                
                # 格式化輸出
                precision = self.display_precision.get(prop_code, 4)
                lines.append(f"{self.output_prop_names[prop_code]:<28}: {display_val:>{precision+4}.{precision}f} {target_unit}")

        # 附加相態資訊
        final_phase_description = self._get_phase_description(si_results.get('phase', 'unknown'))
        lines.append(f"\nPhase (相態): {final_phase_description}")
        return "\n".join(lines)

    def format_extensive_properties(self, si_results, total_mass_kg, use_imperial_units):
        """
        格式化廣延性質 (總性質)。
        注意：total_mass_kg 應始終以 SI (kg) 傳入。
        """
        lines = ["\n--- 廣延性質 (Extensive Properties) ---"]
        
        # --- 移除 Hard-coded 邏輯 ---
        
        # 1. 決定目標單位
        mass_unit = self.unit_converter.imperial_units["Mass"] if use_imperial_units else self.unit_converter.default_units["Mass"]
        energy_unit = self.unit_converter.imperial_units["E"] if use_imperial_units else self.unit_converter.default_units["E"]

        # 2. 轉換質量
        display_mass = self.unit_converter.convert_from_si("Mass", total_mass_kg, mass_unit)
        lines.append(f"總質量 (Mass): {display_mass:.4f} {mass_unit}")

        # 3. 計算 SI 基礎單位的總能量 (J)
        # si_results['H'] 單位是 J/kg, total_mass_kg 單位是 kg -> 結果是 J
        total_h_si = si_results['H'] * total_mass_kg
        total_u_si = si_results['U'] * total_mass_kg
        
        # 4. 轉換總能量
        total_h_val = self.unit_converter.convert_from_si("E", total_h_si, energy_unit)
        total_u_val = self.unit_converter.convert_from_si("E", total_u_si, energy_unit)
            
        lines.append(f"總焓 (Total Enthalpy): {total_h_val:.4f} {energy_unit}")
        lines.append(f"總內能 (Total Int. Energy): {total_u_val:.4f} {energy_unit}")
        
        return "\n".join(lines)