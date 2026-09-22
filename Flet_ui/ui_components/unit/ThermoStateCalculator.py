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

from domain.thermodynamics.reference_state import ReferenceStatePolicy
from domain.thermodynamics.state_service import ThermodynamicStateService
from .UnitConverter import UnitConverter # <-- 關鍵：導入我們的新類別

class ThermoStateCalculator:
    def __init__(self, unit_converter: UnitConverter):
        """
        初始化計算器。
        :param unit_converter: 一個 UnitConverter 的實例 (依賴注入)
        """
        self.unit_converter = unit_converter
        self._service = ThermodynamicStateService(unit_converter)
        self.properties = ["P", "T", "H", "S", "D", "Q", "V", "U"]
        
        # 理想氣體常數 (屬於計算邏輯)
        self.ideal_gas_props = {  
            "Air": {"R": 287.058, "Cp": 1005},  # J/(kg·K)
            "Water": {"R": 461.5, "Cp": 1870} # J/(kg·K)

        }

    @property
    def state_service(self) -> ThermodynamicStateService:
        """Expose the shared service for application composition."""
        return self._service

    def is_fluid_valid(self, fluid_name: str) -> bool:
        """Return whether the shared service recognizes a fluid."""
        return self._service.is_fluid_valid(fluid_name)
        
    def set_coolprop_ref_state(self, fluid_name: str, ref_state: str):
        """Set a CoolProp reference state through the shared mechanism."""
        self._service.set_reference_state(fluid_name, ref_state)
        
    def calculate_properties(
        self,
        fluid,
        known_props,
        is_ideal_gas=False,
        reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT,
    ):
        """Calculate properties under an explicit Flet reference-state policy."""
        return self._service.calculate_properties(
            fluid, known_props, is_ideal_gas, reference_state
        )
