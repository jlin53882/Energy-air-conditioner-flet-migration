"""用於 thermodynamic property query 的中立 application request。"""

from __future__ import annotations

from dataclasses import dataclass

from domain.thermodynamics.reference_state import ReferenceStatePolicy
from domain.thermodynamics.state_service import KnownProperty


@dataclass(frozen=True)
class PropertyQueryRequest:
    """描述不依賴 channel UI 的 property query。"""

    fluid: str
    known_properties: tuple[KnownProperty, ...]
    is_ideal_gas: bool = False
    reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT


@dataclass(frozen=True)
class CompressionRatioRequest:
    """描述以 canonical pascal 為單位的壓縮比計算。"""

    suction_pressure_pa: float
    discharge_pressure_pa: float
