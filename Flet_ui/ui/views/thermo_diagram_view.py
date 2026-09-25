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
_ROUTE_TO_MODE = {"ph_chart": "ph", "ts_chart": "ts"}


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

        模組目前已是同一種圖表時（例如 P-h → 首頁 → P-h）不做任何事，保留
        已繪製的圖與結果文字；只有圖表種類真的改變時才清除。

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
        diagram = _MODE_TO_DIAGRAM[mode]
        if self.module.diagram_dd.value == diagram:
            return
        self.module.set_diagram_type(diagram)

    def activate_route(self, route_key: str) -> None:
        """generic route-activation 協定：由 ``AppShell.navigate`` 呼叫。

        route -> diagram mode 的對照表只存在於這個 View 內部；
        ``flet_app.py`` 不需要知道 ``ph_chart`` / ``ts_chart`` 對應
        ``P-h`` / ``T-s`` 的 mapping。未知的 route_key 會被忽略（維持
        目前 mode 不變），避免此協定被其他 route 誤觸發時炸掉。

        參數：
            route_key: AppShell 目前導覽到的路由鍵。

        回傳：
            無。
        """
        mode = _ROUTE_TO_MODE.get(route_key)
        if mode is not None:
            self.set_mode(mode)

    def perform_calculation(self, event: ft.ControlEvent | None) -> None:
        """讓 AppShell 的 Ctrl+Enter 捷徑也能觸發熱力圖的專屬繪圖流程。

        參數：
            event: Flet 事件；此處不需讀取事件內容。

        回傳：
            無。
        """
        self.module.perform_plot(event)
