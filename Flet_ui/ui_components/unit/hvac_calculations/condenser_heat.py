# 職責：冷凝器計算
#condenser_heat_rate.py
from .exergy import calculate_change_specific_exerpy1_2_simple
from domain.hvac.basic import calculate_condenser_heat_rate_si
import CoolProp.CoolProp as CP
from domain.thermodynamics.reference_state import ReferenceStateService

_REFERENCE_STATE = ReferenceStateService()

def calculate_condenser_heat_rate(mass_flow_rate, h1, h2):
    """針對舊版 kJ/kg API 回傳以 kW 為單位的冷凝器熱傳率。

參數：
    mass_flow_rate (未指定型別): 函數輸入值。
    h1 (未指定型別): 函數輸入值。
    h2 (未指定型別): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
    return calculate_condenser_heat_rate_si(mass_flow_rate, h1 * 1000.0, h2 * 1000.0) / 1000.0

def ebe_water_cooled_condenser(m_dot_R, h1, h2, m_dot_w, h3, h4):
    """
    計算水冷式冷凝器 (圖 3.23b) 的能量平衡。
    假設 m_dot_1 = m_dot_2 = m_dot_R 且 m_dot_3 = m_dot_4 = m_dot_w。
    
    EBE: m_dot_R * (h1 - h2) = m_dot_w * (h4 - h3)
    
    參數:
    m_dot_R (float): 製冷劑質量流量
    h1 (float): 製冷劑入口 (1) 比焓
    h2 (float): 製冷劑出口 (2) 比焓
    m_dot_w (float): 冷卻水質量流量
    h3 (float): 冷卻水入口 (3) 比焓
    h4 (float): 冷卻水出口 (4) 比焓

    回傳:
    float: (製冷劑釋放的能量) - (冷卻水吸收的能量) 的差值。若平衡，則接近 0。
    """
    Q_dot_R = m_dot_R * (h1 - h2) # 製冷劑放熱
    Q_dot_w = m_dot_w * (h4 - h3) # 冷卻水吸熱
    
    return Q_dot_R - Q_dot_w

#不用放UI
def enbe_air_cooled_condenser(m_dot_1, s1, m_dot_2, s2, Q_dot_H, T, S_dot_gen):
    """
    計算空冷式冷凝器 (圖 3.23a) 的熵平衡差值。

    EnBE: m_dot_1 * s1 + S_dot_gen = m_dot_2 * s2 + Q_dot_H / T
    
    參數:
    m_dot_1 (float): 製冷劑入口 (1) 質量流量
    s1 (float): 製冷劑入口 (1) 比熵
    m_dot_2 (float): 製冷劑出口 (2) 質量流量
    s2 (float): 製冷劑出口 (2) 比熵
    Q_dot_H (float): 傳遞給高溫介質的熱傳率
    T (float): 傳熱邊界溫度 (K 或 R)
    S_dot_gen (float): 熵生成率

    回傳:
    float: (m_dot_1 * s1 + S_dot_gen) - (m_dot_2 * s2 + Q_dot_H / T) 的差值。
    """
    input_terms = (m_dot_1 * s1) + S_dot_gen
    output_terms = (m_dot_2 * s2) + (Q_dot_H / T)
    
    return input_terms - output_terms

#不用放UI
def enbe_water_cooled_condenser(m_dot_R, s1, s2, m_dot_w, s3, s4, S_dot_gen=None):
    """
    計算水冷式冷凝器 (圖 3.23b) 的熵平衡。
    假設 m_dot_1 = m_dot_2 = m_dot_R 且 m_dot_3 = m_dot_4 = m_dot_w。
    
    EnBE: S_dot_gen = m_dot_R * (s2 - s1) + m_dot_w * (s4 - s3)
    
    參數:
    m_dot_R (float): 製冷劑質量流量
    s1 (float): 製冷劑入口 (1) 比熵
    s2 (float): 製冷劑出口 (2) 比熵
    m_dot_w (float): 冷卻水質量流量
    s3 (float): 冷卻水入口 (3) 比熵
    s4 (float): 冷卻水出口 (4) 比熵
    S_dot_gen (float, optional): 熵生成率。若提供，則用於驗證平衡；否則，函數計算 S_dot_gen。

    回傳:
    float: 若 S_dot_gen=None，回傳計算出的熵生成率；否則，回傳平衡差值。
    """
    # 熵輸出 - 熵輸入
    entropy_change_R = m_dot_R * (s2 - s1)
    entropy_change_w = m_dot_w * (s4 - s3)
    
    # 計算 S_dot_gen (公式右側 - 公式左側)
    S_dot_gen_calculated = entropy_change_R + entropy_change_w
    
    if S_dot_gen is None:
        return S_dot_gen_calculated
    else:
        # 驗證平衡：S_dot_gen_calculated 應等於 S_dot_gen
        return S_dot_gen_calculated - S_dot_gen

#不用放UI
def exbe_air_cooled_condenser(m_dot_1, ex_1, m_dot_2, ex_2, Q_dot_H, T, T0_dead, Ex_dot_dest=None):
    """
    計算空冷式冷凝器 (圖 3.23a) 的㶲平衡差值。

    ExBE: Ex_dot_1 = Ex_dot_2 + Ex_dot_Q + Ex_dot_dest
    Ex_dot_Q = (1 - T0_dead / T) * Q_dot_H
    Ex_dot_i = m_dot_i * ex_i
    
    參數:
    m_dot_1 (float): 製冷劑入口 (1) 質量流量
    ex_1 (float): 製冷劑入口 (1) 比㶲
    m_dot_2 (float): 製冷劑出口 (2) 質量流量
    ex_2 (float): 製冷劑出口 (2) 比㶲
    Q_dot_H (float): 傳遞給高溫介質的熱傳率
    T (float): 傳熱邊界溫度 (K 或 R)
    T0_dead (float): 參考環境溫度 (K 或 R)
    Ex_dot_dest (float, optional): 㶲破壞率。如果提供，則使用此值；否則，需要平衡。

    回傳:
    float: (輸入㶲) - (輸出㶲 + 㶲破壞) 的差值。
    """
    Ex_dot_1 = m_dot_1 * ex_1
    Ex_dot_2 = m_dot_2 * ex_2
    Ex_dot_Q = (1 - (T0_dead / T)) * Q_dot_H
    
    # 允許不提供 Ex_dot_dest，則函數將計算差值
    if Ex_dot_dest is None:
        # 計算㶲破壞率 (Ex_dot_dest) 的平衡值
        # Ex_dot_dest_calc = Ex_dot_1 - Ex_dot_2 - Ex_dot_Q
        return Ex_dot_1 - Ex_dot_2 - Ex_dot_Q
    else:
        # 驗證給定的㶲破壞率
        output_exergy = Ex_dot_2 + Ex_dot_Q + Ex_dot_dest
        return Ex_dot_1 - output_exergy
    
def exbe_water_cooled_condenser_simplified(m_dot_R, ex_1, ex_2, m_dot_w, ex_3, ex_4, Ex_dot_dest=None):
    """
    計算水冷式冷凝器 (圖 3.23b) 的㶲平衡。
    假設 m_dot_1 = m_dot_2 = m_dot_R 且 m_dot_3 = m_dot_4 = m_dot_w。
    
    ExBE: Ex_dot_dest = m_dot_R * (ex_1 - ex_2) - m_dot_w * (ex_4 - ex_3)
    
    參數:
    m_dot_R (float): 製冷劑質量流量
    ex_1 (float): 製冷劑入口 (1) 比㶲
    ex_2 (float): 製冷劑出口 (2) 比㶲
    m_dot_w (float): 冷卻水質量流量
    ex_3 (float): 冷卻水入口 (3) 比㶲
    ex_4 (float): 冷卻水出口 (4) 比㶲
    Ex_dot_dest (float, optional): 㶲破壞率。若提供，則用於驗證平衡；否則，函數計算 Ex_dot_dest。

    回傳:
    float: 若 Ex_dot_dest=None，回傳計算出的㶲破壞率；否則，回傳平衡差值。
    """
    # 㶲輸入 - 㶲輸出
    Ex_dot_decrease_R = m_dot_R * (ex_1 - ex_2) # 製冷劑㶲減少量 (輸入㶲)
    Ex_dot_increase_w = m_dot_w * (ex_4 - ex_3) # 冷卻水㶲增加量 (輸出㶲)
    
    # 計算 Ex_dot_dest (輸入㶲 - 輸出㶲)
    Ex_dot_dest_calculated = Ex_dot_decrease_R - Ex_dot_increase_w
    
    if Ex_dot_dest is None:
        return Ex_dot_dest_calculated
    else:
        # 驗證平衡：Ex_dot_dest_calculated 應等於 Ex_dot_dest
        return Ex_dot_dest_calculated - Ex_dot_dest


def calculate_exergy_condenser(m_dot_R, h1, h2,T0_dead):
    """
    計算 空冷凝器Exergy
    calculate_condenser_heat_rate= m_dot_R * (h1-h2)  => Q_dot_H
    exergy_condenser=calculate_condenser_heat_rate(m_dot_R, h1, h2)*(1-T0_dead/T)
    """
    T=T0_dead #理想狀態

    exergy_condenser=calculate_condenser_heat_rate(m_dot_R, h1, h2)*(1-T0_dead/T)
    return exergy_condenser


def exergy_efficiency_condenser(m_dot_R, h1, h2, s1, s2, T0_dead, Q_dot_H=None, T=None, Ex_dot_dest=None):
    """
    計算冷凝器的㶲效率 (eta_ex,con)。適用於空冷式冷凝器 (圖 3.23a)。

    參數:
    m_dot_R (float): 製冷劑 (R) 質量流量 (kg/s，m_dot_1 或 m_dot_2, 假設 m_dot_1 = m_dot_2 = m_dot_R)
    h1 (float): 製冷劑入口 (1) 比焓 (kJ/kg)
    h2 (float): 製冷劑出口 (2) 比焓 (kJ/kg)
    s1 (float): 製冷劑入口 (1) 比熵 (kJ/(kg·K))
    s2 (float): 製冷劑出口 (2) 比熵 (kJ/(kg·K))
    T0_dead (float): 參考環境溫度 (K)
    Q_dot_H (float, optional): 傳熱率。用於第一個計算公式。
    T (float, optional): 傳熱邊界溫度 (K 或 R)。用於第一個計算公式。
    Ex_dot_dest (float, optional): 㶲破壞率。用於第三個計算公式。

    回傳:
    float: 冷凝器的㶲效率。
    """
    # 㶲輸入 (Ex_dot_1 - Ex_dot_2) - 製冷劑㶲減少量（kW）
    # 注意：根據比㶲公式 ex = (h - h0) - T0 * (s - s0)，
    # ex1 - ex2 = (h1 - h2) - T0 * (s1 - s2)
    # calculate_change_specific_exerpy1_2_simple 回傳 ex2 - ex1，因此取負號。
    Ex_dot_decrease = -m_dot_R * calculate_change_specific_exerpy1_2_simple(h1, h2, s1, s2, T0_dead)
    
    
    if Ex_dot_decrease == 0:
        return float('nan') # 避免除以零

    if Q_dot_H is not None and T is None:
        # 使用 Q_dot_H 和 T (第一個公式)
        T=T0_dead #理想狀態
        Ex_dot_Q = Q_dot_H * (1 - (T0_dead / T))
        return Ex_dot_Q / Ex_dot_decrease
    
    elif Ex_dot_dest is not None:
        # 使用 Ex_dot_dest (第三個公式)
        return 1.0 - (Ex_dot_dest / Ex_dot_decrease)
        
    else:
        raise ValueError("必須提供 (Q_dot_H 和 T) 或 Ex_dot_dest 才能計算㶲效率。")
    
def calculate_condenser_example_air(m_dot_R, P1, P2, T1, T2,P0_dead, T0_dead,substance: str,ref_state_code: str):
    """在共用狀態同步機制下計算舊版冷凝器範例。

參數：
    m_dot_R (未指定型別): 函數輸入值。
    P1 (未指定型別): 函數輸入值。
    P2 (未指定型別): 函數輸入值。
    T1 (未指定型別): 函數輸入值。
    T2 (未指定型別): 函數輸入值。
    P0_dead (未指定型別): 函數輸入值。
    T0_dead (未指定型別): 函數輸入值。
    substance (str): 函數輸入值。
    ref_state_code (str): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
    with _REFERENCE_STATE.calculation_scope(substance, ref_state_code):
        return _calculate_condenser_example_air_unlocked(
            m_dot_R, P1, P2, T1, T2, P0_dead, T0_dead, substance, ref_state_code
        )

def _calculate_condenser_example_air_unlocked(m_dot_R, P1, P2, T1, T2,P0_dead, T0_dead,substance: str,ref_state_code: str):
    """
    計算空冷 冷凝器 傳熱
    Exergy loss
    Exergy efficiency
    """
    #state 1 (冷凝器入口狀態的熱力學性質計算)
    # H: 比焓
    h1_j_kg=CP.PropsSI('H', 'P', P1, 'T', T1, substance)
    # S: 比熵
    s1_j_kgk=CP.PropsSI('S', 'P', P1, 'T', T1, substance)
    
    #單位換算
    h1 = h1_j_kg / 1000.0  # J/kg -> kJ/kg
    s1 = s1_j_kgk / 1000.0 # J/(kg.K) -> kJ/(kg.K)

    #state 2 (壓縮機出口狀態的熱力學性質計算)
    h2_j_kg=CP.PropsSI('H', 'P', P2, 'T', T2, substance)
    s2_j_kgk=CP.PropsSI('S', 'P', P2, 'T', T2, substance)

    #單位換算
    h2 = h2_j_kg / 1000.0
    s2 = s2_j_kgk / 1000.0

    #state reference (死狀態/環境狀態)
    # 本函式的輸出不需要死狀態的比焓與比熵；仍查詢一次，讓無法求得的死狀態
    # 輸入與原本一樣直接引發錯誤。
    CP.PropsSI('H', 'P', P0_dead, 'T', T0_dead, substance)
    CP.PropsSI('S', 'P', P0_dead, 'T', T0_dead, substance)

    Q_dot_H= calculate_condenser_heat_rate(m_dot_R, h1, h2)
    eta_ex=exergy_efficiency_condenser(m_dot_R, h1, h2, s1, s2, T0_dead)
    Ex_dest_con=calculate_exergy_condenser(m_dot_R, h1, h2,T0_dead)
    Ex_dest_con_eff=exergy_efficiency_condenser(m_dot_R, h1, h2, s1, s2, T0_dead,Q_dot_H)
    return Q_dot_H,eta_ex,Ex_dest_con,Ex_dest_con_eff