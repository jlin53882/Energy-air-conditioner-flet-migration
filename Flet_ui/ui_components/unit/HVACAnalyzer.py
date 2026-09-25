# HVACAnalyzer.py
# 職責：作為 HVAC 計算的「外觀」(Facade)。
# 
# 這些是靜態方法，不需要實例化。
#
# 這個檔案不包含任何計算邏輯。它只是從 `hvac_calculations` 套件中導入
# 實際的函數，並將它們作為靜態方法附加到 HVACAnalyzer 類別上，
# 以確保對舊程式碼的 100% 向後兼容性。

# 從拆分的模組中導入所有計算函數
from .hvac_calculations.common import (
    calculate_steady_flow_variable,
    calculate_volume_flow_rate_relationship,
    calculate_Sgen,
    calculate_Sgen_flow
)
from .hvac_calculations.compressor import (
    calculate_compressor_work,
    calculate_compressor_work_heat_transfer,
    calculate_compressor_reversible_work,
    calculate_compression_ratio,
    calculate_compressor_exerpy_destruction,
    calculate_compressor_exergetic_efficiency_ratio,
    calculate_compressor_exergetic_efficiency_loss,
    calculate_isentropic_efficiency,
    calculate_volumetric_efficiency,
    calculate_refrigeration_capacity,
    calculate_compressor_example
)
from .hvac_calculations.heat_exchanger import (
    calculate_evaporator_heat_rate,
    
)
from .hvac_calculations.condenser_heat import (
    calculate_condenser_heat_rate,

)    

from .hvac_calculations.throttling import (
    calculate_throttling_value,
    calculate_throttling_value_exerpy
)
from .hvac_calculations.exergy import (
    calculate_specific_exerpy,
    calculate_specific_exerpy_flow,
    calculate_change_specific_exerpy1_2
)

class HVACAnalyzer:
    # --- 輔助計算方程式 ---
    calculate_steady_flow_variable = staticmethod(calculate_steady_flow_variable)
    calculate_volume_flow_rate_relationship = staticmethod(calculate_volume_flow_rate_relationship)
    
    # --- 熵計算 ---
    calculate_Sgen = staticmethod(calculate_Sgen)
    calculate_Sgen_flow = staticmethod(calculate_Sgen_flow)
    
    # --- 壓縮機相關計算方程式 ---
    calculate_compressor_work = staticmethod(calculate_compressor_work)
    calculate_compressor_work_heat_transfer = staticmethod(calculate_compressor_work_heat_transfer)
    calculate_compressor_reversible_work = staticmethod(calculate_compressor_reversible_work)
    calculate_compression_ratio = staticmethod(calculate_compression_ratio)
    calculate_compressor_exerpy_destruction = staticmethod(calculate_compressor_exerpy_destruction)
    calculate_compressor_exergetic_efficiency_ratio = staticmethod(calculate_compressor_exergetic_efficiency_ratio)
    calculate_compressor_exergetic_efficiency_loss = staticmethod(calculate_compressor_exergetic_efficiency_loss)
    calculate_isentropic_efficiency = staticmethod(calculate_isentropic_efficiency)
    calculate_volumetric_efficiency = staticmethod(calculate_volumetric_efficiency)
    calculate_refrigeration_capacity = staticmethod(calculate_refrigeration_capacity)
    calculate_compressor_example = staticmethod(calculate_compressor_example)

    # --- 蒸發器計算方程式 ---
    calculate_evaporator_heat_rate = staticmethod(calculate_evaporator_heat_rate)
    
    

    #--- 冷凝器計算方程式 ---
    calculate_condenser_heat_rate = staticmethod(calculate_condenser_heat_rate)

    
    # --- 節流閥相關函數 ---
    calculate_throttling_value = staticmethod(calculate_throttling_value)
    calculate_throttling_value_exerpy = staticmethod(calculate_throttling_value_exerpy)

    # --- 㶲 (Exergy) 相關函數 ---
    calculate_specific_exerpy = staticmethod(calculate_specific_exerpy)
    calculate_specific_exerpy_flow = staticmethod(calculate_specific_exerpy_flow)
    calculate_change_specific_exerpy1_2 = staticmethod(calculate_change_specific_exerpy1_2)