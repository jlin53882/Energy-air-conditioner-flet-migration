"""以桌面為主並支援不同視窗寬度的應用程式外殼。"""

import flet as ft
from collections.abc import Callable

from .components.sidebar import Sidebar
from .navigation import DEFAULT_ROUTE, ROUTE_BY_KEY
from .state import WorkspaceState
from .theme import TOKENS, card_shadow, section_colors

FLUID_SHORTCUTS = ("R32", "R410A", "R134a", "R290", "R600a", "R22")
OUTPUT_SYSTEM_DESCRIPTIONS = {
    "SI": "結果以 SI 公制呈現，例如 kPa、°C、kJ/kg。",
    "Imperial": "結果以英制呈現，例如 psia、°F、Btu/lbm。",
}


class AppShell(ft.Column):
    """負責頂層導覽與版面配置，並將計算工作交由各畫面處理。"""

    REGIONS = frozenset({"sidebar", "top_bar", "workspace", "context_panel"})

    def __init__(self, page: ft.Page, views: dict[str, ft.Control], *,
                 on_route_change: Callable[[str], None] | None = None,
                 on_unit_system_change: Callable[[str], None] | None = None,
                 on_fluid_shortcut: Callable[[str], None] | None = None,
                 state: WorkspaceState | None = None) -> None:
        """建立導覽與工作區版面，並保留路由鍵與顯示標籤的分離。

參數：
    page: Flet 頁面，用於讀取視窗尺寸與註冊事件。
    views: 由穩定路由鍵映射至 Flet 畫面的字典。
    on_route_change: 選用的路由切換回呼函式。
    on_unit_system_change: 選用的輸出單位偏好回呼函式。
    on_fluid_shortcut: 選用的常用冷媒捷徑回呼函式。
    state: 選用的工作區狀態；未提供時建立新狀態。

回傳：
    無。"""
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

        self.route_header = ft.Column(spacing=2, tight=True, expand=True)
        self.route_icon = ft.Icon(ft.Icons.HOME_OUTLINED, size=24)
        self.route_icon_badge = ft.Container(
            content=self.route_icon,
            width=48,
            height=48,
            alignment=ft.Alignment.CENTER,
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
        )
        self.page_header = ft.Row(
            [self.route_icon_badge, self.route_header],
            spacing=TOKENS.spacing_md,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.workspace = ft.Container(expand=True, padding=TOKENS.spacing_lg)
        self.context_panel = self._build_context_panel()
        # 情境面板預設收起，讓計算頁有足夠寬度；寬版可由頂端列按鈕開啟。
        self.context_panel_open = False
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
        self.top_bar = self._build_top_bar()
        self.workspace.content = ft.Column(
            [self.page_header, self.view_host],
            spacing=TOKENS.spacing_lg,
            expand=True,
        )
        self.workspace_row = ft.Row(
            [self.workspace], spacing=0, expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.workspace_region = ft.Container(
            content=self.workspace_row, expand=True, bgcolor=TOKENS.background
        )
        # 情境面板以浮動抽屜覆蓋在工作區右側，開關時不改變計算頁的版面寬度。
        self.context_panel.right = 0
        self.context_panel.top = 0
        self.context_panel.bottom = 0
        self.context_panel.shadow = ft.BoxShadow(blur_radius=24, color="#330F2A47", offset=ft.Offset(-4, 0))
        self.content_row = ft.Stack(
            [self.workspace_region, self.sidebar, self.context_panel],
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

    def _build_top_bar(self) -> ft.Container:
        """建立頂端列：左側品牌區延續深色導覽，右側為麵包屑與輸出單位偏好。

回傳：
    頂端列容器。"""
        self.menu_button = ft.IconButton(
            ft.Icons.MENU,
            icon_color=ft.Colors.WHITE,
            tooltip="顯示或隱藏導覽",
            on_click=self._toggle_sidebar,
            visible=False,
        )
        self.brand_title = ft.Text(
            "熱力學與冷凍空調",
            size=TOKENS.body + 1,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.WHITE,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.brand_subtitle = ft.Text(
            "HVAC & Thermodynamics",
            size=TOKENS.overline,
            color=TOKENS.nav_text_muted,
            max_lines=1,
        )
        self.brand_text = ft.Column(
            [self.brand_title, self.brand_subtitle], spacing=0, tight=True, expand=True
        )
        self.brand_block = ft.Container(
            content=ft.Row(
                [
                    self.menu_button,
                    ft.Container(
                        content=ft.Icon(ft.Icons.AC_UNIT, color=TOKENS.nav_background, size=20),
                        width=34,
                        height=34,
                        alignment=ft.Alignment.CENTER,
                        bgcolor=TOKENS.nav_accent,
                        border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
                    ),
                    self.brand_text,
                ],
                spacing=TOKENS.spacing_sm + 2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=TOKENS.sidebar_width,
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_md),
            bgcolor=TOKENS.nav_background,
        )
        self.breadcrumb_section = ft.Text("", size=TOKENS.caption, color=TOKENS.text_muted)
        self.breadcrumb_label = ft.Text(
            "", size=TOKENS.body, weight=ft.FontWeight.W_600, color=TOKENS.text_primary
        )
        self.shortcut_hint = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.KEYBOARD_OUTLINED, size=14, color=TOKENS.text_muted),
                    ft.Text("Ctrl + Enter 執行計算", size=TOKENS.caption, color=TOKENS.text_muted),
                ],
                spacing=4,
                tight=True,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            bgcolor=TOKENS.surface_variant,
            border_radius=ft.BorderRadius.all(TOKENS.radius_pill),
        )
        self.breadcrumb_prefix = ft.Row(
            [
                self.breadcrumb_section,
                ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=TOKENS.text_muted),
            ],
            spacing=4,
            tight=True,
        )
        self.output_label = ft.Text("輸出單位", size=TOKENS.caption, color=TOKENS.text_secondary)
        self.context_toggle = ft.IconButton(
            ft.Icons.VIEW_SIDEBAR_OUTLINED,
            selected_icon=ft.Icons.VIEW_SIDEBAR,
            selected=False,
            icon_color=TOKENS.text_secondary,
            selected_icon_color=TOKENS.primary,
            tooltip="顯示或隱藏資訊欄（輸出設定、常用冷媒、快捷鍵）",
            on_click=self.toggle_context_panel,
        )
        bar_content = ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [self.breadcrumb_prefix, self.breadcrumb_label],
                        spacing=4,
                        expand=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.shortcut_hint,
                    self.output_label,
                    self.unit_toggle,
                    self.context_toggle,
                ],
                spacing=TOKENS.spacing_md,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_lg),
            expand=True,
        )
        return ft.Container(
            content=ft.Row(
                [self.brand_block, bar_content],
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            height=TOKENS.top_bar_height,
            bgcolor=TOKENS.surface,
            border=ft.Border.only(bottom=ft.BorderSide(1, TOKENS.border)),
        )

    def _panel_section(self, title: str, icon: ft.IconData, content: ft.Control) -> ft.Container:
        """建立情境面板中的一個小型分區卡片。

參數：
    title: 分區標題。
    icon: 分區圖示。
    content: 分區內容控制項。

回傳：
    情境面板分區容器。"""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, size=16, color=TOKENS.primary),
                            ft.Text(title, size=TOKENS.body, weight=ft.FontWeight.W_600,
                                    color=TOKENS.text_primary),
                        ],
                        spacing=TOKENS.spacing_sm,
                    ),
                    content,
                ],
                spacing=TOKENS.spacing_sm + 2,
            ),
            padding=TOKENS.spacing_md,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
        )

    def _build_context_panel(self) -> ft.Container:
        """建立情境面板：輸出設定、常用冷媒、快捷鍵與明確的歷史空狀態。

回傳：
    情境面板容器。"""
        self.output_system_badge = ft.Text(
            "", size=TOKENS.section_title, weight=ft.FontWeight.W_700, color=TOKENS.primary
        )
        self.output_system_hint = ft.Text("", size=TOKENS.caption, color=TOKENS.text_secondary)
        self.fluid_shortcut_buttons = [
            ft.Container(
                content=ft.Text(fluid, size=TOKENS.caption + 1, weight=ft.FontWeight.W_600,
                                color=TOKENS.primary, text_align=ft.TextAlign.CENTER),
                alignment=ft.Alignment.CENTER,
                padding=ft.Padding.symmetric(vertical=8),
                bgcolor=TOKENS.primary_soft,
                border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
                on_click=(lambda _event, value=fluid: self.on_fluid_shortcut(value))
                if self.on_fluid_shortcut else None,
                tooltip=f"以 {fluid} 開啟狀態查詢",
                ink=True,
                col={"xs": 4},
            )
            for fluid in FLUID_SHORTCUTS
        ]
        shortcuts = ft.Column(
            [
                self._shortcut_row("Ctrl + Enter", "執行目前畫面的計算"),
                self._shortcut_row("Esc", "關閉資訊欄或窄視窗導覽抽屜"),
            ],
            spacing=TOKENS.spacing_sm,
        )
        return ft.Container(
            width=TOKENS.context_panel_width,
            padding=TOKENS.spacing_md,
            bgcolor=TOKENS.surface_variant,
            border=ft.Border.only(left=ft.BorderSide(1, TOKENS.border)),
            content=ft.Column(
                [
                    self._panel_section(
                        "輸出設定",
                        ft.Icons.TUNE,
                        ft.Column([self.output_system_badge, self.output_system_hint], spacing=2),
                    ),
                    self._panel_section(
                        "常用冷媒",
                        ft.Icons.PROPANE_TANK_OUTLINED,
                        ft.Column(
                            [
                                ft.Text("點選即以該流體開啟狀態查詢；不代表 CoolProp 的完整支援清單。",
                                        size=TOKENS.caption, color=TOKENS.text_muted),
                                ft.ResponsiveRow(
                                    self.fluid_shortcut_buttons,
                                    spacing=TOKENS.spacing_xs + 2,
                                    run_spacing=TOKENS.spacing_xs + 2,
                                ),
                            ],
                            spacing=TOKENS.spacing_sm,
                        ),
                    ),
                    self._panel_section("鍵盤快捷鍵", ft.Icons.KEYBOARD_OUTLINED, shortcuts),
                    self._panel_section(
                        "計算歷史",
                        ft.Icons.HISTORY,
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.INBOX_OUTLINED, size=18, color=TOKENS.text_muted),
                                ft.Text("計算歷史尚未啟用；本版本不會保存計算紀錄。",
                                        size=TOKENS.caption, color=TOKENS.text_muted, expand=True),
                            ],
                            spacing=TOKENS.spacing_sm,
                        ),
                    ),
                ],
                spacing=TOKENS.spacing_md,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    @staticmethod
    def _shortcut_row(keys: str, description: str) -> ft.Row:
        """建立快捷鍵說明列。

參數：
    keys: 按鍵組合文字。
    description: 快捷鍵用途。

回傳：
    快捷鍵說明列控制項。"""
        return ft.Row(
            [
                ft.Container(
                    content=ft.Text(keys, size=TOKENS.overline, weight=ft.FontWeight.W_600,
                                    color=TOKENS.text_secondary),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    bgcolor=TOKENS.surface_muted,
                    border=ft.Border.all(1, TOKENS.border),
                    border_radius=ft.BorderRadius.all(6),
                ),
                ft.Text(description, size=TOKENS.caption, color=TOKENS.text_secondary, expand=True),
            ],
            spacing=TOKENS.spacing_sm,
        )

    def _refresh_output_system_summary(self) -> None:
        """同步情境面板中顯示的全域輸出單位偏好。

回傳：
    無。"""
        system = self.state.output_unit_system
        self.output_system_badge.value = "SI 公制" if system == "SI" else "Imperial 英制"
        self.output_system_hint.value = OUTPUT_SYSTEM_DESCRIPTIONS.get(system, "")

    def navigate(self, route_key: str, *, notify: bool = True) -> None:
        """依穩定路由鍵選取畫面並更新頁面標題。

        若目標畫面實作了 generic 的 ``activate_route(route_key)`` 協定
        （例如 ``ThermoDiagramView``），會在切換為可見後呼叫它，讓畫面
        自行處理 route-local 的啟用邏輯（如圖表模式）。AppShell 本身完全
        不知道任何特定 route 或 view class 的語意，只依協定呼叫。

參數：
    route_key: 要切換至的工作區路由鍵。
    notify: 是否通知路由回呼函式；初始化時可設為 False。

回傳：
    無。

引發：
    KeyError: 路由鍵未註冊，或沒有對應畫面時。"""
        if route_key not in ROUTE_BY_KEY:
            raise KeyError(f"Unknown workspace route: {route_key}")
        route = ROUTE_BY_KEY[route_key]
        if route_key not in self.views:
            raise KeyError(f"No view registered for route: {route_key}")
        if notify and self.on_route_change:
            self.on_route_change(route_key)
        self.state.route_key = route_key
        self.sidebar.set_selected(route_key)
        active_view = self.views[route_key]
        for view in self._unique_views:
            view.visible = view is active_view
        activate_route = getattr(active_view, "activate_route", None)
        if callable(activate_route):
            activate_route(route_key)
        accent, soft = section_colors(route.section)
        self.route_icon.icon = getattr(ft.Icons, route.icon)
        self.route_icon.color = accent
        self.route_icon_badge.bgcolor = soft
        self.route_header.controls = [
            ft.Text(route.label, size=TOKENS.title, weight=ft.FontWeight.W_700,
                    color=TOKENS.text_primary),
            ft.Text(route.description or "工程計算工作區 · 輸入單位可獨立選擇",
                    size=TOKENS.body, color=TOKENS.text_secondary),
        ]
        self.breadcrumb_section.value = route.section
        self.breadcrumb_label.value = route.label
        self._refresh_output_system_summary()
        self._on_resize(None)
        try:
            self.update()
        except RuntimeError:
            pass

    def set_output_unit_system(self, unit_system: str) -> None:
        """更新全域輸出單位偏好，並通知目前的畫面介接器。

參數：
    unit_system: 要使用的輸出單位系統。

回傳：
    無。"""
        self.state.set_output_unit_system(unit_system)
        self.unit_toggle.selected = [unit_system]
        self._refresh_output_system_summary()
        if self.on_unit_system_change:
            self.on_unit_system_change(unit_system)
        try:
            self.update()
        except RuntimeError:
            pass

    def _on_unit_change(self, event: ft.ControlEvent | None) -> None:
        """轉送顯示單位偏好，不改寫個別欄位所選的輸入單位。

參數：
    event: 單位切換事件；未提供時沿用目前的偏好。

回傳：
    無。"""
        selected = next(iter(event.control.selected), "SI") if event else self.state.output_unit_system
        self.set_output_unit_system(selected)

    def _toggle_sidebar(self, _event: ft.ControlEvent | None) -> None:
        """只在窄視窗中開啟或關閉完整導覽抽屜。

參數：
    _event: Flet 點擊事件；此處不需讀取事件內容。

回傳：
    無。"""
        if (getattr(self._page_ref, "width", None) or 1280) >= 800:
            return
        self.sidebar.set_compact(False)
        self.sidebar.visible = not self.sidebar.visible
        try:
            self.sidebar.update()
        except RuntimeError:
            pass

    def _on_keyboard_event(self, event: ft.KeyboardEvent) -> None:
        """以 Ctrl+Enter 執行目前畫面的計算；Esc 先關閉資訊欄，再關閉窄視窗導覽抽屜。

參數：
    event: 包含按鍵與修飾鍵狀態的 Flet 鍵盤事件。

回傳：
    無。"""
        key = (event.key or "").lower()
        if event.ctrl and key in {"enter", "numpad enter"}:
            view = self.views[self.state.route_key]
            calculate = getattr(view, "perform_calculation", None)
            if calculate is None:
                calculate = getattr(view, "calculate_analysis", None)
            if calculate is not None:
                calculate(None)
        elif key == "escape" and self.context_panel_open:
            self.toggle_context_panel(None)
        elif key == "escape" and (getattr(self._page_ref, "width", 1280) or 1280) < 800:
            self.sidebar.visible = False
            try:
                self.sidebar.update()
            except RuntimeError:
                pass

    def toggle_context_panel(self, _event: ft.ControlEvent | None) -> None:
        """在寬版開啟或收起右側情境面板；中版與窄版不顯示面板。

參數：
    _event: Flet 點擊事件；此處不需讀取內容。

回傳：
    無。"""
        self.context_panel_open = not self.context_panel_open
        self.context_toggle.selected = self.context_panel_open
        self._on_resize(None)
        try:
            self.update()
        except RuntimeError:
            pass

    def _on_resize(self, _event: ft.ControlEvent | None) -> None:
        """依視窗寬度切換導覽尺寸；情境面板只在寬版且使用者開啟時顯示。

參數：
    _event: Flet 尺寸變更事件；版面依 page 的最新寬度計算。

回傳：
    無。"""
        width = getattr(self._page_ref, "width", None) or 1280
        if width < 800:
            self.sidebar.set_compact(False)
            self.sidebar.visible = False
            self.sidebar.width = TOKENS.sidebar_width
            self.sidebar.shadow = card_shadow()
            self.workspace_region.padding = ft.Padding.only(left=0)
            self.context_panel.visible = False
            self.workspace.padding = TOKENS.spacing_md
            self.menu_button.visible = True
            self.brand_block.width = None
            self.brand_text.visible = False
            self.shortcut_hint.visible = False
            self.breadcrumb_prefix.visible = False
            self.output_label.visible = False
            self.context_toggle.visible = False
        elif width < 1200:
            self.sidebar.set_compact(True)
            self.sidebar.visible = True
            self.sidebar.width = TOKENS.sidebar_compact_width
            self.sidebar.shadow = None
            self.workspace_region.padding = ft.Padding.only(left=TOKENS.sidebar_compact_width)
            self.context_panel.visible = False
            self.workspace.padding = TOKENS.spacing_md
            self.menu_button.visible = False
            self.brand_block.width = TOKENS.sidebar_compact_width
            self.brand_text.visible = False
            self.shortcut_hint.visible = False
            self.breadcrumb_prefix.visible = True
            self.output_label.visible = True
            self.context_toggle.visible = False
        else:
            self.sidebar.set_compact(False)
            self.sidebar.visible = True
            self.sidebar.width = TOKENS.sidebar_width
            self.sidebar.shadow = None
            self.workspace_region.padding = ft.Padding.only(left=TOKENS.sidebar_width)
            self.context_panel.visible = self.context_panel_open
            self.workspace.padding = TOKENS.spacing_lg
            self.menu_button.visible = False
            self.brand_block.width = TOKENS.sidebar_width
            self.brand_text.visible = True
            self.shortcut_hint.visible = True
            self.breadcrumb_prefix.visible = True
            self.output_label.visible = True
            self.context_toggle.visible = True
