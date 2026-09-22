"""Neutral application requests for thermodynamic property queries."""

from __future__ import annotations

from dataclasses import dataclass

from domain.thermodynamics.state_service import KnownProperty


@dataclass(frozen=True)
class PropertyQueryRequest:
    """Describe a property query independently of any channel UI."""

    fluid: str
    known_properties: tuple[KnownProperty, ...]
    is_ideal_gas: bool = False
