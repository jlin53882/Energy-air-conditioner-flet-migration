"""Sectioned sidebar navigation with semantic keys and accessible tooltips."""

import flet as ft
from collections.abc import Callable

from ..navigation import ROUTES, WorkspaceRoute
from ..theme import TOKENS


class Sidebar(ft.Container):
    """Expose reachable routes grouped by engineering workflow."""

    def __init__(self, on_select: Callable[[str], None], selected_key: str) -> None:
        """Build icon-and-label items and report stable route keys on selection."""
        self.on_select = on_select
        self.selected_key = selected_key
        self.items: dict[str, ft.Control] = {}
        self.section_labels: list[ft.Text] = []
        groups: dict[str, list[WorkspaceRoute]] = {}
        for route in ROUTES:
            groups.setdefault(route.section, []).append(route)
        section_controls: list[ft.Control] = []
        for section, routes in groups.items():
            section_label = ft.Text(section, size=TOKENS.caption, color=ft.Colors.BLUE_GREY_600,
                                    weight=ft.FontWeight.W_600)
            self.section_labels.append(section_label)
            section_controls.append(section_label)
            for route in routes:
                item = self._route_item(route)
                self.items[route.key] = item
                section_controls.append(item)
        super().__init__(
            width=TOKENS.sidebar_width,
            content=ft.Column(section_controls, spacing=TOKENS.spacing_sm, scroll=ft.ScrollMode.AUTO),
            padding=TOKENS.spacing_md,
            bgcolor=TOKENS.surface,
            border=ft.Border.only(right=ft.BorderSide(1, TOKENS.border)),
        )

    def set_compact(self, compact: bool) -> None:
        """Hide labels and section headings when the rail cannot fit full navigation."""
        for label in self.section_labels:
            label.visible = not compact
        for item in self.items.values():
            _, label = item.content.controls
            label.visible = not compact
            item.content.alignment = (
                ft.MainAxisAlignment.CENTER if compact else ft.MainAxisAlignment.START
            )

    def _route_item(self, route: WorkspaceRoute) -> ft.Control:
        """Build one route control whose callback carries a stable key, not its label."""
        selected = route.key == self.selected_key
        icon = getattr(ft.Icons, route.icon)
        return ft.Container(
            content=ft.Row([ft.Icon(icon, size=18, color=TOKENS.primary if selected else ft.Colors.BLUE_GREY_600),
                            ft.Text(route.label, size=TOKENS.body, weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_400)],
                           spacing=TOKENS.spacing_sm),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_md, vertical=TOKENS.spacing_sm),
            bgcolor="#E7EFF8" if selected else None,
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
            on_click=lambda _event, key=route.key: self.on_select(key),
            tooltip=route.label,
        )
