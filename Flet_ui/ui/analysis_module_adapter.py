"""跨 dedicated analysis view 共用的 tool selection / calculation dispatch adapter。

``AnalysisModuleAdapter`` 只認得 :class:`AnalysisDefinition`；它完全不知道
compressor、evaporator、condenser、psychrometric 等任何特定分類的存在。
新增一種分析類別時，不需要修改這個 class —— 只需要提供新的
``AnalysisDefinition`` 清單。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator

import flet as ft

from .analysis_definition import AnalysisDefinition, PreparedCalculation, definitions_from_module
from .calculation_runner import CalculationOutcome, CalculationRunner
from .components.result_panel import ResultPanel

logger = logging.getLogger(__name__)

# 既有模組以這些前綴的文字回報未完成的計算，呈現為錯誤而非結果指標。
_FAILED_RESULT_PREFIXES = ("計算錯誤", "計算失敗")


# 使用者修改後會改變計算語意的輸入控制項，以及各自的事件屬性名稱。
_SEMANTIC_INPUT_EVENTS = (
    (ft.TextField, "on_change"),
    (ft.Dropdown, "on_select"),
    (ft.Checkbox, "on_change"),
    (ft.Switch, "on_change"),
    (ft.RadioGroup, "on_change"),
    (ft.SegmentedButton, "on_change"),
)


def iter_controls(root: ft.Control) -> Iterator[ft.Control]:
    """依控制項樹的固定順序走訪所有子控制項（含 root）。

    參數：
        root: 起點控制項。

    回傳：
        Iterator：依深度優先順序產生的控制項。
    """
    stack: list[ft.Control] = [root]
    while stack:
        control = stack.pop()
        yield control
        children: list[ft.Control] = []
        content = getattr(control, "content", None)
        if isinstance(content, ft.Control):
            children.append(content)
        for attribute in ("controls", "actions"):
            nested = getattr(control, attribute, None)
            if isinstance(nested, list):
                children.extend(child for child in nested if isinstance(child, ft.Control))
        stack.extend(reversed(children))


class AnalysisModuleAdapter:
    """擁有單一 category 的 active tool、計算 dispatch 與結果呈現狀態。

    這個 adapter 取代舊 ``AnalysisTab`` 內混合 navigation／module／calculation／
    presentation 責任的部分，只保留「module 定義 → dispatch → 呈現」這一段。
    """

    def __init__(self, modules: list[object], runner: CalculationRunner | None = None) -> None:
        """彙整一或多個既有模組提供的分析定義，並以第一項作為預設選取。

        參數：
            modules: 已建構完成的既有 ``BaseAnalysisModule`` 子類別實例；
                通常一個 dedicated view 只會傳入一個模組，但保留清單型別
                以支援未來同一分類需要多個模組協作的情況。
            runner: 選用的背景執行器。提供時，定義了 ``prepare`` 的分析會在背景計算
                （見 :meth:`calculate`）；未提供或分析沒有 ``prepare`` 時照舊同步計算。

        回傳：
            無。

        引發：
            ValueError: 傳入的模組沒有提供任何 analysis definition，或多個
                模組之間出現重複的 analysis key（不允許 silent overwrite，
                必須 fail fast）。
        """
        self.modules = list(modules)
        self.definitions: list[AnalysisDefinition] = []
        seen_keys: set[str] = set()
        for module in self.modules:
            for definition in definitions_from_module(module):
                if definition.key in seen_keys:
                    raise ValueError(
                        "Duplicate AnalysisDefinition key across modules: "
                        f"key={definition.key!r} module={type(module).__name__!r} "
                        f"label={definition.label!r}"
                    )
                seen_keys.add(definition.key)
                self.definitions.append(definition)
        if not self.definitions:
            raise ValueError("AnalysisModuleAdapter requires at least one AnalysisDefinition")
        self._by_key = {definition.key: definition for definition in self.definitions}
        self.active_key = self.definitions[0].key
        self.result_panel = ResultPanel()
        self.result_text: str | None = None
        self._has_calculated_result = False
        # 結果因輸入修改而失效時通知 view 重繪結果區。
        self.on_result_invalidated: Callable[[], None] | None = None
        # 背景計算完成且結果仍屬於目前這一輪時通知 view 重繪結果區。
        self.on_calculation_finished: Callable[[], None] | None = None
        self.runner = runner
        # 每次開始計算、修改語意輸入、切換分析或重新計算都遞增；背景結果只有在 generation
        # 未改變時才發布，舊一輪的結果（含錯誤）完成後直接丟棄。
        self.generation = 0
        self.is_running = False
        self.output_unit_system = "SI"
        self._sync_visibility()
        self._bind_input_invalidation()

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
        self._abandon_running()
        self.active_key = key
        self._has_calculated_result = False
        self.result_text = None
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
        依 PR #4 規格，此處只保存 status 與原始文字（``result_text``），
        指標卡片由呈現層從文字投影，不假造 metric。以「計算錯誤」或
        「計算失敗」開頭的模組文字代表未完成計算，改以錯誤狀態呈現。

        ``AnalysisDefinition.calculate`` 一律是統一的
        ``Callable[[bool], str]``；任何模組專屬的呼叫慣例（例如 PsyModule
        需要的 mode_key）都已由該模組自己在 ``get_analysis_definitions()``
        回傳的 ``calc_func`` 完成綁定，這個 adapter 完全不需要知道
        psychrometric 或任何特定分類的存在。

        有背景執行器且分析提供 ``prepare`` 時改為非阻塞：在 UI 執行緒讀取並驗證輸入
        （``prepare``），進入「計算中」狀態後把 ``compute`` 交給執行器；完成時只有
        generation 未改變才以 ``publish`` 發布（見 :meth:`_finish_background`）。計算中
        再次要求同一輪計算會被忽略（避免重複執行）。

        回傳：
            無。
        """
        definition = self.active_definition
        if self.runner is not None and definition.prepare is not None:
            self._calculate_in_background(definition)
            return
        self.generation += 1
        use_imperial = self.output_unit_system == "Imperial"
        try:
            result_string = definition.calculate(use_imperial)
        except ValueError as ve:
            self._record_failure(f"輸入/計算錯誤: {ve}")
            return
        except Exception as err:
            logger.exception("Unexpected error during analysis calculation")
            self._record_failure(f"計算錯誤: {err}")
            return
        self._record_result(definition, result_string)

    def _calculate_in_background(self, definition: AnalysisDefinition) -> None:
        """在 UI 執行緒準備輸入，把計算交給背景執行器。

        參數：
            definition: 目前選取的分析定義（提供 ``prepare``）。

        回傳：
            無。
        """
        if self.is_running:
            return
        self.generation += 1
        generation = self.generation
        try:
            prepared = definition.prepare(self.output_unit_system == "Imperial")
        except ValueError as ve:
            self._record_failure(f"輸入/計算錯誤: {ve}")
            return
        except Exception as err:
            logger.exception("Unexpected error while preparing analysis calculation")
            self._record_failure(f"計算錯誤: {err}")
            return
        self.result_text = None
        self._has_calculated_result = False
        self.is_running = True
        self.result_panel.set_status("loading", "計算中", f"{definition.label} · 完成後自動顯示結果")
        self.runner.submit(
            prepared.compute,
            lambda outcome: self._finish_background(generation, definition, prepared, outcome),
        )

    def _finish_background(
        self,
        generation: int,
        definition: AnalysisDefinition,
        prepared: PreparedCalculation,
        outcome: CalculationOutcome,
    ) -> None:
        """在 UI 執行緒處理背景計算的結果；已過期的結果（含錯誤）一律丟棄。

        參數：
            generation: 開始計算時的 generation。
            definition: 開始計算時的分析定義。
            prepared: 開始計算時準備好的計算。
            outcome: 背景計算的結果或例外。

        回傳：
            無。
        """
        if generation != self.generation:
            logger.debug("Discarded stale background calculation for %s", definition.key)
            return
        self.is_running = False
        if outcome.error is None:
            try:
                # 圖表與文字都在 publish 內、同一個 generation 產生，不會混用不同輪的結果。
                result_string = prepared.publish(outcome.value)
            except Exception as error:  # noqa: BLE001 — 與背景例外使用相同分類。
                outcome = CalculationOutcome(error=error)
            else:
                self._record_result(definition, result_string)
        if outcome.error is not None:
            if isinstance(outcome.error, ValueError):
                self._record_failure(f"輸入/計算錯誤: {outcome.error}")
            else:
                logger.error("Unexpected error during background analysis calculation", exc_info=outcome.error)
                self._record_failure(f"計算錯誤: {outcome.error}")
        if self.on_calculation_finished is not None:
            self.on_calculation_finished()

    def _abandon_running(self) -> None:
        """使進行中的背景計算過期：它完成後不會發布任何結果或錯誤。

        回傳：
            無。
        """
        if self.is_running:
            self.generation += 1
            self.is_running = False

    def _record_result(self, definition: AnalysisDefinition, result_string: str) -> None:
        """記錄模組回傳的結果文字；以錯誤前綴開頭的文字以錯誤狀態呈現。

        參數：
            definition: 產生結果的分析定義。
            result_string: 模組回傳的結果文字。

        回傳：
            無。
        """
        self.result_text = result_string
        stripped = result_string.strip()
        if stripped.startswith(_FAILED_RESULT_PREFIXES):
            self.result_panel.set_error(stripped)
            self._has_calculated_result = False
            return
        self.result_panel.set_status(
            "success", "計算完成", f"{definition.label} · 輸出 {self.output_unit_system}"
        )
        self._has_calculated_result = True

    def _record_failure(self, message: str) -> None:
        """以錯誤狀態記錄計算失敗，並清除先前的結果文字。

        參數：
            message: 面向使用者的錯誤摘要。

        回傳：
            無。
        """
        self.result_text = None
        self.result_panel.set_error(message)
        self._has_calculated_result = False

    def set_output_unit_system(self, unit_system: str) -> None:
        """更新輸出單位偏好，並以新單位重新呈現仍有效的結果。

        這個偏好只影響「結果如何呈現」，不得覆寫任何 input 欄位的值或單位。
        既有模組只輸出格式化文字，因此目前以重新計算取代重新格式化；這是過渡期
        限制（見 docs/state-invalidation.md §3.1），canonical request 與工程結果不得改變。
        壓縮機等模組的大氣壓力等輸入，一律沿用使用者目前輸入的 value +
        selected input unit；domain/unit converter 會在計算時自行處理換算，
        不需要（也不應該）因為切換輸出單位而竄改 input 預設值。

        參數：
            unit_system: 要套用的輸出單位系統（"SI" 或 "Imperial"）。

        回傳：
            無。
        """
        self.output_unit_system = unit_system
        # 模組只輸出格式化文字，換單位必須重新計算。輸入一被修改結果就已失效
        # （見 invalidate_result），因此仍有結果時輸入必定與該結果一致。進行中的背景計算
        # 以舊單位格式化，改為以同一組輸入、新單位重新計算，舊的一輪完成後丟棄。
        if self._has_calculated_result or self.is_running:
            self._abandon_running()
            self.calculate()

    def invalidate_result(self) -> None:
        """使用者修改計算輸入後清除舊結果，並提示以目前輸入重新計算。

        進行中的背景計算以舊輸入建立，同樣作廢：完成後不發布結果或錯誤。尚無成功結果
        且沒有進行中的計算（未計算或計算失敗）時不做任何事。

        回傳：
            無。
        """
        if self.is_running:
            self._abandon_running()
            self.result_panel.set_status(
                "warning", "輸入已變更", "進行中的計算已作廢，請使用目前輸入重新執行計算。"
            )
            if self.on_result_invalidated is not None:
                self.on_result_invalidated()
            return
        if not self._has_calculated_result:
            return
        self.result_text = None
        self._has_calculated_result = False
        self.result_panel.set_status(
            "warning", "輸入已變更", "舊結果已清除，請使用目前輸入重新執行計算。"
        )
        if self.on_result_invalidated is not None:
            self.on_result_invalidated()

    def _bind_input_invalidation(self) -> None:
        """讓每個會改變計算語意的輸入在使用者修改時使結果失效。

        單位選單（``all_entries[...]["unit"]``）與模組宣告的
        ``presentation_only_controls``（例如錶壓／絕對壓切換）只改變表示方式、
        實際數值不變，不視為修改。既有的事件處理器會先執行，再使結果失效。

        回傳：
            無。
        """
        presentation_only: set[int] = set()
        for module in self.modules:
            for entry in getattr(module, "all_entries", {}).values():
                presentation_only.add(id(entry["unit"]))
            presentation_only.update(id(control) for control in getattr(module, "presentation_only_controls", ()))
        seen: set[int] = set()
        for definition in self.definitions:
            for control in iter_controls(definition.input_view):
                if id(control) in seen or id(control) in presentation_only:
                    continue
                seen.add(id(control))
                for control_type, event_name in _SEMANTIC_INPUT_EVENTS:
                    if isinstance(control, control_type):
                        setattr(control, event_name, self._invalidating_handler(getattr(control, event_name)))
                        break

    def _invalidating_handler(self, original: Callable[[object], object] | None) -> Callable[[object], None]:
        """包裝既有事件處理器：先執行原處理器，再使結果失效。

        參數：
            original: 控制項原有的事件處理器；沒有時為 None。

        回傳：
            新的事件處理器。
        """
        def handler(event: object) -> None:
            if original is not None:
                original(event)
            self.invalidate_result()

        return handler

    def tool_items(self) -> list[tuple[str, str]]:
        """提供給 ToolSelector 使用的 (key, label) 清單。

        回傳：
            依註冊順序排列的 (key, label) tuple 清單。
        """
        return [(definition.key, definition.label) for definition in self.definitions]
