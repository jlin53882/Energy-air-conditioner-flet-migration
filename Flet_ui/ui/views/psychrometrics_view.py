"""濕空氣性質分析的 dedicated workspace view。

PsyModule 使用共用的 ``ui_container``（乾濕球／乾球+RH 兩種模式共用同一組
輸入欄位，只切換部分欄位可見性），因此這個 View 需要在工具切換時額外呼叫
``configure_ui_for_mode``。這個特例被限制在 PsychrometricsView 內，不出現
在共用的 ``DedicatedAnalysisView`` / ``AnalysisModuleAdapter``。
"""

from __future__ import annotations

from ...ui_components.analysis_modules.psy_module import PsyModule
from ..state import WorkspaceState
from .dedicated_analysis_view import DedicatedAnalysisView


class PsychrometricsView(DedicatedAnalysisView):
    """呈現既有 PsyModule 的濕空氣分析模式，並包裝其 legacy UI 特例。"""

    def __init__(self, module: PsyModule, *, workspace_state: WorkspaceState | None = None) -> None:
        """建立濕空氣性質分析畫面。

        參數：
            module: 已建構完成的 PsyModule 實例。
            workspace_state: 選用的共用工作區狀態。

        回傳：
            無。
        """
        self.psy_module = module
        super().__init__(
            title="濕空氣性質分析",
            subtitle="依乾濕球或乾球與相對濕度計算濕空氣性質",
            modules=[module],
            workspace_state=workspace_state,
        )
        # 初始化時同步一次目前選取模式，維持既有 UI 顯示狀態。
        self._on_tool_selected(self.adapter.active_key)

    def _on_tool_selected(self, key: str) -> None:
        """依選取的模式（乾濕球 / 乾球+RH）切換 PsyModule 的欄位可見性。

        參數：
            key: 使用者選取的分析定義 key（analysis_id）。

        回傳：
            無。
        """
        definition = self.adapter.active_definition
        self.psy_module.configure_ui_for_mode(definition.key)
