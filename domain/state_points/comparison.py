"""兩個狀態點（A、B）的性質比較，差值一律為 B − A（canonical SI）。

冷媒狀態點的焓、熵差值經基準防護：流體、reference state 或性質模型不同時不相減，
只列出兩邊數值並說明原因。溫度、壓力、密度等與基準無關的性質照常相減。
冷媒與濕空氣狀態點是不同型別，不能互相比較。
"""

from __future__ import annotations

from dataclasses import dataclass

from .air import AirStatePoint
from .base import StateBasisMismatchError
from .thermo import COOLPROP_SINGLE_PHASE_QUALITY, ThermoStatePoint, enthalpy_difference, entropy_difference

BASIS_MISMATCH_NOTE = "基準不同（流體、Reference State 或性質模型），不相減"
IDEAL_GAS_ENTROPY_NOTE = "理想氣體模型未提供比熵"
SINGLE_PHASE_QUALITY_NOTE = "單相狀態沒有乾度"


@dataclass(frozen=True)
class PropertyComparison:
    """一列性質比較。

    屬性：
        key: 穩定鍵。
        label: 顯示名稱。
        prop_code: UnitConverter 性質代碼（顯示時換算單位用）；無因次量為 ``"-"``。
        a: A 的 SI 數值；不適用時為 None。
        b: B 的 SI 數值；不適用時為 None。
        difference: B − A；不能相減時為 None。
        note: 不能相減或不適用的原因；可為空字串。
    """

    key: str
    label: str
    prop_code: str
    a: float | None
    b: float | None
    difference: float | None
    note: str = ""


@dataclass(frozen=True)
class StateComparison:
    """兩個狀態點的比較結果。

    屬性：
        kind: ``thermo`` 或 ``air``。
        rows: 各性質的比較列。
        same_basis: 冷媒狀態點的焓、熵是否可以相減；濕空氣固定為 True。
        basis_note: 基準說明（例如兩邊的流體與 reference state）。
    """

    kind: str
    rows: tuple[PropertyComparison, ...]
    same_basis: bool
    basis_note: str


def _plain(key: str, label: str, prop_code: str, a: float, b: float) -> PropertyComparison:
    """建立與基準無關、可直接相減的比較列。

參數：
    key: 穩定鍵。
    label: 顯示名稱。
    prop_code: 性質代碼。
    a: A 的值。
    b: B 的值。

回傳：
    PropertyComparison。"""
    return PropertyComparison(key, label, prop_code, a, b, b - a)


def _basis_label(point: ThermoStatePoint) -> str:
    """回傳冷媒狀態點的基準說明。

參數：
    point: 狀態點。

回傳：
    例如 ``R32／ASHRAE`` 或 ``Water／DEF／理想氣體``。"""
    suffix = "／理想氣體" if point.is_ideal_gas else ""
    return f"{point.fluid}／{point.reference_state}{suffix}"


def _compare_thermo(a: ThermoStatePoint, b: ThermoStatePoint) -> StateComparison:
    """比較兩個冷媒狀態點。

參數：
    a: 狀態 A。
    b: 狀態 B。

回傳：
    StateComparison。"""
    same_basis = a.is_same_basis(b)
    if same_basis:
        enthalpy = PropertyComparison("h", "比焓 h", "H", a.enthalpy_j_kg, b.enthalpy_j_kg,
                                      enthalpy_difference(b, a))
    else:
        enthalpy = PropertyComparison("h", "比焓 h", "H", a.enthalpy_j_kg, b.enthalpy_j_kg, None,
                                      BASIS_MISMATCH_NOTE)
    if a.is_ideal_gas or b.is_ideal_gas:
        entropy = PropertyComparison(
            "s", "比熵 s", "S",
            None if a.is_ideal_gas else a.entropy_j_kgk,
            None if b.is_ideal_gas else b.entropy_j_kgk,
            None, IDEAL_GAS_ENTROPY_NOTE,
        )
    elif same_basis:
        entropy = PropertyComparison("s", "比熵 s", "S", a.entropy_j_kgk, b.entropy_j_kgk,
                                     entropy_difference(b, a))
    else:
        entropy = PropertyComparison("s", "比熵 s", "S", a.entropy_j_kgk, b.entropy_j_kgk, None,
                                     BASIS_MISMATCH_NOTE)

    def quality(point: ThermoStatePoint) -> float | None:
        """回傳兩相乾度；單相標記 -1 時為 None。

參數：
    point: 狀態點。

回傳：
    乾度或 None。"""
        return None if point.quality == COOLPROP_SINGLE_PHASE_QUALITY else point.quality

    qa, qb = quality(a), quality(b)
    if qa is not None and qb is not None:
        quality_row = PropertyComparison("q", "乾度 Q", "-", qa, qb, qb - qa)
    else:
        quality_row = PropertyComparison("q", "乾度 Q", "-", qa, qb, None, SINGLE_PHASE_QUALITY_NOTE)

    rows = (
        _plain("t", "溫度", "T", a.temperature_k, b.temperature_k),
        _plain("p", "絕對壓力", "P", a.pressure_pa, b.pressure_pa),
        enthalpy,
        entropy,
        _plain("d", "密度 ρ", "D", a.density_kg_m3, b.density_kg_m3),
        _plain("v", "比容 v", "V", a.specific_volume_m3_kg, b.specific_volume_m3_kg),
        quality_row,
    )
    if same_basis:
        note = f"同一基準：{_basis_label(a)}"
    else:
        note = f"A：{_basis_label(a)}；B：{_basis_label(b)}。{BASIS_MISMATCH_NOTE}。"
    return StateComparison("thermo", rows, same_basis, note)


def _compare_air(a: AirStatePoint, b: AirStatePoint) -> StateComparison:
    """比較兩個濕空氣狀態點（比焓、比容以每公斤乾空氣為基準，基準固定）。

參數：
    a: 狀態 A。
    b: 狀態 B。

回傳：
    StateComparison。"""
    rows = (
        _plain("tdb", "乾球溫度 Tdb", "T", a.dry_bulb_k, b.dry_bulb_k),
        _plain("twb", "濕球溫度 Twb", "T", a.wet_bulb_k, b.wet_bulb_k),
        _plain("tdp", "露點溫度 Tdp", "T", a.dew_point_k, b.dew_point_k),
        _plain("rh", "相對濕度 RH", "RH", a.relative_humidity, b.relative_humidity),
        _plain("w", "濕度比 W", "W", a.humidity_ratio_kg_kg, b.humidity_ratio_kg_kg),
        _plain("h", "比焓 h（每 kg 乾空氣）", "H", a.enthalpy_j_kg, b.enthalpy_j_kg),
        _plain("v", "比容 v（每 kg 乾空氣）", "V", a.specific_volume_m3_kg, b.specific_volume_m3_kg),
        _plain("p", "大氣壓力", "P", a.pressure_pa, b.pressure_pa),
        _plain("alt", "海拔", "L", a.altitude_m, b.altitude_m),
    )
    return StateComparison("air", rows, True, "濕空氣模型的固定基準")


def compare_states(
    a: ThermoStatePoint | AirStatePoint, b: ThermoStatePoint | AirStatePoint
) -> StateComparison:
    """比較兩個同種類的狀態點；差值為 B − A。

參數：
    a: 狀態 A。
    b: 狀態 B。

回傳：
    StateComparison。

引發：
    StateBasisMismatchError：一個是冷媒狀態、另一個是濕空氣狀態時。
    TypeError：不是支援的狀態點型別時。"""
    if isinstance(a, ThermoStatePoint) and isinstance(b, ThermoStatePoint):
        return _compare_thermo(a, b)
    if isinstance(a, AirStatePoint) and isinstance(b, AirStatePoint):
        return _compare_air(a, b)
    if isinstance(a, (ThermoStatePoint, AirStatePoint)) and isinstance(b, (ThermoStatePoint, AirStatePoint)):
        raise StateBasisMismatchError("冷媒狀態與濕空氣狀態是不同型別，不能互相比較。")
    raise TypeError("只能比較 ThermoStatePoint 或 AirStatePoint。")
