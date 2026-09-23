"""Small application state separate from Flet controls and calculation results."""

from dataclasses import dataclass, field


@dataclass
class WorkspaceState:
    """Hold navigation and display preferences without mutating input choices."""

    route_key: str = "thermo_properties"
    output_unit_system: str = "SI"
    input_units: dict[str, str] = field(default_factory=dict)

    def set_input_unit(self, input_key: str, unit: str) -> None:
        """Remember one input's own unit independently of global display units."""
        self.input_units[input_key] = unit

    def set_output_unit_system(self, unit_system: str) -> None:
        """Set the preference used to render output quantities."""
        if unit_system not in {"SI", "Imperial"}:
            raise ValueError(f"Unsupported output unit system: {unit_system}")
        self.output_unit_system = unit_system
