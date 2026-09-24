"""P-h / T-s 熱力圖的 dedicated workspace view。

採用 PR #4 規格中的方案 A：同一個 ``ThermoDiagramView`` instance 由
route 進來時切換 view-local mode，底層共用同一個
``ThermoDiagramModule``／diagram adapter。``flet_app.py`` 不再需要知道
``diagram_type`` 或呼叫 ``module.set_diagram_type`` —— 由這個 View 自己管理。
"""

from __future__ import annotations

import flet as ft

from ...ui_components.analysis_modules.thermo_diagram_module import ThermoDiagramModule

_MODE_TO_DIAGRAM = {"ph": "P-h", "ts": "T-s"}


class ThermoDiagramView(ft.Column):
    """包裝既有 ThermoDiagramModule，管理 P-h / T-s 的 view-local mode。"""

    def __init__(self, module: ThermoDiagramModule) -> None:
        """建立熱力圖畫面外殼。

        參數：
            module: 已建構完成的 ThermoDiagramModule 實例；其 UI 容器已內建
                完整版面（設定卡 + 圖表卡 + 專屬繪圖按鈕），因此本 View
                只需要直接呈現該容器，不套用共用 AnalysisWorkspace 版面。

        回傳：
            無。
        """
        super().__init__(expand=True, spacing=0)
        self.module = module
        self.mode = "ph"
        self.controls = [module.thermo_diagram_ui_container]

    def set_mode(self, mode: str) -> None:
        """切換圖表種類並清除舊圖，對應 route ``ph_chart`` / ``ts_chart``。

        參數：
            mode: ``"ph"`` 或 ``"ts"``。

        回傳：
            無。

        引發：
            ValueError: mode 不是受支援的圖表模式。
        """
        if mode not in _MODE_TO_DIAGRAM:
            raise ValueError(f"不支援的熱力圖模式：{mode}")
        self.mode = mode
        self.module.set_diagram_type(_MODE_TO_DIAGRAM[mode])

    def perform_calculation(self, event: ft.ControlEvent | None) -> None:
        """讓 AppShell 的 Ctrl+Enter 捷徑也能觸發熱力圖的專屬繪圖流程。

        參數：
            event: Flet 事件；此處不需讀取事件內容。

        回傳：
            無。
        """
        self.module._on_plot_click(event)
