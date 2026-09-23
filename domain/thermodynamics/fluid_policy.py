"""中立流體識別與預設 reference-state policy helpers。"""

from __future__ import annotations

from domain.thermodynamics.reference_state import ReferenceStatePolicy


def normalize_fluid_name(fluid: str) -> str:
    """回傳移除使用者輸入前後空白的流體名稱。

參數：
    fluid (str): 函數輸入值。

回傳：
    str：函數計算或處理後的結果。"""
    return fluid.strip()


def is_water(fluid: str) -> bool:
    """回傳流體名稱是否不分大小寫地識別為 Water。

參數：
    fluid (str): 函數輸入值。

回傳：
    bool：函數計算或處理後的結果。"""
    return normalize_fluid_name(fluid).casefold() == "water"


def resolve_reference_state_policy(
    fluid: str,
    requested_policy: ReferenceStatePolicy | str | None = None,
) -> ReferenceStatePolicy | str:
    """為流體解析一個明確的一般 request policy。

    Water 使用 CoolProp 的 default reference state。其他流體保留
    呼叫端的明確 policy；若未提供，則使用 application default。
    """
    if is_water(fluid):
        return ReferenceStatePolicy.DEFAULT
    return requested_policy or ReferenceStatePolicy.ASHRAE
