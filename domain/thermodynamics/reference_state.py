"""Process-wide reference-state 同步與 request policy。"""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
from functools import lru_cache
from threading import RLock
from typing import Iterator

import CoolProp.CoolProp as CP


_PROCESS_COOLPROP_LOCK = RLock()
# 以 CoolProp canonical 流體名稱為 key：``R717``、``NH3``、``Ammonia`` 在 CoolProp 內共用同一個
# reference state，registry 也必須共用同一筆紀錄。
_PROCESS_REFERENCE_STATES: dict[str, str] = {}
# reference-state 能力探測快取：(CoolProp 版本, canonical 流體, policy code) -> 錯誤訊息（None 為支援）。
# 只保存與流體識別、能力及函式庫版本相關的 metadata，不保存任何物性數值。
_CAPABILITY_CACHE: dict[tuple[str, str, str], str | None] = {}


@lru_cache(maxsize=1)
def coolprop_version() -> str:
    """回傳目前載入的 CoolProp 版本字串（例如 ``8.0.0``）；process 內固定，快取。

回傳：
    版本字串；無法取得時為 ``unknown``。"""
    try:
        return str(CP.get_global_param_string("version"))
    except Exception:  # pragma: no cover - CoolProp 內部錯誤
        return "unknown"


def canonical_fluid_name(fluid_name: str) -> str | None:
    """回傳 CoolProp 對此流體識別字的 canonical 名稱；不是單一流體時回傳 None。

結果只與流體識別字及已載入的函式庫有關（與 reference state 無關），因此以去除空白後的
名稱快取；不快取任何物性數值。

以 CoolProp 函式庫本身查驗別名（例如 ``R717``、``NH3`` → ``Ammonia``；``R744`` →
``CarbonDioxide``），不自行維護別名表。混合物字串（含 ``&`` 或組成 ``[...]``）不做別名
解析：CoolProp 對混合物字串只回傳第一個成分名稱，視為同一物質會造成錯誤。

參數：
    fluid_name: 使用者輸入或程式內部的流體名稱，可含 ``HEOS::`` 等 backend 前綴。

回傳：
    canonical 名稱；空字串、混合物字串或 CoolProp 不認得時為 None。"""
    return _canonical_fluid_name_cached((fluid_name or "").strip())


@lru_cache(maxsize=1024)
def _canonical_fluid_name_cached(name: str) -> str | None:
    """:func:`canonical_fluid_name` 的快取實作（key 為去除空白後的名稱）。"""
    if not name or "&" in name or "[" in name:
        return None
    try:
        with _PROCESS_COOLPROP_LOCK:
            canonical = CP.get_fluid_param_string(name, "name")
    except ValueError:
        return None
    return canonical or None


def _registry_key(fluid_name: str) -> str:
    """回傳 registry key：可解析時用 canonical 名稱，否則用去除空白的原字串。"""
    return canonical_fluid_name(fluid_name) or fluid_name.strip()


class ReferenceStatePolicy(str, Enum):
    """reference-state-sensitive request 的明確 policies。"""

    DEFAULT = "DEF"
    ASHRAE = "ASHRAE"
    IIR = "IIR"
    NBP = "NBP"
    CURRENT = "CURRENT"


def normalize_reference_state_policy(policy: ReferenceStatePolicy | str) -> str:
    """將 reference-state policy 正規化為 application 可保存的 canonical code。

    參數：
        policy (ReferenceStatePolicy | str): UI alias、enum 或 policy code。

    回傳：
        str：`DEF`、`ASHRAE`、`IIR`、`NBP` 或內部使用的 `CURRENT`。

    例外：
        ValueError：policy 不在支援的 reference-state code 中。
    """
    normalized = policy.value if isinstance(policy, ReferenceStatePolicy) else policy.strip().upper()
    if normalized == "DEFAULT":
        normalized = ReferenceStatePolicy.DEFAULT.value
    if normalized == ReferenceStatePolicy.CURRENT.value:
        return normalized
    if normalized not in ReferenceStateService.VALID_CODES:
        raise ValueError(f"Unsupported reference state policy '{policy}'")
    return normalized


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
        return normalize_reference_state_policy(policy)

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
        _PROCESS_REFERENCE_STATES[_registry_key(fluid_name)] = normalized

    def unsupported_reason(self, fluid_name: str, ref_state: ReferenceStatePolicy | str) -> str | None:
        """以目前 CoolProp 的實際行為探測流體是否支援指定 reference state。

探測方式是在共用 lock 內真正呼叫 ``CP.set_reference_state``，以函式庫行為為準，不自行
用三相點、臨界點重算判斷條件。成功時會恢復探測前 registry 記錄的基準（若有）。結果以
(CoolProp 版本, canonical 流體, policy) 為 key 快取；不快取任何物性數值。

參數：
    fluid_name: 流體名稱（可為別名）。
    ref_state: 要探測的明確 policy（不可為 CURRENT）。

回傳：
    支援時為 None；不支援時為 CoolProp 回報的原因文字。

引發：
    ValueError：policy 無效或為 CURRENT 時。"""
        normalized = self._normalize_policy(ref_state)
        if normalized == ReferenceStatePolicy.CURRENT.value:
            raise ValueError("CURRENT is not a probe-able reference state")
        canonical = canonical_fluid_name(fluid_name)
        if canonical is None:
            return f"CoolProp 無法辨識單一流體 '{fluid_name.strip()}'"
        key = (coolprop_version(), canonical, normalized)
        with _PROCESS_COOLPROP_LOCK:
            if key in _CAPABILITY_CACHE:
                return _CAPABILITY_CACHE[key]
            previous = _PROCESS_REFERENCE_STATES.get(canonical)
            try:
                CP.set_reference_state(canonical, normalized)
            except (KeyError, ValueError) as exc:
                reason: str | None = str(exc) or "CoolProp 拒絕此 reference state"
            else:
                reason = None
                _PROCESS_REFERENCE_STATES[canonical] = normalized
                if previous is not None and previous != normalized:
                    CP.set_reference_state(canonical, previous)
                    _PROCESS_REFERENCE_STATES[canonical] = previous
            _CAPABILITY_CACHE[key] = reason
            return reason

    def supports(self, fluid_name: str, ref_state: ReferenceStatePolicy | str) -> bool:
        """回傳流體是否支援指定 reference state（見 :meth:`unsupported_reason`）。

參數：
    fluid_name: 流體名稱。
    ref_state: 明確 policy。

回傳：
    bool。"""
        return self.unsupported_reason(fluid_name, ref_state) is None

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
            return _PROCESS_REFERENCE_STATES.get(_registry_key(fluid_name))
