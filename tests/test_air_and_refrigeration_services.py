"""濕空氣線圖資料、空氣處理與冷凍 application service 的測試。"""

from __future__ import annotations

import pytest

from application.air_processes import AirProcessService
from application.models import (
    AirStateInput,
    AirStreamInput,
    CoolingCoilRequest,
    MixingRequest,
    RefrigerationCycleRequest,
    SensibleProcessRequest,
    SuperheatCheckRequest,
    SupplyAirflowRequest,
)
from application.refrigeration import RefrigerationService
from chart.psychrometric import build_psychrometric_chart_data
from domain.psychrometrics.service import PsychrometricService
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter
from infrastructure.psychrometrics import LegacyPsychrometricModelAdapter


@pytest.fixture(scope="module")
def psychrometrics() -> PsychrometricService:
    """回傳正式濕空氣服務。

回傳：
    PsychrometricService。"""
    return PsychrometricService(LegacyPsychrometricModelAdapter())


@pytest.fixture(scope="module")
def air(psychrometrics: PsychrometricService) -> AirProcessService:
    """回傳空氣處理 application service。

參數：
    psychrometrics: 濕空氣服務。

回傳：
    AirProcessService。"""
    return AirProcessService(psychrometrics)


def test_chart_data_curves_stay_inside_axes(psychrometrics: PsychrometricService) -> None:
    """飽和線、等 RH 線與等焓線都在座標範圍內，且 RH 線低於飽和線。

回傳：
    無。"""
    data = build_psychrometric_chart_data(psychrometrics, 0.0, samples=31)

    assert data.pressure_pa == pytest.approx(101_325.0)
    assert len(data.relative_humidity_lines) == 9
    assert data.enthalpy_lines
    for curve in (data.saturation, *data.relative_humidity_lines, *data.enthalpy_lines):
        assert len(curve.dry_bulb_c) == len(curve.humidity_ratio)
        assert all(-10.0 - 1e-9 <= t <= 50.0 + 1e-9 for t in curve.dry_bulb_c)
        assert all(0.0 <= w <= data.humidity_ratio_max + 1e-12 for w in curve.humidity_ratio)
    half = data.relative_humidity_lines[4]
    assert half.label == "50%"
    assert all(w_half < w_sat for w_half, w_sat in zip(half.humidity_ratio, data.saturation.humidity_ratio))


def test_chart_data_rejects_invalid_ranges(psychrometrics: PsychrometricService) -> None:
    """不合理的座標設定明確失敗。

回傳：
    無。"""
    with pytest.raises(ValueError):
        build_psychrometric_chart_data(psychrometrics, dry_bulb_range_c=(30.0, 10.0))


def test_air_state_requires_exactly_one_humidity_input(air: AirProcessService) -> None:
    """空氣狀態必須在 RH 與濕球溫度中擇一。

回傳：
    無。"""
    with pytest.raises(ValueError, match="其中一種"):
        air.resolve_state(AirStateInput(298.15), 0.0)
    with pytest.raises(ValueError, match="其中一種"):
        air.resolve_state(AirStateInput(298.15, 0.5, 290.0), 0.0)
    with pytest.raises(ValueError, match="不可高於"):
        air.resolve_state(AirStateInput(298.15, wet_bulb_k=300.0), 0.0)
    assert air.resolve_state(AirStateInput(298.15, wet_bulb_k=290.15), 0.0)["RH"] < 1.0


def test_mixing_request_converts_volume_flow_per_stream(air: AirProcessService) -> None:
    """各股體積風量以自身比容換算，混合總質量等於兩者之和。

回傳：
    無。"""
    outdoor = AirStateInput(308.15, 0.6)
    returned = AirStateInput(299.15, 0.5)
    result = air.mix(MixingRequest(0.0, (AirStreamInput(outdoor, 0.5), AirStreamInput(returned, 1.5))))

    outdoor_state = air.resolve_state(outdoor, 0.0)
    returned_state = air.resolve_state(returned, 0.0)
    expected = 0.5 / outdoor_state["V"] + 1.5 / returned_state["V"]
    assert result.dry_air_mass_flow_kg_s == pytest.approx(expected)


def test_process_requests_delegate_to_domain(air: AirProcessService) -> None:
    """顯熱、冷卻盤管與送風量 request 皆回傳 domain 結果。

回傳：
    無。"""
    heating = air.sensible(SensibleProcessRequest(0.0, AirStateInput(283.15, 0.5), 303.15, 1.0))
    coil = air.cooling_coil(
        CoolingCoilRequest(0.0, AirStateInput(300.15, 0.5), AirStateInput(286.15, 0.9), 1.0)
    )
    supply = air.supply_airflow(SupplyAirflowRequest(0.0, AirStateInput(299.15, 0.5), 288.15, 5_000.0))

    assert heating.heat_rate_w > 0
    assert coil.total_load_w > coil.sensible_load_w > 0
    assert supply.supply_volume_flow_m3_s > 0


def test_refrigeration_service_resolves_policy_and_solves() -> None:
    """未指定 policy 時冷媒使用 ASHRAE、水使用 DEF，並能求解循環與過熱度。

回傳：
    無。"""
    service = RefrigerationService(ThermodynamicStateService(CanonicalUnitConverter()))

    assert service.resolve_policy("R32", None) == "ASHRAE"
    assert service.resolve_policy("R32", "Auto") == "ASHRAE"
    assert service.resolve_policy("Water", "IIR") == "DEF"
    assert service.resolve_policy("R32", "nbp") == "NBP"
    with pytest.raises(ValueError):
        service.resolve_policy("R32", "CURRENT")

    cycle = service.solve_cycle(RefrigerationCycleRequest("R32", 278.15, 318.15, 5.0, 3.0, 0.75, 7_000.0))
    assert cycle.cop_cooling > 2.0
    assert cycle.mass_flow_kg_s > 0

    check = service.check_superheat(SuperheatCheckRequest("R32", 900_000.0, 290.0))
    assert check.superheat_k is not None
