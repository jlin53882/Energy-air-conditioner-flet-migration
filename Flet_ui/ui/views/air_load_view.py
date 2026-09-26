"""空調負荷（新風負荷、加濕負荷、風量與冷量換算）的 dedicated workspace view。"""

from __future__ import annotations

from ...ui_components.analysis_modules.air_load_module import AirLoadModule
from ..state import WorkspaceState
from .dedicated_analysis_view import DedicatedAnalysisView


class AirLoadView(DedicatedAnalysisView):
    """呈現 AirLoadModule 註冊的空調負荷分析；新風與加濕過程附濕空氣線圖。"""

    def __init__(self, module: AirLoadModule, *, workspace_state: WorkspaceState | None = None) -> None:
        """建立空調負荷畫面。

        參數：
            module: 已建構完成的 AirLoadModule 實例。
            workspace_state: 選用的共用工作區狀態。

        回傳：
            無。
        """
        super().__init__(
            title="空調負荷",
            subtitle="新風負荷、加濕負荷，以及風量與冷量換算",
            modules=[module],
            workspace_state=workspace_state,
        )
