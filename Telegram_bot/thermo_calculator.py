# thermo_calculator.py
# 核心計算引擎：負責所有熱力學性質的計算，與使用者介面分離。

import CoolProp.CoolProp as CP
import math
import numpy as np
from domain.thermodynamics.reference_state import ReferenceStatePolicy
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.psychrometrics.service import PsychrometricService
from infrastructure.psychrometrics import LegacyPsychrometricModelAdapter
from domain.thermodynamics.reference_state import ReferenceStateService
from domain.hvac.basic import (
    calculate_compression_ratio_si,
    calculate_compressor_work_si,
    calculate_condenser_heat_rate_si,
    calculate_evaporator_heat_rate_si,
)
from domain.units.converter import CanonicalUnitConverter

_REFERENCE_STATE = ReferenceStateService()


class ThermoCalculator:
    def __init__(self):
        """
        初始化熱力學計算器，包含所有需要的常數、單位定義和轉換邏輯。
        """
        self._canonical_converter = CanonicalUnitConverter()
        self._shared_state_service = ThermodynamicStateService(self._canonical_converter)
        self._psychrometric_service = PsychrometricService(LegacyPsychrometricModelAdapter())
        # --- 屬性與單位定義 ---
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
        # 更新：修改輸出格式以包含英文、中文和符號
        self.output_prop_names = {
            "P": "Pressure 壓力 (P)", 
            "T": "Temperature 溫度 (T)", 
            "H": "Enthalpy 焓 (h)", 
            "S": "Entropy 熵 (s)",
            "D": "Density 密度 (ρ)", 
            "Q": "Quality 乾度 (Q)", 
            "V": "Specific Volume 比容 (v)", 
            "U": "Internal Energy 內能 (u)"
        }
        self.default_units = {
            "P": "MPa", 
            "T": "°C", 
            "H": "kJ/kg", 
            "S": "kJ/(kg.K)",
            "D": "kg/m³", 
            "Q": "-", 
            "V": "m³/kg", 
            "U": "kJ/kg"
        }
        # 單位轉換映射表
        self.imperial_units = {
            "P": "psia", 
            "T": "°F", 
            "H": "Btu/lbm", 
            "S": "Btu/(lbm.R)",
            "D": "lbm/ft³", 
            "Q": "-", 
            "V": "ft³/lbm", 
            "U": "Btu/lbm"
        }
        self.display_precision = {
            "P": 4, 
            "T": 4, 
            "H": 5, 
            "S": 5, 
            "D": 4, 
            "Q": 4, 
            "V": 5, 
            "U": 4
        }
        
        # --- 單位轉換邏輯 (從 main.py 完整遷移) ---
        self.conversion_map = {
            "P": {
                "to_si": {
                    "Pa": lambda v: v, # 基本單位
                    "kPa": lambda v: v * 1000, # 1 kPa = 1000 Pa
                    "MPa": lambda v: v * 1_000_000,  # 1 MPa = 1,000,000 Pa
                    "bar": lambda v: v * 100_000,   # 1 bar = 100,000 Pa                    
                    "psia": lambda v: v * 6894.757, # 1 psia = 6894.757 Pa
                    "psi": lambda v: v * 6894.757, # 1 psi = 6894.757 Pa
                    "kg/cm^2": lambda v: v * 98066.5 # 1 kg/cm² = 98066.5 Pa
                },
                "from_si": {
                    "Pa": lambda v: v, # 基本單位
                    "kPa": lambda v: v / 1000, # 1 kPa = 1000 Pa
                    "MPa": lambda v: v / 1_000_000, # 1 MPa = 1,000,000 Pa
                    "bar": lambda v: v / 100_000, # 1 bar = 100,000 Pa
                    "psia": lambda v: v / 6894.757, # 1 psia = 6894.757 Pa
                    "psi": lambda v: v / 6894.757, # 1 psi = 6894.757 Pa
                    "kg/cm^2": lambda v: v / 98066.5 # 1 kg/cm² = 98066.5 Pa
                }
            },
            "T": {
                "to_si": {
                    "K": lambda v: v, # 基本單位
                    "°C": lambda v: v + 273.15, # 1 °C = 273.15 K
                    "°F": lambda v: (v - 32) * 5/9 + 273.15 # 1 °F = (°F - 32) * 5/9 + 273.15 K
                },
                "from_si": {
                    "K": lambda v: v, # 基本單位
                    "°C": lambda v: v - 273.15, # 1 °C = 273.15 K
                    "°F": lambda v: (v - 273.15) * 9/5 + 32 # 1 °F = (K - 273.15) * 9/5 + 32
                }
            },
            "H": {
                "to_si": {
                    "J/kg": lambda v: v,  # 基本單位
                    "kJ/kg": lambda v: v * 1000,  # 1 kJ/kg = 1000 J/kg
                    "Btu/lbm": lambda v: v * 2326 # 1 Btu/lbm = 2326 J/kg
                },
                "from_si": {
                    "J/kg": lambda v: v,  # 基本單位
                    "kJ/kg": lambda v: v / 1000,  # 1 kJ/kg = 1000 J/kg
                    "Btu/lbm": lambda v: v / 2326 # 1 Btu/lbm = 2326 J/kg
                },
                # For extensive properties
                "from_si_extensive": {
                    "J": lambda v: v,  # 基本單位
                    "kJ": lambda v: v / 1000,  # 1 kJ = 1000 J
                    "Btu": lambda v: v / 1055.056 # 1 Btu = 1055.056 J
                }
            },
            "S": {
                "to_si": {
                    "J/(kg.K)": lambda v: v,    # 基本單位
                    "kJ/(kg.K)": lambda v: v * 1000,    # 1 kJ/(kg.K) = 1000 J/(kg.K)
                    "Btu/(lbm.R)": lambda v: v * 4186.8 # 1 Btu/(lbm.R) = 4186.8 J/(kg.K)
                },
                "from_si": {
                    "J/(kg.K)": lambda v: v, 
                    "kJ/(kg.K)": lambda v: v / 1000,  # 1 kJ/(kg.K) = 1000 J/(kg.K)
                    "Btu/(lbm.R)": lambda v: v / 4186.8 # 1 Btu/(lbm.R) = 4186.8 J/(kg.K)
                }
            },
            "D": {
                "to_si": {
                    "kg/m³": lambda v: v,  # 基本單位
                    "kg/cm³": lambda v: v * 1_000_000,  # 1 kg/cm³ = 1,000,000 kg/m³
                    "lbm/ft³": lambda v: v * 16.0185 # 1 lbm/ft³ = 16.0185 kg/m³
                },
                "from_si": {
                    "kg/m³": lambda v: v,  # 基本單位
                    "kg/cm³": lambda v: v / 1_000_000,  # 1 kg/cm³ = 1,000,000 kg/m³
                    "lbm/ft³": lambda v: v / 16.0185 # 1 lbm/ft³ = 16.0185 kg/m³
                }
            },
            "V": {
                "to_si": {"m³/kg": lambda v: v},
                "from_si": { 
                    "m³/kg": lambda v: v, 
                    "ft³/lbm": lambda v: v * 16.0185} # Note: v is specific volume, not density
            },
            "U": {
                "to_si": {
                    "J/kg": lambda v: v,  # 基本單位
                    "kJ/kg": lambda v: v * 1000,  # 1 kJ/kg = 1000 J/kg
                    "Btu/lbm": lambda v: v * 2326 # 1 Btu/lbm = 2326 J/kg
                },
                "from_si": {
                    "J/kg": lambda v: v,  # 基本單位
                    "kJ/kg": lambda v: v / 1000,  # 1 kJ/kg = 1000 J/kg
                    "Btu/lbm": lambda v: v / 2326 # 1 Btu/lbm = 2326 J/kg
                },
                # For extensive properties
                "from_si_extensive": {
                    "J": lambda v: v, # 基本單位
                    "kJ": lambda v: v / 1000,  # 1 kJ = 1000 J
                    "Btu": lambda v: v / 1055.056 # 1 Btu = 1055.056 J
                }
            }
        }

        # --- 理想氣體常數 ---
        self.ideal_gas_props = {  
            "Air": {"R": 287.058, "Cp": 1005},  # J/(kg·K)
            "Water": {"R": 461.5, "Cp": 1870} # J/(kg·K)
        }

    def is_fluid_valid(self, fluid_name: str) -> bool:
        """Return whether the shared thermodynamic service recognizes a fluid."""
        return self._shared_state_service.is_fluid_valid(fluid_name)
        
    def _convert_to_si(self, prop_code, value, unit_code): 
        """
        將給定性質的值從指定單位轉換為 SI 單位。
        這是輸入值標準化的關鍵步驟。

        :param prop_code: 性質代碼 (e.g., 'P', 'T', 'V')
        :param value: 輸入值
        :param unit_code: 輸入值的單位代碼 (e.g., 'kPa', 'C')
        :return: 轉換為 SI 單位後的值 (CoolProp 標準)
        """
        if prop_code in self._canonical_converter.CORE_PROPERTIES - {"V"}:
            return self._canonical_converter.convert_to_si(prop_code, value, unit_code)

        if prop_code == 'V': # 特殊處理比容 (Specific Volume) V
            # 註解：在 calculate_properties 函數中，V 會被轉換為密度 D，
            # 但這裡的邏輯看起來是為了在 _convert_to_si 內部完成 V 到 D 的 SI 轉換。
            # V (比容) 的 SI 單位是 m³/kg，CoolProp 通常使用密度 D (kg/m³)
            
            # 先處理預設情況 (假設輸入單位已經是 SI 單位 m³/kg)
            density_val = 1 / value if value != 0 else 0 
            
            # 處理 ft³/lbm 到 m³/kg (CoolProp SI) 的轉換
            if unit_code == 'ft³/lbm':
                # 換算步驟：ft³/lbm -> (m³/kg) -> 得到 D (kg/m³)
                # 1 / ( value * 0.062428 )：
                # value (ft³/lbm) * 0.062428 = V_SI (m³/kg) 
                # 取倒數得到 D_SI (kg/m³)
                # 備註：0.062428 ≈ 1/16.01846 (1 lbm/ft³ = 16.01846 kg/m³)
                return 1 / (value * 0.062428) 
            
            # 如果不是 ft³/lbm，且 prop_code='V'，則返回預設的密度值 (假設輸入的比容單位是 m³/kg)
            return density_val
            
        # 尋找並執行定義在 self.conversion_map 字典中的轉換函數
        if prop_code in self.conversion_map and unit_code in self.conversion_map[prop_code]["to_si"]:
            return self.conversion_map[prop_code]["to_si"][unit_code](value)
        
        # 如果找不到轉換規則，假設輸入值已經是 SI 單位
        return value

    def _convert_from_si(self, prop_code, value_si, unit_code):
        """
        將 SI 單位值轉換為目標顯示單位 (通常是比性質，per mass)。

        :param prop_code: 性質代碼
        :param value_si: SI 單位的值
        :param unit_code: 目標單位代碼
        :return: 轉換為目標單位後的值
        """
        # 尋找並執行定義在 self.conversion_map 字典中的轉換函數
        if prop_code in self._canonical_converter.CORE_PROPERTIES - {"V"}:
            return self._canonical_converter.convert_from_si(prop_code, value_si, unit_code)

        if prop_code in self.conversion_map and unit_code in self.conversion_map[prop_code]["from_si"]:
            return self.conversion_map[prop_code]["from_si"][unit_code](value_si)
            
        # 如果找不到轉換規則，返回原始 SI 值
        return value_si

    def _convert_from_si_extensive(self, prop_code, value_si, unit_code):
        """
        轉換廣延性質 (Extensive Properties) 的單位 (例如總體積 V_total, 總焓 H_total)。
        廣延性質的單位通常不包含 /kg 或 /lbm。
        
        :param prop_code: 性質代碼 (e.g., 'H')
        :param value_si: SI 單位的值 (e.g., J)
        :param unit_code: 目標單位代碼 (e.g., 'kJ')
        :return: 轉換為目標廣延單位後的值
        """
        # 檢查是否存在廣延性質專用的轉換規則
        if prop_code in self.conversion_map and unit_code in self.conversion_map[prop_code].get("from_si_extensive", {}):
            return self.conversion_map[prop_code]["from_si_extensive"][unit_code](value_si)
            
        # 備用邏輯：如果找不到廣延性質轉換規則，則回退到比性質轉換
        # 此處移除單位中的 '/kg' 或 '/lbm'，假設轉換因子與比性質相同
        return self._convert_from_si(prop_code, value_si, unit_code.replace("/kg", "").replace("/lbm",""))
        
    def get_available_units(self, prop_code):
        """
        為給定的性質代碼 (prop_code) 安全地返回所有可用的單位列表。
        單位列表是從 'self.conversion_map' 字典中動態生成的，用於使用者介面顯示。
        
        :param prop_code: 性質代碼 (e.g., 'P', 'T', 'V')
        :return: 單位字串列表 (list of str)
        """
        # 排除乾度 (Q) - 乾度是一個無單位 (無量綱) 的性質
        if prop_code == "Q":
            return ["-"] # 乾度只有一個無單位選項 (或表示無單位)
            
        if prop_code in self.conversion_map:
            # 安全地從 conversion_map 中取得該性質的 'from_si' 字典
            # 'from_si' 的鍵即為所有可用的轉換單位名稱
            return list(self.conversion_map[prop_code].get("from_si", {}).keys())
        
        # 如果性質代碼不在轉換對應表中，返回空列表
        return []
        

    def calculate_properties(
        self,
        fluid,
        known_props,
        is_ideal_gas=False,
        reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT,
    ):
        """Calculate under Telegram's explicit default reference-state policy."""
        if any(prop == "V" for prop, _, _ in known_props):
            return self._calculate_legacy_properties(
                fluid, known_props, is_ideal_gas, reference_state
            )
        return self._shared_state_service.calculate_properties(
            fluid, known_props, is_ideal_gas, reference_state
        )

    def _calculate_legacy_properties(
        self,
        fluid,
        known_props,
        is_ideal_gas=False,
        reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT,
    ):
        """
        主計算函式，返回原始 SI 結果字典。
        負責輸入驗證、單位標準化、V/D 轉換，並分派給 CoolProp 或理想氣體計算。
        
        :param fluid: 流體名稱 (字串)
        :param known_props: 已知性質列表，格式為 [(屬性代碼, 值, 單位), ...]
        :param is_ideal_gas: 是否使用理想氣體模型 (布林值)
        :return: 一個包含計算結果的字典 (SI 單位)
        """
        # 檢查是否提供了足夠的獨立性質 (CoolProp 要求至少兩個)
        if len(known_props) < 2:
            raise ValueError("請至少提供兩組已知的性質。")

        # 處理比容 'V' 的輸入，將其轉換為密度 'D' (D = 1/V)
        known_props_processed = []
        for prop, value, unit in known_props:
            if prop == 'V':
                if value == 0: raise ValueError("比容 (V) 不能為零。")
                # 將 V 轉換為 SI 單位後取倒數，得到 SI 密度的值
                density_value = 1 / self._convert_to_si(prop, value, unit)
                known_props_processed.append(('D', density_value, 'kg/m³'))
            else:
                known_props_processed.append((prop, value, unit))
        
        # 將所有處理後的輸入性質統一轉換為 CoolProp 所需的 SI 單位格式 (屬性代碼, SI 值)
        known_props_si = []
        for prop, value, unit in known_props_processed:
            value_si = self._convert_to_si(prop, value, unit)
            known_props_si.append((prop, value_si))
        
        try:
            # 根據旗標選擇計算模型
            if is_ideal_gas:
                # 理想氣體：將輸入列表轉換為字典，方便內部函數查詢 P, T, D
                results_si = self._calculate_ideal_gas(fluid, dict(known_props_si))
            else:
                # 實際流體：使用 CoolProp 狀態方程
                results_si = self._calculate_coolprop(fluid, known_props_si, reference_state)
            
            return results_si

        except Exception as e:
            # 捕獲所有熱力學計算錯誤，並拋出帶有流體名稱的 RuntimeError
            raise RuntimeError(f"在計算 '{fluid}' 的性質時發生錯誤: {e}") from e

    def _calculate_coolprop(
        self,
        fluid,
        known_props_si,
        reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT,
    ):
        """Query the legacy Telegram path under an explicit policy."""
        with _REFERENCE_STATE.calculation_scope(fluid, reference_state):
            return self._calculate_coolprop_unlocked(fluid, known_props_si)

    def _calculate_coolprop_unlocked(self, fluid, known_props_si):
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

    def format_specific_properties(self, si_results, use_imperial_units):
        """將 SI 單位比性質結果格式化為可讀的字串，並添加詳細的相態描述。"""
        lines = ["--- 比性質 (Specific Properties) ---"]
        
        # 格式化所有性質
        for prop_code in self.properties:
            if prop_code not in si_results: continue

            result_si = si_results[prop_code]
            # 選擇要顯示的單位
            unit_to_display = self.imperial_units.get(prop_code) if use_imperial_units else self.default_units.get(prop_code)
            
            if prop_code == 'Q':
                # 乾度 (Q) 的特殊格式化
                # Q < 0 或 Q > 1 表示非飽和 (過冷或過熱)
                if result_si < 0 or result_si > 1:
                    display_val = "N/A (非飽和狀態)"
                else:
                    # Q 在 [0, 1] 之間表示飽和混合物
                    display_val = f"{result_si:.4f}"
                display_string = f"{display_val}"
            else:
                # 執行單位轉換並應用精度格式
                result_display = self._convert_from_si(prop_code, result_si, unit_to_display)
                precision = self.display_precision.get(prop_code, 2)
                display_string = f"{result_display:.{precision}f} {unit_to_display}"
            
            lines.append(f"{self.output_prop_names.get(prop_code, prop_code)}: {display_string}") 

        # --- 新增：相態描述邏輯 (更詳細的相態名稱) ---
        phase_string = si_results.get('phase', 'unknown')
        quality = si_results.get('Q', -999) # 獲取乾度值，用於判斷飽和/過冷/過熱
        final_phase_description = ""

        if phase_string == 'twophase':
            final_phase_description = "Saturated Mixture (飽和混合物)"
        elif phase_string == 'liquid':
            # 判斷是飽和液體還是過冷液體 (使用乾度 Q 作為輔助判斷)
            if quality == 0:
                final_phase_description = "Saturated Liquid (飽和液體)"
            else:
                final_phase_description = "Compressed / Subcooled Liquid (壓縮/過冷液體)"
        elif phase_string == 'gas':
            # 判斷是飽和蒸汽還是過熱蒸汽 (使用乾度 Q 作為輔助判斷)
            if quality == 1:
                final_phase_description = "Saturated Vapor (飽和蒸汽)"
            else:
                final_phase_description = "Superheated Vapor (過熱蒸汽)"
        elif phase_string == 'supercritical':
            final_phase_description = "Supercritical Fluid (超臨界流體)"
        elif phase_string == 'supercritical_gas':
            final_phase_description = "Supercritical Gas (超臨界氣體)"
        elif phase_string == 'supercritical_liquid':
            final_phase_description = "Supercritical Liquid (超臨界液體)"
        else:
            # 處理 CoolProp 返回的其他相態名稱
            final_phase_description = phase_string.capitalize()

        lines.append(f"\nPhase (相態): {final_phase_description}")
        
        # 返回格式化後的結果字串
        return "\n".join(lines)

    def format_extensive_properties(self, si_results, total_mass, use_imperial_units):
        """計算並格式化廣延性質"""
        lines = ["\n--- 廣延性質 (Extensive Properties) ---"]
        
        # 質量單位轉換
        mass_unit = "kg"
        if use_imperial_units:
            total_mass /= 2.20462 # kg to lbm for display, but calculation uses SI
            mass_unit = "lbm"
        lines.append(f"總質量 (Mass): {total_mass:.4f} {mass_unit}")

        # 總焓和總內能計算
        total_h_si = si_results['H'] * total_mass
        total_u_si = si_results['U'] * total_mass
        
        total_h_unit = "kJ" if not use_imperial_units else "Btu"
        total_u_unit = "kJ" if not use_imperial_units else "Btu"

        total_h = self._convert_from_si_extensive("H", total_h_si, total_h_unit)
        total_u = self._convert_from_si_extensive("U", total_u_si, total_u_unit)
        
        lines.append(f"總焓 (Total Enthalpy): {total_h:.4f} {total_h_unit}")
        lines.append(f"總內能 (Total Internal Energy): {total_u:.4f} {total_u_unit}")

        return "\n".join(lines)

# --- [新功能] 冷凍空調原理分析 ---
    
    def calculate_compressor_work(self, mass_flow_rate, h1, h2):
        """Return compressor work in kW for the legacy kJ/kg API."""
        return calculate_compressor_work_si(mass_flow_rate, h1 * 1000.0, h2 * 1000.0) / 1000.0
    def calculate_compression_ratio(self, p_suction_abs, p_discharge_abs):
        """Return the compression ratio through the shared SI equation."""
        return calculate_compression_ratio_si(p_suction_abs, p_discharge_abs)
    def calculate_evaporator_heat_rate(self, mass_flow_rate, h1, h2):
        """Return evaporator heat rate in kW for the legacy kJ/kg API."""
        return calculate_evaporator_heat_rate_si(mass_flow_rate, h1 * 1000.0, h2 * 1000.0) / 1000.0
    def calculate_condenser_heat_rate(self, mass_flow_rate, h1, h2):
        """Return condenser heat rate in kW for the legacy kJ/kg API."""
        return calculate_condenser_heat_rate_si(mass_flow_rate, h1 * 1000.0, h2 * 1000.0) / 1000.0

    def calculate_throttling_value(self, h1: float, h2: float) -> float:
        """
        計算節流過程後的焓值 (h2)。
        節流過程假設焓值不變: h2 = h1
        :param h1: 節流前的焓值 (單位: kJ/kg)
        :return: 節流後的焓值 (單位: kJ/kg)
        """
        if h1 < 0:
            raise ValueError("焓值必須為正數。")
        
        h2 = h1  # 節流過程中焓值保持不變
        return h2

    def calculate_throttling_value_exergy(self, x1: float, P1: float,P2: float,P0_dead: float, T0_dead: float, substance: str, m_dot: float) -> float:
        """
        計算穩態節流閥過程中的熵產生率和火用破壞率。

        節流過程假設為: 焓值不變 (h2 = h1), 絕熱, 無功。

        注意: CoolProp 預設使用 SI 單位 (壓力: Pa, 溫度: K, 焓: J/kg, 熵: J/(kg*K))。
        使用者輸入時需注意單位轉換。

        :param x1: 節流前的乾度 Q1 (0~1)
        :param P1: 節流前壓力 (Pa)
        :param P2: 節流後實際工作壓力 (Pa)  <- 修正: 新增此參數
        :param P0_dead: 參考狀態壓力 (Pa)
        :param T0_dead: 參考狀態溫度 (K)
        :param substance: 流體名稱 (e.g., 'R134a', 'Water')
        :param m_dot: 質量流率 (kg/s)
        :return: (Sgen_flow (W/K), Ex_destruction (W)) 
        """
        # CoolProp 函式 PropsSI('Output','Input1','Value1','Input2','Value2','Fluid') 用來查詢特定狀態下的性質。
        #定義單位:
        # 壓力: Pa
        # 溫度: K
        # 焓: J/kg
        # 熵: J/(kg*K)

        #狀態前1: 節流前狀態
        """
        計算節流前的焓值和熵值 h1, s1
        x1: 節流前的乾度
        P0: 節流dead狀態壓力
        P1: 節流前壓力
        substance: 流體名稱
        """
        s1 = CP.PropsSI('S', 'P', P1, 'Q', x1, substance)
        h1 = CP.PropsSI('H', 'P', P1, 'Q', x1, substance)

        #狀態後2: 節流後的狀態
        """
        計算節流後的焓值和熵值 h2, s2
        P0_dead: 節流dead狀態壓力
        T0_dead: 節流dead狀態溫度
        T2: 節流後溫度
        s2: 節流後熵值
        substance: 流體名稱
        """
        # 計算節流後的焓值和熵值 h2, s2
        h2=h1 # 節流過程中焓值保持不變
        s2 = CP.PropsSI('S', 'P', P2, 'H', h2, substance) #kJ/(kg K)
        T2= CP.PropsSI('T', 'P', P2, 'H', h2, substance) 

        #reference state: dead state
        # 計算dead狀態的焓值和熵值 h0_dead, s0_dead
        h0_dead= CP.PropsSI('H', 'P', P0_dead, 'T', T0_dead, substance)
        s0_dead= CP.PropsSI('S', 'P', P0_dead, 'T', T0_dead, substance)

        # 計算熵增
        Sgen_tv= s2 - s1  # 計算節流過程的熵增  可能用不到 (預留)
        Sgen_flow=Sgen_tv*m_dot # 熵增的流量形式

        #specific exergy calculation  
        #state 1: throttling state
        exergy_specific_1= (h1 - h0_dead) - T0_dead*(s1 - s0_dead)  # 計算狀態1比焓值

        #state 2: throttling state
        exergy_specific_2= (h2 - h0_dead) - T0_dead*(s2 - s0_dead)  # 計算狀態2比焓值

        Ex_destruction= m_dot*(exergy_specific_1 - exergy_specific_2)  # 計算比焓值損失 KW

        return Sgen_flow, Ex_destruction


    def calculate_psychrometric_properties(self, known_props: dict):
        """Format shared psychrometric results for Telegram responses."""
        altitude = known_props.get("altitude")
        tdb_c = known_props.get("Tdb")
        if "Twb" in known_props:
            result = self._psychrometric_service.calculate_from_tdb_twb(
                tdb_c + 273.15, known_props["Twb"] + 273.15, altitude
            )
            wet_bulb_label = "濕球溫度 (Wet-Bulb Temperature)"
            wet_bulb_value = result["Twb"] - 273.15
        elif "RH" in known_props:
            result = self._psychrometric_service.calculate_from_tdb_rh(
                tdb_c + 273.15, known_props["RH"], altitude
            )
            wet_bulb_label = "計算濕球溫度 (Calculated Wet-Bulb Temp)"
            wet_bulb_value = result["Twb"] - 273.15
        else:
            raise ValueError("請提供濕球溫度 (Twb) 或相對濕度 (RH) 其中之一。")

        return {
            "海拔高度 (Altitude)": f"{altitude:.2f} m",
            "大氣壓力 (Atmospheric Pressure)": f"{result['P']:.4f} Pa",
            "乾球溫度 (Dry-Bulb Temperature)": f"{tdb_c:.2f} °C",
            wet_bulb_label: f"{wet_bulb_value:.2f} °C",
            "露點溫度 (Dew Point Temperature)": f"{result['Tdp'] - 273.15:.2f} °C",
            "相對濕度 (Relative Humidity)": f"{result['RH']:.2f} %",
            "濕度比 (Humidity Ratio)": f"{result['W']:.6f} kg/kg",
            "濕空氣之焓值 (Enthalpy)": f"{result['H'] / 1000.0:.4f} kJ/kg",
            "濕空氣之比容 (Specific Volume)": f"{result['V']:.4f} m³/kg",
            "水蒸氣分壓 (Vapor Pressure)": f"{result['Pw']:.4f} Pa",
            "飽和狀態之水蒸氣分壓 (Saturation Pressure at Tdb)": f"{result['Pws_db']:.4f} Pa",
            "濕球溫度下，飽和狀態之水蒸氣分壓 (Saturation Pressure at Twb)": f"{result['Pws_wd']:.4f} Pa",
            "飽和濕空氣之濕度比 (Saturation Humidity Ratio at Tdb)": f"{result['Ws']:.6f} kg/kg",
            "濕球溫度下，飽和狀態之濕度比 (Saturation Humidity Ratio at Twb)": f"{result['Wss']:.6f} kg/kg",
        }
