"""Process-wide reference-state 同步與 request policy。"""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
from threading import RLock
from typing import Iterator

import CoolProp.CoolProp as CP


_PROCESS_COOLPROP_LOCK = RLock()
_PROCESS_REFERENCE_STATES: dict[str, str] = {}


class ReferenceStatePolicy(str, Enum):
    """reference-state-sensitive request 的明確 policies。"""

    DEFAULT = "DEF"
    ASHRAE = "ASHRAE"
    IIR = "IIR"
    NBP = "NBP"
    CURRENT = "CURRENT"


class ReferenceStateService:
    """序列化 CoolProp transactions，並記錄 process-global state policy。"""

    VALID_CODES = frozenset({"DEF", "ASHRAE", "IIR", "NBP"})

    @property
    def lock(self) -> RLock:
        """公開 process-wide lock，供 identity/regression checks 使用。

回傳：
    RLock：函數計算或處理後的結果。"""
        return _PROCESS_COOLPROP_LOCK

    @staticmethod
    def _normalize_policy(policy: ReferenceStatePolicy | str) -> str:
        """正規化 request policy，不混淆 CURRENT 與 DEFAULT。

參數：
    policy (ReferenceStatePolicy | str): 函數輸入值。

回傳：
    str：函數計算或處理後的結果。"""
        normalized = policy.value if isinstance(policy, ReferenceStatePolicy) else policy.upper()
        if normalized == "DEFAULT":
            normalized = ReferenceStatePolicy.DEFAULT.value
        if normalized == ReferenceStatePolicy.CURRENT.value:
            return normalized
        if normalized not in ReferenceStateService.VALID_CODES:
            raise ValueError(f"Unsupported reference state policy '{policy}'")
        return normalized

    def _set_unlocked(self, fluid_name: str, ref_state: ReferenceStatePolicy | str) -> None:
        """持有共用 lock 時套用具體的 CoolProp mutation。

參數：
    fluid_name (str): 函數輸入值。
    ref_state (ReferenceStatePolicy | str): 函數輸入值。

回傳：
    無。"""
        normalized = self._normalize_policy(ref_state)
        if normalized == ReferenceStatePolicy.CURRENT.value:
            raise ValueError("CURRENT is not valid for set(); choose a concrete policy")
        try:
            CP.set_reference_state(fluid_name, normalized)
        except (KeyError, ValueError) as exc:
            raise ValueError(
                f"Unable to set reference state '{normalized}' for '{fluid_name}'"
            ) from exc
        _PROCESS_REFERENCE_STATES[fluid_name] = normalized

    def set(self, fluid_name: str, ref_state: ReferenceStatePolicy | str) -> None:
        """設定具體的 reference state，並更新共用 process registry。

參數：
    fluid_name (str): 函數輸入值。
    ref_state (ReferenceStatePolicy | str): 函數輸入值。

回傳：
    無。"""
        with _PROCESS_COOLPROP_LOCK:
            self._set_unlocked(fluid_name, ref_state)

    @contextmanager
    def calculation_scope(
        self,
        fluid_name: str,
        ref_state: ReferenceStatePolicy | str = ReferenceStatePolicy.CURRENT,
    ) -> Iterator[None]:
        """在明確 policy 下保護完整的 request transaction。

        ``CURRENT`` 刻意保留目前 process state，供
        流體有效性探測等內部操作使用。一般 property
        entrypoints 必須傳入 ``DEFAULT`` 或
        ``ASHRAE`` 等具體 policy；不得依賴 ambient state。
        """
        normalized = self._normalize_policy(ref_state)
        with _PROCESS_COOLPROP_LOCK:
            if normalized != ReferenceStatePolicy.CURRENT.value:
                self._set_unlocked(fluid_name, normalized)
            yield

    def current(self, fluid_name: str) -> str | None:
        """回傳流體的 process-global observed reference state。

參數：
    fluid_name (str): 函數輸入值。

回傳：
    str | None：函數計算或處理後的結果。"""
        with _PROCESS_COOLPROP_LOCK:
            return _PROCESS_REFERENCE_STATES.get(fluid_name)
