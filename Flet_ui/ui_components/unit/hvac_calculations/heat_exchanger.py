# hvac_calculations/heat_exchanger.py
# 職責：蒸發器計算
from domain.hvac.basic import calculate_evaporator_heat_rate_si

    #蒸發器的計算方程式
def calculate_evaporator_heat_rate(mass_flow_rate, h1, h2):
    """Return evaporator heat rate in kW for the legacy kJ/kg API."""
    return calculate_evaporator_heat_rate_si(mass_flow_rate, h1 * 1000.0, h2 * 1000.0) / 1000.0