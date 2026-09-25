"""舊版 HVAC 計算 API（compressor.py／exergy.py／condenser_heat.py／throttling.py）的單位契約回歸測試。

compressor.py 的舊版 API 以 h = kJ/kg、s = kJ/(kg·K)、ṁ = kg/s、T = K 輸入，
功率與㶲率輸出為 kW；exergy.py 的公式是齊次式，輸出單位跟隨輸入單位。
這些測試固定現有數值行為，避免說明文字與實作再次不一致。
"""

from __future__ import annotations

import CoolProp.CoolProp as CP
import pytest

from Flet_ui.ui_components.unit.hvac_calculations.compressor import (
    calculate_compressor_example,
    calculate_compressor_exergetic_efficiency_loss,
    calculate_compressor_exergetic_efficiency_ratio,
    calculate_compressor_exerpy_destruction,
    calculate_compressor_reversible_work,
    calculate_compressor_work,
    calculate_compressor_work_heat_transfer,
)
from Flet_ui.ui_components.unit.hvac_calculations.condenser_heat import exergy_efficiency_condenser
from Flet_ui.ui_components.unit.hvac_calculations.exergy import (
    calculate_change_specific_exerpy1_2,
    calculate_change_specific_exerpy1_2_simple,
    calculate_specific_exerpy,
    calculate_specific_exerpy_flow,
)
from Flet_ui.ui_components.unit.hvac_calculations.throttling import calculate_throttling_value_exerpy

# 壓縮機分析頁的預設輸入：ṁ = 0.1 kg/s、h 400 → 450 kJ/kg、s 1.7 → 1.8 kJ/(kg·K)、T0 = 25 °C。
M_DOT = 0.1
H1, H2 = 400.0, 450.0
S1, S2 = 1.7, 1.8
T0 = 298.15
H0, S0 = 400.0, 1.7


def test_compressor_legacy_api_takes_kj_per_kg_and_returns_kw() -> None:
    """kJ/kg、kJ/(kg·K)、kg/s、K 輸入時，功率與㶲破壞率以 kW 回傳。

回傳：
    無。"""
    # W_in = 0.1 kg/s × 50 kJ/kg = 5 kW
    assert calculate_compressor_work(M_DOT, H1, H2) == pytest.approx(5.0)
    # W_rev = 0.1 × (50 − 298.15 × 0.1) = 2.0185 kW
    assert calculate_compressor_reversible_work(M_DOT, H1, H2, S1, S2, T0) == pytest.approx(2.0185)
    # X_dest = W_in − W_rev = 2.9815 kW
    assert calculate_compressor_exerpy_destruction(M_DOT, H1, H2, S1, S2, T0, H0, S0) == pytest.approx(2.9815)
    # Q_out 以 kW 相加：5 kW + 1.5 kW
    assert calculate_compressor_work_heat_transfer(M_DOT, H1, H2, 1.5) == pytest.approx(6.5)
    # 兩種㶲效率都是無單位比值 W_rev / W_in。
    assert calculate_compressor_exergetic_efficiency_loss(M_DOT, H1, H2, S1, S2, T0, H0, S0) == pytest.approx(0.4037)
    assert calculate_compressor_exergetic_efficiency_ratio(M_DOT, H1, H2, S1, S2, T0, H0, S0) == pytest.approx(0.4037)


def test_exergy_helpers_follow_the_input_energy_unit() -> None:
    """exergy.py 不換算單位：kJ 輸入得到 kJ/kg（×kg/s 為 kW），J 輸入得到 J/kg（W）。

回傳：
    無。"""
    specific_kj = calculate_specific_exerpy(H2, S2, T0, H0, S0)
    specific_j = calculate_specific_exerpy(H2 * 1000, S2 * 1000, T0, H0 * 1000, S0 * 1000)
    # ex2 = 50 − 298.15 × 0.1 = 20.185 kJ/kg
    assert specific_kj == pytest.approx(20.185)
    assert specific_j == pytest.approx(specific_kj * 1000)
    assert calculate_specific_exerpy_flow(M_DOT, H2, S2, T0, H0, S0) == pytest.approx(2.0185)

    decrease_kj = calculate_change_specific_exerpy1_2(H1, H2, S1, S2, T0, H0, S0)
    decrease_j = calculate_change_specific_exerpy1_2(H1 * 1000, H2 * 1000, S1 * 1000, S2 * 1000, T0,
                                                     H0 * 1000, S0 * 1000)
    assert decrease_j == pytest.approx(decrease_kj * 1000)


def test_exergy_change_helpers_have_opposite_signs() -> None:
    """calculate_change_specific_exerpy1_2 回傳 ex1 − ex2，_simple 版本回傳 ex2 − ex1，且不受死狀態影響。

回傳：
    無。"""
    decrease = calculate_change_specific_exerpy1_2(H1, H2, S1, S2, T0, H0, S0)
    increase = calculate_change_specific_exerpy1_2_simple(H1, H2, S1, S2, T0)
    assert decrease == pytest.approx(-20.185)
    assert increase == pytest.approx(20.185)
    assert calculate_change_specific_exerpy1_2(H1, H2, S1, S2, T0, 120.0, 0.4) == pytest.approx(decrease)


def test_compressor_example_takes_si_states_and_returns_kw() -> None:
    """壓縮機例題以 Pa、K、m³/s 接收狀態，把 CoolProp 的 J 換成 kJ 後以 kW 回傳功率與㶲破壞率。

回傳：
    無。"""
    p1, t1, p2, t2, p0, t0, v1_dot = 100e3, 280.0, 500e3, 380.0, 101.325e3, 298.15, 0.01
    _, win_kw, _, ex_dest_kw, _ = calculate_compressor_example(
        0.05, p1, t1, p2, t2, p0, t0, v1_dot, "R134a", ref_state_code="ASHRAE"
    )
    # 焓差與熵差不受 reference state 影響，直接以 CoolProp SI 值計算預期結果。
    m_dot = v1_dot * CP.PropsSI("D", "P", p1, "T", t1, "R134a")
    dh_j = CP.PropsSI("H", "P", p2, "T", t2, "R134a") - CP.PropsSI("H", "P", p1, "T", t1, "R134a")
    ds_j = CP.PropsSI("S", "P", p2, "T", t2, "R134a") - CP.PropsSI("S", "P", p1, "T", t1, "R134a")
    expected_win_kw = m_dot * dh_j / 1000
    expected_wrev_kw = m_dot * (dh_j - t0 * ds_j) / 1000
    assert win_kw == pytest.approx(expected_win_kw, rel=1e-9)
    assert ex_dest_kw == pytest.approx(expected_win_kw - expected_wrev_kw, rel=1e-9)
    # 量級檢查：0.01 m³/s 的 R134a 蒸氣壓縮功為數 kW，若誤用 W 會大 1000 倍。
    assert 1.0 < win_kw < 20.0


def test_condenser_exergy_efficiency_uses_the_refrigerant_exergy_decrease() -> None:
    """冷凝器㶲效率以冷媒㶲減少量 ṁ·(ex1 − ex2) 為分母，結果落在 0～1。

回傳：
    無。"""
    # 冷媒在冷凝器中放熱：h 430 → 250 kJ/kg、s 1.75 → 1.17 kJ/(kg·K)。
    m_dot, h1, h2, s1, s2 = 0.05, 430.0, 250.0, 1.75, 1.17
    exergy_decrease_kw = m_dot * ((h1 - h2) - T0 * (s1 - s2))
    assert exergy_decrease_kw == pytest.approx(0.35365)
    efficiency = exergy_efficiency_condenser(m_dot, h1, h2, s1, s2, T0, Ex_dot_dest=0.1)
    # 修正前分母正負號相反，會得到 1 + 0.1 / 0.35365 ≈ 1.28（大於 1）。
    assert efficiency == pytest.approx(1.0 - 0.1 / exergy_decrease_kw)
    assert 0.0 < efficiency < 1.0


def test_throttling_exergy_destruction_is_in_watts() -> None:
    """節流閥以 CoolProp SI（J/kg、J/(kg·K)）計算，㶲破壞率以 W 回傳，等於 ṁ·T0·(s2 − s1)。

回傳：
    無。"""
    p1, p2, p0, t0, m_dot = 1.0e6, 0.2e6, 101.325e3, 298.15, 0.05
    t2, ex_dest_w = calculate_throttling_value_exerpy(0.0, p1, p2, p0, t0, "R134a", m_dot)
    h1 = CP.PropsSI("H", "P", p1, "Q", 0.0, "R134a")
    s1 = CP.PropsSI("S", "P", p1, "Q", 0.0, "R134a")
    s2 = CP.PropsSI("S", "P", p2, "H", h1, "R134a")
    assert t2 == pytest.approx(CP.PropsSI("T", "P", p2, "H", h1, "R134a"))
    # 節流前後焓相同，因此 ex1 − ex2 = T0·(s2 − s1)。
    assert ex_dest_w == pytest.approx(m_dot * t0 * (s2 - s1), rel=1e-9)
    # 量級檢查：數十 W；若誤當 kW 解讀會差 1000 倍。
    assert 10.0 < ex_dest_w < 1000.0
