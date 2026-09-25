# hvac_calculations/exergy.py
# 職責：㶲 (Exergy) 相關計算
#
# 單位契約：本檔公式都是齊次式，不做任何單位換算，輸出單位跟隨輸入單位。
# 焓與熵必須使用同一套能量單位，溫度一律為絕對溫度 (K)：
# - 舊版 kJ API（compressor.py 的呼叫端）：h = kJ/kg、s = kJ/(kg·K)
#   → 比㶲為 kJ/kg，乘上質量流率 (kg/s) 後為 kW。
# - CoolProp SI（throttling.py 的呼叫端）：h = J/kg、s = J/(kg·K)
#   → 比㶲為 J/kg，乘上質量流率 (kg/s) 後為 W。

def calculate_specific_exerpy(h1, s1, T0_dead, ho_dead, s0_dead):
    """
    計算比㶲（Specific Exergy, ex）

    比㶲定義為流體在狀態 1 相對於死狀態（Dead State, 0）所能產生的最大有用功。
    公式為： specific_exerpy_1= (h1 - ho_dead) - T0_dead*(s1 - s0_dead)

    參數（單位見檔案開頭的單位契約）:
    h1 (float): 狀態 1 的比焓（kJ/kg 或 J/kg）。
    ho_dead (float): 死狀態 (Dead State, 0) 的比焓（與 h1 同單位）。
    T0_dead (float): 死狀態 (Dead State, 0) 的絕對溫度 (K)。
    s1 (float): 狀態 1 的比熵（kJ/(kg·K) 或 J/(kg·K)，與 h1 同一套能量單位）。
    s0_dead (float): 死狀態 (Dead State, 0) 的比熵（與 s1 同單位）。

    回傳:
    float: 狀態 1 的比㶲 $ex_1$（與 h1 同單位）。
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
    
    參數（單位見檔案開頭的單位契約）:
    h1 (float): 狀態 1 的比焓（kJ/kg 或 J/kg）。
    ho_dead (float): 死狀態 (0) 的比焓（與 h1 同單位）。
    T0_dead (float): 死狀態 (0) 的絕對溫度 (K)。
    s1 (float): 狀態 1 的比熵（與 h1 同一套能量單位）。
    s0_dead (float): 死狀態 (0) 的比熵（與 s1 同單位）。
    m_dot (float): 質量流率 (kg/s)。

    回傳:
    float: 狀態 1 的㶲流率（h 為 kJ/kg 時為 kW；h 為 J/kg 時為 W）。
    """
    
    # 修正後的建議
    specific_exerpy_1 = (h1 - ho_dead) - T0_dead*(s1 - s0_dead)
    specific_exerpy_flow_1 = m_dot * specific_exerpy_1
    return specific_exerpy_flow_1


def calculate_change_specific_exerpy1_2(h1,h2, s1, s2 ,T0_dead,ho_dead, s0_dead):
    """
    計算單一流體由狀態 1 到狀態 2 的比㶲減少量 ex1 − ex2。

    死狀態的焓與熵在相減時互相抵消，因此結果等於
    (h1 − h2) − T0_dead·(s1 − s2) = −[(h2 − h1) − T0_dead·(s2 − s1)]，
    與 calculate_change_specific_exerpy1_2_simple 的正負號相反。

    參數（單位見檔案開頭的單位契約）:
    h1 (float): 狀態 1 的比焓（kJ/kg 或 J/kg）。
    h2 (float): 狀態 2 的比焓（與 h1 同單位）。
    s1 (float): 狀態 1 的比熵（與 h1 同一套能量單位）。
    s2 (float): 狀態 2 的比熵（與 s1 同單位）。
    T0_dead (float): 死狀態 (0) 的絕對溫度 (K)。
    ho_dead (float): 死狀態的比焓（與 h1 同單位；不影響結果）。
    s0_dead (float): 死狀態的比熵（與 s1 同單位；不影響結果）。

    回傳:
    float: 比㶲減少量 ex1 − ex2（與 h1 同單位），其中
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
    計算單一流體由狀態 1 到狀態 2 的比㶲增加量 ex2 − ex1（不需死狀態）。

    specific_exerpy_change_1_2 = h2 - h1 - T0_dead*(s2 - s1)
    正負號與 calculate_change_specific_exerpy1_2（ex1 − ex2）相反。

    參數（單位見檔案開頭的單位契約）:
    h1, h2 (float): 狀態 1、2 的比焓（kJ/kg 或 J/kg）。
    s1, s2 (float): 狀態 1、2 的比熵（與 h 同一套能量單位）。
    T0_dead (float): 死狀態的絕對溫度 (K)。

    回傳:
    float: 比㶲增加量 ex2 − ex1（與 h 同單位）。
    """
    # 根據比㶲變化量公式計算
    specific_exerpy_change_1_2= h2-h1-T0_dead*(s2-s1)
    return specific_exerpy_change_1_2
