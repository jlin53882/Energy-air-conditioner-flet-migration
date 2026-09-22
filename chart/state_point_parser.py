"""Headless parser for thermodynamic chart state-point input."""

from __future__ import annotations

from domain.units.converter import CanonicalUnitConverter

from .models import StatePoint


class StatePointParser:
    """Parse comma-separated chart input into neutral SI state points."""

    def __init__(self, unit_converter: CanonicalUnitConverter | None = None) -> None:
        """Initialize with the shared canonical unit converter."""
        self.unit_converter = unit_converter or CanonicalUnitConverter()

    def parse(
        self,
        pressures: str,
        temperatures: str,
        pressure_unit: str,
        temperature_unit: str,
    ) -> list[StatePoint]:
        """Parse paired comma-separated pressures and temperatures."""
        pressure_values = self._parse_numbers(pressures)
        temperature_values = self._parse_numbers(temperatures)
        if len(pressure_values) != len(temperature_values):
            raise ValueError("pressures and temperatures must contain the same number of values")
        return [
            StatePoint(
                pressure_pa=self.unit_converter.convert_to_si("P", pressure, pressure_unit),
                temperature_k=self.unit_converter.convert_to_si("T", temperature, temperature_unit),
            )
            for pressure, temperature in zip(pressure_values, temperature_values)
        ]

    @staticmethod
    def _parse_numbers(raw_value: str) -> list[float]:
        """Parse a non-empty comma-separated numeric string."""
        try:
            values = [float(item.strip()) for item in raw_value.split(",") if item.strip()]
        except ValueError as exc:
            raise ValueError("chart inputs must be numeric") from exc
        if not values:
            raise ValueError("chart inputs must contain at least one numeric value")
        return values
