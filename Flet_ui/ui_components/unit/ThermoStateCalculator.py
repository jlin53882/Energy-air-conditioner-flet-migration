# ThermoStateCalculator.py
# 職責：執行熱力學計算 (CoolProp / 理想氣體)。
# 依賴 UnitConverter 進行單位標準化。
#不能直接計算比容
#在 CoolProp 函式庫中，代碼 'V' 代表的是黏度 (Viscosity)，而不是比容 (Specific Volume)

"""
🧩 各參考狀態詳細說明
名稱	全名	定義說明	典型用途
"IIR"	International Institute of Refrigeration	
定義：液體在 -40°C 時，焓 = 200 kJ/kg，熵 = 1.0 kJ/kg·K。
這是冷凍產業常用的基準。	❄️ 冷凍空調系統、壓縮機效率計算（例如 R134a、R22、R410A 系統）。

"ASHRAE"	American Society of Heating, Refrigerating, and Air-Conditioning Engineers	
定義：液體在 -40°C 時，焓 = 0，熵 = 0。	
🌡️ 北美 HVAC 標準資料、教科書與工程設計手冊（ASHRAE Fundamentals）。

"NBP"	Normal Boiling Point	
定義：流體在 常壓（1 atm）沸點 時，飽和液的 h = 0，s = 0。	
📘 熱力學理論、基礎物性比較（蒸發潛熱等）。

"DEF"	Default	
定義：CoolProp 內建的預設基準（通常是飽和液在三相點的 h=0, s=0）。	
🧪 一般程式預設狀態，除非特別說明。



"""

import CoolProp.CoolProp as CP
from .UnitConverter import UnitConverter # <-- 關鍵：導入我們的新類別

class ThermoStateCalculator:
    def __init__(self, unit_converter: UnitConverter):
        """
        初始化計算器。
        :param unit_converter: 一個 UnitConverter 的實例 (依賴注入)
        """
        self.unit_converter = unit_converter
        self.properties = ["P", "T", "H", "S", "D", "Q", "V", "U"]
        
        # 理想氣體常數 (屬於計算邏輯)
        self.ideal_gas_props = {  
            "Air": {"R": 287.058, "Cp": 1005},  # J/(kg·K)
            "Water": {"R": 461.5, "Cp": 1870} # J/(kg·K)

        }
        # 預設的參考點標準
        self.current_ref_code = "ASHRAE" 
        # --- 新增結束 ---

    def is_fluid_valid(self, fluid_name: str) -> bool:
        """
        檢查流體名稱在 CoolProp 中是否有效 (屬於計算邏輯)。
        """
        try:
            CP.PropsSI('Tcrit', fluid_name)
            return True
        except ValueError:
            return False
        
    # --- 新增：設定 CoolProp 參考點的方法 ---
    def set_coolprop_ref_state(self, fluid_name: str, ref_state: str):
        """
        設定特定物質的 CoolProp 參考點。
        
        :param fluid_name: 物質名稱 (e.g., 'R134a')
        :param ref_state: 參考點代碼 (e.g., 'Default', 'ASHRAE', 'IIR', 'NBP')
        
        此方法被 PropertyTab 呼叫，用來處理 UI 中參考點標準的變更。
        """
        # CoolProp 接受的代碼需要是大寫字母，並且通常只使用前幾個字母。
        # 為了相容性，我們將傳入的 ref_state 參數（如 'ASHRAE'）轉換為 CoolProp 實際接受的代碼。
        coolprop_code = ref_state.upper() 

        # 處理 'Default' 選項，CoolProp 接受 'DEF'
        if coolprop_code == "DEFAULT":
            coolprop_code = "DEF"
        
        # 由於 CoolProp 的 set_reference_state 函式在輸入無效時可能拋出 ValueError 或 KeyError
        # 我們將其包裝在 try/except 中，以便提供更清晰的錯誤訊息 (如果需要)。
        try:
            # 執行關鍵步驟：呼叫 CoolProp 核心函式
            CP.set_reference_state(fluid_name, coolprop_code)
            # 記住剛剛設定的參考點代碼
            self.current_ref_code = ref_state 
            # --- 新增結束 ---
            
        except ValueError as e:
            # 如果 CoolProp 在執行時遇到問題 (例如，流體不支持該參考點)
            error_msg = f"CoolProp 錯誤: 無法設定物質 '{fluid_name}' 的參考點為 '{coolprop_code}'。請檢查物質是否為純流體。"
            print(error_msg)
            # 重新拋出錯誤讓呼叫方 (property_tab.py) 捕獲
            raise ValueError(error_msg) from e 

    # --- 新增結束 ---
        
    def calculate_properties(self, fluid, known_props, is_ideal_gas=False):
        """
        主計算函式，返回原始 SI 結果字典。
        """
        if len(known_props) < 2:
            raise ValueError("請至少提供兩組已知的性質。")

        known_props_processed = []
        for prop, value, unit in known_props:
            if prop == 'V':
                if value == 0: raise ValueError("比容 (V) 不能為零。")
                # 使用 UnitConverter 將 V 轉換為 SI (m³/kg)
                v_si = self.unit_converter.convert_to_si(prop, value, unit)
                # 轉換為密度 D (SI)
                known_props_processed.append(('D', 1 / v_si, 'kg/m³'))
            else:
                known_props_processed.append((prop, value, unit))
        
        known_props_si = []
        for prop, value, unit in known_props_processed:
            # 使用 UnitConverter 將所有輸入轉為 SI
            value_si = self.unit_converter.convert_to_si(prop, value, unit)
            known_props_si.append((prop, value_si))
        
        try:
            if is_ideal_gas:
                results_si = self._calculate_ideal_gas(fluid, dict(known_props_si))
            else:
                results_si = self._calculate_coolprop(fluid, known_props_si)
            return results_si
        except Exception as e:
            raise RuntimeError(f"在計算 '{fluid}' 的性質時發生錯誤: {e}") from e

    def _calculate_coolprop(self, fluid, known_props_si):
        # 提取 CoolProp 所需的前兩個 SI 輸入性質
        prop1, val1 = known_props_si[0]
        prop2, val2 = known_props_si[1]
        
        results_si = {}
        # 遍歷類別中定義的所有需要計算的性質
        for prop_code in self.properties:
            if prop_code == "V":
                # V 必須通過密度 D 來計算 (V = 1/D)
                density = CP.PropsSI('D', prop1, val1, prop2, val2, fluid)
                # 穩定性檢查：防止除以零，如果密度為零則比容為無窮大
                results_si[prop_code] = 1 / density if density != 0 else float('inf')
            else:
                # 使用 CoolProp.PropsSI 函數計算其他性質
                results_si[prop_code] = CP.PropsSI(prop_code, prop1, val1, prop2, val2, fluid)
        
        # 使用 CoolProp.PhaseSI 獲取熱力學相態 (如 'liquid', 'gas', 'twophase' 等)
        results_si['phase'] = CP.PhaseSI(prop1, val1, prop2, val2, fluid)
        return results_si

    def _calculate_ideal_gas(self, fluid, input_dict):
        # 檢查流體常數是否存在
        if fluid not in self.ideal_gas_props:
            raise ValueError(f"找不到 {fluid} 的理想氣體常數。")
        
        # 獲取 R (個別氣體常數) 和 Cp (定壓比熱)
        R = self.ideal_gas_props[fluid]["R"]
        Cp = self.ideal_gas_props[fluid]["Cp"]
        # 計算 Cv (定容比熱)
        Cv = Cp - R
        
        si_results = {}
        # 理想氣體狀態方程 P = D * R * T 的三種求解情況
        if 'P' in input_dict and 'T' in input_dict:
            si_results['P'] = input_dict['P']
            si_results['T'] = input_dict['T']
            si_results['D'] = input_dict['P'] / (R * input_dict['T']) # 計算密度 D
        elif 'P' in input_dict and 'D' in input_dict:
            si_results['P'] = input_dict['P']
            si_results['D'] = input_dict['D']
            si_results['T'] = input_dict['P'] / (input_dict['D'] * R) # 計算溫度 T
        elif 'T' in input_dict and 'D' in input_dict:
            si_results['T'] = input_dict['T']
            si_results['D'] = input_dict['D']
            si_results['P'] = input_dict['D'] * R * si_results['T'] # 計算壓力 P
        else:
            # 輸入組合不符合要求
            raise ValueError("理想氣體計算需要 P&T, P&D 或 T&D 的組合。")

        # 計算焓 H 和內能 U (假設參考點)
        if 'T' in si_results:
            si_results['H'] = Cp * si_results['T']
            si_results['U'] = Cv * si_results['T']
            
        # 計算比容 V = 1/D
        if 'D' in si_results and si_results['D'] != 0:
            si_results['V'] = 1 / si_results['D']
        else:
            si_results['V'] = float('inf')
        
        # 理想氣體模式下的特殊值設定
        si_results['S'] = 0 # 理想氣體模式下通常不計算熵的絕對值
        si_results['Q'] = -1 # 理想氣體沒有乾度概念 (視為非飽和)
        si_results['phase'] = 'gas'
        return si_results