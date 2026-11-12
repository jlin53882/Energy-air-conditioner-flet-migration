"""物性查詢頁的計算模型／參考基準選擇：實際計算、狀態失效、保存與版面。"""

from __future__ import annotations

from types import SimpleNamespace

import flet as ft
import matplotlib.pyplot as plt
import pytest

from domain.state_points import AirStatePoint, ThermoStatePoint
from Flet_ui.flet_app import main as flet_main


class DummyPage:
    """沒有 Flet session 時的最小頁面替身。"""

    def __init__(self) -> None:
        self.controls = []
        self.overlay = []

    def add(self, *controls) -> None:
        self.controls.extend(controls)

    def update(self) -> None:
        return None


@pytest.fixture
def shell():
    """完整工作區；物性頁未掛載時略過 update／SnackBar。"""
    page = DummyPage()
    flet_main(page)
    app_shell = page.controls[0]
    view = app_shell.views["thermo_properties"]
    view.update = lambda: None
    view.show_error = lambda _message: None
    yield app_shell
    plt.close("all")


def _view(shell):
    shell.navigate("thermo_properties")
    return shell.views["thermo_properties"]


def _select_model(view, model: str) -> None:
    view.mode_dd.value = model
    view.mode_dd.on_select(SimpleNamespace(control=view.mode_dd))


def _query(view, first: str = "1000", second: str = "0") -> None:
    view.input_rows[0]["val"].value = first
    view.input_rows[1]["val"].value = second
    view.perform_calculation(None)


def test_defaults_are_auto_and_preview_shows_concrete_policy(shell) -> None:
    """預設模型與基準都是 Auto；預覽顯示實際採用的 IIR 與原因。"""
    view = _view(shell)
    assert view.mode_dd.value == "auto" and view.ref_state_dd.value == "Auto"
    assert "真實流體" in view.policy_preview.value and "IIR（Auto）" in view.policy_preview.value


def test_auto_result_metadata_shows_resolved_model_and_reference(shell) -> None:
    """結果中繼資料顯示實際模型與 concrete 基準，不只是「Auto」；保存的狀態點帶 IIR。"""
    view = _view(shell)
    _query(view)

    assert view.result_panel.status == "success", view.result_panel.message
    assert view.result_panel.metadata["Reference"] == "IIR（Auto）"
    assert view.result_panel.metadata["Engine"] == "真實流體（CoolProp）"
    assert "--- 模型與基準 ---" in view.raw_output.value
    assert isinstance(view._last_state_point, ThermoStatePoint)
    assert view._last_state_point.reference_state == "IIR"


def test_switching_models_never_resets_fluid_to_r32(shell) -> None:
    """切換模型不會把使用者的物質改成 R32；濕空氣暫存並還原原輸入，且明確提示。"""
    view = _view(shell)
    view.fluid_tf.value = "R717"
    view.on_fluid_change(None)

    for model in ("real_fluid", "ideal_gas", "auto"):
        _select_model(view, model)
        assert view.fluid_tf.value == "R717"

    _select_model(view, "humid_air")
    assert view.fluid_tf.value == "Air" and view.fluid_tf.disabled is True
    assert "R717" in view.mode_notice.value and view.mode_notice.visible
    _select_model(view, "real_fluid")
    assert view.fluid_tf.value == "R717" and view.fluid_tf.disabled is False
    assert "還原" in view.mode_notice.value


def test_reference_selector_disabled_for_models_without_coolprop_reference(shell) -> None:
    """理想氣體／濕空氣沒有 CoolProp reference state：選單固定 Auto 並停用、說明原因。"""
    view = _view(shell)
    view.ref_state_dd.value = "NBP"
    view.on_ref_state_change(None)

    _select_model(view, "ideal_gas")
    assert view.ref_state_dd.disabled is True and view.ref_state_dd.value == "Auto"
    assert "不適用" in view.reference_state_helper.value
    _select_model(view, "real_fluid")
    assert view.ref_state_dd.disabled is False


def test_manual_unsupported_reference_shows_error_and_keeps_inputs(shell) -> None:
    """手動 Water + IIR 不支援：明確錯誤、沒有結果、保留使用者輸入。"""
    view = _view(shell)
    view.fluid_tf.value = "Water"
    view.on_fluid_change(None)
    view.ref_state_dd.value = "IIR"
    view.on_ref_state_change(None)
    assert "無法解析" in view.policy_preview.value

    _query(view, "101.325", "25")
    assert view.result_panel.status == "error"
    assert "IIR" in view.result_panel.message
    assert view.fluid_tf.value == "Water" and view.input_rows[0]["val"].value == "101.325"
    assert view._last_state_point is None


def test_auto_fallback_is_visible_in_preview_and_metadata(shell) -> None:
    """不支援 IIR 的流體（Nitrogen）Auto 改用 DEF，預覽與結果都顯示備援原因。"""
    view = _view(shell)
    view.fluid_tf.value = "Nitrogen"
    view.on_fluid_change(None)
    assert "DEF（Auto）" in view.policy_preview.value and "不支援 IIR" in view.policy_preview.value

    _query(view, "101.325", "25")
    assert view.result_panel.status == "success", view.result_panel.message
    assert view.result_panel.metadata["Reference"] == "DEF（Auto）"
    assert "不支援 IIR" in view.result_panel.metadata["Fallback"]


def test_ideal_gas_result_shows_entropy_unavailable_and_saves_without_entropy(shell) -> None:
    """理想氣體結果不顯示假 S=0；保存為 IDEAL_GAS 基準、比熵 None。"""
    view = _view(shell)
    view.fluid_tf.value = "Air"
    view.on_fluid_change(None)
    _select_model(view, "ideal_gas")
    _query(view, "101.325", "25")

    assert view.result_panel.status == "success", view.result_panel.message
    assert "Entropy" not in view.result_panel.metrics
    assert "不提供（理想氣體模型）" in view.raw_output.value
    assert view._last_state_point.reference_state == "IDEAL_GAS"
    assert view._last_state_point.entropy_j_kgk is None


def test_humid_air_calculation_uses_psychrometrics_per_kg_dry_air(shell) -> None:
    """濕空氣：乾球 25 °C、RH 50 %、海拔 0 m → RH 分率 0.5、kJ/kg_dry_air、保存為 AirStatePoint。"""
    view = _view(shell)
    _select_model(view, "humid_air")
    assert view.humid_air_card.visible and not view.conditions_card.visible
    view.humid_dry_bulb_tf.value = "25"
    view.humidity_value_tf.value = "50"
    view.perform_calculation(None)

    assert view.result_panel.status == "success", view.result_panel.message
    assert view.result_panel.metadata["Basis"] == "kJ/kg_dry_air"
    assert view.result_panel.metadata["Reference"] == "不適用"
    assert view.result_panel.metrics["相對濕度"] == "50.0 %"
    assert isinstance(view._last_state_point, AirStatePoint)
    assert view._last_state_point.relative_humidity == pytest.approx(0.5)


def test_humid_air_missing_humidity_is_an_input_error(shell) -> None:
    """濕空氣缺少濕度條件：欄位錯誤，不偷偷改成乾空氣計算。"""
    view = _view(shell)
    _select_model(view, "humid_air")
    view.humid_dry_bulb_tf.value = "25"
    view.humidity_value_tf.value = ""
    view.perform_calculation(None)

    assert view.result_panel.status == "error"
    assert view.humidity_value_tf.error_text
    assert view._last_si_results is None


@pytest.mark.parametrize(
    "change",
    ["model", "reference", "fluid", "humidity_type", "humidity_value"],
)
def test_semantic_changes_invalidate_previous_result(shell, change) -> None:
    """改變模型、基準、物質或濕度條件會使舊結果、儲存快照失效。"""
    view = _view(shell)
    if change.startswith("humidity"):
        _select_model(view, "humid_air")
        view.humid_dry_bulb_tf.value = "25"
        view.humidity_value_tf.value = "50"
        view.perform_calculation(None)
    else:
        _query(view)
    assert view.result_panel.status == "success", view.result_panel.message

    if change == "model":
        _select_model(view, "ideal_gas")
    elif change == "reference":
        view.ref_state_dd.value = "ASHRAE"
        view.on_ref_state_change(None)
    elif change == "fluid":
        view.fluid_tf.value = "R134a"
        view.on_fluid_change(None)
    elif change == "humidity_type":
        view.humidity_type_dd.value = "Twb"
        view.humidity_type_dd.on_select(SimpleNamespace(control=view.humidity_type_dd))
        assert view.humidity_value_tf.value == ""
    else:
        view.humidity_value_tf.on_change(SimpleNamespace(control=view.humidity_value_tf))

    assert view.result_panel.status == "warning"
    assert view._last_si_results is None and view._last_state_point is None


def test_reference_change_then_recalculate_saves_new_concrete_basis(shell) -> None:
    """換基準後重新計算，保存的是新的 concrete 基準。"""
    view = _view(shell)
    _query(view)
    view.ref_state_dd.value = "ASHRAE"
    view.on_ref_state_change(None)
    _query(view)
    assert view._last_state_point.reference_state == "ASHRAE"


def test_configuration_fields_stack_on_narrow_screens(shell) -> None:
    """設定欄位與濕空氣欄位在 xs（手機寬度 320／375 px）各佔整列，md（≥ 768 px）並排。"""
    view = _view(shell)

    def responsive_containers(control):
        found = []
        stack = [control]
        while stack:
            current = stack.pop()
            if isinstance(current, ft.ResponsiveRow):
                found.extend(current.controls)
            content = getattr(current, "content", None)
            if isinstance(content, ft.Control):
                stack.append(content)
            stack.extend(getattr(current, "controls", None) or [])
        return found

    for card in (view.humid_air_card,):
        cells = responsive_containers(card)
        assert cells and all(cell.col.get("xs") == 12 for cell in cells)
    config_cells = [cell for cell in responsive_containers(view) if getattr(cell, "content", None) in
                    (view.mode_dd, view.fluid_tf)]
    assert len(config_cells) == 2 and all(cell.col == {"xs": 12, "md": 4} for cell in config_cells)
