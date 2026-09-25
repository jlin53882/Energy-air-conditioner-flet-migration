"""Phase 5 的 application-level property orchestration test。"""

from __future__ import annotations

import pytest

from Flet_ui.ui_components.analysis_modules.hvac_compressor_module import CompressorModule
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


def test_query_updates_requested_reference_state() -> None:
    """正式 property query 必須同步 application 擁有的 requested policy。

回傳：
    無。"""
    service = PropertyQueryService(ThermodynamicStateService(CanonicalUnitConverter()))
    try:
        service.query(
            PropertyQueryRequest(
                fluid="R134a",
                known_properties=(("T", 25.0, "°C"), ("P", 1.0, "bar")),
                reference_state="IIR",
            )
        )
        assert service.requested_reference_state("R134a") == "IIR"
    finally:
        service.set_reference_state("R134a", "DEF")


def test_query_policy_is_not_consumed_by_compressor() -> None:
    """物性查詢寫入的 policy 只屬於物性查詢頁；壓縮機依流體決定自己的 policy。

回傳：
    無。"""
    service = PropertyQueryService(ThermodynamicStateService(CanonicalUnitConverter()))
    compressor = CompressorModule.__new__(CompressorModule)
    try:
        service.query(
            PropertyQueryRequest(
                fluid="R134a",
                known_properties=(("T", 25.0, "°C"), ("P", 1.0, "bar")),
                reference_state="IIR",
            )
        )
        assert service.requested_reference_state("R134a") == "IIR"
        assert compressor._reference_state_for("R134a") == "ASHRAE"
    finally:
        service.set_reference_state("R134a", "DEF")


def test_set_reference_state_stores_canonical_default_alias() -> None:
    """Default alias 必須以 canonical `DEF` 保存，而不是保存 UI label。

回傳：
    無。"""
    service = PropertyQueryService(ThermodynamicStateService(CanonicalUnitConverter()))
    service.set_reference_state("R134a", "Default")
    assert service.requested_reference_state("R134a") == "DEF"


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
