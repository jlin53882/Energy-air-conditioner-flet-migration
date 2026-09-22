"""Canonical SI unit conversion for domain services.

The domain contract uses explicit SI quantities.  Display-unit preferences
belong to channel adapters; this module only defines physical conversions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


Conversion = Callable[[float], float]


@dataclass(frozen=True)
class UnitDefinition:
    """Describe one display unit and its explicit bidirectional transforms."""

    property_code: str
    unit_code: str
    to_si: Conversion
    from_si: Conversion


class CanonicalUnitConverter:
    """Convert core thermodynamic quantities to and from canonical SI units."""

    CORE_PROPERTIES = frozenset({"P", "T", "H", "S", "D", "V", "U"})

    def __init__(self) -> None:
        """Build explicit conversion definitions for core quantities."""
        self._definitions = self._build_definitions()

    @staticmethod
    def _build_definitions() -> dict[tuple[str, str], UnitDefinition]:
        """Return the canonical core unit definitions.

        Returns:
            A mapping keyed by ``(property_code, unit_code)``.
        """
        return {
            ("P", "Pa"): UnitDefinition("P", "Pa", lambda v: v, lambda v: v),
            ("P", "kPa"): UnitDefinition("P", "kPa", lambda v: v * 1_000.0, lambda v: v / 1_000.0),
            ("P", "MPa"): UnitDefinition("P", "MPa", lambda v: v * 1_000_000.0, lambda v: v / 1_000_000.0),
            ("P", "bar"): UnitDefinition("P", "bar", lambda v: v * 100_000.0, lambda v: v / 100_000.0),
            ("P", "psia"): UnitDefinition("P", "psia", lambda v: v * 6_894.757, lambda v: v / 6_894.757),
            ("P", "psi"): UnitDefinition("P", "psi", lambda v: v * 6_894.757, lambda v: v / 6_894.757),
            ("P", "kg/cm^2"): UnitDefinition("P", "kg/cm^2", lambda v: v * 98_066.5, lambda v: v / 98_066.5),
            ("T", "K"): UnitDefinition("T", "K", lambda v: v, lambda v: v),
            ("T", "°C"): UnitDefinition("T", "°C", lambda v: v + 273.15, lambda v: v - 273.15),
            ("T", "C"): UnitDefinition("T", "C", lambda v: v + 273.15, lambda v: v - 273.15),
            ("T", "°F"): UnitDefinition("T", "°F", lambda v: (v - 32.0) * 5.0 / 9.0 + 273.15, lambda v: (v - 273.15) * 9.0 / 5.0 + 32.0),
            ("T", "F"): UnitDefinition("T", "F", lambda v: (v - 32.0) * 5.0 / 9.0 + 273.15, lambda v: (v - 273.15) * 9.0 / 5.0 + 32.0),
            ("H", "J/kg"): UnitDefinition("H", "J/kg", lambda v: v, lambda v: v),
            ("H", "kJ/kg"): UnitDefinition("H", "kJ/kg", lambda v: v * 1_000.0, lambda v: v / 1_000.0),
            ("H", "Btu/lbm"): UnitDefinition("H", "Btu/lbm", lambda v: v * 2_326.0, lambda v: v / 2_326.0),
            ("S", "J/(kg.K)"): UnitDefinition("S", "J/(kg.K)", lambda v: v, lambda v: v),
            ("S", "kJ/(kg.K)"): UnitDefinition("S", "kJ/(kg.K)", lambda v: v * 1_000.0, lambda v: v / 1_000.0),
            ("S", "Btu/(lbm.R)"): UnitDefinition("S", "Btu/(lbm.R)", lambda v: v * 4_186.8, lambda v: v / 4_186.8),
            ("D", "kg/m³"): UnitDefinition("D", "kg/m³", lambda v: v, lambda v: v),
            ("D", "kg/cm³"): UnitDefinition("D", "kg/cm³", lambda v: v * 1_000_000.0, lambda v: v / 1_000_000.0),
            ("D", "lbm/ft³"): UnitDefinition("D", "lbm/ft³", lambda v: v * 16.0185, lambda v: v / 16.0185),
            ("V", "m³/kg"): UnitDefinition("V", "m³/kg", lambda v: v, lambda v: v),
            ("V", "ft³/lbm"): UnitDefinition("V", "ft³/lbm", lambda v: v * 0.062428, lambda v: v / 0.062428),
            ("U", "J/kg"): UnitDefinition("U", "J/kg", lambda v: v, lambda v: v),
            ("U", "kJ/kg"): UnitDefinition("U", "kJ/kg", lambda v: v * 1_000.0, lambda v: v / 1_000.0),
            ("U", "Btu/lbm"): UnitDefinition("U", "Btu/lbm", lambda v: v * 2_326.0, lambda v: v / 2_326.0),
        }

    def _get_definition(self, property_code: str, unit_code: str) -> UnitDefinition:
        """Look up a conversion definition or raise an explicit contract error."""
        try:
            return self._definitions[(property_code, unit_code)]
        except KeyError as exc:
            raise ValueError(f"Unknown unit '{unit_code}' for property '{property_code}'") from exc

    def convert_to_si(self, property_code: str, value: float, unit_code: str) -> float:
        """Convert a display value to the canonical SI quantity."""
        return self._get_definition(property_code, unit_code).to_si(value)

    def convert_from_si(self, property_code: str, value_si: float, unit_code: str) -> float:
        """Convert a canonical SI quantity to a display value."""
        return self._get_definition(property_code, unit_code).from_si(value_si)

    def get_available_units(self, property_code: str) -> list[str]:
        """Return the explicitly registered units for a core property."""
        if property_code not in self.CORE_PROPERTIES:
            return []
        return [
            unit_code
            for (registered_property, unit_code) in self._definitions
            if registered_property == property_code
        ]
