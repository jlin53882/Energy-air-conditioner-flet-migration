"""把計算放到背景執行、再回到 UI 執行緒發布結果的執行器。

Flet 1.0 的同步事件處理器直接在 page 的事件迴圈上執行，耗時的計算會讓整個畫面停止回應。
:class:`FletCalculationRunner` 以 ``page.run_thread`` 在 page 的執行緒池中執行計算，完成後以
``page.run_task`` 回到事件迴圈呼叫完成回呼，因此所有 Flet 控制項與圖表的修改都留在 UI 執行緒。
執行器不判斷結果是否過期；新舊判斷（generation）由 ``AnalysisModuleAdapter`` 負責。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CalculationOutcome:
    """背景計算的結果：成功時 ``error`` 為 None，失敗時為計算引發的例外。"""

    value: object = None
    error: Exception | None = None


class CalculationRunner(Protocol):
    """執行背景計算並在 UI 執行緒回報結果的介面。"""

    def submit(self, work: Callable[[], object], on_done: Callable[[CalculationOutcome], None]) -> None:
        """在背景執行 ``work``，完成（含失敗）後在 UI 執行緒呼叫 ``on_done`` 一次。

參數：
    work: 不接觸 Flet 控制項的計算函式。
    on_done: 完成回呼。

回傳：
    無。"""


def run_work(work: Callable[[], object]) -> CalculationOutcome:
    """執行計算並把結果或例外包成 :class:`CalculationOutcome`。

參數：
    work: 計算函式。

回傳：
    CalculationOutcome；``Exception`` 以外的例外（例如 KeyboardInterrupt）照常拋出。"""
    try:
        return CalculationOutcome(value=work())
    except Exception as error:  # noqa: BLE001 — 交給 UI 執行緒依例外類型分類並記錄。
        return CalculationOutcome(error=error)


class FletCalculationRunner:
    """以 Flet page 的執行緒池計算、以 page 的事件迴圈發布結果。"""

    def __init__(self, page) -> None:
        """綁定 Flet page。

參數：
    page: 提供 ``run_thread`` 與 ``run_task`` 的 Flet page。

回傳：
    無。"""
        self.page = page

    def submit(self, work: Callable[[], object], on_done: Callable[[CalculationOutcome], None]) -> None:
        """在背景執行 ``work``，完成後回到事件迴圈呼叫 ``on_done``。

參數：
    work: 不接觸 Flet 控制項的計算函式。
    on_done: 完成回呼（在 UI 執行緒執行）。

回傳：
    無。"""
        def worker() -> None:
            """背景執行緒：只做計算，再把發布排回事件迴圈。

回傳：
    無。"""
            outcome = run_work(work)

            async def publish() -> None:
                """事件迴圈：呼叫完成回呼。

回傳：
    無。"""
                on_done(outcome)

            self.page.run_task(publish)

        self.page.run_thread(worker)
