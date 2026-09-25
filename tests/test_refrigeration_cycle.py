"""蒸氣壓縮循環與過熱度／過冷度判讀的領域測試（使用實際 CoolProp）。"""

from __future__ import annotations

import pytest

from domain.refrigeration import (
    VaporCompressionInputs,
    evaluate_superheat_subcooling,
    solve_vapor_compression_cycle,
)
from domain.refrigeration.saturation import (
    REGION_SUBCOOLED,
    REGION_SUPERHEATED,
    REGION_TWO_PHASE,
)
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter


@pytest.fixture(scope="module")
def provider() -> ThermodynamicStateService:
    """回傳共用 CoolProp 狀態服務。

回傳：
    ThermodynamicStateService。"""
    return ThermodynamicStateService(CanonicalUnitConverter())


def _inputs(**overrides) -> VaporCompressionInputs:
    """建立 R134a −10 °C／40 °C 的預設設計條件。

參數：
    overrides: 要覆寫的欄位。

回傳：
    VaporCompressionInputs。"""
    values = dict(
        fluid="R134a",
        evaporating_temperature_k=263.15,
        condensing_temperature_k=313.15,
        superheat_k=5.0,
        subcooling_k=5.0,
        isentropic_efficiency=0.8,
        refrigeration_capacity_w=10_000.0,
    )
    values.update(overrides)
    return VaporCompressionInputs(**values)


def test_calculate_state_si_rejects_single_property(provider: ThermodynamicStateService) -> None:
    """canonical SI 查詢至少需要兩個已知性質。

回傳：
    無。"""
    with pytest.raises(ValueError):
        provider.calculate_state_si("R134a", [("T", 300.0)])


def test_ideal_saturated_cycle_matches_reference_pressures(provider: ThermodynamicStateService) -> None:
    """理想飽和循環的蒸發／冷凝壓力與 COP 落在 R134a 公開數值附近。

回傳：
    無。"""
    result = solve_vapor_compression_cycle(
        provider,
        _inputs(superheat_k=0.0, subcooling_k=0.0, isentropic_efficiency=1.0),
    )

    assert result.evaporating_pressure_pa == pytest.approx(200_600, rel=0.01)
    assert result.condensing_pressure_pa == pytest.approx(1_016_600, rel=0.01)
    assert 3.8 < result.cop_cooling < 4.4
    assert result.states["1"].quality == pytest.approx(1.0)
    assert result.states["3"].quality == pytest.approx(0.0)


def test_cycle_energy_balance_and_system_quantities(provider: ThermodynamicStateService) -> None:
    """冷凝放熱等於冷凍能力加壓縮功，系統量依冷凍能力換算。

回傳：
    無。"""
    result = solve_vapor_compression_cycle(provider, _inputs())

    assert result.states["4"].enthalpy_j_kg == pytest.approx(result.states["3"].enthalpy_j_kg)
    assert result.heat_rejection_j_kg == pytest.approx(
        result.refrigerating_effect_j_kg + result.compressor_work_j_kg
    )
    assert result.cop_heating == pytest.approx(result.cop_cooling + 1.0)
    assert result.mass_flow_kg_s * result.refrigerating_effect_j_kg == pytest.approx(10_000.0)
    assert result.heat_rejection_w == pytest.approx(10_000.0 + result.compressor_power_w)
    assert result.states["1"].temperature_k == pytest.approx(268.15, abs=1e-6)
    assert result.states["3"].temperature_k == pytest.approx(308.15, abs=1e-6)
    assert result.states["2"].temperature_k > result.states["2s"].temperature_k
    assert [state.key for state in result.cycle_path] == ["1", "2", "3", "4", "1"]


def test_lower_efficiency_reduces_cop(provider: ThermodynamicStateService) -> None:
    """壓縮機等熵效率降低時，COP 必須下降。

回傳：
    無。"""
    efficient = solve_vapor_compression_cycle(provider, _inputs(isentropic_efficiency=0.9))
    inefficient = solve_vapor_compression_cycle(provider, _inputs(isentropic_efficiency=0.6))

    assert inefficient.cop_cooling < efficient.cop_cooling


def test_cycle_without_capacity_only_reports_specific_values(provider: ThermodynamicStateService) -> None:
    """未提供冷凍能力時不回傳推估的系統流量或功率。

回傳：
    無。"""
    result = solve_vapor_compression_cycle(provider, _inputs(refrigeration_capacity_w=None))

    assert result.mass_flow_kg_s is None
    assert result.compressor_power_w is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"condensing_temperature_k": 260.0}, "冷凝溫度必須高於"),
        ({"superheat_k": -1.0}, "不可為負"),
        ({"isentropic_efficiency": 1.2}, "等熵效率"),
        ({"refrigeration_capacity_w": 0.0}, "冷凍能力"),
        ({"fluid": "not-a-fluid"}, "無法計算"),
    ],
)
def test_invalid_cycle_inputs_fail_explicitly(provider, overrides, message) -> None:
    """不合理的設計條件以可理解的訊息失敗。

參數：
    provider: 狀態服務。
    overrides: 不合理的欄位。
    message: 預期訊息片段。

回傳：
    無。"""
    with pytest.raises(ValueError, match=message):
        solve_vapor_compression_cycle(provider, _inputs(**overrides))


def test_superheat_and_subcooling_regions(provider: ThermodynamicStateService) -> None:
    """依量測溫度判斷過熱、過冷與兩相，並回報差值。

回傳：
    無。"""
    suction = evaluate_superheat_subcooling(provider, "R134a", 200_600.0, 268.15)
    liquid = evaluate_superheat_subcooling(provider, "R134a", 1_016_600.0, 308.15)

    assert suction.region == REGION_SUPERHEATED
    assert suction.superheat_k == pytest.approx(5.0, abs=0.1)
    assert suction.subcooling_k is None
    assert liquid.region == REGION_SUBCOOLED
    assert liquid.subcooling_k == pytest.approx(5.0, abs=0.1)
    assert suction.temperature_glide_k == pytest.approx(0.0, abs=1e-6)


def test_zeotropic_blend_reports_glide_and_two_phase(provider: ThermodynamicStateService) -> None:
    """非共沸冷媒有溫度滑移；介於泡點與露點之間判為兩相。

回傳：
    無。"""
    result = evaluate_superheat_subcooling(provider, "R407C", 500_000.0, 273.15)
    middle = (result.dew_point_k + result.bubble_point_k) / 2.0
    two_phase = evaluate_superheat_subcooling(provider, "R407C", 500_000.0, middle)

    assert result.temperature_glide_k > 3.0
    assert two_phase.region == REGION_TWO_PHASE
    assert two_phase.superheat_k is None and two_phase.subcooling_k is None


def test_superheat_check_rejects_supercritical_pressure(provider: ThermodynamicStateService) -> None:
    """高於臨界壓力時沒有飽和狀態，必須明確失敗。

回傳：
    無。"""
    with pytest.raises(ValueError, match="無法計算"):
        evaluate_superheat_subcooling(provider, "R134a", 5_000_000.0, 400.0)
