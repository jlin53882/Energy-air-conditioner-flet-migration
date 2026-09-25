"""包裝 Matplotlib 圖表的共用面板，讓分析模組重複使用同一個 figure。"""

import flet as ft
import flet_charts as fch
import matplotlib.pyplot as plt

from ..theme import TOKENS


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
