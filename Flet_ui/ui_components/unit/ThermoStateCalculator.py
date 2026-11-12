# ThermoStateCalculator.py
# 職責：執行熱力學計算 (CoolProp / 理想氣體)。
# 依賴 UnitConverter 進行單位標準化。
#不能直接計算比容
#在 CoolProp 函式庫中，代碼 'V' 代表的是黏度 (Viscosity)，而不是比容

"""
各參考狀態（CoolProp reference state）說明；Auto 規則見 domain/thermodynamics/thermo_policy.py。

"IIR"    International Institute of Refrigeration：0 °C 飽和液體 h = 200 kJ/kg、s = 1 kJ/(kg·K)。
         冷凍工程 SI 表格常用（ASHRAE Handbook 2025 SI 多數冷媒表亦採此慣例）。
"ASHRAE" −40 °C 飽和液體 h = 0、s = 0（北美 IP 單位表格常見）。注意：名稱為 ASHRAE 的 CoolProp
         代碼不等於所有 ASHRAE SI 表格的基準。
"NBP"    正常沸點飽和液體 h = 0、s = 0；CoolProp 8 以 101.325 kPa 定義（以安裝版本實測驗證）。
"DEF"    CoolProp 該流體狀態方程的預設基準，各流體不同（Water 為 IAPWS-95 三相點飽和液 u = 0、s = 0）。

焓、熵的絕對值依基準改變；同一流體、同一狀態方程下的壓力、溫度、密度、乾度與焓差、潛熱不變。
不同基準的焓、熵不可直接相減。
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
        
        # 舊介面相容：理想氣體常數集中於 domain.thermodynamics.ideal_gas。
        self.ideal_gas_props = self._service.ideal_gas_props

    @property
    def state_service(self) -> ThermodynamicStateService:
        """公開共用 service，供 application composition 使用。

回傳：
    ThermodynamicStateService：函數計算或處理後的結果。"""
        return self._service

    def is_fluid_valid(self, fluid_name: str) -> bool:
        """回傳共用 service 是否辨識指定流體。

參數：
    fluid_name (str): 函數輸入值。

回傳：
    bool：函數計算或處理後的結果。"""
        return self._service.is_fluid_valid(fluid_name)
        
    def set_coolprop_ref_state(self, fluid_name: str, ref_state: str):
        """透過共用機制設定 CoolProp reference state。

參數：
    fluid_name (str): 函數輸入值。
    ref_state (str): 函數輸入值。

回傳：
    無。"""
        self._service.set_reference_state(fluid_name, ref_state)
        
    def calculate_properties(
        self,
        fluid,
        known_props,
        is_ideal_gas=False,
        reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT,
    ):
        """在明確的 Flet reference-state policy 下計算性質。

參數：
    fluid (未指定型別): 函數輸入值。
    known_props (未指定型別): 函數輸入值。
    is_ideal_gas (未指定型別): 函數輸入值。
    reference_state (ReferenceStatePolicy | str): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
        return self._service.calculate_properties(
            fluid, known_props, is_ideal_gas, reference_state
        )
