"""現場過熱度／過冷度判讀的 dedicated workspace view。"""

from __future__ import annotations

from ...ui_components.analysis_modules.superheat_subcooling_module import SuperheatSubcoolingModule
from ..state import WorkspaceState
from .dedicated_analysis_view import DedicatedAnalysisView


class SuperheatSubcoolingView(DedicatedAnalysisView):
    """呈現 SuperheatSubcoolingModule 註冊的過熱度／過冷度判讀。"""

    def __init__(
        self, module: SuperheatSubcoolingModule, *, workspace_state: WorkspaceState | None = None
    ) -> None:
        """建立過熱度／過冷度判讀畫面。

        參數：
            module: 已建構完成的 SuperheatSubcoolingModule 實例。
            workspace_state: 選用的共用工作區狀態。

        回傳：
            無。
        """
        super().__init__(
            title="過熱／過冷",
            subtitle="以現場量測壓力（錶壓或絕對）與管溫判讀過熱度或過冷度",
            modules=[module],
            workspace_state=workspace_state,
        )
