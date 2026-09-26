"""冷媒與濕空氣狀態點模型、基準防護與序列化。"""

from __future__ import annotations

from collections.abc import Mapping

from domain.schema import SCHEMA_KEY

from .air import AIR_STATE_POINT_SCHEMA, AirStatePoint
from .base import StateBasisMismatchError, StatePoint, StateSource
from .thermo import (
    THERMO_STATE_POINT_SCHEMA,
    StatePhase,
    ThermoStatePoint,
    enthalpy_difference,
    entropy_difference,
    require_same_basis,
)


def state_point_from_dict(data: object) -> ThermoStatePoint | AirStatePoint:
    """依文件的 ``schema`` 種類還原對應的狀態點。

參數：
    data: :meth:`ThermoStatePoint.to_dict` 或 :meth:`AirStatePoint.to_dict` 產生的 dict。

回傳：
    ThermoStatePoint 或 AirStatePoint。

引發：
    ValueError：不是 mapping、種類未知或內容無效時。"""
    kind = data.get(SCHEMA_KEY) if isinstance(data, Mapping) else None
    if kind == THERMO_STATE_POINT_SCHEMA:
        return ThermoStatePoint.from_dict(data)
    if kind == AIR_STATE_POINT_SCHEMA:
        return AirStatePoint.from_dict(data)
    raise ValueError(f"未知的狀態點文件種類：{kind!r}。")


__all__ = [
    "AirStatePoint",
    "StateBasisMismatchError",
    "StatePhase",
    "StatePoint",
    "StateSource",
    "ThermoStatePoint",
    "enthalpy_difference",
    "entropy_difference",
    "require_same_basis",
    "state_point_from_dict",
]
