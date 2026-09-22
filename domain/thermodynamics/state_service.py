"""Headless thermodynamic property calculation service."""

from __future__ import annotations

from typing import Iterable

import CoolProp.CoolProp as CP

from domain.units.converter import CanonicalUnitConverter
from .reference_state import ReferenceStateService


KnownProperty = tuple[str, float, str]


class ThermodynamicStateService:
    """Calculate thermodynamic states using canonical SI inputs and outputs."""

    PROPERTIES = ("P", "T", "H", "S", "D", "Q", "V", "U")

    def __init__(
        self,
        unit_converter: CanonicalUnitConverter,
        reference_state: ReferenceStateService | None = None,
    ) -> None:
        """Initialize the service with explicit conversion and state policy."""
        self.unit_converter = unit_converter
        self.reference_state = reference_state or ReferenceStateService()
        self.ideal_gas_props = {
            "Air": {"R": 287.058, "Cp": 1005.0},
            "Water": {"R": 461.5, "Cp": 1870.0},
        }

    def is_fluid_valid(self, fluid_name: str) -> bool:
        """Return whether CoolProp recognizes a fluid identifier."""
        try:
            with self.reference_state.calculation_scope(fluid_name):
                CP.PropsSI("Tcrit", fluid_name)
        except ValueError:
            return False
        return True

    def set_reference_state(self, fluid_name: str, ref_state: str) -> None:
        """Apply a reference state through the centralized mechanism."""
        self.reference_state.set(fluid_name, ref_state)

    def calculate_properties(
        self,
        fluid: str,
        known_props: Iterable[KnownProperty],
        is_ideal_gas: bool = False,
        reference_state: str | None = None,
    ) -> dict[str, float | str]:
        """Calculate a state from at least two known properties.

        Args:
            fluid: CoolProp fluid or supported ideal-gas name.
            known_props: Property code, display value and unit triples.
            is_ideal_gas: Select the built-in ideal-gas model.

        Returns:
            A dictionary of canonical SI values plus ``phase``.

        Raises:
            ValueError: If fewer than two properties are supplied or input
                conversion/model requirements are invalid.
            RuntimeError: If CoolProp cannot calculate the requested state.
        """
        properties = list(known_props)
        if len(properties) < 2:
            raise ValueError("請至少提供兩組已知的性質。")

        processed: list[tuple[str, float, str]] = []
        for prop, value, unit in properties:
            if prop == "V":
                if value == 0:
                    raise ValueError("比容 (V) 不能為零。")
                specific_volume = self.unit_converter.convert_to_si(prop, value, unit)
                processed.append(("D", 1.0 / specific_volume, "kg/m³"))
            else:
                processed.append((prop, value, unit))

        known_si = [
            (prop, self.unit_converter.convert_to_si(prop, value, unit))
            for prop, value, unit in processed
        ]
        try:
            if is_ideal_gas:
                return self._calculate_ideal_gas(fluid, dict(known_si))
            return self._calculate_coolprop(fluid, known_si, reference_state)
        except Exception as exc:
            raise RuntimeError(f"在計算 '{fluid}' 的性質時發生錯誤: {exc}") from exc

    def _calculate_coolprop(
        self,
        fluid: str,
        known_props_si: list[tuple[str, float]],
        reference_state: str | None = None,
    ) -> dict[str, float | str]:
        """Calculate all configured properties in one synchronized transaction."""
        with self.reference_state.calculation_scope(fluid, reference_state):
            prop1, value1 = known_props_si[0]
            prop2, value2 = known_props_si[1]
            result: dict[str, float | str] = {}
            for property_code in self.PROPERTIES:
                if property_code == "V":
                    density = CP.PropsSI("D", prop1, value1, prop2, value2, fluid)
                    result[property_code] = 1.0 / density if density else float("inf")
                else:
                    result[property_code] = CP.PropsSI(
                        property_code, prop1, value1, prop2, value2, fluid
                    )
            result["phase"] = CP.PhaseSI(prop1, value1, prop2, value2, fluid)
            return result

    def _calculate_ideal_gas(
        self,
        fluid: str,
        input_values: dict[str, float],
    ) -> dict[str, float | str]:
        """Calculate the supported ideal-gas state combinations."""
        try:
            constants = self.ideal_gas_props[fluid]
        except KeyError as exc:
            raise ValueError(f"找不到 {fluid} 的理想氣體常數。") from exc

        gas_constant = constants["R"]
        heat_capacity = constants["Cp"]
        cv = heat_capacity - gas_constant
        result: dict[str, float | str]
        if "P" in input_values and "T" in input_values:
            result = {"P": input_values["P"], "T": input_values["T"]}
            result["D"] = result["P"] / (gas_constant * result["T"])
        elif "P" in input_values and "D" in input_values:
            result = {"P": input_values["P"], "D": input_values["D"]}
            result["T"] = result["P"] / (result["D"] * gas_constant)
        elif "T" in input_values and "D" in input_values:
            result = {"T": input_values["T"], "D": input_values["D"]}
            result["P"] = result["D"] * gas_constant * result["T"]
        else:
            raise ValueError("理想氣體計算需要 P&T, P&D 或 T&D 的組合。")

        result["H"] = heat_capacity * result["T"]
        result["U"] = cv * result["T"]
        result["V"] = 1.0 / result["D"] if result["D"] else float("inf")
        result["S"] = 0.0
        result["Q"] = -1.0
        result["phase"] = "gas"
        return result
