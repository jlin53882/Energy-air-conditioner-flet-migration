"""冷凝器能量、熵與㶲平衡的領域測試（使用實際 CoolProp）。"""

from __future__ import annotations

import pytest

from domain.refrigeration import analyze_condenser_exergy, condenser_exergy_balance
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter

T0 = 298.15
# R134a 於 1 MPa：入口 60 °C 過熱蒸氣、出口 35 °C 過冷液體，ṁ = 0.05 kg/s。
PRESSURE = 1.0e6
INLET_K = 333.15
OUTLET_K = 308.15
MASS_FLOW = 0.05


@pytest.fixture(scope="module")
def provider() -> ThermodynamicStateService:
    """回傳共用 CoolProp 狀態服務。

回傳：
    ThermodynamicStateService。"""
    return ThermodynamicStateService(CanonicalUnitConverter())


def _analyze(provider, boundary_k: float, **overrides):
    """以預設 R134a 條件分析冷凝器。

參數：
    provider: 狀態服務。
    boundary_k: 傳熱邊界溫度（K）。
    overrides: 要覆寫的參數。

回傳：
    CondenserExergyResult。"""
    values = dict(
        fluid="R134a",
        pressure_pa=PRESSURE,
        inlet_temperature_k=INLET_K,
        outlet_temperature_k=OUTLET_K,
        mass_flow_kg_s=MASS_FLOW,
        dead_state_temperature_k=T0,
    )
    values.update(overrides)
    return analyze_condenser_exergy(provider, boundary_temperature_k=boundary_k, **values)


@pytest.mark.parametrize("boundary_k", [T0, T0 + 5.0, 312.54])
def test_balances_close_and_satisfy_gouy_stodola(provider, boundary_k) -> None:
    """能量、㶲平衡閉合，且 X_dest = T0 · S_gen（Gouy–Stodola）。

回傳：
    無。"""
    result = _analyze(provider, boundary_k)
    balance = result.balance
    inlet, outlet = result.inlet, result.outlet
    assert balance.heat_rejection_w == pytest.approx(MASS_FLOW * (inlet.enthalpy_j_kg - outlet.enthalpy_j_kg))
    assert balance.exergy_destruction_w == pytest.approx(balance.exergy_decrease_w - balance.heat_exergy_w)
    assert balance.exergy_destruction_w == pytest.approx(T0 * balance.entropy_generation_w_k)
    assert balance.heat_exergy_w == pytest.approx(balance.heat_rejection_w * (1 - T0 / boundary_k))
    assert balance.exergy_efficiency == pytest.approx(balance.heat_exergy_w / balance.exergy_decrease_w)
    assert 0.0 <= balance.exergy_efficiency <= 1.0


def test_r134a_reference_values(provider) -> None:
    """固定 R134a 案例的數值：Q_H 9.627 kW、㶲減少 0.4743 kW、飽和 39.39 °C。

回傳：
    無。"""
    ambient = _analyze(provider, T0)
    assert ambient.balance.heat_rejection_w == pytest.approx(9627, rel=1e-3)
    assert ambient.balance.exergy_decrease_w == pytest.approx(474.3, rel=1e-3)
    assert ambient.dew_point_k - 273.15 == pytest.approx(39.39, abs=0.01)
    assert ambient.bubble_point_k == pytest.approx(ambient.dew_point_k, abs=1e-6)
    assert ambient.balance.mean_heat_rejection_temperature_k - 273.15 == pytest.approx(40.45, abs=0.01)
    # 以飽和冷凝溫度為邊界時 η ≈ 0.934。
    saturation = _analyze(provider, ambient.dew_point_k)
    assert saturation.balance.exergy_efficiency == pytest.approx(0.934, abs=1e-3)


def test_heat_rejected_to_ambient_destroys_all_refrigerant_exergy(provider) -> None:
    """T_b = T0 時熱不帶走㶲：η = 0，冷媒減少的㶲全部被破壞。

回傳：
    無。"""
    balance = _analyze(provider, T0).balance
    assert balance.heat_exergy_w == pytest.approx(0.0)
    assert balance.exergy_efficiency == pytest.approx(0.0)
    assert balance.exergy_destruction_w == pytest.approx(balance.exergy_decrease_w)


def test_mean_heat_rejection_temperature_is_the_reversible_limit() -> None:
    """T_b 等於冷媒平均放熱溫度時為可逆極限：S_gen = 0、η = 1。

回傳：
    無。"""
    h1, h2, s1, s2 = 430e3, 250e3, 1750.0, 1170.0
    mean_k = (h1 - h2) / (s1 - s2)
    balance = condenser_exergy_balance(0.05, h1, h2, s1, s2, T0, boundary_temperature_k=mean_k)
    assert balance.mean_heat_rejection_temperature_k == pytest.approx(mean_k)
    assert balance.entropy_generation_w_k == pytest.approx(0.0, abs=1e-9)
    assert balance.exergy_destruction_w == pytest.approx(0.0, abs=1e-6)
    assert balance.exergy_efficiency == pytest.approx(1.0)


def test_boundary_above_mean_temperature_violates_second_law(provider) -> None:
    """T_b 高於冷媒平均放熱溫度（例如入口溫度，或大量過冷時的飽和溫度）會被拒絕。

回傳：
    無。"""
    with pytest.raises(ValueError, match="第二定律"):
        _analyze(provider, INLET_K)
    # 出口過冷到 20 °C 時，平均放熱溫度 39.10 °C 低於飽和溫度 39.39 °C。
    subcooled = _analyze(provider, T0, outlet_temperature_k=293.15)
    assert subcooled.balance.mean_heat_rejection_temperature_k < subcooled.dew_point_k
    with pytest.raises(ValueError, match="第二定律"):
        _analyze(provider, subcooled.dew_point_k, outlet_temperature_k=293.15)


@pytest.mark.parametrize(
    ("overrides", "boundary_k", "message"),
    [
        ({"mass_flow_kg_s": 0.0}, T0, "質量流率"),
        ({}, T0 - 1.0, "不可低於死狀態溫度"),
        ({"inlet_temperature_k": 300.0, "outlet_temperature_k": 305.0}, T0, "入口溫度必須高於出口溫度"),
        ({"fluid": "  "}, T0, "冷媒名稱"),
        ({"pressure_pa": 0.0}, T0, "絕對"),
    ],
)
def test_invalid_inputs_are_rejected(provider, overrides, boundary_k, message) -> None:
    """無效輸入以明確訊息拒絕。

回傳：
    無。"""
    with pytest.raises(ValueError, match=message):
        _analyze(provider, boundary_k, **overrides)


def test_balance_rejects_heat_gain_and_cold_refrigerant() -> None:
    """冷媒沒有放熱，或冷媒溫度低於 T0（㶲減少量不為正）時拒絕。

回傳：
    無。"""
    with pytest.raises(ValueError, match="須放熱"):
        condenser_exergy_balance(0.05, 250e3, 430e3, 1170.0, 1750.0, T0, boundary_temperature_k=T0)
    # 平均放熱溫度 180/0.64 ≈ 281 K，低於 T0。
    with pytest.raises(ValueError, match="第二定律|Exergy 減少量"):
        condenser_exergy_balance(0.05, 430e3, 250e3, 1810.0, 1170.0, T0, boundary_temperature_k=T0)
