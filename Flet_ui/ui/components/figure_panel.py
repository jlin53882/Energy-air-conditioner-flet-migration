"""包裝 Matplotlib 圖表的共用面板，讓分析模組重複使用同一個 figure。"""

import flet as ft
import flet_charts as fch
import matplotlib.pyplot as plt
from matplotlib import font_manager

from ..theme import TOKENS

# 常見作業系統內建或常裝的中文字型；Matplotlib 預設字型（DejaVu Sans）沒有中文字，
# 圖表標題與座標軸的中文會變成方框。
CJK_FONT_CANDIDATES = (
    "Microsoft JhengHei", "Microsoft YaHei", "PingFang TC", "Heiti TC",
    "Noto Sans CJK TC", "Noto Sans TC", "Source Han Sans TC", "WenQuanYi Zen Hei", "WenQuanYi Zen Hei Mono",
)


def use_cjk_fallback_fonts(installed: set[str] | None = None) -> list[str]:
    """把已安裝的中文字型接在 Matplotlib ``font.family`` 之後，作為逐字的備援字型。

Matplotlib 只在 ``font.family`` 的各個項目之間逐字備援（``sans-serif`` 這類通用字族只會解析成
一個字型），因此中文字型必須加在 ``font.family``：拉丁字母與符號仍用原字族，中文字找不到
字形時依序改用清單中的中文字型。可重複呼叫。

參數：
    installed: 已安裝字型名稱；None 時由 Matplotlib 字型管理器查詢（供測試注入）。

回傳：
    設定後的 ``font.family``。"""
    if installed is None:
        installed = {font.name for font in font_manager.fontManager.ttflist}
    families = [name for name in plt.rcParams["font.family"] if name not in CJK_FONT_CANDIDATES]
    families += [name for name in CJK_FONT_CANDIDATES if name in installed]
    plt.rcParams["font.family"] = families
    return families


use_cjk_fallback_fonts()


class FigurePanel(ft.Container):
    """持有一個長期存在的 Matplotlib figure 與 Flet Charts 控制項。

Flet Charts 的即時連線綁定在 figure 上，因此繪圖程式應清除並重畫 `figure`，
而不是建立新 figure；重畫後呼叫 `refresh()` 通知已掛載的圖表更新。
"""

    def __init__(self, *, height: int = 460, figsize: tuple[float, float] = (8.0, 5.2),
                 placeholder: str = "執行計算後顯示圖表") -> None:
        """建立圖表面板並畫上預設提示文字。

參數：
    height: 面板高度（px）。
    figsize: Matplotlib figure 尺寸（英吋）。
    placeholder: 尚未繪圖時的提示文字。

回傳：
    無。"""
        self.figure = plt.figure(figsize=figsize)
        self.chart = fch.MatplotlibChart(figure=self.figure, expand=True)
        super().__init__(
            content=self.chart,
            height=height,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
        self.show_placeholder(placeholder)

    def show_placeholder(self, message: str) -> None:
        """清除圖表並顯示置中的提示文字。

參數：
    message: 提示文字。

回傳：
    無。"""
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.axis("off")
        axes.text(0.5, 0.5, message, ha="center", va="center", color="gray")
        self.refresh()

    def refresh(self) -> None:
        """通知已掛載的 Flet Charts 重新繪製目前 figure；未掛載時不做任何事。

回傳：
    無。"""
        self.chart.figure = self.figure
        try:
            attached_page = self.chart.page
        except RuntimeError:
            attached_page = None
        if attached_page:
            self.chart.send_message({"type": "refresh"})
