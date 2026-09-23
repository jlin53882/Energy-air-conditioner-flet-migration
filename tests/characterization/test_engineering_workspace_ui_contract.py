"""HVAC 工程工作區 UI 遷移的回歸契約測試。"""

from __future__ import annotations

import importlib


def _module(name: str):
    """確認遷移所需 UI 模組存在後再匯入。

參數：
    name: 完整的 Python 模組名稱。

回傳：
    匯入成功的模組。

引發：
    AssertionError: 必要的工作區模組不存在時。"""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith("Flet_ui.ui"):
            raise AssertionError(f"Required UI module is missing: {name}") from error
        raise


def test_navigation_uses_stable_route_ids_and_exposes_existing_calculators() -> None:
    """確認導覽採穩定路由識別碼，且現有工具可分別到達。

回傳：
    無。"""
    navigation = _module("Flet_ui.ui.navigation")
    route_ids = {route.key for route in navigation.ROUTES}

    assert {
        "thermo_properties",
        "compressor",
        "evaporator",
        "condenser",
        "psychrometrics",
        "ph_chart",
        "ts_chart",
    } <= route_ids


def test_app_shell_owns_sidebar_top_bar_workspace_and_context_panel() -> None:
    """確認應用程式外殼包含必要的導覽與工作區區域。

回傳：
    無。"""
    shell = _module("Flet_ui.ui.app_shell")
    assert hasattr(shell, "AppShell")
    assert {"sidebar", "top_bar", "workspace", "context_panel"} <= set(
        shell.AppShell.REGIONS
    )


def test_shared_quantity_input_keeps_value_and_unit_semantically_together() -> None:
    """確認共用數量輸入元件將數值與單位控制項組合在一起。

回傳：
    無。"""
    module = _module("Flet_ui.ui.components.quantity_input")
    component = module.QuantityInput(label="入口壓力", property_code="P")

    assert component.property_code == "P"
    assert component.value_control is not None
    assert component.unit_control is not None
    assert component.control is not None
    assert component.control.expand is True


def test_structured_result_panel_has_non_dump_success_and_error_states() -> None:
    """確認結果面板提供明確狀態，不只以文字顏色區分結果。

回傳：
    無。"""
    module = _module("Flet_ui.ui.components.result_panel")
    panel = module.ResultPanel()

    assert {"empty", "loading", "success", "warning", "error"} <= set(
        panel.SUPPORTED_STATES
    )
    assert hasattr(panel, "set_metrics")


def test_global_unit_preference_is_separate_from_input_units() -> None:
    """確認切換輸出偏好不會取代個別欄位的輸入單位。

回傳：
    無。"""
    module = _module("Flet_ui.ui.state")
    state = module.WorkspaceState(output_unit_system="SI")
    state.set_input_unit("condition_0_P", "psia")
    state.set_input_unit("condition_1_P", "kPa")
    state.set_output_unit_system("Imperial")

    assert state.output_unit_system == "Imperial"
    assert state.input_units == {"condition_0_P": "psia", "condition_1_P": "kPa"}


def test_relative_humidity_and_quality_keep_distinct_display_contracts() -> None:
    """確認 RH 以百分比呈現，熱力學乾度則維持無單位比例值。

回傳：
    無。"""
    from Flet_ui.ui_components.unit.PropertyFormatter import PropertyFormatter
    from Flet_ui.ui_components.unit.UnitConverter import UnitConverter

    converter = UnitConverter()
    formatter = PropertyFormatter(converter)
    quality = formatter.format_specific_properties({"Q": 0.88, "phase": "twophase"}, False)
    rh_percent = converter.convert_from_si("RH", 0.88, "%")

    assert "0.8800 (0-1)" in quality
    assert f"{rh_percent:.0f} %" == "88 %"
    assert "0.88 %" not in quality
