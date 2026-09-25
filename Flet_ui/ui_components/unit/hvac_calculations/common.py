# hvac_calculations/common.py
# 職責：通用的熱力學計算 (穩態流、熵)

#輔助計算方程式
def calculate_steady_flow_variable(
    rho1=None, A1=None, V1=None,
    rho2=None, A2=None, V2=None,
    known_variable="mass_flow_rate_1" # 用於指定要計算的變數
):
    """
    計算穩態流動（Steady Flow）中，基於質量守恆 (rho*A*V = constant) 的未知變數。

    質量流率的關係式為：rho1 * A1 * V1 = rho2 * A2 * V2

    參數:
    - rho1 (float): 截面 1 的密度 (Density)
    - A1 (float): 截面 1 的截面積 (Area)
    - V1 (float): 截面 1 的流速 (Velocity)
    - rho2 (float): 截面 2 的密度
    - A2 (float): 截面 2 的截面積
    - V2 (float): 截面 2 的流速
    - known_variable (str): 必須是 'rho1', 'A1', 'V1', 'rho2', 'A2', 'V2' 之一，
                            指定要計算的未知變數。

    回傳:
    - float: 計算出的未知變數值。
    - ValueError: 如果輸入的參數不正確（例如缺少計算所需的值）。
    """

    # 檢查並確保只有一個變數是 None (即未知數)
    variables = {
        "rho1": rho1, "A1": A1, "V1": V1,
        "rho2": rho2, "A2": A2, "V2": V2
    }

    # 刪除已知變數字典中的指定未知變數，以便檢查其餘是否為數字
    if known_variable in variables:
        # 將要計算的變數設為 None 以進行後續檢查
        variables[known_variable] = None
    else:
        raise ValueError(f"指定的未知變數 '{known_variable}' 無效。必須是 'rho1', 'A1', 'V1', 'rho2', 'A2', 'V2' 之一。")


    # 檢查是否有且只有一個未知數
    unknowns = [key for key, value in variables.items() if value is None]

    if len(unknowns) != 1:
        # 如果使用者沒有輸入所有已知數，或輸入了超過一個 None，則提示錯誤
        raise ValueError("必須提供五個已知變數的值，並將一個未知變數 (例如 'V2') 設為 None 來計算。")

    # 將已知變數提取到各自的區塊
    try:
        # 截面 1 的所有變數
        R1, Area1, Vel1 = variables["rho1"], variables["A1"], variables["V1"]
        # 截面 2 的所有變數
        R2, Area2, Vel2 = variables["rho2"], variables["A2"], variables["V2"]
    except TypeError:
        # 為了更友善的錯誤提示
        raise ValueError("所有已知變數都必須是有效的數字 (float/int)。")

    # 計算截面 1 和截面 2 的質量流率乘積
    # 質量流率： mass_flow_rate = rho * A * V

    if known_variable in ["rho1", "A1", "V1"]:
        # 如果未知數在截面 1，則計算截面 2 的已知乘積
        # mass_flow_rate_2_product = R2 * Area2 * Vel2
        mass_flow_rate_2_product = R2 * Area2 * Vel2

        # 截面 1 的質量流率： mass_flow_rate_1 = R1 * Area1 * Vel1 = mass_flow_rate_2_product

        # 計算未知數 (例如 V1 = mass_flow_rate_2_product / (R1 * Area1))
        if known_variable == "rho1":
            return mass_flow_rate_2_product / (Area1 * Vel1)
        elif known_variable == "A1":
            return mass_flow_rate_2_product / (R1 * Vel1)
        elif known_variable == "V1":
            return mass_flow_rate_2_product / (R1 * Area1)

    elif known_variable in ["rho2", "A2", "V2"]:
        # 如果未知數在截面 2，則計算截面 1 的已知乘積
        # mass_flow_rate_1_product = R1 * Area1 * Vel1
        mass_flow_rate_1_product = R1 * Area1 * Vel1

        # 截面 2 的質量流率： mass_flow_rate_2 = R2 * Area2 * Vel2 = mass_flow_rate_1_product

        # 計算未知數 (例如 V2 = mass_flow_rate_1_product / (R2 * Area2))
        if known_variable == "rho2":
            return mass_flow_rate_1_product / (Area2 * Vel2)
        elif known_variable == "A2":
            return mass_flow_rate_1_product / (R2 * Vel2)
        elif known_variable == "V2":
            return mass_flow_rate_1_product / (R2 * Area2)

    # 理論上不應該到達這裡
    raise Exception("發生未知錯誤。請檢查輸入。")
"""
# --- 使用範例 ---
# 假設已知條件：
# 截面 1 (入口): 密度 rho1=1.2 kg/m^3, 面積 A1=0.5 m^2, 流速 V1=10 m/s
# 截面 2 (出口): 密度 rho2=1.0 kg/m^3, 面積 A2=0.2 m^2
# 欲求：截面 2 的流速 V2

try:
    V2_result = calculate_steady_flow_variable(
        rho1=1.2, A1=0.5, V1=10.0,
        rho2=1.0, A2=0.2, V2=None,  # V2 是未知數
        known_variable="V2"       # 告訴函數要計算 V2
    )
    print(f"截面 2 的流速 V2 (m/s) 為: {V2_result:.4f}")

    # 驗證質量流率：
    m_dot_1 = 1.2 * 0.5 * 10.0
    m_dot_2 = 1.0 * 0.2 * V2_result
    print(f"質量流率 1: {m_dot_1:.4f} kg/s")
    print(f"質量流率 2: {m_dot_2:.4f} kg/s")

except ValueError as e:
    print(f"計算錯誤: {e}")    
"""  

def calculate_volume_flow_rate_relationship(rho1=None, V_dot1=None, rho2=None, V_dot2=None, known_variable="V_dot2"):
    """
    計算基於體積流率和密度的質量守恆 (rho * V_dot = constant) 的未知變數。

    質量流率的關係式為：rho1 * V_dot1 = rho2 * V_dot2

    參數:
    - rho1 (float): 截面 1 的密度
    - V_dot1 (float): 截面 1 的體積流率
    - rho2 (float): 截面 2 的密度
    - V_dot2 (float): 截面 2 的體積流率
    - known_variable (str): 必須是 'rho1', 'V_dot1', 'rho2', 'V_dot2' 之一。
    """

    variables = {"rho1": rho1, "V_dot1": V_dot1, "rho2": rho2, "V_dot2": V_dot2}

    if known_variable not in variables:
         raise ValueError(f"指定的未知變數 '{known_variable}' 無效。")

    # 確保要計算的變數設為 None
    variables[known_variable] = None

    unknowns = [key for key, value in variables.items() if value is None]

    if len(unknowns) != 1:
        raise ValueError("必須提供三個已知變數的值，並將一個未知變數設為 None 來計算。")

    R1, VD1, R2, VD2 = variables["rho1"], variables["V_dot1"], variables["rho2"], variables["V_dot2"]

    try:
        if known_variable in ["rho1", "V_dot1"]:
            # rho1 * V_dot1 = R2 * VD2
            product_2 = R2 * VD2
            if known_variable == "rho1":
                return product_2 / VD1
            elif known_variable == "V_dot1":
                return product_2 / R1
        elif known_variable in ["rho2", "V_dot2"]:
            # rho2 * V_dot2 = R1 * VD1
            product_1 = R1 * VD1
            if known_variable == "rho2":
                return product_1 / VD2
            elif known_variable == "V_dot2":
                return product_1 / R2
    except TypeError:
        raise ValueError("所有已知變數都必須是有效的數字 (float/int)。")
"""
# 範例：計算 V_dot2
# V_dot1 = 0.5 m^3/s, rho1 = 1.2 kg/m^3, rho2 = 1.0 kg/m^3
try:
    V_dot2_result = calculate_volume_flow_rate_relationship(
        rho1=1.2, V_dot1=0.5,
        rho2=1.0, V_dot2=None, 
        known_variable="V_dot2"
    )
    print(f"\n截面 2 的體積流率 V_dot2 (m^3/s) 為: {V_dot2_result:.4f}")
except ValueError as e:
    print(f"計算錯誤: {e}")    
"""

def calculate_Sgen( s1, s2):
    """
    計算比熵變化 (Specific Entropy Change)。
    此值在開放系統中常被用作計算實際熵生成流率的基礎。
    公式: Δs = s2 - s1
    
    參數:
    s1 (float): 初始比熵 (例如： kJ/(kg.K))。
    s2 (float): 最終比熵 (例如： kJ/(kg.K))。
    
    回傳值:
    float: 比熵變化 Δs (與輸入單位一致)。
    """
    delta_s = s2 - s1
    return delta_s

def calculate_Sgen_flow(m_dot,s1, s2):
    """
    計算穩態流動系統中的熵生成流率 (Entropy Generation Rate, S_gen_dot)。
    
    公式: S_gen_dot = m_dot * (s2 - s1) + (Q_dot / T_boundary)
    此函數忽略與邊界熱傳遞引起的熵變化，僅計算因流動和系統內部不可逆性引起的流動項。

    參數:
    s1 (float): 入口比熵 (kJ/(kg.K))。
    s2 (float): 出口比熵 (kJ/(kg.K))。
    m_dot (float): 質量流率 (kg/s)。

    回傳值:
    float: 熵生成流率 (kW/K 或 kJ/(s·K))。
    """
    # 比熵變化 (Δs)
    delta_s = s2 - s1 
    
    # 質量流率 * 比熵變化 (流動項的熵流率差)
    Sgen_flow_term = m_dot * delta_s 
    
    return Sgen_flow_term

