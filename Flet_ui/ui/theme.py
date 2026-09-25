"""集中管理工程工作區的視覺設計權杖、主題與共用控制項樣式。

配色採暖灰白底、白色卡片細框線，搭配單一深青綠強調色；數值一律使用等寬字型，
方便上下比較位數。
"""

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
    top_bar_height: int = 64

    # 品牌與語意色彩：暖灰白底＋單一深青綠強調色
    primary: str = "#115E63"
    primary_hover: str = "#0B4B4F"
    primary_soft: str = "#E1EEEC"
    accent: str = "#115E63"
    accent_soft: str = "#E1EEEC"
    background: str = "#EFEFEA"
    surface: str = "#FFFFFF"
    surface_variant: str = "#F4F4F0"
    surface_muted: str = "#ECECE6"
    border: str = "#E2E2DB"
    border_strong: str = "#CDCDC4"
    text_primary: str = "#1E2421"
    text_secondary: str = "#4D5550"
    text_muted: str = "#878E89"
    success: str = "#2E7D4F"
    success_soft: str = "#E6F2EA"
    warning: str = "#A15C07"
    warning_soft: str = "#FBF1E1"
    error: str = "#B4371F"
    error_soft: str = "#FBEAE5"
    info: str = "#115E63"
    info_soft: str = "#E1EEEC"
    # 圖表中「目前狀態點」與輔助線使用的橘紅色
    highlight: str = "#C2410C"

    # 淺色導覽區
    nav_background: str = "#F7F7F3"
    nav_selected: str = "#E1EEEC"
    nav_text: str = "#3E4541"
    nav_text_muted: str = "#878E89"
    nav_accent: str = "#115E63"

    # 等寬數字字型（於 flet_app 以 page.fonts 註冊；無法載入時由系統字型替代）
    mono_font: str = "IBM Plex Mono"

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

# 等寬字型來源（IBM Plex Mono，SIL Open Font License）。
MONO_FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexmono/IBMPlexMono-Regular.ttf"


def mono_style(**kwargs) -> ft.TextStyle:
    """建立數值使用的等寬字型樣式。

參數：
    kwargs: 其他 TextStyle 參數（例如 size、weight、color）。

回傳：
    Flet TextStyle 物件。"""
    return ft.TextStyle(font_family=TOKENS.mono_font, **kwargs)


def card_shadow() -> ft.BoxShadow:
    """建立卡片共用的柔和陰影，避免各畫面各自定義層次。

回傳：
    Flet BoxShadow 物件。"""
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=4,
        color="#0A1E2421",
        offset=ft.Offset(0, 1),
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
    control.text_style = mono_style()
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
