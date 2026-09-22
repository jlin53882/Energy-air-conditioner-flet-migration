"""Reference-state policy and mechanism for CoolProp's process-global state."""

from __future__ import annotations

from threading import RLock

import CoolProp.CoolProp as CP


class ReferenceStateService:
    """Serialize and validate CoolProp reference-state mutations."""

    VALID_CODES = frozenset({"DEF", "ASHRAE", "IIR", "NBP"})

    def __init__(self) -> None:
        """Initialize the lock and per-fluid observed state registry."""
        self._lock = RLock()
        self._current_by_fluid: dict[str, str] = {}

    def set(self, fluid_name: str, ref_state: str) -> None:
        """Set a validated CoolProp reference state for one fluid.

        Args:
            fluid_name: CoolProp fluid identifier.
            ref_state: ``DEF``, ``ASHRAE``, ``IIR`` or ``NBP``.

        Raises:
            ValueError: If the reference-state code is unsupported or CoolProp
                rejects the mutation.
        """
        normalized = ref_state.upper()
        if normalized == "DEFAULT":
            normalized = "DEF"
        if normalized not in self.VALID_CODES:
            raise ValueError(f"Unsupported reference state '{ref_state}'")

        with self._lock:
            try:
                CP.set_reference_state(fluid_name, normalized)
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    f"Unable to set reference state '{normalized}' for '{fluid_name}'"
                ) from exc
            self._current_by_fluid[fluid_name] = normalized

    def current(self, fluid_name: str) -> str | None:
        """Return the last reference state set through this service."""
        with self._lock:
            return self._current_by_fluid.get(fluid_name)
