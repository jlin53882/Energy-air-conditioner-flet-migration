"""蒸氣壓縮冷凍循環的 dedicated workspace view。"""

from __future__ import annotations

from ...ui_components.analysis_modules.refrigeration_cycle_module import RefrigerationCycleModule
from ..state import WorkspaceState
from .dedicated_analysis_view import DedicatedAnalysisView


class RefrigerationCycleView(DedicatedAnalysisView):
    """呈現 RefrigerationCycleModule 註冊的循環分析，循環結果附 P-h 圖。"""

    def __init__(
        self, module: RefrigerationCycleModule, *, workspace_state: WorkspaceState | None = None
    ) -> None:
        """建立冷凍循環畫面。

        參數：
            module: 已建構完成的 RefrigerationCycleModule 實例。
            workspace_state: 選用的共用工作區狀態。

        回傳：
            無。
        """
        super().__init__(
            title="冷凍循環",
            subtitle="蒸氣壓縮循環 COP、流量與 P-h 圖",
            modules=[module],
            workspace_state=workspace_state,
        )
