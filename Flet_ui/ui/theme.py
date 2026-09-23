"""集中管理工程工作區的視覺設計 設計 設計參數。"""

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
    radius_sm: int = 6
    radius_md: int = 10
    radius_lg: int = 14
    control_height: int = 42
    input_height: int = 44
    button_height: int = 44
    content_max_width: int = 1480
    sidebar_width: int = 244
    context_panel_width: int = 272
    primary: str = "#1D4E89"
    background: str = "#EEF3F8"
    surface: str = "#FFFFFF"
    surface_variant: str = "#F5F8FC"
    border: str = "#D8E1EB"
    success: str = "#16835D"
    warning: str = "#B7791F"
    error: str = "#C2413B"
    info: str = "#2563A6"
    title: int = 25
    section_title: int = 18
    body: int = 15
    caption: int = 12
    metric: int = 30


TOKENS = DesignTokens()


def workspace_theme() -> ft.Theme:
    """建立應用程式外殼共用的淺色工程主題。

回傳：
    套用中央設計 設計 設計參數 的 Flet Theme。"""
    return ft.Theme(color_scheme_seed=TOKENS.primary)
