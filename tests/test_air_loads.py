"""空調側負荷：新風負荷、加濕負荷、風量與冷量換算（domain、application 與「空調負荷」頁）。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import CoolProp.CoolProp as CP
import matplotlib.pyplot as plt
import pytest

from application.air_loads import AirLoadService
from application.air_processes import AirProcessService
from application.models import (
    AirStateInput,
    HumidificationRequest,
    OutdoorAirLoadRequest,
    StateAirflowCapacityRequest,
)
from application.state_library import StateLibraryService
from domain.psychrometrics.loads import (
    MODE_COOLING,
    MODE_HEATING,
    STANDARD_AIR_CP_J_KGK,
    STANDARD_AIR_DENSITY_KG_M3,
    humidification_load,
    outdoor_air_load,
    split_sensible_latent,
    standard_air_airflow,
    standard_air_capacity,
    state_airflow_from_capacity,
    state_capacity_from_airflow,
)
from domain.state_points import AirStatePoint, StateSource
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units import CanonicalUnitConverter
from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui.analysis_presentation import ANALYSIS_PRESENTATION
from Flet_ui.ui.navigation import ROUTES
from Flet_ui.ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from infrastructure.storage import JsonDocumentStore, workspace_directory

CMH = 1 / 3600  # 1 m³/h 換算為 m³/s


@pytest.fixture(scope="module")
def service() -> AirLoadService:
    """建立空調負荷 application service。

回傳：
    AirLoadService。"""
    psychrometrics = PsychrometricCalculator().service
    return AirLoadService(AirProcessService(psychrometrics), ThermodynamicStateService(CanonicalUnitConverter()))


def _state(service: AirLoadService, tdb_c: float, rh: float, altitude_m: float = 0.0) -> dict:
    """計算濕空氣狀態。

參數：
    service: 空調負荷服務。
    tdb_c: 乾球溫度（°C）。
    rh: 相對濕度（0–1）。
    altitude_m: 海拔（m）。

回傳：
    狀態 dict。"""
    return service.air_processes.resolve_state(AirStateInput(tdb_c + 273.15, relative_humidity=rh), altitude_m)


# ======================================================
# domain：顯熱／潛熱分解與新風負荷
# ======================================================
def test_outdoor_air_load_uses_enthalpy_difference_and_splits_it(service) -> None:
    """夏季新風：全熱 = ṁ(h_OA − h_room)，顯熱＋潛熱＝全熱，中間點為（外氣乾球、室內濕度比）。

回傳：
    無。"""
    outdoor, room = _state(service, 35, 0.6), _state(service, 26, 0.5)
    mass_flow = 0.3

    result = outdoor_air_load(service.psychrometrics, outdoor, room, mass_flow)

    load = result.load
    assert load.total_w == pytest.approx(mass_flow * (outdoor["H"] - room["H"]))
    assert load.sensible_w + load.latent_w == pytest.approx(load.total_w)
    intermediate = service.psychrometrics.enthalpy_at(outdoor["Tdb"], room["W"])
    assert load.sensible_w == pytest.approx(mass_flow * (intermediate - room["H"]))
    assert load.sensible_w > 0 and load.latent_w > 0 and load.mode == MODE_COOLING
    assert result.outdoor_volume_flow_m3_s == pytest.approx(mass_flow * outdoor["V"])


def test_winter_outdoor_air_is_a_heating_load(service) -> None:
    """冬季新風：全熱、顯熱、潛熱皆為負值（加熱、加濕）。

回傳：
    無。"""
    load = outdoor_air_load(service.psychrometrics, _state(service, 5, 0.5), _state(service, 22, 0.4), 0.3).load

    assert load.total_w < 0 and load.sensible_w < 0 and load.latent_w < 0
    assert load.mode == MODE_HEATING


def test_hot_dry_outdoor_air_has_opposite_sensible_and_latent_signs(service) -> None:
    """炎熱乾燥的外氣：顯熱為冷卻（正）、潛熱為加濕（負）。

回傳：
    無。"""
    load = outdoor_air_load(service.psychrometrics, _state(service, 38, 0.1), _state(service, 26, 0.5), 0.3).load

    assert load.sensible_w > 0 and load.latent_w < 0


def test_split_is_zero_for_identical_states(service) -> None:
    """進出狀態相同時負荷為 0，方向為 none。

回傳：
    無。"""
    state = _state(service, 26, 0.5)
    split = split_sensible_latent(service.psychrometrics, state, state, 1.0)

    assert split.total_w == pytest.approx(0.0, abs=1e-9) and split.mode == "none"


def test_application_converts_outdoor_volume_flow_at_outdoor_state(service) -> None:
    """application：新風量以外氣狀態比容換算為乾空氣質量流率。

回傳：
    無。"""
    result = service.outdoor_air(OutdoorAirLoadRequest(
        0.0, AirStateInput(308.15, 0.6), AirStateInput(299.15, 0.5), 1000 * CMH))

    assert result.dry_air_mass_flow_kg_s == pytest.approx(1000 * CMH / result.outdoor["V"])
    assert result.outdoor_volume_flow_m3_s == pytest.approx(1000 * CMH)
    with pytest.raises(ValueError, match="風量必須大於 0"):
        service.outdoor_air(OutdoorAirLoadRequest(0.0, AirStateInput(308.15, 0.6), AirStateInput(299.15, 0.5), 0.0))


# ======================================================
# domain／application：加濕負荷
# ======================================================
def test_humidification_water_and_steam_heat(service) -> None:
    """加濕水量 = ṁ(W_target − W_in)，蒸汽熱量 = 水量 × 蒸發潛熱。

回傳：
    無。"""
    inlet, target = _state(service, 22, 0.2), _state(service, 22, 0.45)

    result = humidification_load(inlet, target, 0.33, 2_256_000.0)

    assert result.required
    assert result.water_kg_s == pytest.approx(0.33 * (target["W"] - inlet["W"]))
    assert result.steam_heat_w == pytest.approx(result.water_kg_s * 2_256_000.0)


def test_no_humidification_needed_when_target_is_drier(service) -> None:
    """目標濕度比不高於入口時不需加濕，水量與熱量為 0。

回傳：
    無。"""
    result = humidification_load(_state(service, 22, 0.5), _state(service, 22, 0.3), 0.3, 2_256_000.0)

    assert not result.required
    assert result.water_kg_s == 0.0 and result.steam_heat_w == 0.0


def test_steam_latent_heat_uses_local_atmospheric_pressure(service) -> None:
    """application：蒸發潛熱取當地大氣壓力下水的同壓飽和焓差（海拔越高、壓力越低、潛熱越大）。

回傳：
    無。"""
    sea_level = service.humidification(HumidificationRequest(
        0.0, AirStateInput(295.15, 0.2), AirStateInput(295.15, 0.45), 1000 * CMH))
    mountain = service.humidification(HumidificationRequest(
        2000.0, AirStateInput(295.15, 0.2), AirStateInput(295.15, 0.45), 1000 * CMH))

    pressure = sea_level.inlet["P"]
    expected = (CP.PropsSI("H", "P", pressure, "Q", 1, "Water") - CP.PropsSI("H", "P", pressure, "Q", 0, "Water"))
    assert sea_level.steam_latent_heat_j_kg == pytest.approx(expected, rel=1e-7)
    assert sea_level.steam_latent_heat_j_kg == pytest.approx(2_256_500, rel=1e-3)
    assert mountain.steam_latent_heat_j_kg > sea_level.steam_latent_heat_j_kg


@pytest.mark.parametrize(("flow", "latent", "message"), [(0.0, 2e6, "風量"), (1.0, 0.0, "蒸發潛熱")])
def test_humidification_rejects_invalid_inputs(service, flow, latent, message) -> None:
    """流量或蒸發潛熱不為正時明確失敗。

參數：
    service: 空調負荷服務。
    flow: 乾空氣質量流率。
    latent: 蒸發潛熱。
    message: 錯誤訊息應包含的文字。

回傳：
    無。"""
    state = _state(service, 22, 0.3)
    with pytest.raises(ValueError, match=message):
        humidification_load(state, state, flow, latent)


# ======================================================
# domain：標準空氣快算
# ======================================================
def test_standard_air_capacity_and_airflow_are_inverse() -> None:
    """標準空氣：Q = ρ·V·cp·ΔT，反算風量回到原值。

回傳：
    無。"""
    capacity = standard_air_capacity(1000 * CMH, 10.0)
    airflow = standard_air_airflow(capacity.sensible_capacity_w, 10.0)

    assert capacity.sensible_capacity_w == pytest.approx(
        STANDARD_AIR_DENSITY_KG_M3 * 1000 * CMH * STANDARD_AIR_CP_J_KGK * 10.0)
    assert capacity.sensible_capacity_w == pytest.approx(3353.33, rel=1e-5)
    assert airflow.volume_flow_m3_s == pytest.approx(1000 * CMH)


@pytest.mark.parametrize("call", [
    lambda: standard_air_capacity(0.0, 10.0), lambda: standard_air_capacity(1.0, 0.0),
    lambda: standard_air_airflow(-1.0, 10.0), lambda: standard_air_airflow(1000.0, -2.0),
])
def test_standard_air_rejects_non_positive_inputs(call) -> None:
    """風量、熱量或溫差不為正時明確失敗。

參數：
    call: 呼叫函式。

回傳：
    無。"""
    with pytest.raises(ValueError):
        call()


# ======================================================
# domain／application：狀態精算
# ======================================================
def test_state_capacity_and_airflow_are_inverse(service) -> None:
    """狀態精算：由風量求全熱，再由全熱反算風量，回到原值；風量以進風狀態換算。

回傳：
    無。"""
    entering, leaving = _state(service, 26, 0.5), _state(service, 13, 0.9)

    forward = state_capacity_from_airflow(service.psychrometrics, entering, leaving, 1000 * CMH)
    backward = state_airflow_from_capacity(service.psychrometrics, entering, leaving, forward.load.total_w)

    assert forward.dry_air_mass_flow_kg_s == pytest.approx(1000 * CMH / entering["V"])
    assert forward.load.total_w == pytest.approx(forward.dry_air_mass_flow_kg_s * (entering["H"] - leaving["H"]))
    assert backward.entering_volume_flow_m3_s == pytest.approx(1000 * CMH)


def test_heating_capacity_gives_positive_airflow(service) -> None:
    """加熱（出風較熱）：已知熱量反算的風量為正，負荷為負（加熱）。

回傳：
    無。"""
    result = state_airflow_from_capacity(service.psychrometrics, _state(service, 15, 0.5),
                                         _state(service, 35, 0.2), 5000.0)

    assert result.dry_air_mass_flow_kg_s > 0
    assert result.load.total_w == pytest.approx(-5000.0) and result.load.mode == MODE_HEATING


def test_state_airflow_rejects_equal_enthalpy_and_ambiguous_requests(service) -> None:
    """進出風焓相同無法反算；風量與冷量必須恰好提供一個。

回傳：
    無。"""
    state = _state(service, 26, 0.5)
    with pytest.raises(ValueError, match="焓值幾乎相同"):
        state_airflow_from_capacity(service.psychrometrics, state, state, 1000.0)
    for kwargs in ({}, {"entering_volume_flow_m3_s": 0.3, "total_capacity_w": 1000.0}):
        with pytest.raises(ValueError, match="其中一個"):
            service.state_airflow_capacity(StateAirflowCapacityRequest(
                0.0, AirStateInput(299.15, 0.5), AirStateInput(286.15, 0.9), **kwargs))


# ======================================================
# UI：「空調負荷」頁
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
def view(isolated_workspace):
    """建構完整工作區並切到「空調負荷」頁。

依賴 conftest 的 ``isolated_workspace``（``HVAC_WORKSPACE_DIR`` 指向本測試的暫存資料夾），
工作區的 State Library 只讀寫該資料夾，不碰使用者真正的工作區。

參數：
    isolated_workspace: 本測試的暫存工作區。

回傳：
    AirLoadView。"""
    assert workspace_directory() == isolated_workspace
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    shell.navigate("air_loads")
    yield shell.views["air_loads"]
    plt.close("all")


def _select(control, value: str) -> None:
    """模擬切換分段按鈕。

參數：
    control: SegmentedButton。
    value: 選取值。

回傳：
    無。"""
    control.selected = [value]
    control.on_change(SimpleNamespace(control=control))


def _result(view) -> dict[str, str]:
    """回傳結果文字中的「名稱: 數值」。

參數：
    view: 分析頁。

回傳：
    名稱 → 數值文字。"""
    lines = [line.split(": ", 1) for line in (view.adapter.result_text or "").splitlines() if ": " in line]
    return {label: value for label, value in lines}


def test_air_loads_route_lists_three_analyses(view) -> None:
    """「空調負荷」位於空氣處理分區，提供三項分析。

回傳：
    無。"""
    route = next(route for route in ROUTES if route.key == "air_loads")
    assert route.section == "空氣處理" and route.label == "空調負荷"
    assert [key for key, _ in view.adapter.tool_items()] == [
        "airside.outdoor_air_load", "airside.humidification", "airside.airflow_capacity"]


def test_outdoor_air_page_reports_signed_split_and_offers_states(view) -> None:
    """新風負荷頁：預設夏季條件為冷卻負荷，顯熱＋潛熱＝全熱；外氣與室內狀態可保存。

回傳：
    無。"""
    view._handle_tool_change("airside.outdoor_air_load")
    view.perform_calculation(None)

    assert view.result_panel.status == "success", view.result_panel.message
    values = _result(view)
    total, sensible, latent = (float(values[name].split()[0]) for name in ("全熱負荷", "顯熱負荷", "潛熱負荷"))
    assert total > 0 and sensible + latent == pytest.approx(total, abs=2e-3)
    assert values["新風量（外氣狀態）"] == "1000.0 m³/h"
    assert view.workspace.result_view.chart_column.visible is True

    service = view.save_menu.service
    before = len(service.entries)
    view.save_menu.save(view.save_menu.points)
    added = [entry.point for entry in service.entries[before:]]
    assert all(isinstance(point, AirStatePoint) and point.source is StateSource.AIR_PROCESS for point in added)
    assert [point.label for point in added] == ["外氣", "室內設計"]


def test_humidification_page_in_imperial_and_no_need_case(view) -> None:
    """加濕負荷頁：英制以 lbm/h 顯示水量；目標較乾時提示不需加濕。

回傳：
    無。"""
    view._handle_tool_change("airside.humidification")
    view.perform_calculation(None)
    si_water = float(_result(view)["加濕水量"].split()[0])

    view.set_output_unit_system("Imperial")
    imperial_water, unit = _result(view)["加濕水量"].split()
    assert unit == "lbm/h" and float(imperial_water) == pytest.approx(si_water / 0.45359237, abs=0.02)
    view.set_output_unit_system("SI")

    module = view.adapter.modules[0]
    module.all_entries["hum_target_rh"]["val"].value = "10"
    view.perform_calculation(None)
    assert _result(view)["加濕水量"] == "0.00 kg/h"
    assert "不需加濕" in view.adapter.result_text


def test_capacity_page_modes_switch_rows_and_invalidate(view) -> None:
    """風量與冷量換算頁：計算方式與已知條件決定輸入列；切換屬於語意輸入，會使結果失效。

回傳：
    無。"""
    view._handle_tool_change("airside.airflow_capacity")
    module = view.adapter.modules[0]

    def visible() -> set[str]:
        """回傳目前顯示的輸入列。

回傳：
    識別鍵集合。"""
        return {key for key in module.all_entries if key.startswith("cap_") and module.all_entries[key]["ui_row"].visible}

    assert visible() == {"cap_dt", "cap_flow"}
    view.perform_calculation(None)
    assert module.all_entries["cap_load"]["label_control"].value == "顯熱容量（大小）"
    assert _result(view)["顯熱容量（大小）"] == "3.353 kW"
    assert view.save_menu.visible is False

    _select(module.cap_known, "capacity")
    assert view.result_panel.status == "warning"
    assert visible() == {"cap_dt", "cap_load"}
    view.perform_calculation(None)
    assert _result(view)["風量"] == "1491.1 m³/h"

    _select(module.cap_method, "state")
    assert visible() == {"cap_alt", "cap_in_tdb", "cap_in_rh", "cap_out_tdb", "cap_out_rh", "cap_load"}
    assert module.all_entries["cap_load"]["label_control"].value == "全熱容量（取大小）"
    view.perform_calculation(None)
    assert _result(view)["全熱量"] == "5.000 kW"
    assert view.save_menu.visible is True

    _select(module.cap_known, "airflow")
    assert module.all_entries["cap_flow"]["label_control"].value == "風量（進風狀態）"
    view.perform_calculation(None)
    values = _result(view)
    assert values["風量（進風狀態）"] == "1000.0 m³/h"
    assert float(values["全熱量"].split()[0]) > 0


def test_standard_mode_does_not_offer_states_from_a_previous_state_calculation(view) -> None:
    """狀態精算後改用標準空氣快算：快算沒有空氣狀態，不得沿用上一次精算的狀態點。

回傳：
    無。"""
    view._handle_tool_change("airside.airflow_capacity")
    module = view.adapter.modules[0]
    _select(module.cap_method, "state")
    view.perform_calculation(None)
    assert view.save_menu.visible is True

    _select(module.cap_method, "standard")
    view.perform_calculation(None)

    assert view.result_panel.status == "success"
    assert view.save_menu.visible is False


# ======================================================
# Review hardening
# ======================================================
@pytest.mark.parametrize("mass_flow", [0.0, -1.0])
def test_split_sensible_latent_rejects_non_positive_mass_flow(service, mass_flow) -> None:
    """分解函式自己守住質量流率為正：0 或負值（會讓所有符號反轉）明確失敗。

參數：
    service: 空調負荷服務。
    mass_flow: 乾空氣質量流率。

回傳：
    無。"""
    with pytest.raises(ValueError, match="質量流率"):
        split_sensible_latent(service.psychrometrics, _state(service, 35, 0.6), _state(service, 26, 0.5), mass_flow)


def test_air_load_saves_go_only_to_the_isolated_workspace(isolated_workspace, tmp_path, monkeypatch) -> None:
    """狀態庫已有資料時，儲存只新增本次狀態、只寫入隔離工作區；正式預設路徑（家目錄）不被建立或讀取。

參數：
    isolated_workspace: conftest 提供的暫存工作區。
    tmp_path: pytest 暫存資料夾（作為假的家目錄）。
    monkeypatch: pytest monkeypatch。

回傳：
    無。"""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    existing = StateLibraryService(JsonDocumentStore(isolated_workspace)).save(
        AirStatePoint(altitude_m=0.0, pressure_pa=101_325.0, dry_bulb_k=298.15, wet_bulb_k=291.15,
                      dew_point_k=288.15, relative_humidity=0.5, humidity_ratio_kg_kg=0.01,
                      enthalpy_j_kg=50_000.0, specific_volume_m3_kg=0.86,
                      source=StateSource.MANUAL, label="既有"))

    page = DummyPage()
    flet_main(page)
    view = page.controls[0].views["air_loads"]
    view._handle_tool_change("airside.outdoor_air_load")
    view.perform_calculation(None)
    view.save_menu.save(view.save_menu.points)
    plt.close("all")

    reloaded = StateLibraryService(JsonDocumentStore(isolated_workspace)).entries
    assert reloaded[0] == existing
    assert [entry.point.label for entry in reloaded[1:]] == ["外氣", "室內設計"]
    assert list(fake_home.iterdir()) == []


def _record_chart_draws(module, monkeypatch) -> list[dict]:
    """攔截線圖面板的 draw，記錄每次傳入的 markers 與 paths（仍照常繪圖）。

參數：
    module: 空調負荷模組。
    monkeypatch: pytest monkeypatch。

回傳：
    每次呼叫的關鍵字參數清單。"""
    calls: list[dict] = []
    original = module.chart_panel.draw

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(module.chart_panel, "draw", spy)
    return calls


def test_humidification_page_states_it_is_a_demand_estimate_not_a_process_model(view, monkeypatch) -> None:
    """加濕頁說明目標是設計狀態、不預測出口，線圖只標示兩點而不畫過程線。

參數：
    view: 空調負荷頁。
    monkeypatch: pytest monkeypatch。

回傳：
    無。"""
    view._handle_tool_change("airside.humidification")
    draws = _record_chart_draws(view.adapter.modules[0], monkeypatch)
    view.perform_calculation(None)

    text = view.adapter.result_text
    assert "蒸汽需求估算" in text
    assert "設計目標" in text and "不代表實際蒸汽加濕過程" in text
    assert draws[-1]["paths"] == []
    assert [marker.label for marker in draws[-1]["markers"]] == ["1 入口", "2 設計目標"]
    presentation = ANALYSIS_PRESENTATION["airside.humidification"]
    assert "設計目標" in presentation.summary and "不代表實際蒸汽加濕" in presentation.summary


def test_outdoor_air_chart_still_draws_the_process_line(view, monkeypatch) -> None:
    """新風負荷仍以連線表示外氣處理到室內（只有加濕改為不連線）。

參數：
    view: 空調負荷頁。
    monkeypatch: pytest monkeypatch。

回傳：
    無。"""
    view._handle_tool_change("airside.outdoor_air_load")
    draws = _record_chart_draws(view.adapter.modules[0], monkeypatch)
    view.perform_calculation(None)

    assert len(draws[-1]["paths"]) == 1


def test_capacity_labels_follow_the_method(view) -> None:
    """快算與精算的容量欄位標明取大小；精算結果保留冷卻正、加熱負的符號說明。

參數：
    view: 空調負荷頁。

回傳：
    無。"""
    view._handle_tool_change("airside.airflow_capacity")
    module = view.adapter.modules[0]
    _select(module.cap_known, "capacity")
    label = module.all_entries["cap_load"]["label_control"]

    assert label.value == "顯熱容量（大小）"
    _select(module.cap_method, "state")
    assert label.value == "全熱容量（取大小）"
    view.perform_calculation(None)
    assert "正值為冷卻、負值為加熱" in view.adapter.result_text
    _select(module.cap_method, "standard")
    assert label.value == "顯熱容量（大小）"
    view.perform_calculation(None)
    assert "不區分冷卻或加熱" in view.adapter.result_text


def test_domain_contract_documents_humidification_as_a_demand_estimate() -> None:
    """domain contract 明寫加濕是需求估算：目標為設計目標、不代表實際蒸汽加濕過程；分解要求質量流率為正。

回傳：
    無。"""
    contracts = (Path(__file__).resolve().parents[1] / "docs" / "domain-contracts.md").read_text(encoding="utf-8")
    humidification = next(line for line in contracts.splitlines() if "`humidification_load`" in line)
    assert "不是加濕過程模擬" in humidification
    assert "設計目標" in humidification and "W_target" in humidification
    assert "不代表實際蒸汽加濕過程" in humidification
    split = next(line for line in contracts.splitlines() if "`split_sensible_latent`" in line)
    assert "質量流率必須為正" in split
