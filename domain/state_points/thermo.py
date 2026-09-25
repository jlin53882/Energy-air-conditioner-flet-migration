"""冷媒／工作流體的熱力狀態點（canonical SI）。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from domain.schema import document_payload, require_exact_fields, versioned_document
from domain.thermodynamics.reference_state import ReferenceStatePolicy, normalize_reference_state_policy

from .base import (
    StateBasisMismatchError,
    StateSource,
    finite_float,
    parse_source,
    positive_float,
    text,
)

THERMO_STATE_POINT_SCHEMA = "thermo_state_point"
THERMO_STATE_POINT_VERSION = 1

_FIELDS = {
    "fluid", "reference_state", "pressure_pa", "temperature_k", "enthalpy_j_kg", "entropy_j_kgk",
    "density_kg_m3", "quality", "source", "is_ideal_gas", "key", "label",
}


class StatePhase(str, Enum):
    """由乾度推導的相態分類。"""

    SATURATED_LIQUID = "saturated_liquid"
    SATURATED_VAPOR = "saturated_vapor"
    TWO_PHASE = "two_phase"
    SINGLE_PHASE = "single_phase"


@dataclass(frozen=True)
class ThermoStatePoint:
    """一個工作流體狀態點。

    焓與熵的數值取決於 ``reference_state``，因此不同流體、不同 reference state 或不同
    性質模型（CoolProp／理想氣體）的狀態點不得直接相減；請使用 :func:`enthalpy_difference`
    與 :func:`entropy_difference`，它們會先檢查基準是否相同。

    屬性：
        fluid: 流體名稱（例如 ``R32``）。
        reference_state: 求解時實際使用的 policy code（``DEF``、``ASHRAE``、``IIR``、``NBP``）；
            不接受 ``Auto`` 或 ``CURRENT``，必須是已解析的明確基準。
        pressure_pa: 絕對壓力（Pa）。
        temperature_k: 溫度（K）。
        enthalpy_j_kg: 比焓（J/kg）。
        entropy_j_kgk: 比熵（J/(kg·K)）；理想氣體模型不提供（值為 0）。
        density_kg_m3: 密度（kg/m³）。
        quality: 乾度；CoolProp 以 -1 表示單相。
        source: 產生此狀態點的工具。
        is_ideal_gas: 是否由理想氣體模型計算。
        key: 所屬計算中的穩定鍵，例如循環的 ``"1"``、``"2s"``；可為空字串。
        label: 顯示用名稱；可為空字串。
    """

    fluid: str
    reference_state: str
    pressure_pa: float
    temperature_k: float
    enthalpy_j_kg: float
    entropy_j_kgk: float
    density_kg_m3: float
    quality: float
    source: StateSource
    is_ideal_gas: bool = False
    key: str = ""
    label: str = ""

    def __post_init__(self) -> None:
        """驗證並正規化欄位。

回傳：
    無。

引發：
    ValueError：流體空白、reference state 不是明確基準、數值無效或來源未知時。"""
        fluid = text("流體名稱", self.fluid).strip()
        if not fluid:
            raise ValueError("狀態點必須指定流體名稱。")
        reference_state = self._explicit_reference_state(self.reference_state)
        if not isinstance(self.is_ideal_gas, bool):
            raise ValueError("is_ideal_gas 必須是布林值。")
        values = {
            "fluid": fluid,
            "reference_state": reference_state,
            "pressure_pa": positive_float("壓力", self.pressure_pa),
            "temperature_k": positive_float("溫度", self.temperature_k),
            "enthalpy_j_kg": finite_float("比焓", self.enthalpy_j_kg),
            "entropy_j_kgk": finite_float("比熵", self.entropy_j_kgk),
            "density_kg_m3": positive_float("密度", self.density_kg_m3),
            "quality": finite_float("乾度", self.quality),
            "source": parse_source(self.source),
            "key": text("狀態鍵", self.key),
            "label": text("顯示名稱", self.label),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @staticmethod
    def _explicit_reference_state(policy: object) -> str:
        """將 reference state 正規化為明確的 policy code。

參數：
    policy: 列舉或 policy code。

回傳：
    canonical policy code。

引發：
    ValueError：不是支援的明確基準（含 ``Auto``、``CURRENT``）時。"""
        if not isinstance(policy, (str, ReferenceStatePolicy)):
            raise ValueError("reference_state 必須是 policy code。")
        try:
            normalized = normalize_reference_state_policy(policy)
        except ValueError:
            raise ValueError(f"狀態點的 reference_state 必須是明確基準（目前為 {policy!r}）。") from None
        if normalized == ReferenceStatePolicy.CURRENT.value:
            raise ValueError("狀態點不得使用 CURRENT，必須記錄求解時實際使用的基準。")
        return normalized

    @classmethod
    def from_state_mapping(
        cls,
        state: Mapping[str, float | str],
        *,
        fluid: str,
        reference_state: ReferenceStatePolicy | str,
        source: StateSource | str,
        key: str = "",
        label: str = "",
        is_ideal_gas: bool = False,
    ) -> "ThermoStatePoint":
        """由 ``ThermodynamicStateService`` 回傳的 canonical SI dict 建立狀態點。

參數：
    state: 含 ``P``、``T``、``H``、``S``、``D``、``Q`` 的狀態 dict。
    fluid: 流體名稱。
    reference_state: 求解時實際使用的 policy。
    source: 產生此狀態點的工具。
    key: 所屬計算中的穩定鍵。
    label: 顯示用名稱。
    is_ideal_gas: 是否由理想氣體模型計算。

回傳：
    ThermoStatePoint。

引發：
    ValueError：缺少性質或數值無效時。"""
        try:
            return cls(
                fluid=fluid,
                reference_state=reference_state,
                pressure_pa=state["P"],
                temperature_k=state["T"],
                enthalpy_j_kg=state["H"],
                entropy_j_kgk=state["S"],
                density_kg_m3=state["D"],
                quality=state["Q"],
                source=source,
                is_ideal_gas=is_ideal_gas,
                key=key,
                label=label,
            )
        except KeyError as exc:
            raise ValueError(f"狀態資料缺少性質 {exc.args[0]}。") from None

    @property
    def specific_volume_m3_kg(self) -> float:
        """比容（m³/kg），由密度推導。

回傳：
    1 / density。"""
        return 1.0 / self.density_kg_m3

    @property
    def phase(self) -> StatePhase:
        """由乾度推導的相態分類。

乾度 0 為飽和液、1 為飽和蒸氣、介於兩者之間為兩相；其他值（CoolProp 以 -1 表示
過冷液、過熱蒸氣或超臨界）一律視為單相。

回傳：
    StatePhase。"""
        if self.quality == 0.0:
            return StatePhase.SATURATED_LIQUID
        if self.quality == 1.0:
            return StatePhase.SATURATED_VAPOR
        if 0.0 < self.quality < 1.0:
            return StatePhase.TWO_PHASE
        return StatePhase.SINGLE_PHASE

    def is_same_basis(self, other: "ThermoStatePoint") -> bool:
        """回傳兩個狀態點的焓、熵是否以相同基準表示，可以直接相減。

參數：
    other: 另一個狀態點。

回傳：
    流體（不分大小寫）、reference state 與性質模型皆相同時為 True。"""
        return (
            self.fluid.casefold() == other.fluid.casefold()
            and self.reference_state == other.reference_state
            and self.is_ideal_gas == other.is_ideal_gas
        )

    def to_dict(self) -> dict[str, object]:
        """回傳含 schema 標記、可保存為 JSON 的 dict。

回傳：
    dict。"""
        return versioned_document(THERMO_STATE_POINT_SCHEMA, THERMO_STATE_POINT_VERSION, {
            "fluid": self.fluid,
            "reference_state": self.reference_state,
            "pressure_pa": self.pressure_pa,
            "temperature_k": self.temperature_k,
            "enthalpy_j_kg": self.enthalpy_j_kg,
            "entropy_j_kgk": self.entropy_j_kgk,
            "density_kg_m3": self.density_kg_m3,
            "quality": self.quality,
            "source": self.source.value,
            "is_ideal_gas": self.is_ideal_gas,
            "key": self.key,
            "label": self.label,
        })

    @classmethod
    def from_dict(cls, data: object) -> "ThermoStatePoint":
        """由 :meth:`to_dict` 產生的 dict 還原狀態點。

參數：
    data: 文件 dict。

回傳：
    ThermoStatePoint。

引發：
    ValueError：schema 種類或版本不符、欄位缺漏或多出、數值無效時。"""
        payload = document_payload(data, kind=THERMO_STATE_POINT_SCHEMA, version=THERMO_STATE_POINT_VERSION)
        require_exact_fields(payload, _FIELDS, kind=THERMO_STATE_POINT_SCHEMA)
        return cls(**payload)  # type: ignore[arg-type]


def require_same_basis(first: ThermoStatePoint, second: ThermoStatePoint) -> None:
    """確認兩個狀態點可以直接比較或相減。

參數：
    first: 第一個狀態點。
    second: 第二個狀態點。

回傳：
    無。

引發：
    StateBasisMismatchError：流體、reference state 或性質模型不同時。"""
    if not first.is_same_basis(second):
        raise StateBasisMismatchError(
            "狀態點基準不同，不能直接比較或相減："
            f"{first.fluid}／{first.reference_state}{'／理想氣體' if first.is_ideal_gas else ''} 與 "
            f"{second.fluid}／{second.reference_state}{'／理想氣體' if second.is_ideal_gas else ''}。"
        )


def enthalpy_difference(first: ThermoStatePoint, second: ThermoStatePoint) -> float:
    """回傳比焓差 ``first.h − second.h``（J/kg），先確認兩者基準相同。

參數：
    first: 被減數狀態點。
    second: 減數狀態點。

回傳：
    比焓差。

引發：
    StateBasisMismatchError：基準不同時。"""
    require_same_basis(first, second)
    return first.enthalpy_j_kg - second.enthalpy_j_kg


def entropy_difference(first: ThermoStatePoint, second: ThermoStatePoint) -> float:
    """回傳比熵差 ``first.s − second.s``（J/(kg·K)），先確認兩者基準相同。

參數：
    first: 被減數狀態點。
    second: 減數狀態點。

回傳：
    比熵差。

引發：
    StateBasisMismatchError：基準不同時。
    ValueError：理想氣體模型未提供比熵時。"""
    require_same_basis(first, second)
    if first.is_ideal_gas:
        raise ValueError("理想氣體模型未提供比熵，不能計算熵差。")
    return first.entropy_j_kgk - second.entropy_j_kgk
