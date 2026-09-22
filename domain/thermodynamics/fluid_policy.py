"""Neutral fluid identity and default reference-state policy helpers."""

from __future__ import annotations

from domain.thermodynamics.reference_state import ReferenceStatePolicy


def normalize_fluid_name(fluid: str) -> str:
    """Return a fluid name with user-entered surrounding whitespace removed."""
    return fluid.strip()


def is_water(fluid: str) -> bool:
    """Return whether a fluid name identifies Water case-insensitively."""
    return normalize_fluid_name(fluid).casefold() == "water"


def resolve_reference_state_policy(
    fluid: str,
    requested_policy: ReferenceStatePolicy | str | None = None,
) -> ReferenceStatePolicy | str:
    """Resolve one explicit ordinary-request policy for a fluid.

    Water uses CoolProp's default reference state. Other fluids retain the
    caller's explicit policy, or the application default when none is given.
    """
    if is_water(fluid):
        return ReferenceStatePolicy.DEFAULT
    return requested_policy or ReferenceStatePolicy.ASHRAE
