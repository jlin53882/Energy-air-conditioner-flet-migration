"""Desktop-first application shell with responsive navigation regions."""

import flet as ft
from collections.abc import Callable

from .components.sidebar import Sidebar
from .navigation import DEFAULT_ROUTE, ROUTE_BY_KEY
from .state import WorkspaceState
from .theme import TOKENS


class AppShell(ft.Column):
    """Own top-level navigation and layout while delegating each calculation view."""

    REGIONS = frozenset({"sidebar", "top_bar", "workspace", "context_panel"})


    def __init__(self, page: ft.Page, views: dict[str, ft.Control], *,
                 on_route_change: Callable[[str], None] | None = None,
                 on_unit_system_change: Callable[[str], None] | None = None,
                 on_fluid_shortcut: Callable[[str], None] | None = None,
                 state: WorkspaceState | None = None) -> None:
        """Compose application regions without coupling route state to display labels."""
        super().__init__(expand=True, spacing=0)
        self._page_ref = page
        self.views = views
        self._unique_views = list({id(view): view for view in views.values()}.values())
        for view in self._unique_views:
            view.visible = False
        self.view_host = ft.Stack(controls=self._unique_views, expand=True)
        self.on_route_change = on_route_change
        self.on_unit_system_change = on_unit_system_change
        self.on_fluid_shortcut = on_fluid_shortcut
        self.state = state or WorkspaceState(route_key=DEFAULT_ROUTE)
        self.route_header = ft.Column(spacing=TOKENS.spacing_xs)
        self.workspace = ft.Container(expand=True, padding=TOKENS.spacing_lg)
        self.context_panel = ft.Container(
            width=TOKENS.context_panel_width,
            padding=TOKENS.spacing_md,
            bgcolor=TOKENS.surface,
            content=ft.Column([
                ft.Text("計算歷史", size=TOKENS.section_title, weight=ft.FontWeight.W_600),
                ft.Text("計算歷史尚未啟用；本版本不會保存計算紀錄。", size=TOKENS.caption,
                        color=ft.Colors.BLUE_GREY_600),
                ft.Divider(height=1, color=TOKENS.border),
                ft.Text("常用冷媒", size=TOKENS.section_title, weight=ft.FontWeight.W_600),
                ft.Text("快捷選項，不代表 CoolProp 的完整支援清單。",
                        size=TOKENS.caption, color=ft.Colors.BLUE_GREY_600),
                ft.ResponsiveRow([
                    ft.Container(
                        ft.OutlinedButton(
                            fluid,
                            on_click=(lambda _event, value=fluid: self.on_fluid_shortcut(value))
                            if self.on_fluid_shortcut else None,
                        ),
                        col={"xs": 6},
                    )
                    for fluid in ("R32", "R410A", "R134a", "R290", "R600a", "R22")
                ], spacing=TOKENS.spacing_xs, run_spacing=TOKENS.spacing_xs),
            ], spacing=TOKENS.spacing_md),
            border=ft.Border.only(left=ft.BorderSide(1, TOKENS.border)),
        )
        self.sidebar = Sidebar(self.navigate, self.state.route_key)
        self.sidebar.left = 0
        self.sidebar.top = 0
        self.sidebar.bottom = 0
        self.unit_toggle = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value="SI", label=ft.Text("SI")),
                ft.Segment(value="Imperial", label=ft.Text("Imperial")),
            ],
            selected=[self.state.output_unit_system],
            on_change=self._on_unit_change,
        )
        self.top_bar = ft.Container(
            content=ft.Row([
                ft.IconButton(ft.Icons.MENU, tooltip="顯示或隱藏導覽", on_click=self._toggle_sidebar),
                ft.Icon(ft.Icons.AC_UNIT, color=TOKENS.primary, size=26),
                ft.Column([
                    ft.Text("熱力學計算與冷凍空調分析工具", size=17, weight=ft.FontWeight.W_600),
                    ft.Text("HVAC & Thermodynamics Analysis Workspace", size=TOKENS.caption,
                            color=ft.Colors.BLUE_GREY_600),
                ], spacing=0, expand=True),
                ft.Text("輸出", size=TOKENS.caption, color=ft.Colors.BLUE_GREY_600),
                self.unit_toggle,
            ], spacing=TOKENS.spacing_sm, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_lg, vertical=TOKENS.spacing_sm),
            bgcolor=TOKENS.surface,
            border=ft.Border.only(bottom=ft.BorderSide(1, TOKENS.border)),
        )
        self.workspace.content = ft.Column(
            [self.route_header, self.view_host],
            spacing=TOKENS.spacing_lg,
            expand=True,
        )
        self.workspace_row = ft.Row(
            [self.workspace, self.context_panel], spacing=0, expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.workspace_region = ft.Container(content=self.workspace_row, expand=True)
        self.content_row = ft.Stack(
            [self.workspace_region, self.sidebar],
            expand=True,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        self.controls = [self.top_bar, self.content_row]
        self.navigate(self.state.route_key, notify=False)
        try:
            self._page_ref.on_resize = self._on_resize
            self._page_ref.on_keyboard_event = self._on_keyboard_event
        except (AttributeError, RuntimeError):
            pass
        self._on_resize(None)

    def navigate(self, route_key: str, *, notify: bool = True) -> None:
        """Select an implemented view by stable route key and refresh its heading."""
        if route_key not in ROUTE_BY_KEY:
            raise KeyError(f"Unknown workspace route: {route_key}")
        route = ROUTE_BY_KEY[route_key]
        if route_key not in self.views:
            raise KeyError(f"No view registered for route: {route_key}")
        if notify and self.on_route_change:
            self.on_route_change(route_key)
        self.state.route_key = route_key
        self.sidebar.selected_key = route_key
        for key, item in self.sidebar.items.items():
            selected = key == route_key
            icon, label = item.content.controls
            icon.color = TOKENS.primary if selected else ft.Colors.BLUE_GREY_600
            label.weight = ft.FontWeight.W_600 if selected else ft.FontWeight.W_400
            item.bgcolor = "#E7EFF8" if selected else None
        active_view = self.views[route_key]
        for view in self._unique_views:
            view.visible = view is active_view
        self.route_header.controls = [
            ft.Text(route.label, size=TOKENS.title, weight=ft.FontWeight.W_700),
            ft.Text("工程計算工作區 · 輸入單位可獨立選擇", size=TOKENS.body,
                    color=ft.Colors.BLUE_GREY_600),
        ]
        self._on_resize(None)
        try:
            self.update()
        except RuntimeError:
            pass

    def set_output_unit_system(self, unit_system: str) -> None:
        """Update only the global output preference and notify the active view adapter."""
        self.state.set_output_unit_system(unit_system)
        self.unit_toggle.selected = [unit_system]
        if self.on_unit_system_change:
            self.on_unit_system_change(unit_system)
        try:
            self.update()
        except RuntimeError:
            pass

    def _on_unit_change(self, event: ft.ControlEvent | None) -> None:
        """Forward a display preference without rewriting per-field input units."""
        selected = next(iter(event.control.selected), "SI") if event else self.state.output_unit_system
        self.set_output_unit_system(selected)

    def _toggle_sidebar(self, _event: ft.ControlEvent | None) -> None:
        """Open or close the full navigation drawer only at narrow widths."""
        if (getattr(self._page_ref, "width", None) or 1280) >= 800:
            return
        self.sidebar.set_compact(False)
        self.sidebar.visible = not self.sidebar.visible
        try:
            self.sidebar.update()
        except RuntimeError:
            pass

    def _on_keyboard_event(self, event: ft.KeyboardEvent) -> None:
        """Run the active calculation on Ctrl+Enter and dismiss a narrow nav drawer on Esc."""
        key = (event.key or "").lower()
        if event.ctrl and key in {"enter", "numpad enter"}:
            view = self.views[self.state.route_key]
            calculate = getattr(view, "perform_calculation", None)
            if calculate is None:
                calculate = getattr(view, "calculate_analysis", None)
            if calculate is not None:
                calculate(None)
        elif key == "escape" and (getattr(self._page_ref, "width", 1280) or 1280) < 800:
            self.sidebar.visible = False
            try:
                self.sidebar.update()
            except RuntimeError:
                pass

    def _on_resize(self, _event: ft.ControlEvent | None) -> None:
        """Use compact navigation and collapse contextual content as the window narrows."""
        width = getattr(self._page_ref, "width", None) or 1280
        if width < 800:
            self.sidebar.set_compact(False)
            self.sidebar.visible = False
            self.sidebar.width = TOKENS.sidebar_width
            self.workspace_region.padding = ft.Padding.only(left=0)
            self.context_panel.visible = False
            self.workspace.padding = TOKENS.spacing_sm
        elif width < 1200:
            self.sidebar.set_compact(True)
            self.sidebar.visible = True
            self.sidebar.width = 76
            self.workspace_region.padding = ft.Padding.only(left=76)
            self.context_panel.visible = False
            self.workspace.padding = TOKENS.spacing_md
        else:
            self.sidebar.set_compact(False)
            self.sidebar.visible = True
            self.sidebar.width = TOKENS.sidebar_width
            self.workspace_region.padding = ft.Padding.only(left=TOKENS.sidebar_width)
            self.context_panel.visible = True
            self.workspace.padding = TOKENS.spacing_lg
