"""Shared card container for consistent engineering workspace hierarchy."""

import flet as ft

from ..theme import TOKENS


class EngineeringCard(ft.Container):
    """Present a titled content group with the shared workspace surface style."""

    def __init__(self, title: str, content: ft.Control, subtitle: str | None = None):
        """Build a consistent card without taking ownership of its content logic."""
        children: list[ft.Control] = [ft.Text(title, size=TOKENS.section_title, weight=ft.FontWeight.W_600)]
        if subtitle:
            children.append(ft.Text(subtitle, size=TOKENS.caption, color=ft.Colors.BLUE_GREY_600))
        children.append(content)
        super().__init__(
            content=ft.Column(children, spacing=TOKENS.spacing_md),
            padding=TOKENS.spacing_lg,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
        )
