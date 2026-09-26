"""冷媒飽和性質的 dedicated workspace view。"""

from __future__ import annotations

from ...ui_components.analysis_modules.saturation_module import SaturationModule
from ..state import WorkspaceState
from .dedicated_analysis_view import DedicatedAnalysisView


class SaturationView(DedicatedAnalysisView):
    """呈現 SaturationModule 註冊的飽和性質分析。"""

    def __init__(self, module: SaturationModule, *, workspace_state: WorkspaceState | None = None) -> None:
        """建立飽和性質畫面。

        參數：
            module: 已建構完成的 SaturationModule 實例。
            workspace_state: 選用的共用工作區狀態。

        回傳：
            無。
        """
        super().__init__(
            title="飽和性質",
            subtitle="已知壓力或溫度，查詢冷媒泡點、露點與溫度滑移；已知壓力時另提供蒸發潛熱",
            modules=[module],
            workspace_state=workspace_state,
        )
