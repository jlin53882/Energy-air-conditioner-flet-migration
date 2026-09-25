"""獨立濕空氣線圖（多狀態點標示）的 dedicated workspace view。"""

from __future__ import annotations

from ...ui_components.analysis_modules.psychrometric_chart_module import PsychrometricChartModule
from ..state import WorkspaceState
from .dedicated_analysis_view import DedicatedAnalysisView


class PsychrometricChartView(DedicatedAnalysisView):
    """呈現 PsychrometricChartModule；圖表為主要產出，放在逐點性質之前。"""

    def __init__(
        self, module: PsychrometricChartModule, *, workspace_state: WorkspaceState | None = None
    ) -> None:
        """建立濕空氣線圖畫面。

        參數：
            module: 已建構完成的 PsychrometricChartModule 實例。
            workspace_state: 選用的共用工作區狀態。

        回傳：
            無。
        """
        super().__init__(
            title="濕空氣線圖",
            subtitle="依海拔繪製濕空氣線圖並標示多個狀態點",
            modules=[module],
            workspace_state=workspace_state,
        )
