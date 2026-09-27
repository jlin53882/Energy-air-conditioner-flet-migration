"""Typed contract separating an analysis's internal key from its display label.

PR #4 (Analysis Workspace Migration) 引入這個型別，讓 routing / dispatch
只依賴穩定的 ``key``（即既有 module 的 ``analysis_id``），而顯示用的
``label`` 只用於 UI 呈現。翻譯或文案調整永遠不應該影響 routing 行為。

``calculate`` 一律要求呼叫端（既有模組）就已提供統一的
``Callable[[bool], str]`` 簽章：任何模組專屬的計算參數（例如
``PsyModule`` 需要的 ``mode_key``）都必須由該模組自己在
``get_analysis_definitions()`` 回傳的 ``calc_func`` 建構時完成綁定，
這個轉換層與下游的
:class:`~Flet_ui.ui.analysis_module_adapter.AnalysisModuleAdapter`
完全不知道任何特定模組的計算模式或呼叫慣例。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import flet as ft

from domain.state_library import SavedPoint

from .structured_result import StructuredResult


@dataclass(frozen=True)
class PreparedCalculation:
    """已在 UI 執行緒讀取並驗證完輸入的一次計算，分成背景計算與 UI 發布兩段。

    Attributes:
        compute: 無參數函式，只做 domain／application 計算並回傳結構化結果。它可能在
            背景執行緒執行，因此不得讀取或修改任何 Flet 控制項、共用圖表（Matplotlib
            figure）或模組狀態；所需輸入必須在建立本物件時就已複製成不可變的 request。
        publish: 以 ``compute`` 的結果在 UI 執行緒格式化文字、繪製圖表並更新模組狀態，
            回傳與 ``calculate`` 相同格式的結果文字。只有結果仍屬於目前這一輪計算時才會被呼叫。
    """

    compute: Callable[[], object]
    publish: Callable[[object], str]


def run_prepared(prepare: Callable[[bool], PreparedCalculation]) -> Callable[[bool], str]:
    """把兩段式計算組成同步的 ``calculate``（在同一執行緒依序 prepare → compute → publish）。

    參數：
        prepare: 模組的 ``prepare_func``。

    回傳：
        統一簽章 ``Callable[[bool], str]`` 的計算函式。
    """
    def calculate(use_imperial: bool) -> str:
        prepared = prepare(use_imperial)
        return prepared.publish(prepared.compute())

    return calculate


@dataclass(frozen=True)
class AnalysisDefinition:
    """描述一項已存在的分析計算及其呈現方式。

    Attributes:
        key: 穩定的內部識別碼（沿用既有模組的 ``analysis_id``），routing /
            dispatch 一律使用這個欄位，不得使用 ``label``。
        label: 顯示於 ToolSelector 的文字，可隨時調整文案而不影響行為。
        input_view: 此分析對應的輸入 Flet 控制項。
        calculate: 統一簽章 ``Callable[[bool], str]``（輸入 use_imperial，
            回傳格式化結果文字）；模組必須在 ``get_analysis_definitions()``
            回傳的 ``calc_func`` 就已是這個簽章，任何模組專屬參數（例如
            ``PsyModule`` 的 ``mode_key``）都由該模組自己預先綁定完成。
        show_execute_button: 是否顯示共用的「執行分析」按鈕。
        result_chart: 選用的結果圖表控制項（例如 ``FigurePanel``）；成功
            計算後顯示於結果卡片，重設或失敗時隱藏。
        structured_result: 選用的無參數函式，回傳最近一次成功計算的
            :class:`~Flet_ui.ui.structured_result.StructuredResult`（關鍵數值、
            性質表與計算過程）；未提供時結果區由文字投影分組指標。
        state_points: 選用的無參數函式，回傳最近一次成功計算可保存到 State Library
            的狀態點（只能是 ``ThermoStatePoint``／``AirStatePoint``，其他型別在顯示儲存選單時
            以 ``TypeError`` 立即失敗）；未提供時不顯示儲存選單。
        prepare: 選用的兩段式計算（見 :class:`PreparedCalculation`）。提供時 ``calculate``
            由它組成；搭配背景執行器的 adapter 會改在背景執行 ``compute``，UI 執行緒不被阻塞。
    """

    key: str
    label: str
    input_view: ft.Control
    calculate: Callable[[bool], str]
    show_execute_button: bool = True
    result_chart: ft.Control | None = None
    structured_result: Callable[[], StructuredResult | None] | None = None
    state_points: Callable[[], Sequence[SavedPoint]] | None = None
    prepare: Callable[[bool], PreparedCalculation] | None = None


def definitions_from_module(module: object) -> list[AnalysisDefinition]:
    """將既有 ``BaseAnalysisModule.get_analysis_definitions()`` 的 legacy dict 轉為型別化定義。

    這個轉換不改變任何計算邏輯；它只是把既有 module 自我註冊的 magic dict
    重新包裝為 :class:`AnalysisDefinition`，讓 View / Adapter 層只依賴穩定
    key 與統一的 ``Callable[[bool], str]`` calculate 簽章。模組專屬的呼叫
    慣例（目前僅 ``PsyModule`` 需要額外的 ``mode_key`` 參數）完全由該模組
    自己在 ``get_analysis_definitions()`` 內預先綁定完成——這個工廠函式
    本身不判斷、不 import、也不知道任何特定模組的存在或計算模式。

    參數：
        module: 已實作 ``get_analysis_definitions()`` 的既有分析模組實例。

    回傳：
        依模組註冊順序排列的 :class:`AnalysisDefinition` 清單。

    引發：
        ValueError: 任一項目缺少 ``analysis_id``，或 ``analysis_id`` 重複。
    """
    definitions: list[AnalysisDefinition] = []
    seen_ids: set[str] = set()
    for label, raw in module.get_analysis_definitions().items():
        analysis_id = raw.get("analysis_id")
        if not isinstance(analysis_id, str) or not analysis_id.strip():
            raise ValueError(f"Analysis '{label}' is missing analysis_id")
        if analysis_id in seen_ids:
            raise ValueError(f"Duplicate analysis_id: {analysis_id}")
        seen_ids.add(analysis_id)

        # 模組提供 calc_func（同步計算），或 prepare_func（兩段式計算，calculate 由它組成），
        # 不可同時提供，避免兩條路徑的計算語意不一致。
        prepare = raw.get("prepare_func")
        if prepare is not None and "calc_func" in raw:
            raise ValueError(f"Analysis '{analysis_id}' must provide calc_func or prepare_func, not both")
        raw_calc_func = run_prepared(prepare) if prepare is not None else raw["calc_func"]

        definitions.append(
            AnalysisDefinition(
                key=analysis_id,
                label=label,
                input_view=raw["ui"],
                calculate=raw_calc_func,
                show_execute_button=raw.get("show_execute_button", True),
                result_chart=raw.get("result_chart"),
                structured_result=raw.get("structured_result"),
                state_points=raw.get("state_points"),
                prepare=prepare,
            )
        )
    return definitions
