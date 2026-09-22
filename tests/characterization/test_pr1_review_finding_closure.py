"""Regression tests for PR #1 review findings F1-F7."""

from __future__ import annotations

import ast
import inspect
import threading
from pathlib import Path

import CoolProp.CoolProp as CP
import pytest

from domain.thermodynamics.reference_state import ReferenceStateService
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter
from application.models import PropertyQueryRequest
from Flet_ui.ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter
from Telegram_bot.thermo_calculator import ThermoCalculator

ROOT = Path(__file__).parents[2]


def test_reference_state_services_share_process_lock() -> None:
    """Every service instance must serialize the same CoolProp process state."""
    assert ReferenceStateService().lock is ReferenceStateService().lock


def test_reference_state_registry_is_process_global() -> None:
    """A registry read from another service sees the process-global state."""
    first = ReferenceStateService()
    second = ReferenceStateService()
    try:
        first.set("R134a", "IIR")
        assert second.current("R134a") == "IIR"
    finally:
        first.set("R134a", "DEF")


def test_calculation_default_policy_does_not_inherit_ambient_state() -> None:
    """An omitted request policy resolves to the explicit channel default."""
    service = ThermodynamicStateService(CanonicalUnitConverter())
    known_props = (("P", 101.325, "kPa"), ("T", 25.0, "°C"))
    try:
        service.calculate_properties("R134a", known_props, reference_state="ASHRAE")
        service.calculate_properties("R134a", known_props, reference_state="IIR")
        default_expected = service.calculate_properties(
            "R134a", known_props, reference_state="DEF"
        )
        service.calculate_properties("R134a", known_props, reference_state="IIR")
        channel_default = service.calculate_properties("R134a", known_props)
    finally:
        service.set_reference_state("R134a", "DEF")

    assert channel_default["H"] == pytest.approx(default_expected["H"])
    assert channel_default["S"] == pytest.approx(default_expected["S"])


def test_telegram_uses_explicit_default_after_flet_changes_state() -> None:
    """Telegram's default policy is independent from a preceding Flet request."""
    known_props = [("P", 101.325, "kPa"), ("T", 25.0, "°C")]
    flet = ThermoStateCalculator(UnitConverter())
    telegram = ThermoCalculator()
    expected = ThermodynamicStateService(CanonicalUnitConverter()).calculate_properties(
        "R134a", known_props, reference_state="DEF"
    )
    try:
        flet.set_coolprop_ref_state("R134a", "IIR")
        actual = telegram.calculate_properties("R134a", known_props)
    finally:
        flet.set_coolprop_ref_state("R134a", "DEF")

    assert actual["H"] == pytest.approx(expected["H"])
    assert actual["S"] == pytest.approx(expected["S"])


def test_telegram_legacy_v_path_accepts_explicit_policy() -> None:
    """The deferred Telegram V semantics still use explicit state ownership."""
    telegram = ThermoCalculator()
    flet = ThermoStateCalculator(UnitConverter())
    known_props = [("T", 25.0, "°C"), ("V", 0.2, "m³/kg")]
    try:
        flet.set_coolprop_ref_state("R134a", "IIR")
        actual = telegram.calculate_properties("R134a", known_props)
        expected = telegram.calculate_properties(
            "R134a", known_props, reference_state="DEF"
        )
    finally:
        flet.set_coolprop_ref_state("R134a", "DEF")

    assert actual["H"] == pytest.approx(expected["H"])
    assert actual["S"] == pytest.approx(expected["S"])


def test_thermodynamic_entrypoints_have_non_ambient_defaults() -> None:
    """Production entrypoints expose a concrete reference-state policy."""
    assert inspect.signature(ThermodynamicStateService.calculate_properties).parameters[
        "reference_state"
    ].default is not None
    assert inspect.signature(ThermoCalculator.calculate_properties).parameters[
        "reference_state"
    ].default is not None
    assert inspect.signature(ThermoCalculator._calculate_legacy_properties).parameters[
        "reference_state"
    ].default is not None
    assert PropertyQueryRequest(
        "R134a", (("P", 1.0, "bar"), ("T", 25.0, "°C"))
    ).reference_state is not None


def test_reference_state_and_query_are_one_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    """A concurrent mutation cannot interleave with a complete property query."""
    entered_first_query = threading.Event()
    release_query = threading.Event()
    mutation_finished = threading.Event()
    call_count = 0

    def fake_props_si(*args):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            entered_first_query.set()
            assert release_query.wait(timeout=2)
        output = args[0]
        if output in {"Tcrit", "Ttriple", "pcrit", "ptriple"}:
            return 300.0
        if output == "D":
            return 10.0
        return 100.0

    monkeypatch.setattr(CP, "PropsSI", fake_props_si)
    monkeypatch.setattr(CP, "PhaseSI", lambda *args: "gas")
    monkeypatch.setattr(CP, "set_reference_state", lambda *args: None)

    reference_state = ReferenceStateService()
    state_service = ThermodynamicStateService(CanonicalUnitConverter(), reference_state)
    result: dict[str, object] = {}

    def calculate() -> None:
        result.update(
            state_service.calculate_properties(
                "R134a",
                (("P", 100.0, "kPa"), ("T", 25.0, "°C")),
                reference_state="ASHRAE",
            )
        )

    def mutate_other_state() -> None:
        reference_state.set("R134a", "IIR")
        mutation_finished.set()

    query_thread = threading.Thread(target=calculate)
    query_thread.start()
    assert entered_first_query.wait(timeout=2)
    mutation_thread = threading.Thread(target=mutate_other_state)
    mutation_thread.start()

    assert not mutation_finished.wait(timeout=0.1)
    release_query.set()
    query_thread.join(timeout=2)
    mutation_thread.join(timeout=2)

    assert result["phase"] == "gas"
    assert mutation_finished.is_set()
    assert call_count >= 2


def test_domain_has_no_channel_package_imports() -> None:
    """The domain layer must not import Flet or Telegram packages."""
    forbidden = {"Flet_ui", "Telegram_bot", "flet", "telegram", "matplotlib"}
    for source_path in (ROOT / "domain").rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported.update(
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not imported & forbidden, source_path


def test_application_has_no_channel_package_imports() -> None:
    """The application layer must not import channel implementations."""
    forbidden = {"Flet_ui", "Telegram_bot", "flet", "telegram"}
    for source_path in (ROOT / "application").rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported.update(
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not imported & forbidden, source_path


def test_only_reference_state_service_may_mutate_coolprop() -> None:
    """Production direct mutation is limited to the approved mechanism."""
    approved = ROOT / "domain/thermodynamics/reference_state.py"
    for source_path in ROOT.rglob("*.py"):
        if source_path == approved or "tests" in source_path.parts:
            continue
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        direct_mutations = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "CP"
            and node.func.attr == "set_reference_state"
        ]
        assert not direct_mutations, source_path


def test_canonical_facades_reject_unknown_units() -> None:
    """Flet and Telegram canonical properties must not silently accept units."""
    flet_converter = UnitConverter()
    telegram_converter = ThermoCalculator()
    for converter, to_si, from_si in (
        (flet_converter, flet_converter.convert_to_si, flet_converter.convert_from_si),
        (telegram_converter, telegram_converter._convert_to_si, telegram_converter._convert_from_si),
    ):
        for property_code in ("P", "T", "H", "S", "D", "U"):
            with pytest.raises(ValueError):
                to_si(property_code, 1.0, "not-a-unit")
            with pytest.raises(ValueError):
                from_si(property_code, 1.0, "not-a-unit")


def test_analysis_ids_are_semantic_and_unique() -> None:
    """Each definition owns an explicit semantic ID, not a positional ID."""
    from Flet_ui.ui_components.analysis_tab import AnalysisTab
    from Flet_ui.ui_components.unit.HVACAnalyzer import HVACAnalyzer
    from Flet_ui.ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
    from Flet_ui.ui_components.unit.ThermoStateCalculator import ThermoStateCalculator

    class DummyPage:
        overlay: list[object] = []
        controls: list[object] = []

        def update(self) -> None:
            pass

    tab = AnalysisTab(
        unit_converter=UnitConverter(),
        page=DummyPage(),
        analyzer=HVACAnalyzer(),
        psy_calculator=PsychrometricCalculator(),
        state_calculator=ThermoStateCalculator(UnitConverter()),
    )
    definitions = list(tab.analysis_map.values())
    ids = [definition["analysis_id"] for definition in definitions]
    assert len(ids) == len(set(ids))
    assert all("Module." not in analysis_id for analysis_id in ids)
    assert all(not analysis_id.rsplit(".", 1)[-1].isdigit() for analysis_id in ids)


def test_property_tab_uses_property_query_service_for_lifecycle() -> None:
    """PropertyTab must not directly call ThermoStateCalculator lifecycle APIs."""
    source = (ROOT / "Flet_ui/ui_components/property_tab.py").read_text(encoding="utf-8")
    assert "state_calculator.set_coolprop_ref_state" not in source
    assert "self.state_calculator.is_fluid_valid" not in source


def test_readme_and_project_description_exist() -> None:
    """The published project must have a real landing document and metadata."""
    readme = ROOT / "README.md"
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert readme.exists()
    assert "Add your description here" not in pyproject
