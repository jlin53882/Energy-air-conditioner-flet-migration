"""冷凍計算共用的狀態查詢協定與狀態點模型。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True)
class CycleState:
    """循環中的一個狀態點（canonical SI）。"""

    key: str
    label: str
    pressure_pa: float
    temperature_k: float
    enthalpy_j_kg: float
    entropy_j_kgk: float
    density_kg_m3: float
    quality: float

    @classmethod
    def from_mapping(cls, key: str, label: str, state: Mapping[str, float | str]) -> "CycleState":
        """由狀態服務回傳的 dict 建立狀態點。

參數：
    key: 穩定狀態鍵，例如 "1"、"2s"。
    label: 顯示用說明。
    state: calculate_state_si 回傳的 dict。

回傳：
    CycleState。"""
        return cls(
            key=key,
            label=label,
            pressure_pa=float(state["P"]),
            temperature_k=float(state["T"]),
            enthalpy_j_kg=float(state["H"]),
            entropy_j_kgk=float(state["S"]),
            density_kg_m3=float(state["D"]),
            quality=float(state["Q"]),
        )


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
