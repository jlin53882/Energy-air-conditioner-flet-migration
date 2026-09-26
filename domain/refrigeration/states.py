"""冷凍計算共用的狀態查詢協定。

狀態點模型為 :class:`domain.state_points.ThermoStatePoint`。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from domain.thermodynamics.reference_state import ReferenceStatePolicy


class ThermodynamicStateProvider(Protocol):
    """以 canonical SI 已知性質回傳 CoolProp 狀態的服務（由 ThermodynamicStateService 實作）。"""

    def calculate_state_si(
        self,
        fluid: str,
        known_si: Sequence[tuple[str, float]],
        reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT,
    ) -> Mapping[str, float | str]: ...


def query_state(
    provider: ThermodynamicStateProvider,
    fluid: str,
    known_si: Sequence[tuple[str, float]],
    reference_state: ReferenceStatePolicy | str,
    description: str,
) -> Mapping[str, float | str]:
    """查詢狀態，失敗時轉為帶有狀態說明的 ValueError。

參數：
    provider: 狀態服務。
    fluid: CoolProp 流體名稱。
    known_si: 兩組 SI 已知性質。
    reference_state: reference-state policy。
    description: 失敗訊息中的狀態說明。

回傳：
    狀態 dict。

引發：
    ValueError：狀態服務無法計算時。"""
    try:
        return provider.calculate_state_si(fluid, known_si, reference_state)
    except RuntimeError as exc:
        raise ValueError(f"無法計算{description}，請確認流體與溫度／壓力是否在適用範圍：{exc}") from exc
