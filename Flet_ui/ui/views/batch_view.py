"""批次計算與比較（參數掃描、冷媒比較、敏感度分析）的 dedicated workspace view。"""

from __future__ import annotations

from ...ui_components.analysis_modules.batch_module import BatchModule
from ..state import WorkspaceState
from .dedicated_analysis_view import DedicatedAnalysisView


class BatchView(DedicatedAnalysisView):
    """呈現 BatchModule 註冊的批次分析；結果附曲線圖、長條圖或龍捲風圖。"""

    def __init__(self, module: BatchModule, *, workspace_state: WorkspaceState | None = None) -> None:
        """建立批次與比較畫面。

        參數：
            module: 已建構完成的 BatchModule 實例。
            workspace_state: 選用的共用工作區狀態。

        回傳：
            無。
        """
        super().__init__(
            title="批次與比較",
            subtitle="冷凍循環與冷凝器 Exergy 的參數掃描、冷媒比較與敏感度分析",
            modules=[module],
            workspace_state=workspace_state,
        )
