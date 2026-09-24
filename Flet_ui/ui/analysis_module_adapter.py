"""跨 dedicated analysis view 共用的 tool selection / calculation dispatch adapter。

``AnalysisModuleAdapter`` 只認得 :class:`AnalysisDefinition`；它完全不知道
compressor、evaporator、condenser、psychrometric 等任何特定分類的存在。
新增一種分析類別時，不需要修改這個 class —— 只需要提供新的
``AnalysisDefinition`` 清單。
"""

from __future__ import annotations

import logging

from .analysis_definition import AnalysisDefinition, definitions_from_module
from .components.result_panel import ResultPanel

logger = logging.getLogger(__name__)


class AnalysisModuleAdapter:
    """擁有單一 category 的 active tool、計算 dispatch 與結果呈現狀態。

    這個 adapter 取代舊 ``AnalysisTab`` 內混合 navigation／module／calculation／
    presentation 責任的部分，只保留「module 定義 → dispatch → 呈現」這一段。
    """

    def __init__(self, modules: list[object]) -> None:
        """彙整一或多個既有模組提供的分析定義，並以第一項作為預設選取。

        參數：
            modules: 已建構完成的既有 ``BaseAnalysisModule`` 子類別實例；
                通常一個 dedicated view 只會傳入一個模組，但保留清單型別
                以支援未來同一分類需要多個模組協作的情況。

        回傳：
            無。

        引發：
            ValueError: 傳入的模組沒有提供任何 analysis definition。
        """
        self.modules = list(modules)
        self.definitions: list[AnalysisDefinition] = []
        for module in self.modules:
            self.definitions.extend(definitions_from_module(module))
        if not self.definitions:
            raise ValueError("AnalysisModuleAdapter requires at least one AnalysisDefinition")
        self._by_key = {definition.key: definition for definition in self.definitions}
        self.active_key = self.definitions[0].key
        self.result_panel = ResultPanel()
        self._has_calculated_result = False
        self.output_unit_system = "SI"
        self._sync_visibility()

    @property
    def active_definition(self) -> AnalysisDefinition:
        """回傳目前選取的分析定義。

        回傳：
            AnalysisDefinition：目前 active_key 對應的定義。
        """
        return self._by_key[self.active_key]

    def select(self, key: str) -> None:
        """切換目前選取的分析工具，並將結果狀態重設為未計算。

        參數：
            key: 要選取的分析定義 key。

        回傳：
            無。

        引發：
            KeyError: key 不屬於此 adapter 已知的定義。
        """
        if key not in self._by_key:
            raise KeyError(f"Unknown analysis key: {key}")
        self.active_key = key
        self._has_calculated_result = False
        self.result_panel.set_status("empty", "尚未執行分析", "請完成必要輸入後執行計算。")
        self._sync_visibility()

    def _sync_visibility(self) -> None:
        """只顯示目前選取分析的輸入控制項，其餘全部隱藏。

        回傳：
            無。
        """
        seen_ui_ids: set[int] = set()
        for definition in self.definitions:
            if id(definition.input_view) in seen_ui_ids:
                continue
            seen_ui_ids.add(id(definition.input_view))
            definition.input_view.visible = definition.input_view is self.active_definition.input_view

    def calculate(self) -> None:
        """執行目前選取分析的計算，並以 ResultPanel 呈現狀態。

        既有模組目前只能可靠提供 formatted text（而非結構化 metrics）；
        依 PR #4 規格，此處只呈現 status + primary text，不假造 metric。

        回傳：
            無。
        """
        definition = self.active_definition
        use_imperial = self.output_unit_system == "Imperial"
        try:
            if definition.calculation_mode == "psychrometric":
                # PsyModule 既有 calc_func 仍以顯示文字判斷模式；
                # adapter 保留原始呼叫慣例以避免改動 domain 行為。
                result_string = definition.calculate(use_imperial, mode_name=definition.label)
            else:
                result_string = definition.calculate(use_imperial)
            self.result_panel.set_status("success", "計算完成", result_string)
            self._has_calculated_result = True
        except ValueError as ve:
            self.result_panel.set_error(f"輸入/計算錯誤: {ve}")
            self._has_calculated_result = False
        except Exception as err:
            logger.exception("Unexpected error during analysis calculation")
            self.result_panel.set_error(f"計算錯誤: {err}")
            self._has_calculated_result = False

    def set_output_unit_system(self, unit_system: str) -> None:
        """更新輸出單位偏好，並視需要以新單位重新格式化既有結果。

        這個偏好只影響「結果如何呈現」，不得覆寫任何 input 欄位的值或單位。
        壓縮機等模組的大氣壓力等輸入，一律沿用使用者目前輸入的 value +
        selected input unit；domain/unit converter 會在計算時自行處理換算，
        不需要（也不應該）因為切換輸出單位而竄改 input 預設值。

        參數：
            unit_system: 要套用的輸出單位系統（"SI" 或 "Imperial"）。

        回傳：
            無。
        """
        self.output_unit_system = unit_system
        if self._has_calculated_result:
            self.calculate()

    def tool_items(self) -> list[tuple[str, str]]:
        """提供給 ToolSelector 使用的 (key, label) 清單。

        回傳：
            依註冊順序排列的 (key, label) tuple 清單。
        """
        return [(definition.key, definition.label) for definition in self.definitions]
