"""Phase 5 tests for application-level property orchestration."""

from __future__ import annotations

import pytest

from application.models import PropertyQueryRequest
from application.property_queries import PropertyQueryService
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter


def test_property_query_service_is_headless_and_returns_neutral_result() -> None:
    """Application orchestration can run without Flet controls or Telegram state."""
    service = PropertyQueryService(ThermodynamicStateService(CanonicalUnitConverter()))
    result = service.query(
        PropertyQueryRequest(
            fluid="Air",
            known_properties=(
                ("P", 101.325, "kPa"),
                ("T", 25.0, "°C"),
            ),
            is_ideal_gas=True,
        )
    )

    assert result["phase"] == "gas"
    assert result["P"] == pytest.approx(101325.0)


def test_property_query_service_owns_fluid_validation_and_reference_state() -> None:
    """The application boundary exposes lifecycle operations without UI types."""
    service = PropertyQueryService(ThermodynamicStateService(CanonicalUnitConverter()))
    assert service.is_fluid_valid("R134a") is True
    assert service.is_fluid_valid("not-a-fluid") is False
    service.set_reference_state("R134a", "ASHRAE")
    assert service.reference_state.current("R134a") == "ASHRAE"
    service.set_reference_state("R134a", "DEF")


def test_property_query_service_rejects_insufficient_inputs() -> None:
    """Application validation fails before entering the domain calculation."""
    service = PropertyQueryService(ThermodynamicStateService(CanonicalUnitConverter()))
    with pytest.raises(ValueError, match="at least two"):
        service.query(
            PropertyQueryRequest(
                fluid="Air",
                known_properties=(("T", 25.0, "°C"),),
                is_ideal_gas=True,
            )
        )
