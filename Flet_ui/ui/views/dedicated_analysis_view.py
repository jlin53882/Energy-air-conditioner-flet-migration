"""所有 dedicated analysis view 共用的骨架：tool selection + calculate + unit propagation。

這個基底類別只依賴 :class:`AnalysisModuleAdapter` 與 :class:`AnalysisWorkspace`
提供的泛用契約，完全不知道 compressor / evaporator / condenser /
psychrometric 等任何特定分類邏輯。新增分類時只需要提供新的 module 與
子類別，不需要修改這個檔案。
"""

from __future__ import annotations

import flet as ft

from ..analysis_module_adapter import AnalysisModuleAdapter
from ..analysis_presentation import presentation_for
from ..components.analysis_workspace import AnalysisWorkspace
from ..components.state_save_menu import StateSaveMenu
from ..components.tool_selector import ToolSelector
from ..state import WorkspaceState
from ..structured_result import structured_from_text


class DedicatedAnalysisView(ft.Column):
    """擁有自己 active tool 與 result 狀態的獨立分析畫面骨架。

    子類別 (CompressorView / EvaporatorView / CondenserView /
    PsychrometricsView) 只需要在建構時提供 title、subtitle 與已建構完成的
    既有分析模組；如需額外的 tool-switch 行為（例如 PsyModule 的顯示模式
    切換），可覆寫 :meth:`_on_tool_selected`。
    """

    def __init__(
        self,
        *,
        title: str,
        subtitle: str,
        modules: list[object],
        workspace_state: WorkspaceState | None = None,
        tool_label: str = "分析項目",
    ) -> None:
        """組合 tool selector、輸入堆疊與結果面板。

        參數：
            title: 頁面標題。
            subtitle: 頁面副標題。
            modules: 此分類使用的既有分析模組實例清單。
            workspace_state: 選用的共用工作區狀態；用於讀取全域輸出單位。
            tool_label: 分析項目選單的欄位名稱。

        回傳：
            無。
        """
        super().__init__(expand=True, spacing=0)
        self.adapter = AnalysisModuleAdapter(modules)
        self.adapter.on_result_invalidated = self._on_result_invalidated
        # workspace_state 只在建構當下讀取一次目前的全域輸出單位；此 View
        # 不持有對它的長期參照（沒有 ongoing ownership），避免造成「看似
        # 訂閱了 WorkspaceState 但實際上沒有」的誤導。
        if workspace_state is not None:
            self.adapter.output_unit_system = workspace_state.output_unit_system

        tool_items = self.adapter.tool_items()
        # 選單顯示 analysis_presentation 的短標籤，完整名稱顯示在輸入卡中；
        # dispatch 仍只使用 key。
        self.tool_selector = ToolSelector(
            items=[(key, self._short_label(key, label)) for key, label in tool_items],
            selected=self.adapter.active_key,
            on_change=self._handle_tool_change,
            disabled=len(tool_items) <= 1,
            label=tool_label,
        )

        seen_ui_ids: set[int] = set()
        unique_inputs: list[ft.Control] = []
        for definition in self.adapter.definitions:
            if id(definition.input_view) in seen_ui_ids:
                continue
            seen_ui_ids.add(id(definition.input_view))
            unique_inputs.append(definition.input_view)
        self.input_stack = ft.Stack(controls=unique_inputs)

        self.workspace = AnalysisWorkspace(
            title=title,
            subtitle=subtitle,
            tool_selector=self.tool_selector,
            input_content=self.input_stack,
            result_panel=self.adapter.result_panel,
            on_calculate=self._handle_calculate,
            show_execute_button=self.adapter.active_definition.show_execute_button,
            show_tool_selector=len(tool_items) > 1,
        )
        # 「儲存狀態點」選單放在結果區動作列；連接 State Library 前保持隱藏。
        self.save_menu = StateSaveMenu()
        self.workspace.result_view.actions_row.controls.insert(1, self.save_menu)
        self.controls = [self.workspace]
        self._sync_presentation()

    def attach_state_library(self, service) -> None:
        """連接 State Library：提供 ``state_points`` 的分析在成功計算後可保存狀態點。

參數：
    service: :class:`~application.state_library.StateLibraryService`。

回傳：
    無。"""
        self.save_menu.attach(service)
        self._show_result()

    @staticmethod
    def _short_label(key: str, label: str) -> str:
        """回傳工具按鈕使用的短標籤；未定義時沿用完整名稱。

        參數：
            key: 分析定義 key。
            label: 分析完整名稱。

        回傳：
            str：按鈕顯示文字。
        """
        presentation = presentation_for(key)
        return presentation.short_label if presentation and presentation.short_label else label

    def _sync_presentation(self) -> None:
        """依目前選取的分析更新輸入卡片說明與結果區。

        回傳：
            無。
        """
        definition = self.adapter.active_definition
        presentation = presentation_for(definition.key)
        self.workspace.show_analysis(
            definition.label,
            presentation.summary if presentation else "",
            presentation.formula if presentation and presentation.formula else "",
        )
        self._show_result()

    def _show_result(self) -> None:
        """以 adapter 目前的結果與選取分析的結果圖表重繪結果區。

        回傳：
            無。
        """
        definition = self.adapter.active_definition
        structured = None
        if self.adapter.result_panel.status == "success":
            if definition.structured_result:
                structured = definition.structured_result()
            else:
                # 尚未直接提供結構化結果的模組：由格式化文字重新排版，關鍵數值
                # 依分析說明表宣告的結果名稱挑選。
                presentation = presentation_for(definition.key)
                structured = structured_from_text(
                    self.adapter.result_text,
                    key_labels=presentation.key_metrics if presentation else (),
                    chart_title=presentation.chart_title if presentation else "圖表",
                )
        self.workspace.show_result(
            self.adapter.result_text, chart=definition.result_chart, structured=structured
        )
        # 只在成功狀態列出狀態點；失效、錯誤或切換分析時隱藏，避免保存舊結果。
        if self.adapter.result_panel.status == "success" and definition.state_points:
            self.save_menu.show_points(definition.state_points())
        else:
            self.save_menu.hide()

    @property
    def active_key(self) -> str:
        """回傳此畫面目前選取的分析定義 key。

        回傳：
            str：目前選取的 analysis_id。
        """
        return self.adapter.active_key

    @property
    def active_definition(self):
        """回傳此畫面目前選取的分析定義。

        回傳：
            AnalysisDefinition：目前選取的定義。
        """
        return self.adapter.active_definition

    @property
    def result_panel(self):
        """回傳此畫面使用的 ResultPanel 實例，供測試與外部整合讀取狀態。

        回傳：
            ResultPanel：呈現計算狀態的共用元件。
        """
        return self.adapter.result_panel

    def _handle_tool_change(self, key: str) -> None:
        """回應 ToolSelector 選取事件：切換 adapter 狀態並重繪。

        參數：
            key: 使用者選取的分析定義 key。

        回傳：
            無。
        """
        self.adapter.select(key)
        self.workspace.set_action_bar_visible(self.adapter.active_definition.show_execute_button)
        self._on_tool_selected(key)
        self._sync_presentation()
        self._refresh()

    def _on_tool_selected(self, key: str) -> None:
        """子類別可覆寫的擴充點，用於處理特定模組的模式切換需求。

        參數：
            key: 使用者選取的分析定義 key。

        回傳：
            無。
        """

    def _on_result_invalidated(self) -> None:
        """使用者修改輸入使結果失效時，重繪結果區（隱藏舊數值與圖表）。

        回傳：
            無。
        """
        self._show_result()
        self._refresh()

    def _handle_calculate(self, _event: ft.ControlEvent | None) -> None:
        """執行目前選取分析的計算並重繪結果面板。

        參數：
            _event: Flet 點擊事件；此處不需讀取事件內容。

        回傳：
            無。
        """
        self.adapter.calculate()
        self._show_result()
        self._refresh()

    def perform_calculation(self, event: ft.ControlEvent | None) -> None:
        """提供與 PropertyTab 一致的呼叫慣例，供 AppShell 的 Ctrl+Enter 捷徑使用。

        參數：
            event: Flet 事件；此處不需讀取事件內容。

        回傳：
            無。
        """
        self._handle_calculate(event)

    def set_output_unit_system(self, unit_system: str) -> None:
        """套用全域輸出單位偏好，不影響各輸入欄位既有單位。

        參數：
            unit_system: 要套用的輸出單位系統。

        回傳：
            無。
        """
        self.adapter.set_output_unit_system(unit_system)
        self._show_result()
        self._refresh()

    def _refresh(self) -> None:
        """在已掛載頁面時更新畫面，避免建構期間呼叫 update() 拋出例外。

        回傳：
            無。
        """
        try:
            attached_page = self.page
        except RuntimeError:
            attached_page = None
        if attached_page:
            self.update()
