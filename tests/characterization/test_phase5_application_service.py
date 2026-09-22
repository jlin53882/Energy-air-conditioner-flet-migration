"""Phase 5 的 application-level property orchestration test。"""

from __future__ import annotations

import pytest

from application.models import PropertyQueryRequest
from application.property_queries import PropertyQueryService
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter


def test_property_query_service_is_headless_and_returns_neutral_result() -> None:
    """Application orchestration 不依賴 Flet control 或 Telegram state 也能執行。

回傳：
    無。"""
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
    """application boundary 提供 lifecycle operation，但不使用 UI type。

回傳：
    無。"""
    service = PropertyQueryService(ThermodynamicStateService(CanonicalUnitConverter()))
    assert service.is_fluid_valid("R134a") is True
    assert service.is_fluid_valid("not-a-fluid") is False
    service.set_reference_state("R134a", "ASHRAE")
    assert service.reference_state.current("R134a") == "ASHRAE"
    service.set_reference_state("R134a", "DEF")


def test_property_query_service_rejects_insufficient_inputs() -> None:
    """Application validation 必須在進入 domain calculation 前失敗。

回傳：
    無。"""
    service = PropertyQueryService(ThermodynamicStateService(CanonicalUnitConverter()))
    with pytest.raises(ValueError, match="at least two"):
        service.query(
            PropertyQueryRequest(
                fluid="Air",
                known_properties=(("T", 25.0, "°C"),),
                is_ideal_gas=True,
            )
        )
