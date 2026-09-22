"""Application service for neutral thermodynamic property queries."""

from __future__ import annotations

from domain.thermodynamics.state_service import ThermodynamicStateService

from .models import PropertyQueryRequest


class PropertyQueryService:
    """Validate and orchestrate property requests without channel concerns."""

    def __init__(self, state_service: ThermodynamicStateService) -> None:
        """Initialize with an explicit shared thermodynamic service."""
        self.state_service = state_service
        self._requested_reference_states: dict[str, str] = {}

    def is_fluid_valid(self, fluid_name: str) -> bool:
        """Validate a fluid through the shared thermodynamic service."""
        return self.state_service.is_fluid_valid(fluid_name)

    @property
    def reference_state(self):
        """Expose the service-owned reference-state registry for composition/tests."""
        return self.state_service.reference_state

    def set_reference_state(self, fluid_name: str, ref_state: str) -> None:
        """Apply and record the requested policy through the shared service."""
        normalized_fluid = fluid_name.strip()
        self.state_service.set_reference_state(normalized_fluid, ref_state)
        self._requested_reference_states[normalized_fluid.casefold()] = ref_state

    def requested_reference_state(
        self, fluid_name: str, default: str = "ASHRAE"
    ) -> str:
        """Return the application-owned requested policy for a fluid.

        This is distinct from ``ReferenceStateService.current()``, which reports
        the observed process state rather than the user's requested policy.
        """
        return self._requested_reference_states.get(fluid_name.strip().casefold(), default)

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
