"""Composable quantity controls that keep numeric value adjacent to its unit."""

import flet as ft

from ..theme import TOKENS


class QuantityInput:
    """Bundle a quantity label, numeric field, unit menu, and local validation."""

    def __init__(
        self,
        label: str,
        property_code: str,
        *,
        value_control: ft.TextField | None = None,
        unit_control: ft.Dropdown | None = None,
        helper_text: str | None = None,
    ) -> None:
        """Create a display component, optionally adopting compatible controls."""
        self.label = label
        self.property_code = property_code
        self.value_control = value_control or ft.TextField(
            keyboard_type=ft.KeyboardType.NUMBER,
            height=TOKENS.input_height,
            expand=True,
        )
        self.unit_control = unit_control or ft.Dropdown(width=118, height=TOKENS.input_height)
        self.helper_text = helper_text
        self.label_control = ft.Text(label, size=TOKENS.body, weight=ft.FontWeight.W_500)
        self.error_control = ft.Text("", size=TOKENS.caption, color=TOKENS.error, visible=False)
        content: list[ft.Control] = [
            self.label_control,
            ft.Row([self.value_control, self.unit_control], spacing=TOKENS.spacing_sm),
            self.error_control,
        ]
        if helper_text:
            content.append(ft.Text(helper_text, size=TOKENS.caption, color=ft.Colors.BLUE_GREY_600))
        self.control = ft.Column(content, spacing=TOKENS.spacing_xs, tight=True, expand=True)

    def set_error(self, message: str | None) -> None:
        """Show validation next to the field instead of routing it only to a snackbar."""
        self.value_control.error_text = message
        self.error_control.value = message or ""
        self.error_control.visible = bool(message)
        try:
            self.error_control.update()
        except RuntimeError:
            pass
