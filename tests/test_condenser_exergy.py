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


class _DummyPage:
    """提供建構工作區時所需的 page API。"""

    def __init__(self) -> None:
        self.overlay = []
        self.controls = []
        self.width = 1440

    def update(self) -> None:
        """在沒有 live Flet session 的情況下接受 updates。

回傳：
    無。"""

    def add(self, *controls) -> None:
        """收集 page entry point 新增的 controls。

參數：
    controls: 新增的控制項。

回傳：
    無。"""
        self.controls.extend(controls)


@pytest.fixture(scope="module")
def condenser_view():
    """建構完整工作區並回傳冷凝器分析頁。

回傳：
    CondenserView。"""
    from Flet_ui.flet_app import main as flet_main

    page = _DummyPage()
    flet_main(page)
    return page.controls[0].views["condenser"]


def _result_lines(view) -> dict[str, str]:
    """把結果文字轉成「名稱 → 數值」對照。

參數：
    view: 冷凝器分析頁。

回傳：
    dict。"""
    lines = {}
    for line in (view.adapter.result_text or "").splitlines():
        label, separator, value = line.partition(": ")
        if separator:
            lines[label] = value
    return lines


def test_condenser_exergy_analysis_defaults_to_heat_rejected_to_ambient(condenser_view) -> None:
    """預設「整體排熱至環境（T_b = T0）」：η = 0、㶲破壞率等於冷媒 Exergy 減少量，並顯示關鍵數值與溫度範圍。

回傳：
    無。"""
    module = condenser_view.adapter.modules[0]
    condenser_view._handle_tool_change("condenser.exergy")
    assert module.all_entries["cx_t_b"]["ui_row"].visible is False
    condenser_view.perform_calculation(None)
    assert condenser_view.result_panel.status == "success"
    lines = _result_lines(condenser_view)
    assert lines["Exergy 效率 η"] == "0.0 %"
    assert lines["Exergy 破壞率 X_dest"] == lines["冷媒 Exergy 減少量"] == "0.474 kW"
    assert lines["放熱量 Q_H"] == "9.627 kW"
    assert lines["傳熱邊界"] == "整體排熱至環境（T_b = T0）"
    assert lines["等效傳熱邊界溫度 T_b"] == "25.00 °C"
    # 選項與欄位使用「等效傳熱邊界溫度」，不描述成外部熱匯的溫度。
    segment_labels = [segment.label.value for segment in module.cx_boundary.segments]
    assert segment_labels == ["整體排熱至環境", "指定等效傳熱邊界溫度"]
    assert module.all_entries["cx_t_b"]["label_control"].value == "等效傳熱邊界溫度 T_b"
    # 說明預設收起，點標題右側的「?」展開，再點一次收起。
    assert module.cx_boundary_help.visible is False
    module.toggle_boundary_help(None)
    help_text = " ".join(text.value for text in module.cx_boundary_help.content.controls)
    assert module.cx_boundary_help.visible is True
    assert "不一定等於外氣或熱水的 bulk temperature" in help_text
    assert "T_b = T0" in help_text
    module.toggle_boundary_help(None)
    assert module.cx_boundary_help.visible is False
    assert lines["冷媒平均放熱溫度"] == "40.45 °C"
    kpis = [tile.label_control.value for tile in condenser_view.workspace.result_view.kpi_row.controls]
    assert kpis == ["Exergy 破壞率 X_dest", "Exergy 效率 η", "放熱量 Q_H", "熵產生率 S_gen"]


def test_condenser_exergy_analysis_with_a_heat_sink_temperature(condenser_view) -> None:
    """指定等效傳熱邊界溫度時計算熱帶走的㶲；高於冷媒平均放熱溫度時以第二定律說明拒絕。

回傳：
    無。"""
    module = condenser_view.adapter.modules[0]
    condenser_view._handle_tool_change("condenser.exergy")
    module.cx_boundary.selected = ["custom"]
    module.on_boundary_change(None)
    field = module.all_entries["cx_t_b"]["val"]
    original = field.value
    try:
        assert module.all_entries["cx_t_b"]["ui_row"].visible is True
        field.value = "35"
        condenser_view.perform_calculation(None)
        assert condenser_view.result_panel.status == "success"
        lines = _result_lines(condenser_view)
        # Ex_Q = 9.627 × (1 − 298.15 / 308.15) ≈ 0.312 kW，η ≈ 0.312 / 0.474 ≈ 65.9 %。
        assert lines["傳熱邊界"] == "指定等效傳熱邊界溫度"
        assert lines["熱帶走的 Exergy Ex_Q"] == "0.312 kW"
        assert lines["Exergy 效率 η"] == "65.9 %"

        field.value = "60"
        condenser_view.perform_calculation(None)
        assert condenser_view.result_panel.status == "error"
        assert "第二定律" in condenser_view.result_panel.message
    finally:
        field.value = original
        module.cx_boundary.selected = ["ambient"]
        module.on_boundary_change(None)
