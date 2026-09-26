"""狀態點共用的來源列舉、protocol 與數值驗證。"""

from __future__ import annotations

from enum import Enum
from math import isfinite
from typing import Protocol, runtime_checkable


class StateSource(str, Enum):
    """狀態點由哪一個工具產生；值會寫入保存的文件，不得任意更名。"""

    PROPERTY_QUERY = "property_query"
    REFRIGERATION_CYCLE = "refrigeration_cycle"
    CONDENSER_EXERGY = "condenser_exergy"
    PSYCHROMETRICS = "psychrometrics"
    AIR_PROCESS = "air_process"
    MANUAL = "manual"


class StateBasisMismatchError(ValueError):
    """兩個狀態點的流體、reference state 或性質模型不同，不能直接比較或相減。"""


@runtime_checkable
class StatePoint(Protocol):
    """冷媒與濕空氣狀態點共用的最小介面。"""

    @property
    def source(self) -> StateSource:
        """產生此狀態點的工具。"""

    @property
    def label(self) -> str:
        """顯示用名稱；可為空字串。"""

    def to_dict(self) -> dict[str, object]:
        """回傳含 schema 標記、可保存為 JSON 的 dict。"""


def parse_source(value: StateSource | str) -> StateSource:
    """將來源正規化為 :class:`StateSource`。

參數：
    value: 列舉或其字串值。

回傳：
    StateSource。

引發：
    ValueError：不是已知來源時。"""
    try:
        return StateSource(value)
    except ValueError:
        raise ValueError(f"未知的狀態點來源：{value!r}。") from None


def finite_float(name: str, value: object) -> float:
    """轉為有限浮點數。

參數：
    name: 錯誤訊息中的欄位名稱。
    value: 要轉換的值（不接受布林值）。

回傳：
    float。

引發：
    ValueError：不是數字、為布林值或不是有限數字時。"""
    if isinstance(value, bool):
        raise ValueError(f"{name} 必須是數字。")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"{name} 必須是數字（目前為 {value!r}）。") from None
    if not isfinite(number):
        raise ValueError(f"{name} 必須是有限數字。")
    return number


def positive_float(name: str, value: object) -> float:
    """轉為大於 0 的有限浮點數。

參數：
    name: 錯誤訊息中的欄位名稱。
    value: 要轉換的值。

回傳：
    float。

引發：
    ValueError：不是有限數字或不大於 0 時。"""
    number = finite_float(name, value)
    if number <= 0:
        raise ValueError(f"{name} 必須大於 0。")
    return number


def text(name: str, value: object) -> str:
    """確認為字串。

參數：
    name: 錯誤訊息中的欄位名稱。
    value: 要檢查的值。

回傳：
    原字串。

引發：
    ValueError：不是字串時。"""
    if not isinstance(value, str):
        raise ValueError(f"{name} 必須是文字。")
    return value
