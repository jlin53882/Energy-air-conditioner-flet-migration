"""壓縮機分析的 dedicated workspace view。"""

from __future__ import annotations

from ...ui_components.analysis_modules.hvac_compressor_module import CompressorModule
from ..state import WorkspaceState
from .dedicated_analysis_view import DedicatedAnalysisView


class CompressorView(DedicatedAnalysisView):
    """呈現既有 CompressorModule 已註冊的所有壓縮機分析。"""

    def __init__(self, module: CompressorModule, *, workspace_state: WorkspaceState | None = None) -> None:
        """建立壓縮機分析畫面。

        參數：
            module: 已建構完成的 CompressorModule 實例。
            workspace_state: 選用的共用工作區狀態。

        回傳：
            無。
        """
        super().__init__(
            title="壓縮機分析",
            subtitle="分析壓縮機壓力、功率與效率相關計算",
            modules=[module],
            workspace_state=workspace_state,
        )
