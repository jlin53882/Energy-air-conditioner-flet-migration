"""Process-wide reference-state synchronization for CoolProp."""

from __future__ import annotations

from contextlib import contextmanager
from threading import RLock
from typing import Iterator

import CoolProp.CoolProp as CP


_PROCESS_COOLPROP_LOCK = RLock()


class ReferenceStateService:
    """Serialize CoolProp mutation and dependent query transactions.

    CoolProp stores reference state globally in the process. Every service
    instance therefore uses the same module-level lock; callers can use
    :meth:`calculation_scope` to keep a requested mutation and all dependent
    queries atomic.
    """

    VALID_CODES = frozenset({"DEF", "ASHRAE", "IAPWS", "IIR", "NBP"})

    def __init__(self) -> None:
        """Initialize the per-fluid observed state registry."""
        self._current_by_fluid: dict[str, str] = {}

    @property
    def lock(self) -> RLock:
        """Expose the process-wide lock for identity/regression checks."""
        return _PROCESS_COOLPROP_LOCK

    def _normalize(self, ref_state: str) -> str:
        """Normalize and validate a public reference-state code."""
        normalized = ref_state.upper()
        if normalized == "DEFAULT":
            normalized = "DEF"
        if normalized not in self.VALID_CODES:
            raise ValueError(f"Unsupported reference state '{ref_state}'")
        return normalized

    def _set_unlocked(self, fluid_name: str, ref_state: str) -> None:
        """Apply a reference-state mutation while the shared lock is held."""
        normalized = self._normalize(ref_state)
        try:
            CP.set_reference_state(fluid_name, normalized)
        except (KeyError, ValueError) as exc:
            raise ValueError(
                f"Unable to set reference state '{normalized}' for '{fluid_name}'"
            ) from exc
        self._current_by_fluid[fluid_name] = normalized

    def set(self, fluid_name: str, ref_state: str) -> None:
        """Set a validated CoolProp reference state atomically."""
        with _PROCESS_COOLPROP_LOCK:
            self._set_unlocked(fluid_name, ref_state)

    @contextmanager
    def calculation_scope(
        self,
        fluid_name: str,
        ref_state: str | None = None,
    ) -> Iterator[None]:
        """Protect a complete mutation plus dependent CoolProp query sequence.

        Args:
            fluid_name: Fluid whose global CoolProp state is being queried.
            ref_state: Optional state to apply before entering the query body.

        Yields:
            Nothing; the caller performs all dependent ``PropsSI``/``PhaseSI``
            calls inside the context.
        """
        with _PROCESS_COOLPROP_LOCK:
            if ref_state is not None:
                self._set_unlocked(fluid_name, ref_state)
            yield

    def current(self, fluid_name: str) -> str | None:
        """Return the last reference state set through this service."""
        with _PROCESS_COOLPROP_LOCK:
            return self._current_by_fluid.get(fluid_name)
