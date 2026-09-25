"""濕空氣服務新增反解能力與空氣處理過程的領域測試。"""

from __future__ import annotations

import pytest

from domain.psychrometrics.processes import (
    AirStream,
    cooling_dehumidification,
    dry_air_mass_flow_from_volume,
    mix_air_streams,
    sensible_heating_cooling,
    supply_airflow_for_sensible_load,
)
from domain.psychrometrics.service import PsychrometricService
from infrastructure.psychrometrics import LegacyPsychrometricModelAdapter


@pytest.fixture
def service() -> PsychrometricService:
    """回傳使用正式 model adapter 的濕空氣服務。

回傳：
    PsychrometricService。"""
    return PsychrometricService(LegacyPsychrometricModelAdapter())


def _state(service: PsychrometricService, tdb_c: float, rh: float, altitude_m: float = 0.0):
    """以攝氏溫度與 RH 分率建立狀態。

參數：
    service: 濕空氣服務。
    tdb_c: 乾球溫度（°C）。
    rh: RH 分率。
    altitude_m: 海拔（m）。

回傳：
    中立狀態 dict。"""
    return service.calculate_from_tdb_rh(tdb_c + 273.15, rh, altitude_m)


def test_tdb_w_round_trip_matches_rh_path(service: PsychrometricService) -> None:
    """由 (Tdb, W) 計算的狀態與原 (Tdb, RH) 狀態一致。

回傳：
    無。"""
    reference = _state(service, 25.0, 0.5)
    rebuilt = service.calculate_from_tdb_w(reference["Tdb"], reference["W"], 0.0)

    assert rebuilt["RH"] == pytest.approx(0.5, abs=1e-6)
    assert rebuilt["H"] == pytest.approx(reference["H"], rel=1e-6)
    assert service.humidity_ratio_from_rh(298.15, 0.5, 0.0) == pytest.approx(reference["W"])


def test_supersaturated_tdb_w_state_is_rejected(service: PsychrometricService) -> None:
    """濕度比超過飽和時明確失敗，而不是回傳 RH 大於 100% 的狀態。

回傳：
    無。"""
    saturated_w = service.humidity_ratio_from_rh(283.15, 1.0, 0.0)
    with pytest.raises(ValueError, match="超過飽和"):
        service.calculate_from_tdb_w(283.15, saturated_w * 1.2, 0.0)


def test_dry_bulb_from_enthalpy_inverts_model_enthalpy(service: PsychrometricService) -> None:
    """反解乾球溫度後，以同一 model 計算的焓值回到原值。

回傳：
    無。"""
    enthalpy = service.enthalpy_at(303.15, 0.012)

    assert service.dry_bulb_from_enthalpy(enthalpy, 0.012) == pytest.approx(303.15, abs=1e-5)
    with pytest.raises(ValueError):
        service.dry_bulb_from_enthalpy(1e9, 0.01)


def test_mixing_conserves_mass_and_energy(service: PsychrometricService) -> None:
    """混合結果的濕度比與比焓等於乾空氣質量加權平均。

回傳：
    無。"""
    outdoor = _state(service, 35.0, 0.5)
    returned = _state(service, 25.0, 0.5)

    result = mix_air_streams(
        service, [AirStream(outdoor, 1.0), AirStream(returned, 3.0)], 0.0
    )

    assert result.dry_air_mass_flow_kg_s == pytest.approx(4.0)
    assert result.mass_fractions == pytest.approx((0.25, 0.75))
    assert result.state["W"] == pytest.approx(0.25 * outdoor["W"] + 0.75 * returned["W"], rel=1e-6)
    assert result.state["H"] == pytest.approx(0.25 * outdoor["H"] + 0.75 * returned["H"], rel=1e-6)
    assert 298.15 < result.state["Tdb"] < 308.15
    assert result.volume_flow_m3_s == pytest.approx(4.0 * result.state["V"])


def test_mixing_requires_two_positive_streams(service: PsychrometricService) -> None:
    """混合計算拒絕單一股或零流量。

回傳：
    無。"""
    state = _state(service, 25.0, 0.5)
    with pytest.raises(ValueError, match="至少需要兩股"):
        mix_air_streams(service, [AirStream(state, 1.0)], 0.0)
    with pytest.raises(ValueError, match="大於 0"):
        mix_air_streams(service, [AirStream(state, 1.0), AirStream(state, 0.0)], 0.0)


def test_sensible_heating_uses_constant_humidity_ratio(service: PsychrometricService) -> None:
    """顯熱加熱維持濕度比，熱量等於 ṁ·Δh 且 RH 下降。

回傳：
    無。"""
    inlet = _state(service, 20.0, 0.6)
    result = sensible_heating_cooling(service, inlet, 303.15, 1.0, 0.0)

    assert result.outlet["W"] == pytest.approx(inlet["W"], rel=1e-6)
    assert result.heat_rate_w == pytest.approx(result.outlet["H"] - inlet["H"])
    assert result.heat_rate_w > 10_000
    assert result.outlet["RH"] < inlet["RH"]


def test_sensible_cooling_below_dew_point_is_rejected(service: PsychrometricService) -> None:
    """顯熱冷卻到露點以下會凝結，必須引導改用冷卻除濕。

回傳：
    無。"""
    inlet = _state(service, 27.0, 0.6)
    with pytest.raises(ValueError, match="冷卻除濕"):
        sensible_heating_cooling(service, inlet, inlet["Tdp"] - 1.0, 1.0, 0.0)


def test_cooling_coil_load_split_is_consistent(service: PsychrometricService) -> None:
    """冷卻盤管的顯熱與潛熱合計等於全熱，並回報冷凝水量。

回傳：
    無。"""
    inlet = _state(service, 27.0, 0.5)
    outlet = _state(service, 13.0, 0.9)

    result = cooling_dehumidification(service, inlet, outlet, 2.0)

    assert result.total_load_w == pytest.approx(2.0 * (inlet["H"] - outlet["H"]))
    assert result.sensible_load_w + result.latent_load_w == pytest.approx(result.total_load_w)
    assert 0.0 < result.sensible_heat_ratio < 1.0
    assert result.condensate_kg_s == pytest.approx(2.0 * (inlet["W"] - outlet["W"]))


def test_cooling_coil_rejects_humidifying_outlet(service: PsychrometricService) -> None:
    """出口濕度比高於入口時不是除濕過程。

回傳：
    無。"""
    inlet = _state(service, 27.0, 0.3)
    outlet = _state(service, 20.0, 0.9)
    with pytest.raises(ValueError, match="不是除濕"):
        cooling_dehumidification(service, inlet, outlet, 1.0)


def test_supply_airflow_matches_sensible_load(service: PsychrometricService) -> None:
    """送風量乘以焓差等於顯熱負荷，體積風量以送風比容換算。

回傳：
    無。"""
    room = _state(service, 26.0, 0.5)
    result = supply_airflow_for_sensible_load(service, room, 288.15, 10_000.0, 0.0)

    assert result.dry_air_mass_flow_kg_s * (room["H"] - result.supply["H"]) == pytest.approx(10_000.0)
    assert result.supply["W"] == pytest.approx(room["W"], rel=1e-6)
    assert result.supply_volume_flow_m3_s == pytest.approx(
        result.dry_air_mass_flow_kg_s * result.supply["V"]
    )
    assert result.temperature_difference_k == pytest.approx(11.0, abs=1e-9)
    with pytest.raises(ValueError, match="露點"):
        supply_airflow_for_sensible_load(service, room, room["Tdp"] - 1.0, 10_000.0, 0.0)


def test_volume_flow_conversion_uses_specific_volume(service: PsychrometricService) -> None:
    """體積風量除以濕空氣比容得到乾空氣質量流率。

回傳：
    無。"""
    state = _state(service, 25.0, 0.5)

    assert dry_air_mass_flow_from_volume(1.0, state) == pytest.approx(1.0 / state["V"])
    with pytest.raises(ValueError):
        dry_air_mass_flow_from_volume(0.0, state)
