"""中立流體識別與舊版 reference-state policy helper（相容層）。

Auto 的實際規則集中於 :mod:`domain.thermodynamics.thermo_policy`；本模組只保留舊呼叫端
使用的函式名稱，並委派給同一個 resolver，避免出現第二套 Auto 規則。
"""

from __future__ import annotations

from domain.thermodynamics.reference_state import ReferenceStatePolicy, canonical_fluid_name
from domain.thermodynamics.thermo_policy import WATER, Workflow, resolve_thermo_policy


def normalize_fluid_name(fluid: str) -> str:
    """回傳移除使用者輸入前後空白的流體名稱。

參數：
    fluid (str): 函數輸入值。

回傳：
    str：函數計算或處理後的結果。"""
    return fluid.strip()


def is_water(fluid: str) -> bool:
    """回傳流體是否為 Water（以 CoolProp 別名解析，例如 ``water``、``H2O``）。

參數：
    fluid (str): 函數輸入值。

回傳：
    bool：函數計算或處理後的結果。"""
    name = normalize_fluid_name(fluid)
    return name.casefold() == "water" or canonical_fluid_name(name) == WATER


def resolve_reference_state_policy(
    fluid: str,
    requested_policy: ReferenceStatePolicy | str | None = None,
    *,
    workflow: Workflow = Workflow.LEGACY,
) -> str:
    """回傳 CoolProp 真實流體 request 的明確 policy code。

    ``requested_policy`` 為 None 或 ``Auto`` 時套用集中 Auto 規則；手動指定但流體不支援時
    引發 :class:`~domain.thermodynamics.thermo_policy.ThermoPolicyError`（不再靜默改用 DEF）。
    """
    policy = resolve_thermo_policy(
        fluid, model="auto", reference=requested_policy, workflow=workflow
    )
    assert policy.reference_state is not None
    return policy.reference_state
