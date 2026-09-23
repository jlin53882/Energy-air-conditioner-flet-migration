"""Regression contracts for the HVAC engineering workspace UI migration."""

from __future__ import annotations

import importlib


def _module(name: str):
    """Import one target UI module after checking that the migration created it."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith("Flet_ui.ui"):
            raise AssertionError(f"Required UI module is missing: {name}") from error
        raise


def test_navigation_uses_stable_route_ids_and_exposes_existing_calculators() -> None:
    """Navigation identity must be stable and all existing tools independently reachable."""
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
    """The application shell must provide the required independent navigation regions."""
    shell = _module("Flet_ui.ui.app_shell")
    assert hasattr(shell, "AppShell")
    assert {"sidebar", "top_bar", "workspace", "context_panel"} <= set(
        shell.AppShell.REGIONS
    )


def test_shared_quantity_input_keeps_value_and_unit_semantically_together() -> None:
    """Reusable quantity control must own its value and unit controls as one component."""
    module = _module("Flet_ui.ui.components.quantity_input")
    component = module.QuantityInput(label="入口壓力", property_code="P")

    assert component.property_code == "P"
    assert component.value_control is not None
    assert component.unit_control is not None
    assert component.control is not None
    assert component.control.expand is True


def test_structured_result_panel_has_non_dump_success_and_error_states() -> None:
    """Result rendering must expose semantic states instead of relying on text color alone."""
    module = _module("Flet_ui.ui.components.result_panel")
    panel = module.ResultPanel()

    assert {"empty", "loading", "success", "warning", "error"} <= set(
        panel.SUPPORTED_STATES
    )
    assert hasattr(panel, "set_metrics")


def test_global_unit_preference_is_separate_from_input_units() -> None:
    """Switching output preferences must not replace independently selected inputs."""
    module = _module("Flet_ui.ui.state")
    state = module.WorkspaceState(output_unit_system="SI")
    state.set_input_unit("suction_pressure", "psi")
    state.set_output_unit_system("Imperial")

    assert state.output_unit_system == "Imperial"
    assert state.input_units["suction_pressure"] == "psi"


def test_relative_humidity_and_quality_keep_distinct_display_contracts() -> None:
    """RH uses percentage display while thermodynamic quality remains a unitless fraction."""
    from Flet_ui.ui_components.unit.PropertyFormatter import PropertyFormatter
    from Flet_ui.ui_components.unit.UnitConverter import UnitConverter

    converter = UnitConverter()
    formatter = PropertyFormatter(converter)
    quality = formatter.format_specific_properties({"Q": 0.88, "phase": "twophase"}, False)
    rh_percent = converter.convert_from_si("RH", 0.88, "%")

    assert "0.8800 (0-1)" in quality
    assert f"{rh_percent:.0f} %" == "88 %"
    assert "0.88 %" not in quality
