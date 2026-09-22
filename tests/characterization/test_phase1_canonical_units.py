"""Phase 1 tests for the canonical unit contract."""

from __future__ import annotations

import pytest

from domain.units.converter import CanonicalUnitConverter
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter
from Telegram_bot.thermo_calculator import ThermoCalculator


@pytest.fixture
def canonical_converter() -> CanonicalUnitConverter:
    """Create the canonical unit converter under test."""
    return CanonicalUnitConverter()


def test_canonical_converter_round_trips_core_quantities(
    canonical_converter: CanonicalUnitConverter,
) -> None:
    """Core physical quantities round-trip through explicit SI transforms."""
    cases = (
        ("P", 1.2, "bar"),
        ("T", 25.0, "°C"),
        ("H", 250.0, "kJ/kg"),
        ("S", 1.1, "kJ/(kg.K)"),
        ("D", 1.5, "lbm/ft³"),
        ("U", 300.0, "Btu/lbm"),
    )

    for prop_code, value, unit_code in cases:
        si_value = canonical_converter.convert_to_si(prop_code, value, unit_code)
        assert canonical_converter.convert_from_si(prop_code, si_value, unit_code) == pytest.approx(value)


def test_canonical_converter_uses_specific_volume_semantics(
    canonical_converter: CanonicalUnitConverter,
) -> None:
    """V is a specific volume at the domain boundary, not density."""
    assert canonical_converter.convert_to_si("V", 0.5, "m³/kg") == pytest.approx(0.5)
    assert canonical_converter.convert_to_si("V", 16.0185, "ft³/lbm") == pytest.approx(
        16.0185 * 0.062428
    )
    assert canonical_converter.convert_from_si("V", 1.0, "ft³/lbm") == pytest.approx(
        1.0 / 0.062428
    )


def test_flet_converter_delegates_core_quantities_to_canonical_contract() -> None:
    """The existing Flet facade exposes the canonical core transforms."""
    converter = UnitConverter()
    canonical = CanonicalUnitConverter()

    for prop_code, value, unit_code in (("P", 1.2, "bar"), ("T", 25.0, "°C"), ("H", 250.0, "kJ/kg")):
        assert converter.convert_to_si(prop_code, value, unit_code) == pytest.approx(
            canonical.convert_to_si(prop_code, value, unit_code)
        )


def test_telegram_converter_delegates_core_quantities_to_canonical_contract() -> None:
    """The Telegram calculator uses the same core conversion semantics."""
    converter = ThermoCalculator()
    canonical = CanonicalUnitConverter()

    for prop_code, value, unit_code in (("P", 1.2, "bar"), ("T", 25.0, "°C"), ("H", 250.0, "kJ/kg")):
        assert converter._convert_to_si(prop_code, value, unit_code) == pytest.approx(
            canonical.convert_to_si(prop_code, value, unit_code)
        )
        assert converter._convert_from_si(
            prop_code,
            canonical.convert_to_si(prop_code, value, unit_code),
            unit_code,
        ) == pytest.approx(value)


def test_canonical_converter_rejects_unknown_units() -> None:
    """Unknown core units fail explicitly instead of silently changing semantics."""
    with pytest.raises(ValueError, match="Unknown unit"):
        CanonicalUnitConverter().convert_to_si("P", 1.0, "not-a-pressure-unit")
