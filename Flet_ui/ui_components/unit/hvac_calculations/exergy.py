# hvac_calculations/exergy.py
# 職責：㶲 (Exergy) 相關計算

def calculate_specific_exerpy(h1, s1, T0_dead, ho_dead, s0_dead):
    """
    計算比㶲（Specific Exergy, ex）

    比㶲定義為流體在狀態 1 相對於死狀態（Dead State, 0）所能產生的最大有用功。
    公式為： specific_exerpy_1= (h1 - ho_dead) - T0_dead*(s1 - s0_dead)

    參數:
    h1 (float): 狀態 1 的比焓 (Specific Enthalpy)。
    ho_dead (float): 死狀態 (Dead State, 0) 的比焓。
    T0_dead (float): 死狀態 (Dead State, 0) 的溫度 (C)。
    s1 (float): 狀態 1 的比熵 (Specific Entropy)。
    s0_dead (float): 死狀態 (Dead State, 0) 的比熵。

    回傳:
    float: 狀態 1 的比㶲 $ex_1$。
    """
    # 根據比㶲公式計算 (流動㶲 component)
    specific_exerpy_1= (h1 - ho_dead) - T0_dead*(s1 - s0_dead)
    """
    print("h1:",h1)
    print("ho_dead:",ho_dead)
    print("T0_dead:",T0_dead)
    print("s1:",s1)
    print("s0_dead:",s0_dead)
    print("specific_exerpy_1:",specific_exerpy_1)
    """
    return specific_exerpy_1

def calculate_specific_exerpy_flow(m_dot,h1, s1, T0_dead , ho_dead, s0_dead):
    """
    計算㶲流率
    specific_exerpy_1 = (h1 - ho_dead) - T0_dead*(s1 - s0_dead)
    specific_exerpy_flow_1 = m_dot * specific_exerpy_1
    
    參數:
    h1 (float): 狀態 1 的比焓。
    ho_dead (float): 死狀態 (0) 的比焓。
    T0_dead (float): 死狀態 (0) 的溫度 (C)。
    s1 (float): 狀態 1 的比熵。
    s0_dead (float): 死狀態 (0) 的比熵。
    m_dot (float): 質量流率 (kg/s)。

    回傳:
    float: 狀態 1 的㶲流率
    """
    
    # 修正後的建議
    specific_exerpy_1 = (h1 - ho_dead) - T0_dead*(s1 - s0_dead)
    specific_exerpy_flow_1 = m_dot * specific_exerpy_1
    return specific_exerpy_flow_1


def calculate_change_specific_exerpy1_2(h1,h2, s1, s2 ,T0_dead,ho_dead, s0_dead):
    """
    計算單一流體在流動中比㶲變化量 
    參數:
    h2 (float): 狀態 2 的比焓。
    h1 (float): 狀態 1 的比焓。
    s2 (float): 狀態 2 的比熵。
    s1 (float): 狀態 1 的比熵。
    T0_dead (float): 死狀態 (0) 的絕對溫度 (K)。

    回傳:
    float: 從狀態 1 到狀態 2 的比㶲變化量 (h2 - h1) - T0_dead*(s2 - s1)。
            specific_exerpy_1 = (h1 - ho_dead) - T0_dead*(s1 - s0_dead)
            specific_exerpy_2 = (h2 - ho_dead) - T0_dead*(s2 - s0_dead)
            specific_exerpy_change_1_2 = specific_exerpy_1 - specific_exerpy_2
    """
    # 根據比㶲變化量公式計算
    specific_exerpy_1= calculate_specific_exerpy(h1, s1, T0_dead, ho_dead, s0_dead)
    specific_exerpy_2= calculate_specific_exerpy(h2, s2, T0_dead, ho_dead, s0_dead)
    specific_exerpy_change_1_2= specific_exerpy_1-specific_exerpy_2
    return specific_exerpy_change_1_2

def calculate_change_specific_exerpy1_2_simple(h1,h2, s1, s2 ,T0_dead):
    """
    計算單一流體在流動中比㶲變化量 
    specific_exerpy_change_1_2= h2-h1-T0_dead*(s2-s1)
    """
    # 根據比㶲變化量公式計算
    specific_exerpy_change_1_2= h2-h1-T0_dead*(s2-s1)
    return specific_exerpy_change_1_2
