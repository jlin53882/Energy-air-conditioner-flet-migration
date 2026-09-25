"""蒸發器分析的 dedicated workspace view。"""

from __future__ import annotations

from ...ui_components.analysis_modules.hvac_evaporator_module import EvaporatorModule
from ..state import WorkspaceState
from ..theme import section_colors
from .dedicated_analysis_view import DedicatedAnalysisView


class EvaporatorView(DedicatedAnalysisView):
    """呈現既有 EvaporatorModule 已註冊的所有蒸發器分析。"""

    def __init__(self, module: EvaporatorModule, *, workspace_state: WorkspaceState | None = None) -> None:
        """建立蒸發器分析畫面。

        參數：
            module: 已建構完成的 EvaporatorModule 實例。
            workspace_state: 選用的共用工作區狀態。

        回傳：
            無。
        """
        super().__init__(
            title="蒸發器分析",
            subtitle="分析蒸發器熱交換相關計算",
            modules=[module],
            workspace_state=workspace_state,
            accent=section_colors("冷凍系統")[0],
        )
