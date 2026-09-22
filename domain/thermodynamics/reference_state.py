"""Process-wide reference-state synchronization and request policy."""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
from threading import RLock
from typing import Iterator

import CoolProp.CoolProp as CP


_PROCESS_COOLPROP_LOCK = RLock()
_PROCESS_REFERENCE_STATES: dict[str, str] = {}


class ReferenceStatePolicy(str, Enum):
    """Explicit policies for a reference-state-sensitive request."""

    DEFAULT = "DEF"
    ASHRAE = "ASHRAE"
    IIR = "IIR"
    NBP = "NBP"
    CURRENT = "CURRENT"


class ReferenceStateService:
    """Serialize CoolProp transactions and record process-global state policy."""

    VALID_CODES = frozenset({"DEF", "ASHRAE", "IIR", "NBP"})

    @property
    def lock(self) -> RLock:
        """Expose the process-wide lock for identity/regression checks."""
        return _PROCESS_COOLPROP_LOCK

    @staticmethod
    def _normalize_policy(policy: ReferenceStatePolicy | str) -> str:
        """Normalize a request policy without conflating CURRENT and DEFAULT."""
        normalized = policy.value if isinstance(policy, ReferenceStatePolicy) else policy.upper()
        if normalized == "DEFAULT":
            normalized = ReferenceStatePolicy.DEFAULT.value
        if normalized == ReferenceStatePolicy.CURRENT.value:
            return normalized
        if normalized not in ReferenceStateService.VALID_CODES:
            raise ValueError(f"Unsupported reference state policy '{policy}'")
        return normalized

    def _set_unlocked(self, fluid_name: str, ref_state: ReferenceStatePolicy | str) -> None:
        """Apply a concrete CoolProp mutation while the shared lock is held."""
        normalized = self._normalize_policy(ref_state)
        if normalized == ReferenceStatePolicy.CURRENT.value:
            raise ValueError("CURRENT is not valid for set(); choose a concrete policy")
        try:
            CP.set_reference_state(fluid_name, normalized)
        except (KeyError, ValueError) as exc:
            raise ValueError(
                f"Unable to set reference state '{normalized}' for '{fluid_name}'"
            ) from exc
        _PROCESS_REFERENCE_STATES[fluid_name] = normalized

    def set(self, fluid_name: str, ref_state: ReferenceStatePolicy | str) -> None:
        """Set a concrete reference state and update the shared process registry."""
        with _PROCESS_COOLPROP_LOCK:
            self._set_unlocked(fluid_name, ref_state)

    @contextmanager
    def calculation_scope(
        self,
        fluid_name: str,
        ref_state: ReferenceStatePolicy | str = ReferenceStatePolicy.CURRENT,
    ) -> Iterator[None]:
        """Protect a complete request transaction under an explicit policy.

        ``CURRENT`` deliberately preserves the current process state for an
        internal operation such as a fluid-validity probe. Ordinary property
        entrypoints must pass a concrete policy such as ``DEFAULT`` or
        ``ASHRAE``; they must not rely on ambient state.
        """
        normalized = self._normalize_policy(ref_state)
        with _PROCESS_COOLPROP_LOCK:
            if normalized != ReferenceStatePolicy.CURRENT.value:
                self._set_unlocked(fluid_name, normalized)
            yield

    def current(self, fluid_name: str) -> str | None:
        """Return the process-global observed reference state for a fluid."""
        with _PROCESS_COOLPROP_LOCK:
            return _PROCESS_REFERENCE_STATES.get(fluid_name)
