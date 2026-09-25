"""空氣處理程序（混合、顯熱、冷卻除濕、送風量）的 dedicated workspace view。"""

from __future__ import annotations

from ...ui_components.analysis_modules.psy_process_module import PsyProcessModule
from ..state import WorkspaceState
from .dedicated_analysis_view import DedicatedAnalysisView


class AirProcessView(DedicatedAnalysisView):
    """呈現 PsyProcessModule 註冊的空氣處理分析，結果附濕空氣線圖。"""

    def __init__(self, module: PsyProcessModule, *, workspace_state: WorkspaceState | None = None) -> None:
        """建立空氣處理程序畫面。

        參數：
            module: 已建構完成的 PsyProcessModule 實例。
            workspace_state: 選用的共用工作區狀態。

        回傳：
            無。
        """
        super().__init__(
            title="空氣處理程序",
            subtitle="氣流混合、顯熱加熱／冷卻、冷卻除濕與送風量估算",
            modules=[module],
            workspace_state=workspace_state,
        )
