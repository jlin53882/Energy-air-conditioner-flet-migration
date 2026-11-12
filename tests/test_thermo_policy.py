"""計算模型與 reference state 集中解析（Auto）的回歸測試。

外部表格對照來源：Siemens Building Technologies「Refrigeration Technology」手冊 Table 2-5
「Vapor table of Ammonia (R717, NH3)」（壓力為絕對壓 bar；0 °C 飽和液 h' = 200.0 kJ/kg，
即 IIR 慣例）。CoolProp 8.0.0 的 Ammonia 使用 Gao et al. (JPCRD 2020) 狀態方程；Siemens 表格
的臨界點（132.35 °C、113.53 bar）與 Gao 2020（132.41 °C、113.64 bar）不同，屬於不同 EOS／年代
的資料，因此跨來源比較使用另訂容差（由 −40…0 °C 全表實測差異決定，見 docs/reference-state.md），
同一 CoolProp 版本、同一基準的比較則要求數值一致。
"""

from __future__ import annotations

import threading
from dataclasses import replace

import CoolProp.CoolProp as CP
import pytest

from application.models import (
    HumidAirQueryRequest,
    PropertyQueryRequest,
    RefrigerationCycleRequest,
    SaturationPropertiesRequest,
)
from application.property_queries import PropertyQueryService
from application.refrigeration import RefrigerationService
from domain.psychrometrics.service import PsychrometricService
from domain.state_points import StateSource, ThermoStatePoint, compare_states
from domain.thermodynamics.reference_state import (
    ReferenceStateService,
    canonical_fluid_name,
    coolprop_version,
)
from domain.thermodynamics.state_service import IndeterminateStateError, ThermodynamicStateService
from domain.thermodynamics.thermo_policy import (
    AUTO,
    CalculationModel,
    PropertyBasis,
    ThermoPolicyError,
    Workflow,
    resolve_thermo_policy,
)
from domain.units.converter import CanonicalUnitConverter
from infrastructure.psychrometrics.legacy_model_adapter import LegacyPsychrometricModelAdapter

STANDARD_ATMOSPHERE_PA = 101_325.0
T_MINUS_25C_K = 248.15

# Siemens Table 2-5（R717）：(°C, p [bar abs], h' [kJ/kg], h'' [kJ/kg], r [kJ/kg])
SIEMENS_R717_ROWS = (
    (-40.0, 0.72, 20.3, 1407.3, 1387.0),
    (-35.0, 0.93, 42.4, 1415.0, 1372.6),
    (-30.0, 1.20, 64.6, 1422.5, 1357.8),
    (-25.0, 1.52, 87.0, 1429.6, 1342.7),
    (-20.0, 1.90, 109.4, 1436.5, 1327.1),
    (-15.0, 2.36, 131.9, 1443.1, 1311.2),
    (-10.0, 2.91, 154.5, 1449.3, 1294.8),
    (-5.0, 3.55, 177.2, 1455.2, 1278.0),
    (0.0, 4.29, 200.0, 1460.7, 1260.7),
)
# 跨來源容差（−40…0 °C）：壓力為表格解析度 0.01 bar 的半格加上 EOS 差異；焓為 Gao 2020
# 與表格 EOS 的實測最大差異（|Δh'| 1.36、|Δh''| 1.07、|Δr| 2.19 kJ/kg）再留少量餘裕。
SIEMENS_PRESSURE_TOLERANCE_BAR = 0.01
SIEMENS_ENTHALPY_TOLERANCE_KJ_KG = 1.5
SIEMENS_LATENT_TOLERANCE_KJ_KG = 2.5


@pytest.fixture()
def state_service() -> ThermodynamicStateService:
    """回傳共用 canonical SI 狀態服務。"""
    return ThermodynamicStateService(CanonicalUnitConverter())


@pytest.fixture()
def refrigeration(state_service) -> RefrigerationService:
    """回傳冷凍 application service。"""
    return RefrigerationService(state_service)


def _coolprop_iir(output: str, *inputs) -> float:
    """在 IIR 基準下直接呼叫 CoolProp（經由共用 transaction，避免與其他測試互相污染）。"""
    with ReferenceStateService().calculation_scope("Ammonia", "IIR"):
        return CP.PropsSI(output, *inputs, "Ammonia")


# ======================================================
# 6.2 Auto 模型解析矩陣
# ======================================================
@pytest.mark.parametrize(
    ("fluid", "workflow", "expected_model", "expected_reference"),
    [
        ("R717", Workflow.REFRIGERATION, CalculationModel.REAL_FLUID, "IIR"),
        ("Ammonia", Workflow.REFRIGERATION, CalculationModel.REAL_FLUID, "IIR"),
        ("NH3", Workflow.PROPERTY_QUERY, CalculationModel.REAL_FLUID, "IIR"),
        ("R134a", Workflow.REFRIGERATION, CalculationModel.REAL_FLUID, "IIR"),
        ("R1234yf", Workflow.CHART, CalculationModel.REAL_FLUID, "IIR"),
        ("R744", Workflow.REFRIGERATION, CalculationModel.REAL_FLUID, "IIR"),
        ("Water", Workflow.PROPERTY_QUERY, CalculationModel.REAL_FLUID, "DEF"),
        ("H2O", Workflow.PROPERTY_QUERY, CalculationModel.REAL_FLUID, "DEF"),
        ("Air", Workflow.PROPERTY_QUERY, CalculationModel.REAL_FLUID, "DEF"),
    ],
)
def test_auto_matrix_without_refrigerant_whitelist(fluid, workflow, expected_model, expected_reference) -> None:
    """Auto 以 CoolProp 能力探測決定：冷媒 IIR、水 DEF、乾空氣 DEF；resolved 結果不會是 Auto。"""
    policy = resolve_thermo_policy(fluid, workflow=workflow)

    assert policy.model is expected_model
    assert policy.reference_state == expected_reference
    assert policy.requested_reference == AUTO and policy.is_auto_reference
    assert policy.workflow is workflow
    assert policy.property_basis is PropertyBasis.PER_KG
    assert policy.library_version == coolprop_version() != "unknown"
    assert policy.reason


def test_air_without_humidity_is_dry_air_and_never_guesses_humidity() -> None:
    """Air 只有 P/T 時為乾空氣真實流體，原因明示不猜濕度。"""
    policy = resolve_thermo_policy("Air")
    assert policy.model is CalculationModel.REAL_FLUID
    assert "乾空氣" in policy.model_label and "不猜測濕度" in policy.reason


def test_auto_routes_air_to_humid_air_only_with_explicit_humidity() -> None:
    """只有 Air + 明確濕度條件才自動走濕空氣；沒有 CoolProp 基準，比性質為每 kg 乾空氣。"""
    policy = resolve_thermo_policy("Air", humidity_specified=True)

    assert policy.model is CalculationModel.HUMID_AIR
    assert policy.reference_state is None and policy.reference_label == "不適用"
    assert policy.property_basis is PropertyBasis.PER_KG_DRY_AIR
    with pytest.raises(ThermoPolicyError, match="只適用於 Air"):
        resolve_thermo_policy("R32", humidity_specified=True)


def test_humid_air_model_requires_humidity_and_does_not_fall_back_to_dry_air() -> None:
    """濕空氣模型缺濕度條件時明確失敗，不偷偷改成乾空氣。"""
    with pytest.raises(ThermoPolicyError, match="RH"):
        resolve_thermo_policy("Air", model="humid_air")


def test_ideal_gas_has_no_coolprop_reference_state() -> None:
    """理想氣體：焓基準清楚（h = cp·T）、不提供比熵、不接受 IIR/ASHRAE/NBP 偽裝。"""
    policy = resolve_thermo_policy("Air", model="ideal_gas")

    assert policy.model is CalculationModel.IDEAL_GAS
    assert policy.reference_state is None
    assert "cp·T" in policy.enthalpy_basis and "不提供比熵" in policy.enthalpy_basis
    for code in ("IIR", "ASHRAE", "NBP", "DEF"):
        with pytest.raises(ThermoPolicyError, match="沒有 CoolProp reference state"):
            resolve_thermo_policy("Air", model="ideal_gas", reference=code)
    with pytest.raises(ThermoPolicyError, match="理想氣體"):
        resolve_thermo_policy("R32", model="ideal_gas")


@pytest.mark.parametrize(
    ("fluid", "reference", "message"),
    [("Water", "IIR", "Ttriple"), ("Water", "ASHRAE", "Ttriple"), ("CO2", "NBP", "p_triple"),
     ("Nitrogen", "IIR", "critical")],
)
def test_manual_unsupported_reference_fails_explicitly(fluid, reference, message) -> None:
    """手動指定不支援的基準時帶 CoolProp 原因明確失敗，不靜默改 DEF。"""
    with pytest.raises(ThermoPolicyError, match=message):
        resolve_thermo_policy(fluid, reference=reference)


def test_auto_fallback_is_announced_and_reproducible() -> None:
    """Auto 遇到不支援 IIR 的流體時改用 DEF，並記錄 fallback 原因；重複解析結果相同。"""
    first = resolve_thermo_policy("Nitrogen")
    second = resolve_thermo_policy("Nitrogen")

    assert first.reference_state == "DEF"
    assert "不支援 IIR" in first.fallback_reason
    assert first == second


def test_aliases_share_one_physical_identity_and_registry_entry() -> None:
    """R717／NH3／Ammonia 解析為同一 canonical 流體與同一政策；registry 不因別名分裂。"""
    policies = [resolve_thermo_policy(name) for name in ("R717", "NH3", "Ammonia", "ammonia")]
    assert {p.canonical_fluid for p in policies} == {"Ammonia"}
    assert {p.reference_state for p in policies} == {"IIR"}

    service = ReferenceStateService()
    try:
        service.set("R717", "ASHRAE")
        assert service.current("Ammonia") == service.current("NH3") == "ASHRAE"
    finally:
        service.set("Ammonia", "DEF")


@pytest.mark.parametrize("fluid", ["", "   ", "NotAFluid", "R32&R125"])
def test_unknown_or_unsupported_fluid_fails_closed(fluid) -> None:
    """空字串、未知流體與混合物字串不猜測，明確失敗。"""
    with pytest.raises(ThermoPolicyError):
        resolve_thermo_policy(fluid)


def test_mixture_string_is_not_treated_as_its_first_component() -> None:
    """CoolProp 對混合物字串的 name 只回第一成分；canonical 解析必須拒絕而不是當作 R32。"""
    assert canonical_fluid_name("R32&R125") is None
    assert canonical_fluid_name("R32[0.5]&R125[0.5]") is None


def test_current_is_not_a_request_policy() -> None:
    """CURRENT 不能成為 request 的基準。"""
    with pytest.raises(ThermoPolicyError, match="CURRENT"):
        resolve_thermo_policy("R32", reference="CURRENT")


def test_capability_probe_restores_previously_recorded_reference_state() -> None:
    """能力探測不得改變其他 request 觀察到的已記錄基準。"""
    service = ReferenceStateService()
    try:
        service.set("R1234ze(E)", "ASHRAE")
        assert service.supports("R1234ze(E)", "NBP")
        assert service.current("R1234ze(E)") == "ASHRAE"
        assert CP.PropsSI("H", "T", 233.15, "Q", 0, "R1234ze(E)") == pytest.approx(0.0, abs=1e-6)
    finally:
        service.set("R1234ze(E)", "DEF")


# ======================================================
# 6.1 Ammonia / Siemens 基準
# ======================================================
def test_r717_auto_saturation_at_minus_25c_matches_coolprop_iir(refrigeration) -> None:
    """冷凍飽和性質：Auto → IIR；服務結果與同版本 CoolProp IIR 直接查詢一致。"""
    policy = refrigeration.resolve("R717", "Auto")
    assert policy.reference_state == "IIR"

    result = refrigeration.saturation_properties(
        SaturationPropertiesRequest("R717", temperature_k=T_MINUS_25C_K, reference_state=policy.reference_state)
    )
    assert result.reference_state == "IIR"
    assert result.vapor.enthalpy_j_kg == pytest.approx(_coolprop_iir("H", "T", T_MINUS_25C_K, "Q", 1), rel=1e-12)
    assert result.liquid.enthalpy_j_kg == pytest.approx(_coolprop_iir("H", "T", T_MINUS_25C_K, "Q", 0), rel=1e-12)
    assert result.vapor.pressure_pa == pytest.approx(_coolprop_iir("P", "T", T_MINUS_25C_K, "Q", 1), rel=1e-12)
    latent = _coolprop_iir("H", "T", T_MINUS_25C_K, "Q", 1) - _coolprop_iir("H", "T", T_MINUS_25C_K, "Q", 0)
    assert result.vapor.enthalpy_j_kg - result.liquid.enthalpy_j_kg == pytest.approx(latent, rel=1e-12)
    # IIR 錨點：0 °C 飽和液 h = 200 kJ/kg、s = 1 kJ/(kg·K)。
    assert _coolprop_iir("H", "T", 273.15, "Q", 0) == pytest.approx(200_000.0, abs=1e-6)
    assert _coolprop_iir("S", "T", 273.15, "Q", 0) == pytest.approx(1_000.0, abs=1e-6)


def test_r717_minus_25c_cross_check_against_siemens_table(refrigeration) -> None:
    """−25 °C 飽和蒸氣與 Siemens 表格（h'' 1429.6、p 1.52 bar abs）在跨來源容差內一致。

    不以常數修正 CoolProp 結果去對齊表格；差異來自 EOS 與表格四捨五入。"""
    result = refrigeration.saturation_properties(
        SaturationPropertiesRequest("Ammonia", temperature_k=T_MINUS_25C_K, reference_state="Auto")
    )
    assert abs(result.vapor.enthalpy_j_kg / 1000 - 1429.6) <= SIEMENS_ENTHALPY_TOLERANCE_KJ_KG
    assert abs(result.liquid.enthalpy_j_kg / 1000 - 87.0) <= SIEMENS_ENTHALPY_TOLERANCE_KJ_KG
    assert abs(result.vapor.pressure_pa / 1e5 - 1.52) <= SIEMENS_PRESSURE_TOLERANCE_BAR
    # CoolProp 8 實測值鎖定（同版本、同基準應高度一致；升級 CoolProp 時需重新檢視）。
    if coolprop_version() == "8.0.0":
        assert result.vapor.enthalpy_j_kg / 1000 == pytest.approx(1430.506, abs=1e-3)
        assert result.vapor.pressure_pa == pytest.approx(151_420.05, abs=0.1)


@pytest.mark.parametrize(("t_c", "p_bar", "h_liquid", "h_vapor", "latent"), SIEMENS_R717_ROWS)
def test_r717_low_temperature_rows_within_documented_tolerance(state_service, t_c, p_bar, h_liquid,
                                                               h_vapor, latent) -> None:
    """Siemens 表 −40…0 °C 每列都在文件化的跨來源容差內（壓力、h'、h''、r）。"""
    temperature = t_c + 273.15
    liquid = state_service.calculate_state_si("R717", [("T", temperature), ("Q", 0.0)], "IIR")
    vapor = state_service.calculate_state_si("R717", [("T", temperature), ("Q", 1.0)], "IIR")

    assert abs(liquid["P"] / 1e5 - p_bar) <= SIEMENS_PRESSURE_TOLERANCE_BAR
    assert abs(liquid["H"] / 1000 - h_liquid) <= SIEMENS_ENTHALPY_TOLERANCE_KJ_KG
    assert abs(vapor["H"] / 1000 - h_vapor) <= SIEMENS_ENTHALPY_TOLERANCE_KJ_KG
    assert abs((vapor["H"] - liquid["H"]) / 1000 - latent) <= SIEMENS_LATENT_TOLERANCE_KJ_KG


def test_known_pressure_and_known_temperature_are_not_the_same_exact_state(refrigeration) -> None:
    """表格壓力 152 kPa（四捨五入）與 −25 °C 不是逐位相同的狀態；只要求在合理範圍內接近。"""
    by_pressure = refrigeration.saturation_properties(
        SaturationPropertiesRequest("R717", pressure_pa=152_000.0, reference_state="Auto")
    )
    by_temperature = refrigeration.saturation_properties(
        SaturationPropertiesRequest("R717", temperature_k=T_MINUS_25C_K, reference_state="Auto")
    )
    assert by_pressure.vapor.temperature_k != by_temperature.vapor.temperature_k
    assert by_pressure.vapor.temperature_k == pytest.approx(T_MINUS_25C_K, abs=0.15)
    assert by_pressure.vapor.enthalpy_j_kg == pytest.approx(by_temperature.vapor.enthalpy_j_kg, abs=300.0)


def test_gauge_and_absolute_152_kpa_are_different_physical_states(refrigeration) -> None:
    """152 kPag → 253 325 Pa（標準大氣）；152 kPa abs → 152 000 Pa；兩者飽和溫度不同。"""
    from Flet_ui.ui_components.unit.UnitConverter import UnitConverter

    converter = UnitConverter()
    absolute_from_gauge = converter.gauge_to_absolute_pa(152_000.0, STANDARD_ATMOSPHERE_PA)
    assert absolute_from_gauge == pytest.approx(253_325.0)

    gauge = refrigeration.saturation_properties(
        SaturationPropertiesRequest("R717", pressure_pa=absolute_from_gauge, reference_state="Auto")
    )
    absolute = refrigeration.saturation_properties(
        SaturationPropertiesRequest("R717", pressure_pa=152_000.0, reference_state="Auto")
    )
    assert gauge.vapor.temperature_k - 273.15 == pytest.approx(-13.2, abs=0.2)
    assert absolute.vapor.temperature_k - 273.15 == pytest.approx(-24.9, abs=0.2)


def test_reference_switch_round_trip_keeps_state_and_latent_heat(state_service) -> None:
    """IIR → ASHRAE → NBP → DEF → IIR：P、T、D、Q 不變；焓可平移但同基準潛熱不變；無殘留污染。"""
    snapshots = {}
    for code in ("IIR", "ASHRAE", "NBP", "DEF", "IIR"):
        liquid = state_service.calculate_state_si("Ammonia", [("T", T_MINUS_25C_K), ("Q", 0.0)], code)
        vapor = state_service.calculate_state_si("Ammonia", [("T", T_MINUS_25C_K), ("Q", 1.0)], code)
        snapshots.setdefault(code, []).append((liquid, vapor))
    reference_liquid, reference_vapor = snapshots["IIR"][0]
    for code, runs in snapshots.items():
        for liquid, vapor in runs:
            for prop in ("P", "T", "D", "Q"):
                assert vapor[prop] == pytest.approx(reference_vapor[prop], rel=1e-10), (code, prop)
            assert vapor["H"] - liquid["H"] == pytest.approx(reference_vapor["H"] - reference_liquid["H"], rel=1e-9)
    assert snapshots["IIR"][1][1]["H"] == pytest.approx(snapshots["IIR"][0][1]["H"], rel=1e-14)
    assert snapshots["ASHRAE"][0][1]["H"] != pytest.approx(reference_vapor["H"])
    # NBP：CoolProp 8 以 101.325 kPa 的飽和液為零點（以安裝版本實測）。
    nbp_zero = state_service.calculate_state_si("Ammonia", [("P", STANDARD_ATMOSPHERE_PA), ("Q", 0.0)], "NBP")
    assert nbp_zero["H"] == pytest.approx(0.0, abs=1e-6)
    assert nbp_zero["S"] == pytest.approx(0.0, abs=1e-9)


def test_cycle_performance_is_reference_state_invariant(refrigeration) -> None:
    """冷凍循環 COP、質量流量、壓縮功、冷凍效果在不同基準下相同；狀態點焓可平移。"""
    results = {
        code: refrigeration.solve_cycle(RefrigerationCycleRequest(
            "R717", 248.15, 308.15, 5.0, 3.0, 0.75, 10_000.0, reference_state=code
        ))
        for code in ("IIR", "ASHRAE", "NBP", "DEF", "Auto")
    }
    base = results["IIR"]
    for code, result in results.items():
        assert result.cop_cooling == pytest.approx(base.cop_cooling, rel=1e-9), code
        assert result.mass_flow_kg_s == pytest.approx(base.mass_flow_kg_s, rel=1e-9), code
        assert result.compressor_work_j_kg == pytest.approx(base.compressor_work_j_kg, rel=1e-9), code
        assert result.refrigerating_effect_j_kg == pytest.approx(base.refrigerating_effect_j_kg, rel=1e-9), code
    assert results["Auto"].reference_state == "IIR"
    assert results["ASHRAE"].states["1"].enthalpy_j_kg != pytest.approx(base.states["1"].enthalpy_j_kg)


def test_interleaved_threads_do_not_contaminate_reference_states(state_service) -> None:
    """多執行緒交錯 IIR／ASHRAE／DEF 查詢同一冷媒，各自結果與其基準一致。"""
    expected = {
        code: state_service.calculate_state_si("R717", [("T", T_MINUS_25C_K), ("Q", 1.0)], code)["H"]
        for code in ("IIR", "ASHRAE", "DEF")
    }
    errors: list[str] = []

    def worker(code: str) -> None:
        for _ in range(40):
            value = state_service.calculate_state_si("R717", [("T", T_MINUS_25C_K), ("Q", 1.0)], code)["H"]
            if value != pytest.approx(expected[code], rel=1e-12):
                errors.append(f"{code}: {value} != {expected[code]}")

    threads = [threading.Thread(target=worker, args=(code,)) for code in ("IIR", "ASHRAE", "DEF") * 3]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors


def test_pt_on_saturation_boundary_keeps_indeterminate_contract(state_service) -> None:
    """真實流體 P/T 落在飽和邊界時仍為 IndeterminateStateError，不偷偷猜 Q。"""
    pressure = state_service.calculate_state_si("R717", [("T", T_MINUS_25C_K), ("Q", 1.0)], "IIR")["P"]
    with pytest.raises(IndeterminateStateError):
        state_service.calculate_state_si("R717", [("P", pressure), ("T", T_MINUS_25C_K)], "IIR")


# ======================================================
# 物性查詢 application、理想氣體與濕空氣
# ======================================================
@pytest.fixture()
def query_service(state_service) -> PropertyQueryService:
    """含濕空氣服務的物性查詢 application service。"""
    return PropertyQueryService(state_service, PsychrometricService(LegacyPsychrometricModelAdapter()))


def test_property_query_returns_values_with_single_resolution_snapshot(query_service) -> None:
    """query_with_policy 回傳數值與 concrete policy；Auto 不出現在結果基準。"""
    outcome = query_service.query_with_policy(PropertyQueryRequest(
        "R717", (("T", -25.0, "°C"), ("P", 1.0, "bar")), reference_state="Auto"
    ))
    assert outcome.policy.reference_state == "IIR"
    assert outcome.values["H"] == pytest.approx(_coolprop_iir("H", "T", T_MINUS_25C_K, "P", 1e5), rel=1e-12)


def test_ideal_gas_query_has_no_fake_entropy(query_service) -> None:
    """理想氣體結果不含 S，不再以 0 代替；飽和輸入（Q）明確拒絕。"""
    outcome = query_service.query_with_policy(PropertyQueryRequest(
        "Air", (("T", 25.0, "°C"), ("P", 101.325, "kPa")), model="ideal_gas", reference_state="Auto"
    ))
    assert "S" not in outcome.values
    assert outcome.values["H"] == pytest.approx(1005.0 * 298.15)
    assert outcome.policy.model is CalculationModel.IDEAL_GAS
    from Flet_ui.ui_components.unit.UnitConverter import UnitConverter

    ui_service = PropertyQueryService(ThermodynamicStateService(UnitConverter()))
    with pytest.raises(RuntimeError, match="乾度"):
        ui_service.query(PropertyQueryRequest(
            "Water", (("T", 100.0, "°C"), ("Q", 1.0, "-")), is_ideal_gas=True
        ))


def test_humid_air_query_requires_exactly_one_humidity_condition(query_service) -> None:
    """濕空氣：RH 為 0–1 分率、焓為每 kg 乾空氣；缺或多個濕度條件都明確失敗。"""
    outcome = query_service.query_humid_air(HumidAirQueryRequest(298.15, relative_humidity=0.5))
    assert outcome.policy.model is CalculationModel.HUMID_AIR
    assert outcome.policy.property_basis is PropertyBasis.PER_KG_DRY_AIR
    assert outcome.values["RH"] == pytest.approx(0.5)
    w = outcome.values["W"]
    assert outcome.values["H"] == pytest.approx((1.006 * 25 + w * (2501 + 1.86 * 25)) * 1000, rel=1e-3)
    # 與一般 PropsSI('H', ..., 'Air') 的乾空氣焓是不同性質與不同基準。
    dry_air_def = CP.PropsSI("H", "T", 298.15, "P", outcome.values["P"], "Air")
    assert abs(dry_air_def - outcome.values["H"]) > 100_000.0

    with pytest.raises(ThermoPolicyError, match="無"):
        query_service.query_humid_air(HumidAirQueryRequest(298.15))
    with pytest.raises(ThermoPolicyError, match="RH、Twb"):
        query_service.query_humid_air(HumidAirQueryRequest(298.15, relative_humidity=0.5, wet_bulb_k=290.0))
    with pytest.raises(ValueError, match="0–1"):
        query_service.query_humid_air(HumidAirQueryRequest(298.15, relative_humidity=50.0))


def test_humid_air_cross_check_with_coolprop_haprops(query_service) -> None:
    """既有濕空氣公式與 CoolProp HAPropsSI 的交叉驗證（不切換 backend，只記錄差異）。"""
    from CoolProp.HumidAirProp import HAPropsSI

    outcome = query_service.query_humid_air(HumidAirQueryRequest(298.15, relative_humidity=0.5))
    pressure = outcome.values["P"]
    assert outcome.values["W"] == pytest.approx(HAPropsSI("W", "T", 298.15, "P", pressure, "R", 0.5), rel=5e-3)
    assert outcome.values["H"] == pytest.approx(HAPropsSI("H", "T", 298.15, "P", pressure, "R", 0.5), rel=5e-3)


# ======================================================
# 狀態點 schema：理想氣體與 v1 遷移
# ======================================================
def _real_point(**overrides) -> ThermoStatePoint:
    values = dict(fluid="R717", reference_state="IIR", pressure_pa=151_420.0, temperature_k=248.15,
                  enthalpy_j_kg=1_430_506.0, entropy_j_kgk=5_600.0, density_kg_m3=1.3, quality=1.0,
                  source=StateSource.SATURATION)
    values.update(overrides)
    return ThermoStatePoint(**values)


def test_ideal_gas_point_requires_ideal_gas_basis_and_no_entropy() -> None:
    """理想氣體狀態點只能是 IDEAL_GAS 基準且比熵為 None；真實流體不得使用 IDEAL_GAS。"""
    point = ThermoStatePoint.from_state_mapping(
        {"P": 1e5, "T": 300.0, "H": 301_500.0, "D": 1.16, "Q": -1.0},
        fluid="Air", reference_state="DEF", source=StateSource.PROPERTY_QUERY, is_ideal_gas=True,
    )
    assert point.reference_state == "IDEAL_GAS" and point.entropy_j_kgk is None
    with pytest.raises(ValueError, match="IDEAL_GAS"):
        replace(point, reference_state="DEF")
    with pytest.raises(ValueError, match="比熵"):
        replace(point, entropy_j_kgk=0.0)
    with pytest.raises(ValueError, match="明確基準"):
        _real_point(reference_state="IDEAL_GAS")


def test_v1_documents_migrate_without_changing_real_fluid_semantics() -> None:
    """v1 冷媒狀態點內容不變；v1 理想氣體（S=0、記錄 DEF）轉為 IDEAL_GAS／None。"""
    real_v1 = {**_real_point().to_dict(), "schema_version": 1}
    assert ThermoStatePoint.from_dict(real_v1) == _real_point()

    ideal_v1 = {
        "schema": "thermo_state_point", "schema_version": 1, "fluid": "Water", "reference_state": "DEF",
        "pressure_pa": 1e5, "temperature_k": 400.0, "enthalpy_j_kg": 748_000.0, "entropy_j_kgk": 0.0,
        "density_kg_m3": 0.54, "quality": -1.0, "source": "property_query", "is_ideal_gas": True,
        "key": "", "label": "",
    }
    migrated = ThermoStatePoint.from_dict(ideal_v1)
    assert migrated.reference_state == "IDEAL_GAS" and migrated.entropy_j_kgk is None
    assert migrated.to_dict()["schema_version"] == 2
    with pytest.raises(ValueError, match="無法安全轉換"):
        ThermoStatePoint.from_dict({**ideal_v1, "entropy_j_kgk": 12.0})


def test_comparison_blocks_cross_basis_and_cross_model_subtraction() -> None:
    """IIR 與 ASHRAE、真實流體與理想氣體的焓不可相減；同基準可相減。"""
    iir = _real_point()
    ashrae = _real_point(reference_state="ASHRAE", enthalpy_j_kg=1_411_564.0)
    assert compare_states(iir, ashrae).rows[2].difference is None
    same = compare_states(iir, replace(iir, enthalpy_j_kg=iir.enthalpy_j_kg + 1000.0))
    assert same.rows[2].difference == pytest.approx(1000.0)
