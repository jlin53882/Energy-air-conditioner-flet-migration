# hvac_calculations/throttling.py
# 職責：節流閥相關計算

import CoolProp.CoolProp as CP
# 從兄弟模組導入依賴項
from .exergy import calculate_change_specific_exerpy1_2


def calculate_throttling_value( h1, h2):
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

def calculate_throttling_value_exerpy(x1, P1,P2,P0_dead, T0_dead, substance: str, m_dot):
    """
    計算穩態節流閥過程中的熵產生率和㶲破壞率。
    節流過程假設為: 焓值不變 (h2 = h1), 絕熱, 無功。
    注意: CoolProp 預設使用 SI 單位 (壓力: Pa, 溫度: K, 焓: J/kg, 熵: J/(kg*K))。
    使用者輸入時需注意單位轉換。
    :param x1: 節流前的乾度 Q1 (0~1)
    :param P1: 節流前壓力 (Pa)
    :param P2: 節流後實際工作壓力 (Pa)  <- 修正: 新增此參數
    :param P0_dead: 參考狀態壓力 (Pa)
    :param T0_dead: 參考狀態溫度 (K)
    :param substance: 流體名稱 (例如： 'R134a', 'Water')
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

    # 參考狀態：dead state
    # 計算dead狀態的焓值和熵值 h0_dead, s0_dead
    h0_dead= CP.PropsSI('H', 'P', P0_dead, 'T', T0_dead, substance)
    s0_dead= CP.PropsSI('S', 'P', P0_dead, 'T', T0_dead, substance)
    
    # specific exergy 計算

    """
    state 1: throttling state
    exerpy_specific_1=calculate_specific_exerpy(h1,s1,T0_dead,h0_dead,s0_dead) # 計算狀態1比焓值
    state 2: throttling state
    exerpy_specific_2=calculate_specific_exerpy(h2,s2,T0_dead,h0_dead,s0_dead) # 計算狀態2比焓值
    exerpy_ex_destruction_flow
    """
    #Ex_destruction_flow= m_dot*(exerpy_specific_1-exerpy_specific_2)
    Ex_destruction_flow= m_dot*calculate_change_specific_exerpy1_2(h1,h2,s1,s2,T0_dead,h0_dead,s0_dead)
  # 計算比焓值損失 KW
    return T2, Ex_destruction_flow