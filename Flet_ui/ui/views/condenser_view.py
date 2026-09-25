"""冷凝器分析的 dedicated workspace view。"""

from __future__ import annotations

from ...ui_components.analysis_modules.hvac_condenser_module import CondenserModule
from ..state import WorkspaceState
from .dedicated_analysis_view import DedicatedAnalysisView


class CondenserView(DedicatedAnalysisView):
    """呈現既有 CondenserModule 已註冊的所有冷凝器分析。"""

    def __init__(self, module: CondenserModule, *, workspace_state: WorkspaceState | None = None) -> None:
        """建立冷凝器分析畫面。

        參數：
            module: 已建構完成的 CondenserModule 實例。
            workspace_state: 選用的共用工作區狀態。

        回傳：
            無。
        """
        super().__init__(
            title="冷凝器分析",
            subtitle="分析冷凝器熱交換相關計算",
            modules=[module],
            workspace_state=workspace_state,
        )
