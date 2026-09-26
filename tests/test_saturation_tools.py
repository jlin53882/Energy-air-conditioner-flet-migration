"""飽和性質工具與過熱度／過冷度現場工具：domain 狀態點、application 與獨立工作區頁面。"""

from __future__ import annotations

from types import SimpleNamespace

import CoolProp.CoolProp as CP
import matplotlib.pyplot as plt
import pytest

from application.models import SaturationPropertiesRequest, SuperheatCheckRequest
from application.refrigeration import RefrigerationService
from domain.refrigeration.saturation import (
    KNOWN_PRESSURE,
    KNOWN_TEMPERATURE,
    REGION_SUPERHEATED,
    REGION_TWO_PHASE,
    evaluate_superheat_subcooling,
    saturation_properties,
)
from domain.state_points import StatePhase, StateSource, ThermoStatePoint
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units import CanonicalUnitConverter
from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui.navigation import ROUTES
from Flet_ui.ui_components.analysis_modules.base_analysis_module import COMMON_REFRIGERANTS

STANDARD_ATMOSPHERE_PA = 101_325.0


@pytest.fixture(scope="module")
def provider() -> ThermodynamicStateService:
    """建立 canonical SI 狀態服務。

回傳：
    ThermodynamicStateService。"""
    return ThermodynamicStateService(CanonicalUnitConverter())


def _coolprop(output: str, name1: str, value1: float, name2: str, value2: float, fluid: str) -> float:
    """直接向 CoolProp 查詢（預設基準），作為獨立比對值。

參數：
    output: 輸出性質。
    name1: 第一個輸入性質。
    value1: 第一個輸入值。
    name2: 第二個輸入性質。
    value2: 第二個輸入值。
    fluid: 流體名稱。

回傳：
    SI 數值。"""
    return CP.PropsSI(output, name1, value1, name2, value2, fluid)


# ======================================================
# domain：飽和性質
# ======================================================
def test_saturation_at_known_pressure_returns_bubble_and_dew_state_points(provider) -> None:
    """已知壓力：泡點（Q=0）與露點（Q=1）同壓，溫度、潛熱與 CoolProp 一致。

回傳：
    無。"""
    pressure = 1_000_000.0
    result = saturation_properties(provider, " R410A ", pressure_pa=pressure, reference_state="ASHRAE")

    assert result.fluid == "R410A" and result.known == KNOWN_PRESSURE
    for point, quality, phase, key in (
        (result.liquid, 0.0, StatePhase.SATURATED_LIQUID, "liquid"),
        (result.vapor, 1.0, StatePhase.SATURATED_VAPOR, "vapor"),
    ):
        assert isinstance(point, ThermoStatePoint)
        assert point.quality == quality and point.phase is phase and point.key == key
        assert point.source is StateSource.SATURATION
        assert point.reference_state == "ASHRAE"
        assert point.pressure_pa == pytest.approx(pressure)
    assert result.liquid.temperature_k == pytest.approx(_coolprop("T", "P", pressure, "Q", 0, "R410A"), rel=1e-9)
    assert result.vapor.temperature_k == pytest.approx(_coolprop("T", "P", pressure, "Q", 1, "R410A"), rel=1e-9)
    assert 0.05 < result.temperature_glide_k < 0.2
    expected_latent = (_coolprop("H", "P", pressure, "Q", 1, "R410A")
                       - _coolprop("H", "P", pressure, "Q", 0, "R410A"))
    assert result.latent_heat_j_kg == pytest.approx(expected_latent, rel=1e-7)
    assert result.reference_state == "ASHRAE"


def test_saturation_at_known_temperature_reports_zeotropic_pressure_difference(provider) -> None:
    """已知溫度：兩個狀態同溫；非共沸 R407C 的泡點壓力高於露點壓力。

回傳：
    無。"""
    temperature = 278.15
    result = saturation_properties(provider, "R407C", temperature_k=temperature)

    assert result.known == KNOWN_TEMPERATURE
    assert result.liquid.temperature_k == pytest.approx(temperature)
    assert result.vapor.temperature_k == pytest.approx(temperature)
    assert result.liquid.pressure_pa == pytest.approx(_coolprop("P", "T", temperature, "Q", 0, "R407C"), rel=1e-9)
    assert result.vapor.pressure_pa == pytest.approx(_coolprop("P", "T", temperature, "Q", 1, "R407C"), rel=1e-9)
    assert result.pressure_difference_pa > 50_000.0
    assert result.temperature_glide_k == pytest.approx(0.0, abs=1e-9)


def test_pure_refrigerant_has_no_glide(provider) -> None:
    """純冷媒 R32 的泡點與露點溫度相同。

回傳：
    無。"""
    result = saturation_properties(provider, "R32", pressure_pa=1_000_000.0)

    assert result.temperature_glide_k == pytest.approx(0.0, abs=1e-6)


def test_latent_heat_is_independent_of_reference_state(provider) -> None:
    """Reference State 改變焓的基準，但潛熱（同基準相減）不變。

回傳：
    無。"""
    ashrae = saturation_properties(provider, "R134a", temperature_k=273.15, reference_state="ASHRAE")
    iir = saturation_properties(provider, "R134a", temperature_k=273.15, reference_state="IIR")

    assert iir.reference_state == "IIR"
    assert iir.liquid.enthalpy_j_kg == pytest.approx(200_000.0, rel=1e-6)
    assert ashrae.liquid.enthalpy_j_kg != pytest.approx(iir.liquid.enthalpy_j_kg, rel=1e-3)
    assert iir.latent_heat_j_kg == pytest.approx(ashrae.latent_heat_j_kg, rel=1e-7)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "其中一個"),
        ({"pressure_pa": 1e6, "temperature_k": 280.0}, "其中一個"),
        ({"pressure_pa": 0.0}, "絕對壓力"),
        ({"temperature_k": -1.0}, "絕對溫度"),
    ],
)
def test_saturation_rejects_invalid_known_values(provider, kwargs, message) -> None:
    """壓力與溫度必須恰好提供一個，且為正值。

參數：
    provider: 狀態服務。
    kwargs: 已知條件。
    message: 錯誤訊息應包含的文字。

回傳：
    無。"""
    with pytest.raises(ValueError, match=message):
        saturation_properties(provider, "R32", **kwargs)


def test_saturation_rejects_blank_fluid_and_supercritical_input(provider) -> None:
    """空白冷媒與高於臨界點的條件明確失敗。

回傳：
    無。"""
    with pytest.raises(ValueError, match="冷媒名稱"):
        saturation_properties(provider, "  ", pressure_pa=1e6)
    with pytest.raises(ValueError):
        saturation_properties(provider, "R744", temperature_k=320.0)


def test_saturation_state_points_round_trip_through_documents(provider) -> None:
    """飽和狀態點可經 to_dict／from_dict 保存與還原。

回傳：
    無。"""
    result = saturation_properties(provider, "R32", temperature_k=283.15)

    for point in (result.liquid, result.vapor):
        assert ThermoStatePoint.from_dict(point.to_dict()) == point


# ======================================================
# domain：過熱度／過冷度狀態點
# ======================================================
def test_superheat_check_returns_dew_bubble_and_measured_state_points(provider) -> None:
    """判讀結果附露點、泡點與量測點狀態點；過熱度 = 管溫 − 露點。

回傳：
    無。"""
    pressure = 1_001_325.0
    result = evaluate_superheat_subcooling(provider, "R32", pressure, 293.15, "ASHRAE")

    assert result.region == REGION_SUPERHEATED
    assert result.dew_state.quality == 1.0 and result.bubble_state.quality == 0.0
    assert result.dew_state.source is StateSource.SUPERHEAT_CHECK
    assert (result.dew_state.key, result.bubble_state.key) == ("dew", "bubble")
    assert result.dew_point_k == pytest.approx(_coolprop("T", "P", pressure, "Q", 1, "R32"), rel=1e-9)
    assert result.superheat_k == pytest.approx(293.15 - result.dew_point_k)
    measured = result.measured_state
    assert measured is not None and measured.key == "measured"
    assert measured.phase is StatePhase.SINGLE_PHASE
    assert measured.temperature_k == pytest.approx(293.15)
    assert measured.pressure_pa == pytest.approx(pressure)
    assert result.reference_state == "ASHRAE"


def test_two_phase_measurement_has_no_measured_state(provider) -> None:
    """管溫落在泡點與露點之間（兩相）時沒有量測點狀態，也沒有過熱度／過冷度。

回傳：
    無。"""
    pressure = 600_000.0
    bubble = _coolprop("T", "P", pressure, "Q", 0, "R407C")
    dew = _coolprop("T", "P", pressure, "Q", 1, "R407C")

    result = evaluate_superheat_subcooling(provider, "R407C", pressure, (bubble + dew) / 2)

    assert result.region == REGION_TWO_PHASE
    assert result.measured_state is None
    assert result.superheat_k is None and result.subcooling_k is None


# ======================================================
# application
# ======================================================
def test_application_resolves_auto_reference_state(provider) -> None:
    """Auto／None 依流體解析為明確 policy；指定值直接使用，且不影響過熱度。

回傳：
    無。"""
    service = RefrigerationService(provider)

    auto = service.saturation_properties(SaturationPropertiesRequest("R32", pressure_pa=1e6, reference_state="Auto"))
    iir = service.saturation_properties(SaturationPropertiesRequest("R32", pressure_pa=1e6, reference_state="IIR"))
    assert auto.reference_state == "ASHRAE"
    assert iir.reference_state == "IIR"

    default = service.check_superheat(SuperheatCheckRequest("R32", 1e6, 300.0))
    nbp = service.check_superheat(SuperheatCheckRequest("R32", 1e6, 300.0, reference_state="NBP"))
    assert default.reference_state == "ASHRAE"
    assert nbp.reference_state == "NBP"
    assert nbp.superheat_k == pytest.approx(default.superheat_k, rel=1e-9)
    assert nbp.dew_state.enthalpy_j_kg != pytest.approx(default.dew_state.enthalpy_j_kg, rel=1e-3)


# ======================================================
# UI：工作區頁面
# ======================================================
class DummyPage:
    """提供建構完整工作區所需的最小 page 介面。"""

    def __init__(self) -> None:
        """初始化控制項與 overlay 容器。

回傳：
    無。"""
        self.controls = []
        self.overlay = []

    def add(self, *controls) -> None:
        """收集進入點新增的控制項。

參數：
    controls: 要加入頁面的控制項。

回傳：
    無。"""
        self.controls.extend(controls)

    def update(self) -> None:
        """在沒有 Flet session 時接受更新呼叫。

回傳：
    無。"""


@pytest.fixture
def shell():
    """為每個測試建構獨立的完整工作區。

回傳：
    AppShell。"""
    page = DummyPage()
    flet_main(page)
    yield page.controls[0]
    plt.close("all")


def _open(shell, route_key: str):
    """切到指定頁面並回傳 (view, module)。

參數：
    shell: 工作區外殼。
    route_key: 路由鍵。

回傳：
    (view, module)。"""
    shell.navigate(route_key)
    view = shell.views[route_key]
    return view, view.adapter.modules[0]


def _select(control, values: list[str]) -> None:
    """模擬使用者切換分段按鈕。

參數：
    control: SegmentedButton。
    values: 新的選取值。

回傳：
    無。"""
    control.selected = values
    control.on_change(SimpleNamespace(control=control))


def _kpis(view) -> dict[str, tuple[str, str]]:
    """回傳結果區關鍵數值（名稱 → (數值, 單位)）。

參數：
    view: 分析頁。

回傳：
    關鍵數值。"""
    return {
        tile.label_control.value: (tile.value_control.value, tile.unit_control.value)
        for tile in view.workspace.result_view.kpi_row.controls
    }


def _group(view, title: str) -> dict[str, str]:
    """回傳結果性質表中指定分組的（名稱 → 數值）。

參數：
    view: 分析頁。
    title: 分組標題。

回傳：
    分組內容。"""
    group = next(group for group in view.workspace.result_view.property_table.groups if group.title == title)
    return {row.label: row.value for row in group.rows}


def test_refrigeration_routes_expose_standalone_tools() -> None:
    """冷凍系統分區提供獨立的飽和性質與過熱／過冷頁面。

回傳：
    無。"""
    routes = {route.key: route for route in ROUTES}

    assert routes["saturation"].section == "冷凍系統"
    assert routes["superheat_subcooling"].section == "冷凍系統"
    assert "過熱" not in routes["refrigeration_cycle"].description


def test_cycle_page_no_longer_lists_superheat_tool(shell) -> None:
    """冷凍循環頁只保留循環分析；過熱度判讀只在獨立頁面。

回傳：
    無。"""
    cycle_view, _ = _open(shell, "refrigeration_cycle")
    superheat_view, _ = _open(shell, "superheat_subcooling")

    assert [key for key, _ in cycle_view.adapter.tool_items()] == ["cycle.vapor_compression"]
    assert [key for key, _ in superheat_view.adapter.tool_items()] == ["refrigerant.superheat_subcooling"]


def test_saturation_page_converts_gauge_pressure_and_shows_structured_result(shell) -> None:
    """預設 900 kPag + 101.325 kPa 以絕對壓力查詢，結果以狀態點性質表呈現。

回傳：
    無。"""
    view, module = _open(shell, "saturation")
    assert module.all_entries["sat_p"]["unit"].value == "kPag"

    view.perform_calculation(None)

    assert view.result_panel.status == "success", view.result_panel.message
    absolute = 900_000.0 + STANDARD_ATMOSPHERE_PA
    bubble_c = _coolprop("T", "P", absolute, "Q", 0, "R32") - 273.15
    kpis = _kpis(view)
    assert list(kpis) == ["泡點溫度", "露點溫度", "溫度滑移", "蒸發潛熱 h_fg"]
    assert kpis["泡點溫度"] == (f"{bubble_c:.2f}", "°C")
    latent = (_coolprop("H", "P", absolute, "Q", 1, "R32") - _coolprop("H", "P", absolute, "Q", 0, "R32")) / 1000
    assert kpis["蒸發潛熱 h_fg"] == (f"{latent:.2f}", "kJ/kg")
    assert _group(view, "輸入") == {"冷媒": "R32", "已知飽和壓力（絕對）": "1001.33", "參考狀態": "ASHRAE"}
    liquid = _group(view, "飽和液體（泡點）")
    assert liquid["絕對壓力"] == "1001.33"
    assert list(liquid) == ["溫度", "絕對壓力", "比焓 h", "比熵 s", "密度 ρ", "比容 v"]
    assert "--- 飽和蒸氣（露點） ---" in view.adapter.result_text

    view.set_output_unit_system("Imperial")
    assert _kpis(view)["泡點溫度"][1] == "°F"
    assert _group(view, "飽和液體（泡點）")["絕對壓力"] == (
        f"{module.unit_converter.convert_from_si('P', absolute, 'psia'):.2f}"
    )


def test_saturation_known_temperature_mode_switches_rows_and_invalidates(shell) -> None:
    """切換為已知溫度會使結果失效、只顯示溫度列，計算結果改以壓力為關鍵數值。

回傳：
    無。"""
    view, module = _open(shell, "saturation")
    view.perform_calculation(None)

    _select(module.sat_known, [KNOWN_TEMPERATURE])

    assert view.result_panel.status == "warning"
    assert module.all_entries["sat_t"]["ui_row"].visible is True
    for key in ("sat_p", "sat_alt", "sat_atm"):
        assert module.all_entries[key]["ui_row"].visible is False, key
    assert module.sat_pressure_type_row.visible is False

    module.text_entries["sat_fluid"]["val"].value = "R407C"
    view.perform_calculation(None)
    kpis = _kpis(view)
    assert list(kpis) == ["泡點壓力", "露點壓力", "泡點－露點壓力差", "蒸發潛熱 h_fg"]
    expected = _coolprop("P", "T", 278.15, "Q", 0, "R407C") / 1000
    assert kpis["泡點壓力"] == (f"{expected:.2f}", "kPa")

    # 切回已知壓力：錶壓模式恢復海拔與大氣壓力列。
    _select(module.sat_known, [KNOWN_PRESSURE])
    for key in ("sat_p", "sat_alt", "sat_atm"):
        assert module.all_entries[key]["ui_row"].visible is True, key
    assert module.all_entries["sat_t"]["ui_row"].visible is False


def test_saturation_absolute_mode_hides_atmosphere_even_after_known_toggle(shell) -> None:
    """絕對壓力模式下海拔與大氣壓力列保持隱藏，且切換壓力類型不使結果失效。

回傳：
    無。"""
    view, module = _open(shell, "saturation")
    view.perform_calculation(None)

    _select(module.sat_pressure_type, ["Absolute"])
    assert view.result_panel.status == "success"
    assert module.all_entries["sat_p"]["unit"].value == "kPa"
    assert float(module.all_entries["sat_p"]["val"].value) == pytest.approx(1001.325)

    _select(module.sat_known, [KNOWN_TEMPERATURE])
    _select(module.sat_known, [KNOWN_PRESSURE])
    assert module.all_entries["sat_alt"]["ui_row"].visible is False
    assert module.all_entries["sat_atm"]["ui_row"].visible is False


def test_saturation_reference_state_changes_enthalpy_but_not_latent_heat(shell) -> None:
    """頁面自己的 Reference State 屬於計算輸入；改變焓值但潛熱不變。

回傳：
    無。"""
    view, module = _open(shell, "saturation")
    view.perform_calculation(None)
    latent = _kpis(view)["蒸發潛熱 h_fg"]
    enthalpy = _group(view, "飽和液體（泡點）")["比焓 h"]

    module.sat_ref_state.value = "IIR"
    module.sat_ref_state.on_select(SimpleNamespace(control=module.sat_ref_state))
    assert view.result_panel.status == "warning"
    view.perform_calculation(None)

    assert _kpis(view)["蒸發潛熱 h_fg"] == latent
    assert _group(view, "輸入")["參考狀態"] == "IIR"
    assert _group(view, "飽和液體（泡點）")["比焓 h"] != enthalpy


@pytest.mark.parametrize(("route_key", "fluid_key"), [("saturation", "sat_fluid"),
                                                      ("superheat_subcooling", "sh_fluid")])
def test_common_refrigerant_shortcut_sets_fluid_and_invalidates(shell, route_key, fluid_key) -> None:
    """點選常用冷媒快捷等同修改冷媒欄位：填入名稱並使既有結果失效。

參數：
    shell: 工作區外殼。
    route_key: 路由鍵。
    fluid_key: 冷媒欄位識別鍵。

回傳：
    無。"""
    view, module = _open(shell, route_key)
    view.perform_calculation(None)
    shortcuts = module.text_entries[fluid_key]["shortcuts"].controls
    assert [button.content for button in shortcuts] == list(COMMON_REFRIGERANTS)

    button = shortcuts[list(COMMON_REFRIGERANTS).index("R410A")]
    button.on_click(SimpleNamespace(control=button))

    assert module.text_entries[fluid_key]["val"].value == "R410A"
    assert view.result_panel.status == "warning"
    view.perform_calculation(None)
    assert view.result_panel.status == "success", view.result_panel.message


def test_every_common_refrigerant_is_computable(provider) -> None:
    """快捷清單中的冷媒都能以 CoolProp 計算飽和性質。

回傳：
    無。"""
    for fluid in COMMON_REFRIGERANTS:
        result = saturation_properties(provider, fluid, temperature_k=273.15)
        assert result.latent_heat_j_kg > 0, fluid


def test_superheat_page_shows_structured_result_with_state_points(shell) -> None:
    """過熱／過冷頁以關鍵數值與露點、泡點、量測點性質表呈現，文字結果不變。

回傳：
    無。"""
    view, module = _open(shell, "superheat_subcooling")
    view.perform_calculation(None)

    assert view.result_panel.status == "success", view.result_panel.message
    kpis = _kpis(view)
    assert list(kpis) == ["過熱蒸氣・過熱度", "露點溫度", "絕對壓力", "溫度滑移"]
    assert kpis["過熱蒸氣・過熱度"][1] == "K"
    dew_c = _coolprop("T", "P", 900_000.0 + STANDARD_ATMOSPHERE_PA, "Q", 1, "R32") - 273.15
    assert kpis["露點溫度"] == (f"{dew_c:.1f}", "°C")
    assert kpis["絕對壓力"] == ("1001.33", "kPa")
    titles = [group.title for group in view.workspace.result_view.property_table.groups]
    assert titles == ["量測", "露點（飽和蒸氣）", "泡點（飽和液體）", "量測點"]
    assert _group(view, "量測點")["溫度"] == "20.00"
    assert _group(view, "量測")["參考狀態"] == "ASHRAE"
    assert "狀態: 過熱蒸氣" in view.adapter.result_text
    assert "絕對壓力: 1001.33 kPa" in view.adapter.result_text


def test_superheat_page_two_phase_measurement(shell) -> None:
    """量測點落在兩相區時顯示兩相、沒有量測點性質表。

回傳：
    無。"""
    view, module = _open(shell, "superheat_subcooling")
    _select(module.sh_pressure_type, ["Absolute"])
    module.text_entries["sh_fluid"]["val"].value = "R407C"
    module.all_entries["sh_p"]["val"].value = "600"
    bubble = _coolprop("T", "P", 600_000.0, "Q", 0, "R407C")
    dew = _coolprop("T", "P", 600_000.0, "Q", 1, "R407C")
    module.all_entries["sh_t"]["val"].value = f"{(bubble + dew) / 2 - 273.15:.3f}"

    view.perform_calculation(None)

    kpis = _kpis(view)
    assert kpis["兩相（飽和區）・無過熱／過冷"][0] == "—"
    titles = [group.title for group in view.workspace.result_view.property_table.groups]
    assert "量測點" not in titles


def test_superheat_page_uses_its_own_reference_state(shell) -> None:
    """過熱／過冷頁的 Reference State 只改變狀態點焓值，不改變過熱度。

回傳：
    無。"""
    view, module = _open(shell, "superheat_subcooling")
    view.perform_calculation(None)
    superheat = _kpis(view)["過熱蒸氣・過熱度"]
    enthalpy = _group(view, "露點（飽和蒸氣）")["比焓 h"]

    module.sh_ref_state.value = "IIR"
    module.sh_ref_state.on_select(SimpleNamespace(control=module.sh_ref_state))
    assert view.result_panel.status == "warning"
    view.perform_calculation(None)

    assert _group(view, "量測")["參考狀態"] == "IIR"
    assert _group(view, "露點（飽和蒸氣）")["比焓 h"] != enthalpy
    assert _kpis(view)["過熱蒸氣・過熱度"] == superheat


def test_state_point_table_values_match_the_state_point(shell, provider) -> None:
    """性質表每一列都來自同一個狀態點：比容 = 1 / 密度，數值與 domain 狀態點一致。

回傳：
    無。"""
    view, _module = _open(shell, "saturation")
    view.perform_calculation(None)
    point = saturation_properties(provider, "R32", pressure_pa=900_000.0 + STANDARD_ATMOSPHERE_PA).vapor

    vapor = _group(view, "飽和蒸氣（露點）")
    assert vapor["溫度"] == f"{point.temperature_k - 273.15:.2f}"
    assert vapor["比焓 h"] == f"{point.enthalpy_j_kg / 1000:.2f}"
    assert vapor["比熵 s"] == f"{point.entropy_j_kgk / 1000:.4f}"
    assert vapor["密度 ρ"] == f"{point.density_kg_m3:.3f}"
    assert vapor["比容 v"] == f"{1 / point.density_kg_m3:.5f}"
