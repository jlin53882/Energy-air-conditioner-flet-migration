# hvac_calculations/compressor.py
# 職責：壓縮機相關計算

import CoolProp.CoolProp as CP
from domain.thermodynamics.reference_state import ReferenceStateService

_REFERENCE_STATE = ReferenceStateService()
from domain.hvac.basic import (
    calculate_compression_ratio_si,
    calculate_compressor_work_si,
)
# 從兄弟模組導入依賴項
from .exergy import calculate_specific_exerpy,calculate_change_specific_exerpy1_2

#壓縮機相關計算方程式
def calculate_compressor_work(mass_flow_rate, h1, h2):
    """Return compressor work in kW for the legacy kJ/kg API."""
    return calculate_compressor_work_si(mass_flow_rate, h1 * 1000.0, h2 * 1000.0) / 1000.0

def calculate_compressor_work_heat_transfer( mass_flow_rate,h1, h2, Q_out):
    """
    計算壓縮機所作的功 (Win) 有外部熱能傳輸情況。
    公式: Win = ṁ * (h2 - h1)+ Q_out
    :param mass_flow_rate: 質量流率 (單位: kg/s)
    :param h1: 壓縮機入口焓值 (單位: kJ/kg)
    :param h2: 壓縮機出口焓值 (單位: kJ/kg)
    :param Q_out: 外部熱傳輸量 (單位: kW)
    :return: 壓縮機功 (單位: kW)

    """
    # ṁ (kg/s) * (h2 (kJ/kg) - h1 (kJ/kg)) 的結果直接就是 kJ/s，即 kW
    if mass_flow_rate < 0 or h1 < 0 or h2 < 0:
        raise ValueError("質量流率和焓值必須為正數。")
    
    work_kw = mass_flow_rate * (h2 - h1)+ Q_out
    return work_kw    


def calculate_compressor_reversible_work(mass_flow_rate , h1, h2, s1, s2,T0_dead):
    """
    計算壓縮機可逆的功 (Wrev)。
    公式: Wrev = ṁ * ((h2 - h1 - T0_dead * (s2 - s1))
    :param mass_flow_rate: 質量流率 (單位: kg/s)
    """
    Wrev=mass_flow_rate*((h2-h1)-T0_dead*(s2-s1))
    return Wrev



def calculate_compression_ratio(p_suction_abs, p_discharge_abs):
    """Return the compression ratio through the shared SI equation."""
    return calculate_compression_ratio_si(p_suction_abs, p_discharge_abs)

def calculate_compressor_exerpy_destruction(mass_flow_rate, h1,h2, s1, s2 ,T0_dead,ho_dead, s0_dead):
    """
    計算壓縮機的㶲破壞 (Ex_destruction)。
    公式: Ex_destruction = mass_flow_rate * [ (h2 - h1) - T0_dead * (s2 - s1) ] + W_in

    :param mass_flow_rate: 質量流率 (kg/s)
    :param h1: 壓縮機入口比焓 (J/kg)
    :param s1: 壓縮機入口比熵 (J/(kg.K))
    :param h2: 壓縮機出口比焓 (J/kg)
    :param s2: 壓縮機出口比熵 (J/(kg.K))
    :param T0_dead: 參考狀態溫度 (K)
    :return: 㶲破壞 (W)
    """
    # 計算壓縮機的功 (W_in)
    W_in = calculate_compressor_work(mass_flow_rate, h1, h2) # 這裡的h1, h2是J/kg，W_in會是W
    # 計算入口和出口的比㶲
    Ex_change = mass_flow_rate*calculate_change_specific_exerpy1_2(h1,h2, s1, s2 ,T0_dead,ho_dead, s0_dead,)
    
    #print("Ex_change:",Ex_change)
    #print("W_in:",W_in)
    # 㶲破壞 = 進入的功+可逆功
    Ex_destruction =Ex_change+W_in
    return Ex_destruction


def calculate_compressor_exergetic_efficiency_ratio(mass_flow_rate, h1,h2, s1, s2 ,T0_dead,ho_dead, s0_dead):
    """
    計算壓縮機的㶲效率 (Wrev / Win)。
    """
    Wrev=calculate_compressor_exerpy_destruction(mass_flow_rate, h1,h2, s1, s2 ,T0_dead,ho_dead, s0_dead)
    #print("Wrev:",Wrev)
    Win=calculate_compressor_work(mass_flow_rate, h1,h2)
    #print("Win:",Win)
    if Win <= 0:
        raise ValueError("實際輸入功 (Win) 必須大於零。")
    if Wrev < 0:
        raise ValueError("可逆功 (Wrev) 必須大於或等於零。")
        
    efficiency = 1-(Wrev / Win)
    
    if efficiency < 0 or efficiency > 1.05:
        raise ValueError(f"計算出的效率 ({efficiency:.4f}) 不在合理範圍。")
        
    return efficiency


def calculate_compressor_exergetic_efficiency_loss(mass_flow_rate, h1,h2, s1, s2 ,T0_dead,ho_dead, s0_dead):
    """
    計算壓縮機的㶲效率 (1 - Ex_destruction / Win)。
    """
    Ex_destruction =calculate_compressor_exerpy_destruction(mass_flow_rate, h1,h2, s1, s2 ,T0_dead,ho_dead,s0_dead)
    Win=calculate_compressor_work(mass_flow_rate, h1,h2)
    #print("Ex_destruction:",Ex_destruction)
    #print("Win:",Win)
    if Win <= 0:
        raise ValueError("實際輸入功 (Win) 必須大於零。")
    if Ex_destruction < 0:
         raise ValueError("㶲破壞率 (Ex_destruction) 必須大於或等於零。")
         
    efficiency = 1.0 - (Ex_destruction / Win)
    
    if efficiency < 0 or efficiency > 1.05:
        raise ValueError(f"計算出的效率 ({efficiency:.4f}) 不在合理範圍。")
        
    return efficiency


def calculate_isentropic_efficiency(h1_inlet_enthalpy, h2_actual_enthalpy,h2s_isentropic_enthalpy) :
    """
    計算壓縮機的等熵效率 (Isentropic Efficiency)。

    公式 (3.8): η_comp, isen = (h2s - h1) / (h2 - h1)

    參數 (Parameters):
    h2s_isentropic_enthalpy (float): 冷媒在等熵壓縮後出口處的比焓 (kJ/kg)。
    h1_inlet_enthalpy (float): 冷媒在壓縮機入口處的比焓 (kJ/kg)。
    h2_actual_enthalpy (float): 冷媒在實際壓縮後出口處的比焓 (kJ/kg)。

    回傳值 (Returns):
    float: 壓縮機的等熵效率 (無單位)。

    例外處理 (Raises):
    ValueError: 如果實際功 (分母 h2 - h1) 為零，表示無法計算。
    """

    # 實際功 (分母)
    actual_work = h2_actual_enthalpy - h1_inlet_enthalpy

    if actual_work == 0:
        raise ValueError("實際壓縮功 (h2 - h1) 為零，無法計算等熵效率。")

    # 等熵功 (分子)
    isentropic_work = h2s_isentropic_enthalpy - h1_inlet_enthalpy

    # 等熵效率
    isentropic_efficiency = isentropic_work / actual_work

    return isentropic_efficiency


def calculate_volumetric_efficiency(R_clearance_ratio, v1_inlet_spec_volume, v2_discharge_spec_volume) :
    """
    計算壓縮機的容積效率 (Volumetric Efficiency)。

    公式 (3.9): η_comp, vol = 1 - R * ((v1 / v2) - 1)

    參數 (Parameters):
    R_clearance_ratio (float): 餘隙容積與排氣量之比 (R)。
    v1_inlet_spec_volume (float): 冷媒在壓縮機入口處的比容 (v1) (m^3/kg)。
    v2_discharge_spec_volume (float): 冷媒在壓縮機出口處的比容 (v2) (m^3/kg)。

    回傳值 (Returns):
    float: 壓縮機的容積效率 (無單位)。

    例外處理 (Raises):
    ValueError: 如果出口比容 (v2) 為零，表示無法計算。
    """

    if v2_discharge_spec_volume == 0:
        raise ValueError("冷媒在壓縮機出口處的比容 (v2) 為零，無法計算容積效率。")

    # 括號內的部分: (v1 / v2) - 1
    term_in_parentheses = (v1_inlet_spec_volume / v2_discharge_spec_volume) - 1

    # 容積效率
    volumetric_efficiency = 1 - R_clearance_ratio * term_in_parentheses

    return volumetric_efficiency


def calculate_refrigeration_capacity(Vdot_displacement_rate, eta_vol_efficiency, rho1_inlet_density, h1_evaporator_exit_enthalpy, h4_evaporator_inlet_enthalpy) :
    """
    計算製冷量 (Refrigeration Capacity)。
    
    公式 (3.10): Q_dot_R = V_dot * η_comp, vol * ρ1 * (h1 - h4)

    參數 (Parameters):
    Vdot_displacement_rate (float): 壓縮機的容積排氣量 (V_dot) (m^3/s)。
    eta_vol_efficiency (float): 壓縮機容積效率 (η_comp, vol) (無單位)。
    rho1_inlet_density (float): 冷媒在壓縮機入口處的密度 (ρ1) (kg/m^3)。
    h1_evaporator_exit_enthalpy (float): 冷媒在蒸發器出口/壓縮機入口的比焓 (h1) (kJ/kg)。
    h4_evaporator_inlet_enthalpy (float): 冷媒在蒸發器入口的比焓 (h4) (kJ/kg)。

    回傳值 (Returns):
    float: 製冷量 (Q_dot_R) (kW)。
    
    注意: 由於 (m^3/s) * (kg/m^3) * (kJ/kg) = kJ/s = kW，所以結果的單位是 kW (千瓦)。
    """
    
    # 焓差: h1 - h4
    enthalpy_difference = h1_evaporator_exit_enthalpy - h4_evaporator_inlet_enthalpy
    
    # 製冷量
    Qdot_R = Vdot_displacement_rate * eta_vol_efficiency * rho1_inlet_density * enthalpy_difference
    
    return Qdot_R


def calculate_compressor_example(R,P1,T1,P2,T2,P0_dead,T0_dead,V1_dot,substance: str,ref_state_code: str):
    """Calculate the legacy compressor example under shared state synchronization."""
    with _REFERENCE_STATE.calculation_scope(substance, ref_state_code):
        return _calculate_compressor_example_unlocked(
            R, P1, T1, P2, T2, P0_dead, T0_dead, V1_dot, substance, ref_state_code
        )

def _calculate_compressor_example_unlocked(R,P1,T1,P2,T2,P0_dead,T0_dead,V1_dot,substance: str,ref_state_code: str):
    """
    計算壓縮機 例題內容

    此函式用於計算壓縮機的多項熱力學性能參數，包括
    進出口狀態、死狀態（參考狀態）的性質、等熵過程的焓值、
    比㶲（比㶲）、容積效率、輸入功、等熵效率，以及
    㶲（㶲）破壞量與㶲效率。

    參數:
    R (float): 壓縮比 (Compression Ratio, P2/P1) 或與體積效率相關的參數，通常為容積效率計算公式中的參數。
               **請注意：此處 R 的實際物理意義取決於 calculate_volumetric_efficiency 的定義。**
    P1 (float): 壓縮機入口壓力 (Pa 或 kPa，依 CoolProp 單位而定)
    T1 (float): 壓縮機入口溫度 (K)
    P2 (float): 壓縮機出口壓力 (Pa 或 kPa)
    T2 (float): 壓縮機出口溫度 (K)
    P0_dead (float): 死狀態（環境）壓力 (Pa 或 kPa)
    T0_dead (float): 死狀態（環境）溫度 (K)
    V1_dot (float): 壓縮機入口體積流率 (m^3/s)
    substance (str): 工作流體物質名稱 (e.g., 'R134a', 'Air', 'Water')

    回傳:
    tuple: 包含 (Eff_vol, Win, Eff_isen, Ex_destruction_flow, EFF_comp_ex)
           分別為 容積效率、壓縮機輸入功、等熵效率、流動㶲破壞率、㶲效率
    """

    #state 1 (壓縮機入口狀態的熱力學性質計算)
    # H: 比焓 (Specific Enthalpy)
    h1_j_kg=CP.PropsSI('H', 'P', P1, 'T', T1, substance)
    # S: 比熵 (Specific Entropy)
    s1_j_kgk=CP.PropsSI('S', 'P', P1, 'T', T1, substance)
    # V: 比容 (Specific Volume)
    D1=CP.PropsSI('D', 'P', P1, 'T', T1, substance)

    #單位換算
    h1 = h1_j_kg / 1000.0  # J/kg -> kJ/kg
    s1 = s1_j_kgk / 1000.0 # J/(kg.K) -> kJ/(kg.K)
    v1=1/D1

    #state 2 (壓縮機出口狀態的熱力學性質計算)
    h2_j_kg=CP.PropsSI('H', 'P', P2, 'T', T2, substance)
    s2_j_kgk=CP.PropsSI('S', 'P', P2, 'T', T2, substance)
    D2=CP.PropsSI('D', 'P', P2, 'T', T2, substance)

    #單位換算
    h2 = h2_j_kg / 1000.0
    s2 = s2_j_kgk / 1000.0
    v2=1/D2

    #state reference (死狀態/環境狀態的熱力學性質計算)
    # 這是計算比㶲（比㶲）時的參考狀態
    h0_dead_j_kg=CP.PropsSI('H', 'P', P0_dead, 'T', T0_dead, substance)
    s0_dead_j_kgk=CP.PropsSI('S', 'P', P0_dead, 'T', T0_dead, substance)
   
    #單位換算
    h0_dead = h0_dead_j_kg / 1000.0
    s0_dead = s0_dead_j_kgk / 1000.0

    #calculate Isentroty 1-2 (計算等熵過程的出口狀態)
    # 等熵過程：假設為理想壓縮過程，熵值不變 (s2s = s1)
    s2s=s1 
    s2s_for_coolprop = s2s * 1000.0 #轉換成j/kg*k 
    # H2s: 理想等熵壓縮過程結束時的焓值 (使用 P2 和 s2s=s1 決定)
    h2s_j_kg=CP.PropsSI('H', 'P', P2, 'S', s2s_for_coolprop, substance)
    h2s = h2s_j_kg / 1000.0
    #calculate exerpy state 1 (計算入口狀態的比㶲/比㶲)
    # ex1 = h1 - h0 - T0 * (s1 - s0)
    ex1=calculate_specific_exerpy(h1,s1,T0_dead,h0_dead,s0_dead)

    #calculate exerpy state 2 (計算出口狀態的比㶲/比㶲)
    ex2=calculate_specific_exerpy(h2,s2,T0_dead,h0_dead,s0_dead)

    #calculate efficiency compress (計算壓縮機效率)

    # 容積效率 (Volumetric Efficiency): 用於活塞式壓縮機，表示實際吸入氣體體積與活塞掃描體積的比值
    Eff_vol=calculate_volumetric_efficiency(R,v1,v2)

    # 質量流率計算 (Mass Flow Rate): mass_flow_rate = V_dot / v
    m1_dot=V1_dot/v1

    # 壓縮機輸入功計算 (Compressor Work Rate, Win): 根據能量平衡 W_in = mass_flow_rate * (h2 - h1)
    Win=calculate_compressor_work(m1_dot,h1,h2)

    # 等熵效率計算 (Isentropic Efficiency): 效率 = (理想功) / (實際功) = (h2s - h1) / (h2 - h1)
    Eff_isen=calculate_isentropic_efficiency(h1,h2,h2s)

    # 㶲破壞率計算 (exerpy Destruction Rate): Ex_destruction_flow
    Ex_destruction_flow=m1_dot*(ex1-ex2)+Win 

    # 㶲效率計算 (Exergetic Efficiency): 效率 = (㶲產出) / (㶲輸入)
    EFF_comp_ex=calculate_compressor_exergetic_efficiency_loss(m1_dot,h1,h2,s1,s2,T0_dead,h0_dead,s0_dead)

    return Eff_vol,Win ,Eff_isen,Ex_destruction_flow ,EFF_comp_ex