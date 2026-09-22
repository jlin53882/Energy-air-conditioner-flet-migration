"""Neutral application requests for thermodynamic property queries."""

from __future__ import annotations

from dataclasses import dataclass

from domain.thermodynamics.reference_state import ReferenceStatePolicy
from domain.thermodynamics.state_service import KnownProperty


@dataclass(frozen=True)
class PropertyQueryRequest:
    """Describe a property query independently of any channel UI."""

    fluid: str
    known_properties: tuple[KnownProperty, ...]
    is_ideal_gas: bool = False
    reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT


@dataclass(frozen=True)
class CompressionRatioRequest:
    """Describe a compression-ratio calculation in canonical pascals."""

    suction_pressure_pa: float
    discharge_pressure_pa: float
