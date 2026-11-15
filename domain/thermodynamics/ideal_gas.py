"""理想氣體（常數比熱）簡化模型。

模型契約（與 CoolProp 真實流體的 reference state 無關，兩者的焓、熵不可互相比較或相減）：

* 狀態方程：``P = ρ·R·T``。
* 比熱：常數 ``cp``、``cv = cp − R``（不隨溫度變化）；適用於遠離飽和線、低壓的氣相，
  溫度範圍越大誤差越大。
* 焓零點：``h = cp·T``、``u = cv·T``，即以 0 K 外插 ``h = 0``（常數 cp 外插，不是物理狀態）。
* 比熵：**不提供**。常數 cp 理想氣體的熵需要另外定義 ``T_ref``、``P_ref``，目前未實作；
  結果不含 ``S``，不得以 0 代替。
* 只計算單相氣體；不處理飽和或兩相狀態（不接受乾度 Q 輸入）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# 狀態點保存理想氣體結果時使用的焓基準代碼；不是 CoolProp reference state。
IDEAL_GAS_BASIS = "IDEAL_GAS"
IDEAL_GAS_ENTHALPY_BASIS = "h = cp·T（常數 cp，0 K 外插 h = 0）；不提供比熵"


@dataclass(frozen=True)
class IdealGasConstants:
    """單一氣體的理想氣體常數（SI）。"""

    gas_constant_j_kgk: float
    cp_j_kgk: float


# key 為 CoolProp canonical 名稱；常數沿用既有實作的數值。
IDEAL_GAS_CONSTANTS: Mapping[str, IdealGasConstants] = {
    "Air": IdealGasConstants(gas_constant_j_kgk=287.058, cp_j_kgk=1005.0),
    "Water": IdealGasConstants(gas_constant_j_kgk=461.5, cp_j_kgk=1870.0),
}


def calculate_ideal_gas_state(
    constants: IdealGasConstants, input_values: Mapping[str, float]
) -> dict[str, float | str]:
    """以 P&T、P&D 或 T&D 計算理想氣體狀態；結果不含比熵。

參數：
    constants: 氣體常數。
    input_values: canonical SI 已知性質。

回傳：
    含 ``P``、``T``、``D``、``V``、``H``、``U``、``Q``（-1，單相標記）與 ``phase`` 的 dict。

引發：
    ValueError：輸入組合不支援（含乾度 Q）或數值非正時。"""
    if "Q" in input_values:
        raise ValueError("理想氣體模型只計算單相氣體，不接受乾度 Q；飽和狀態請改用真實流體模型。")
    gas_constant = constants.gas_constant_j_kgk
    cp = constants.cp_j_kgk
    if "P" in input_values and "T" in input_values:
        pressure, temperature = input_values["P"], input_values["T"]
        density = pressure / (gas_constant * temperature) if temperature > 0 else 0.0
    elif "P" in input_values and "D" in input_values:
        pressure, density = input_values["P"], input_values["D"]
        temperature = pressure / (density * gas_constant) if density > 0 else 0.0
    elif "T" in input_values and "D" in input_values:
        temperature, density = input_values["T"], input_values["D"]
        pressure = density * gas_constant * temperature
    else:
        raise ValueError("理想氣體計算需要 P&T, P&D 或 T&D 的組合。")
    if not (pressure > 0 and temperature > 0 and density > 0):
        raise ValueError("理想氣體的壓力、溫度與密度必須大於 0。")
    return {
        "P": pressure,
        "T": temperature,
        "D": density,
        "V": 1.0 / density,
        "H": cp * temperature,
        "U": (cp - gas_constant) * temperature,
        "Q": -1.0,
        "phase": "gas",
    }
