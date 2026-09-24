"""集中管理工程工作區的視覺設計權杖、主題與共用控制項樣式。"""

from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class DesignTokens:
    """集中定義工作區的間距、尺寸、色彩與字體層級。"""

    spacing_xs: int = 4
    spacing_sm: int = 8
    spacing_md: int = 16
    spacing_lg: int = 24
    spacing_xl: int = 32
    radius_sm: int = 8
    radius_md: int = 12
    radius_lg: int = 16
    radius_pill: int = 999
    control_height: int = 44
    input_height: int = 48
    button_height: int = 44
    content_max_width: int = 1480
    sidebar_width: int = 256
    sidebar_compact_width: int = 76
    context_panel_width: int = 288
    top_bar_height: int = 64

    # 品牌與語意色彩
    primary: str = "#1B5FAA"
    primary_hover: str = "#154C8A"
    primary_soft: str = "#E6F0FB"
    accent: str = "#0F9D9A"
    accent_soft: str = "#E3F6F5"
    background: str = "#F2F5F9"
    surface: str = "#FFFFFF"
    surface_variant: str = "#F6F8FB"
    surface_muted: str = "#EDF1F6"
    border: str = "#DCE3EC"
    border_strong: str = "#C3CEDB"
    text_primary: str = "#0F1E2E"
    text_secondary: str = "#4A5B6E"
    text_muted: str = "#7A8898"
    success: str = "#15803D"
    success_soft: str = "#E7F6EC"
    warning: str = "#B45309"
    warning_soft: str = "#FDF3E4"
    error: str = "#C0362C"
    error_soft: str = "#FCEBEA"
    info: str = "#1D63B8"
    info_soft: str = "#E8F1FC"

    # 深色導覽區
    nav_background: str = "#0E2239"
    nav_surface: str = "#15304F"
    nav_selected: str = "#1F4B7A"
    nav_text: str = "#C9D6E5"
    nav_text_muted: str = "#7F97B2"
    nav_accent: str = "#5CC8F0"

    # 字體層級
    display: int = 30
    title: int = 24
    section_title: int = 17
    body: int = 14
    caption: int = 12
    overline: int = 11
    metric: int = 22
    metric_large: int = 30


TOKENS = DesignTokens()

# 依工作區分類使用的強調色，讓導覽、頁首與首頁卡片使用同一套語意。
SECTION_COLORS: dict[str, tuple[str, str]] = {
    "工作區": ("#1B5FAA", "#E6F0FB"),
    "熱力學": ("#6D4BC4", "#F0EBFB"),
    "冷凍系統": ("#0F7EA8", "#E3F3FA"),
    "空氣處理": ("#0F9D9A", "#E3F6F5"),
    "圖表": ("#C2620F", "#FCF0E3"),
}


def section_colors(section: str) -> tuple[str, str]:
    """回傳工作區分類對應的強調色與淡色背景。

參數：
    section: 導覽路由所屬的分類名稱。

回傳：
    由強調色與淡色背景組成的二元組；未知分類使用主要品牌色。"""
    return SECTION_COLORS.get(section, (TOKENS.primary, TOKENS.primary_soft))


def card_shadow() -> ft.BoxShadow:
    """建立卡片共用的柔和陰影，避免各畫面各自定義層次。

回傳：
    Flet BoxShadow 物件。"""
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=18,
        color="#140F2A47",
        offset=ft.Offset(0, 4),
    )


def style_text_field(control: ft.TextField, *, dense: bool = False) -> ft.TextField:
    """套用工作區一致的輸入框外觀，不改變控制項的值與事件。

參數：
    control: 要套用樣式的 Flet TextField。
    dense: 是否使用較緊湊的內距。

回傳：
    套用樣式後的同一個 TextField。"""
    control.border_radius = ft.BorderRadius.all(TOKENS.radius_sm)
    control.border_color = TOKENS.border_strong
    control.focused_border_color = TOKENS.primary
    control.focused_border_width = 2
    control.filled = True
    control.fill_color = TOKENS.surface
    control.text_size = TOKENS.body
    control.cursor_color = TOKENS.primary
    control.content_padding = ft.Padding.symmetric(
        horizontal=12, vertical=8 if dense else 12
    )
    return control


def style_dropdown(control: ft.Dropdown) -> ft.Dropdown:
    """套用工作區一致的下拉選單外觀，不改變選項、值與事件。

參數：
    control: 要套用樣式的 Flet Dropdown。

回傳：
    套用樣式後的同一個 Dropdown。"""
    control.border_radius = ft.BorderRadius.all(TOKENS.radius_sm)
    control.border_color = TOKENS.border_strong
    control.focused_border_color = TOKENS.primary
    control.focused_border_width = 2
    control.filled = True
    control.fill_color = TOKENS.surface
    control.text_size = TOKENS.body
    return control


def primary_button_style() -> ft.ButtonStyle:
    """建立主要行動按鈕樣式。

回傳：
    Flet ButtonStyle 物件。"""
    return ft.ButtonStyle(
        color=ft.Colors.WHITE,
        bgcolor=TOKENS.primary,
        overlay_color=TOKENS.primary_hover,
        shape=ft.RoundedRectangleBorder(radius=TOKENS.radius_sm),
        padding=ft.Padding.symmetric(horizontal=20, vertical=14),
        elevation=0,
    )


def secondary_button_style() -> ft.ButtonStyle:
    """建立次要（外框）按鈕樣式。

回傳：
    Flet ButtonStyle 物件。"""
    return ft.ButtonStyle(
        color=TOKENS.text_secondary,
        shape=ft.RoundedRectangleBorder(radius=TOKENS.radius_sm),
        side=ft.BorderSide(1, TOKENS.border_strong),
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
    )


def chip_button_style(selected: bool, accent: str = TOKENS.primary) -> ft.ButtonStyle:
    """建立分析模式或預設組合使用的膠囊按鈕樣式。

參數：
    selected: 是否為目前選取的項目。
    accent: 選取時使用的強調色。

回傳：
    Flet ButtonStyle 物件；選取狀態同時改變背景、文字與外框。"""
    return ft.ButtonStyle(
        color=ft.Colors.WHITE if selected else TOKENS.text_secondary,
        bgcolor=accent if selected else TOKENS.surface,
        side=ft.BorderSide(1, accent if selected else TOKENS.border_strong),
        shape=ft.RoundedRectangleBorder(radius=TOKENS.radius_pill),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
    )


def workspace_theme() -> ft.Theme:
    """建立應用程式外殼共用的淺色工程主題。

回傳：
    套用中央設計權杖的 Flet Theme。"""
    return ft.Theme(
        color_scheme_seed=TOKENS.primary,
        color_scheme=ft.ColorScheme(
            primary=TOKENS.primary,
            on_primary=ft.Colors.WHITE,
            primary_container=TOKENS.primary_soft,
            secondary=TOKENS.accent,
            secondary_container=TOKENS.accent_soft,
            surface=TOKENS.surface,
            on_surface=TOKENS.text_primary,
            on_surface_variant=TOKENS.text_secondary,
            outline=TOKENS.border_strong,
            outline_variant=TOKENS.border,
            error=TOKENS.error,
        ),
        scaffold_bgcolor=TOKENS.background,
        divider_color=TOKENS.border,
        visual_density=ft.VisualDensity.COMFORTABLE,
    )
