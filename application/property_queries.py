"""Application service for neutral thermodynamic property queries."""

from __future__ import annotations

from domain.thermodynamics.state_service import ThermodynamicStateService

from .models import PropertyQueryRequest


class PropertyQueryService:
    """Validate and orchestrate property requests without channel concerns."""

    def __init__(self, state_service: ThermodynamicStateService) -> None:
        """Initialize with an explicit shared thermodynamic service."""
        self.state_service = state_service

    def is_fluid_valid(self, fluid_name: str) -> bool:
        """Validate a fluid through the shared thermodynamic service."""
        return self.state_service.is_fluid_valid(fluid_name)

    @property
    def reference_state(self):
        """Expose the service-owned reference-state registry for composition/tests."""
        return self.state_service.reference_state

    def set_reference_state(self, fluid_name: str, ref_state: str) -> None:
        """Apply reference-state policy through the shared service."""
        self.state_service.set_reference_state(fluid_name, ref_state)

    def query(self, request: PropertyQueryRequest) -> dict[str, float | str]:
        """Validate a request and return a neutral thermodynamic result."""
        if not request.fluid.strip():
            raise ValueError("fluid is required")
        if len(request.known_properties) < 2:
            raise ValueError("at least two known properties are required")
        return self.state_service.calculate_properties(
            request.fluid.strip(),
            request.known_properties,
            request.is_ideal_gas,
            request.reference_state,
        )
