"""PR #1 review finding F1-F7 的 regression test。"""

from __future__ import annotations

import ast
import inspect
import threading
from pathlib import Path

import CoolProp.CoolProp as CP
import pytest

from domain.thermodynamics.reference_state import ReferenceStatePolicy, ReferenceStateService
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter
from application.models import PropertyQueryRequest
from application.property_queries import PropertyQueryService
from Flet_ui.ui_components.analysis_modules.hvac_compressor_module import CompressorModule
from Flet_ui.ui_components.property_tab import PropertyTab
from Flet_ui.ui_components.unit.PropertyFormatter import PropertyFormatter
from Flet_ui.ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter
from Telegram_bot.thermo_calculator import ThermoCalculator

ROOT = Path(__file__).parents[2]


def test_reference_state_services_share_process_lock() -> None:
    """每個 service instance 都必須序列化相同的 CoolProp process state。

回傳：
    無。"""
    assert ReferenceStateService().lock is ReferenceStateService().lock


def test_iapws_is_not_a_reference_state_policy() -> None:
    """只有 CoolProp 預先定義的 states 與 CURRENT 屬於 policy enum。

回傳：
    無。"""
    service = ReferenceStateService()
    assert {
        ReferenceStatePolicy.DEFAULT.value,
        ReferenceStatePolicy.ASHRAE.value,
        ReferenceStatePolicy.IIR.value,
        ReferenceStatePolicy.NBP.value,
        ReferenceStatePolicy.CURRENT.value,
    } == {"DEF", "ASHRAE", "IIR", "NBP", "CURRENT"}
    for policy in ("DEF", "ASHRAE", "IIR", "NBP"):
        assert service._normalize_policy(policy) == policy
    with pytest.raises(ValueError):
        service.set("R134a", "IAPWS")


def test_water_property_request_uses_default_not_ambient_state() -> None:
    """Water 的一般 query 會重設為 CoolProp 的明確 default policy。

回傳：
    無。"""
    from domain.thermodynamics.fluid_policy import resolve_reference_state_policy

    service = ThermodynamicStateService(CanonicalUnitConverter())
    query_service = PropertyQueryService(service)
    known_props = (("T", 25.0, "°C"), ("P", 1.0, "bar"))
    assert resolve_reference_state_policy("Water", "ASHRAE") == ReferenceStatePolicy.DEFAULT
    assert resolve_reference_state_policy("Water", "ASHRAE") != ReferenceStatePolicy.CURRENT
    try:
        service.set_reference_state("Water", "NBP")
        actual = query_service.query(PropertyQueryRequest("Water", known_props))
        expected = service.calculate_properties(
            "Water", known_props, reference_state=ReferenceStatePolicy.DEFAULT
        )
    finally:
        service.set_reference_state("Water", "DEF")

    assert actual["H"] == pytest.approx(expected["H"])
    assert actual["S"] == pytest.approx(expected["S"])


def test_chart_auto_policy_is_explicit_for_water() -> None:
    """Chart Auto 會選擇具體 defaults，並拒絕將 IAPWS 作為 policy code。

回傳：
    無。"""
    from Flet_ui.ui_components.unit.thermo_draw.coolprop_utils import (
        _effective_reference_state,
    )

    assert _effective_reference_state("Water", "Auto") == ReferenceStatePolicy.DEFAULT
    assert _effective_reference_state("R134a", "Auto") == ReferenceStatePolicy.ASHRAE
    with pytest.raises(ValueError):
        _effective_reference_state("Water", "IAPWS")


@pytest.mark.parametrize("fluid", ["Water", "water", "WATER", " Water "])
def test_property_water_aliases_use_default_reference_state(fluid: str) -> None:
    """Property request 不論流體拼法為何，都使用同一個 Water policy。

參數：
    fluid (str): 函數輸入值。

回傳：
    無。"""
    from domain.thermodynamics.fluid_policy import resolve_reference_state_policy

    assert resolve_reference_state_policy(fluid) == ReferenceStatePolicy.DEFAULT


@pytest.mark.parametrize("fluid", ["Water", "water", "WATER", " Water "])
def test_chart_auto_water_aliases_use_default_reference_state(fluid: str) -> None:
    """Chart Auto 共用中立的 Water policy resolver。

參數：
    fluid (str): 函數輸入值。

回傳：
    無。"""
    from Flet_ui.ui_components.unit.thermo_draw.coolprop_utils import (
        _effective_reference_state,
    )

    assert _effective_reference_state(fluid, "Auto") == ReferenceStatePolicy.DEFAULT
    assert _effective_reference_state("R134a", "Auto") == ReferenceStatePolicy.ASHRAE


def test_property_selection_policy_is_shared_with_compressor_example() -> None:
    """PropertyTab 的選擇就是 compressor page 消費的 policy。

回傳：
    None：函數計算或處理後的結果。"""
    class DummyPage:
        overlay = []

    class ValueControl:
        def __init__(self, value: str) -> None:
            self.value = value

    class CapturingAnalyzer:
        def __init__(self) -> None:
            self.reference_states: list[str] = []

        def calculate_compressor_example(self, *args, ref_state_code: str):
            self.reference_states.append(ref_state_code)
            return 0.8, 1.0, 0.7, 2.0, 0.6

    converter = UnitConverter()
    state_calculator = ThermoStateCalculator(converter)
    query_service = PropertyQueryService(state_calculator.state_service)
    property_tab = PropertyTab(
        unit_converter=converter,
        formatter=PropertyFormatter(converter),
        page=DummyPage(),
        query_service=query_service,
    )
    property_tab.mode_dd.value = "CoolProp (冷媒)"
    property_tab.fluid_tf.value = "R134a"
    property_tab.ref_state_dd.value = "IIR"
    property_tab.on_ref_state_change(None)

    compressor = CompressorModule.__new__(CompressorModule)
    compressor.reference_state_provider = query_service
    compressor.unit_converter = converter
    compressor.analyzer = CapturingAnalyzer()
    compressor.ce_substance_tf = ValueControl("R134a")
    compressor.all_entries = {
        key: {"val": ValueControl(value), "unit": ValueControl(unit)}
        for key, value, unit in (
            ("ce_r", "8", ""),
            ("ce_p1", "1", converter.default_units["P"]),
            ("ce_p2", "2", converter.default_units["P"]),
            ("ce_p0", "1", converter.default_units["P"]),
            ("ce_t1", "20", converter.default_units["T"]),
            ("ce_t2", "40", converter.default_units["T"]),
            ("ce_t0", "20", converter.default_units["T"]),
            ("ce_v1_dot", "1", converter.default_units["VolumeFlow"]),
        )
    }
    compressor._reference_state_for("R134a")
    assert compressor._reference_state_for(" water ") == ReferenceStatePolicy.DEFAULT
    compressor.calculate_comp_example(use_imperial=False)
    assert compressor.analyzer.reference_states == ["IIR"]

    property_tab.ref_state_dd.value = "NBP"
    property_tab.on_ref_state_change(None)
    compressor.calculate_comp_example(use_imperial=False)
    assert compressor.analyzer.reference_states == ["IIR", "NBP"]


def test_t_s_renderer_path_returns_figure_without_residual_count_access(monkeypatch) -> None:
    """set_ylim 不再回傳 attribute 後，T-s renderer path 仍可執行。

參數：
    monkeypatch (未指定型別): 函數輸入值。

回傳：
    無。"""
    from Flet_ui.ui_components.unit import UnitConverter as unit_converter_module
    from Flet_ui.ui_components.unit.thermo_draw import coolprop_utils

    converter = unit_converter_module.UnitConverter()
    monkeypatch.setattr(
        coolprop_utils,
        "get_saturation_curve",
        lambda *args, **kwargs: (
            [300.0, 320.0],
            [100000.0, 200000.0],
            [300.0, 320.0],
            [100000.0, 200000.0],
        ),
    )
    monkeypatch.setattr(
        coolprop_utils,
        "safe_props",
        lambda output, *args, **kwargs: {
            "S": 1000.0,
            "H": 250000.0,
            "D": 1.0,
        }.get(output, 300.0),
    )
    monkeypatch.setattr(
        coolprop_utils.CP,
        "PropsSI",
        lambda output, *args: {
            "Tcrit": 500.0,
            "pcrit": 5.0e6,
            "ptriple": 1.0e3,
            "Ttriple": 250.0,
        }[output],
    )

    figure = coolprop_utils.generate_thermo_diagram(
        "R134a",
        "T-s",
        [{"input_type": "T-P", "T_K": 300.0, "P_Pa": 1.0e5, "label": "1"}],
        converter,
        ref_state="Auto",
    )
    assert figure.axes
    source = (ROOT / "Flet_ui/ui_components/unit/thermo_draw/coolprop_utils.py").read_text(
        encoding="utf-8"
    )
    assert "set_ylim(bottom=None, top=max(current_ymax, display_T_max * 1.05)) .count" not in source


def test_reference_state_registry_is_process_global() -> None:
    """由另一個 service 讀取 registry 時可看見 process-global state。

回傳：
    無。"""
    first = ReferenceStateService()
    second = ReferenceStateService()
    try:
        first.set("R134a", "IIR")
        assert second.current("R134a") == "IIR"
    finally:
        first.set("R134a", "DEF")


def test_calculation_default_policy_does_not_inherit_ambient_state() -> None:
    """省略的 request policy 會解析為明確的 channel default。

回傳：
    無。"""
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
    """Telegram 的 default policy 不受先前 Flet request 影響。

回傳：
    無。"""
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
    """延後處理的 Telegram V semantics 仍使用明確的 state ownership。

回傳：
    無。"""
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
    """Production entrypoints 公開具體的 reference-state policy。

回傳：
    無。"""
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
    """並行 mutation 不可插入完整的 property query。

參數：
    monkeypatch (pytest.MonkeyPatch): 函數輸入值。

回傳：
    None：函數計算或處理後的結果。"""
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
    """Domain layer 不得 import Flet 或 Telegram 套件。

回傳：
    無。"""
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
    """Application layer 不得 import channel implementations。

回傳：
    無。"""
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
    """Production direct mutation 僅限於核准的 mechanism。

回傳：
    無。"""
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
    """Flet 與 Telegram canonical properties 不得默默接受 units。

回傳：
    無。"""
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
    """每個 definition 都擁有明確的 semantic ID，而不是 positional ID。

回傳：
    無。"""
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
    """PropertyTab 與 compressor pages 不得以 facade state 作為真實來源。

回傳：
    無。"""
    property_source = (ROOT / "Flet_ui/ui_components/property_tab.py").read_text(encoding="utf-8")
    calculator_source = (ROOT / "Flet_ui/ui_components/unit/ThermoStateCalculator.py").read_text(encoding="utf-8")
    compressor_source = (ROOT / "Flet_ui/ui_components/analysis_modules/hvac_compressor_module.py").read_text(encoding="utf-8")
    assert "state_calculator.set_coolprop_ref_state" not in property_source
    assert "self.state_calculator.is_fluid_valid" not in property_source
    assert "current_ref_code" not in calculator_source
    assert "self.state_calculator.current_ref_code" not in compressor_source


def test_readme_and_project_description_exist() -> None:
    """已發布專案必須具備實際的 landing document 與 metadata。

回傳：
    無。"""
    readme = ROOT / "README.md"
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert readme.exists()
    assert "Add your description here" not in pyproject
