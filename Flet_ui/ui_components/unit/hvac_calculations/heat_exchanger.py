# hvac_calculations/heat_exchanger.py
# 職責：蒸發器計算

    #蒸發器的計算方程式
def calculate_evaporator_heat_rate( mass_flow_rate,h1, h2 ):
    """
    計算蒸發器熱交換率 (Qe)。
    公式: Qeva = ṁ * (h2 - h1)
    :param mass_flow_rate: 質量流率 (單位: kg/s)
    :param h1: 蒸發器入口焓值 (單位: kJ/kg)
    :param h2: 蒸發器出口焓值 (單位: kJ/kg)
    :return: 蒸發器熱交換率 (單位: kW)
    """
    #print("h1:",h1)
    #print("h2:",h2)
    #print("mass_flow_rate:",mass_flow_rate)
    if mass_flow_rate < 0 or h1 < 0 or h2 < 0:
        raise ValueError("質量流率和焓值必須為正數。")
    elif h2 < h1:
        raise ValueError("出口焓值必須大於入口焓值。")
    heat_rate_kw = mass_flow_rate * (h2 - h1)
   
    return heat_rate_kw
