"""ThermoStatePoint／AirStatePoint 模型、基準防護與序列化的測試。"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from domain.psychrometrics.service import PsychrometricService
from domain.refrigeration import (
    VaporCompressionInputs,
    analyze_condenser_exergy,
    solve_vapor_compression_cycle,
)
from domain.state_points import (
    AirStatePoint,
    StateBasisMismatchError,
    StatePhase,
    StatePoint,
    StateSource,
    ThermoStatePoint,
    enthalpy_difference,
    entropy_difference,
    require_same_basis,
    state_point_from_dict,
)
from domain.thermodynamics.reference_state import ReferenceStatePolicy
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units import CanonicalUnitConverter
from infrastructure.psychrometrics import LegacyPsychrometricModelAdapter


@pytest.fixture(scope="module")
def provider() -> ThermodynamicStateService:
    """回傳共用 CoolProp 狀態服務。

回傳：
    ThermodynamicStateService。"""
    return ThermodynamicStateService(CanonicalUnitConverter())


def _point(provider, known, *, fluid="R32", reference_state="ASHRAE", **overrides) -> ThermoStatePoint:
    """以狀態服務查詢並建立狀態點。

參數：
    provider: 狀態服務。
    known: 兩組 SI 已知性質。
    fluid: 流體名稱。
    reference_state: policy code。
    overrides: 其他建構參數。

回傳：
    ThermoStatePoint。"""
    state = provider.calculate_state_si(fluid, known, reference_state)
    options = {"source": StateSource.PROPERTY_QUERY, **overrides}
    return ThermoStatePoint.from_state_mapping(state, fluid=fluid, reference_state=reference_state, **options)


# ======================================================
# ThermoStatePoint
# ======================================================
def test_from_state_mapping_keeps_canonical_si_values(provider) -> None:
    """由狀態服務建立的狀態點保留 canonical SI 數值，比容由密度推導。

回傳：
    無。"""
    state = provider.calculate_state_si("R32", [("P", 1_000_000.0), ("T", 330.0)], "ASHRAE")

    point = ThermoStatePoint.from_state_mapping(
        state, fluid=" R32 ", reference_state=ReferenceStatePolicy.ASHRAE,
        source="property_query", key="A", label="狀態 A",
    )

    assert point.fluid == "R32"
    assert point.reference_state == "ASHRAE"
    assert point.source is StateSource.PROPERTY_QUERY
    assert point.pressure_pa == pytest.approx(1_000_000.0)
    assert point.temperature_k == pytest.approx(330.0)
    assert point.enthalpy_j_kg == pytest.approx(float(state["H"]))
    assert point.entropy_j_kgk == pytest.approx(float(state["S"]))
    assert point.specific_volume_m3_kg == pytest.approx(1.0 / float(state["D"]))
    assert point.phase is StatePhase.SINGLE_PHASE
    assert (point.key, point.label, point.is_ideal_gas) == ("A", "狀態 A", False)
    assert isinstance(point, StatePoint)


@pytest.mark.parametrize(
    ("quality", "phase"),
    [(0.0, StatePhase.SATURATED_LIQUID), (1.0, StatePhase.SATURATED_VAPOR), (0.4, StatePhase.TWO_PHASE)],
)
def test_phase_is_derived_from_quality(provider, quality, phase) -> None:
    """相態由乾度推導：0 飽和液、1 飽和蒸氣、之間為兩相。

參數：
    provider: 狀態服務。
    quality: 乾度。
    phase: 預期相態。

回傳：
    無。"""
    assert _point(provider, [("T", 280.0), ("Q", quality)]).phase is phase


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"fluid": "  "}, "流體"),
        ({"reference_state": "Auto"}, "明確基準"),
        ({"reference_state": "CURRENT"}, "CURRENT"),
        ({"reference_state": "XYZ"}, "明確基準"),
        ({"pressure_pa": 0.0}, "壓力"),
        ({"temperature_k": -1.0}, "溫度"),
        ({"density_kg_m3": float("nan")}, "密度"),
        ({"enthalpy_j_kg": float("inf")}, "比焓"),
        ({"quality": "abc"}, "乾度"),
        ({"source": "unknown"}, "來源"),
        ({"is_ideal_gas": 1}, "is_ideal_gas"),
        ({"pressure_pa": True}, "壓力"),
    ],
)
def test_invalid_thermo_state_point_fails_explicitly(provider, overrides, message) -> None:
    """無效欄位建立狀態點時明確失敗並指出欄位。

參數：
    provider: 狀態服務。
    overrides: 要替換成無效值的欄位。
    message: 錯誤訊息應包含的文字。

回傳：
    無。"""
    point = _point(provider, [("P", 1_000_000.0), ("T", 330.0)])
    with pytest.raises(ValueError, match=message):
        replace(point, **overrides)


def test_reference_state_aliases_are_normalized(provider) -> None:
    """Reference state 以 canonical code 保存（Default → DEF、小寫也接受）。

回傳：
    無。"""
    point = _point(provider, [("P", 1_000_000.0), ("T", 330.0)])

    assert replace(point, reference_state="Default").reference_state == "DEF"
    assert replace(point, reference_state="iir").reference_state == "IIR"


def test_missing_property_in_state_mapping_fails(provider) -> None:
    """狀態資料缺少性質時明確失敗。

回傳：
    無。"""
    with pytest.raises(ValueError, match="缺少性質"):
        ThermoStatePoint.from_state_mapping(
            {"P": 1.0, "T": 1.0}, fluid="R32", reference_state="ASHRAE", source="manual"
        )


def test_differences_require_same_basis(provider) -> None:
    """同基準的狀態點可相減；不同 reference state、流體或性質模型時禁止相減。

回傳：
    無。"""
    known_a = [("P", 1_000_000.0), ("T", 330.0)]
    known_b = [("P", 1_000_000.0), ("T", 350.0)]
    ashrae_a = _point(provider, known_a, reference_state="ASHRAE")
    ashrae_b = _point(provider, known_b, reference_state="ASHRAE")
    iir_b = _point(provider, known_b, reference_state="IIR")

    assert enthalpy_difference(ashrae_b, ashrae_a) == pytest.approx(ashrae_b.enthalpy_j_kg - ashrae_a.enthalpy_j_kg)
    assert entropy_difference(ashrae_b, ashrae_a) == pytest.approx(ashrae_b.entropy_j_kgk - ashrae_a.entropy_j_kgk)
    # 不同基準下的絕對焓值不同，但同一基準內的差值相同。
    iir_a = _point(provider, known_a, reference_state="IIR")
    assert iir_b.enthalpy_j_kg != pytest.approx(ashrae_b.enthalpy_j_kg)
    assert enthalpy_difference(iir_b, iir_a) == pytest.approx(enthalpy_difference(ashrae_b, ashrae_a), rel=1e-7)

    with pytest.raises(StateBasisMismatchError, match="ASHRAE.*IIR"):
        enthalpy_difference(ashrae_a, iir_b)
    with pytest.raises(StateBasisMismatchError):
        entropy_difference(iir_b, ashrae_a)
    with pytest.raises(StateBasisMismatchError):
        require_same_basis(ashrae_a, replace(ashrae_a, fluid="R134a"))
    with pytest.raises(StateBasisMismatchError):
        require_same_basis(ashrae_a, replace(ashrae_a, is_ideal_gas=True))
    require_same_basis(ashrae_a, replace(ashrae_b, fluid="r32"))


def test_ideal_gas_points_do_not_provide_entropy_difference() -> None:
    """理想氣體模型沒有提供比熵，熵差明確失敗；焓差仍可計算。

回傳：
    無。"""
    service = ThermodynamicStateService(CanonicalUnitConverter())
    first_state = service.calculate_properties("Water", [("P", 101.325, "kPa"), ("T", 400.0, "K")], is_ideal_gas=True)
    second_state = service.calculate_properties("Water", [("P", 101.325, "kPa"), ("T", 450.0, "K")], is_ideal_gas=True)
    first, second = (
        ThermoStatePoint.from_state_mapping(state, fluid="Water", reference_state="DEF",
                                            source=StateSource.PROPERTY_QUERY, is_ideal_gas=True)
        for state in (first_state, second_state)
    )

    assert enthalpy_difference(second, first) > 0
    with pytest.raises(ValueError, match="理想氣體"):
        entropy_difference(second, first)


def test_thermo_state_point_round_trips_through_json(provider) -> None:
    """to_dict → JSON → from_dict 後與原狀態點完全相同，並帶 schema 標記。

回傳：
    無。"""
    point = _point(provider, [("T", 280.0), ("Q", 0.4)], key="4", label="蒸發器入口")

    document = point.to_dict()
    restored = ThermoStatePoint.from_dict(json.loads(json.dumps(document, allow_nan=False)))

    assert document["schema"] == "thermo_state_point"
    assert document["schema_version"] == 1
    assert document["source"] == "property_query"
    assert restored == point
    assert state_point_from_dict(document) == point


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda doc: doc.update(schema="air_state_point"), "文件種類不符"),
        (lambda doc: doc.update(schema_version=2), "較新的版本"),
        (lambda doc: doc.update(schema_version=0), "不支援"),
        (lambda doc: doc.update(schema_version=True), "schema_version"),
        (lambda doc: doc.pop("schema_version"), "schema_version"),
        (lambda doc: doc.pop("density_kg_m3"), "缺少欄位"),
        (lambda doc: doc.update(extra=1), "未知欄位"),
        (lambda doc: doc.update(reference_state="Auto"), "明確基準"),
    ],
)
def test_invalid_thermo_documents_fail_explicitly(provider, mutate, message) -> None:
    """文件種類、版本、欄位不符或內容無效時明確失敗，不猜測資料意義。

參數：
    provider: 狀態服務。
    mutate: 修改文件的函式。
    message: 錯誤訊息應包含的文字。

回傳：
    無。"""
    document = _point(provider, [("P", 1_000_000.0), ("T", 330.0)]).to_dict()
    mutate(document)
    with pytest.raises(ValueError, match=message):
        ThermoStatePoint.from_dict(document)


def test_state_point_from_dict_rejects_unknown_kind() -> None:
    """未知的文件種類或非 mapping 明確失敗。

回傳：
    無。"""
    with pytest.raises(ValueError, match="未知的狀態點文件種類"):
        state_point_from_dict({"schema": "other", "schema_version": 1})
    with pytest.raises(ValueError, match="未知的狀態點文件種類"):
        state_point_from_dict([1, 2])


# ======================================================
# AirStatePoint
# ======================================================
@pytest.fixture(scope="module")
def air_state() -> dict:
    """回傳 25 °C、RH 50%、海平面的濕空氣狀態。

回傳：
    PsychrometricService 的結果 dict。"""
    return PsychrometricService(LegacyPsychrometricModelAdapter()).calculate_from_tdb_rh(298.15, 0.5, 0.0)


def test_air_state_point_from_psychrometric_service(air_state) -> None:
    """由濕空氣服務結果建立的狀態點保留 canonical SI 數值。

回傳：
    無。"""
    point = AirStatePoint.from_state_mapping(air_state, source=StateSource.PSYCHROMETRICS, label="室內")

    assert point.dry_bulb_k == pytest.approx(298.15)
    assert point.relative_humidity == pytest.approx(0.5)
    assert point.pressure_pa == pytest.approx(101_325.0)
    assert point.humidity_ratio_kg_kg == pytest.approx(float(air_state["W"]))
    assert point.enthalpy_j_kg == pytest.approx(float(air_state["H"]))
    assert point.source is StateSource.PSYCHROMETRICS
    assert isinstance(point, StatePoint)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"relative_humidity": 1.2}, "相對濕度"),
        ({"relative_humidity": -0.1}, "相對濕度"),
        ({"humidity_ratio_kg_kg": -0.001}, "濕度比"),
        ({"pressure_pa": 0.0}, "大氣壓力"),
        ({"specific_volume_m3_kg": float("nan")}, "比容"),
        ({"source": "x"}, "來源"),
    ],
)
def test_invalid_air_state_point_fails_explicitly(air_state, overrides, message) -> None:
    """無效的濕空氣狀態點明確失敗並指出欄位。

參數：
    air_state: 有效的濕空氣狀態。
    overrides: 要替換成無效值的欄位。
    message: 錯誤訊息應包含的文字。

回傳：
    無。"""
    point = AirStatePoint.from_state_mapping(air_state, source=StateSource.PSYCHROMETRICS)
    with pytest.raises(ValueError, match=message):
        replace(point, **overrides)


def test_air_state_point_round_trips_and_is_not_a_thermo_document(air_state) -> None:
    """濕空氣狀態點可往返 JSON，且不能被當成冷媒狀態點讀取。

回傳：
    無。"""
    point = AirStatePoint.from_state_mapping(air_state, source=StateSource.AIR_PROCESS, label="出風")
    document = json.loads(json.dumps(point.to_dict(), allow_nan=False))

    assert AirStatePoint.from_dict(document) == point
    assert state_point_from_dict(document) == point
    with pytest.raises(ValueError, match="文件種類不符"):
        ThermoStatePoint.from_dict(document)


# ======================================================
# 遷移後的冷凍計算
# ======================================================
def test_vapor_compression_states_are_thermo_state_points(provider) -> None:
    """循環狀態點帶有流體、求解時的基準與來源，並可經基準防護計算冷凍效果。

回傳：
    無。"""
    result = solve_vapor_compression_cycle(
        provider, VaporCompressionInputs("R134a", 263.15, 313.15, 5.0, 5.0, 0.7, reference_state="IIR")
    )

    for key, point in result.states.items():
        assert isinstance(point, ThermoStatePoint)
        assert (point.fluid, point.reference_state, point.source, point.key) == (
            "R134a", "IIR", StateSource.REFRIGERATION_CYCLE, key)
    assert enthalpy_difference(result.states["1"], result.states["3"]) == pytest.approx(
        result.refrigerating_effect_j_kg)
    assert result.states["3"].phase is StatePhase.SINGLE_PHASE
    assert [point.key for point in result.cycle_path] == ["1", "2", "3", "4", "1"]


def test_cycles_with_different_reference_states_cannot_be_mixed(provider) -> None:
    """不同基準求解的循環狀態點不能互相相減；同一循環內的差值相同。

回傳：
    無。"""
    inputs = VaporCompressionInputs("R32", 278.15, 318.15, 5.0, 5.0, 0.7)
    ashrae = solve_vapor_compression_cycle(provider, inputs)
    iir = solve_vapor_compression_cycle(provider, replace(inputs, reference_state="IIR"))

    assert ashrae.refrigerating_effect_j_kg == pytest.approx(iir.refrigerating_effect_j_kg, rel=1e-7)
    with pytest.raises(StateBasisMismatchError):
        enthalpy_difference(ashrae.states["1"], iir.states["3"])


def test_condenser_exergy_inlet_and_outlet_are_thermo_state_points(provider) -> None:
    """冷凝器 Exergy 的進出口是同基準的狀態點，記錄求解時的基準。

回傳：
    無。"""
    result = analyze_condenser_exergy(
        provider, "R134a", 1_000_000.0, 333.15, 308.15, 0.05, 298.15,
        boundary_temperature_k=308.15, reference_state=ReferenceStatePolicy.NBP,
    )

    for point, key in ((result.inlet, "1"), (result.outlet, "2")):
        assert (point.fluid, point.reference_state, point.source, point.key) == (
            "R134a", "NBP", StateSource.CONDENSER_EXERGY, key)
    assert result.balance.heat_rejection_w == pytest.approx(
        0.05 * enthalpy_difference(result.inlet, result.outlet))
