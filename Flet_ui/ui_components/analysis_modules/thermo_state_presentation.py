"""把 :class:`~domain.state_points.ThermoStatePoint` 整理成結果文字與性質表列。

飽和性質與過熱度／過冷度判讀共用同一組性質（T、P、h、s、ρ、v）與格式，
確保文字結果與結構化性質表來自同一個狀態點、使用相同的單位與位數。
"""

from __future__ import annotations

from domain.state_points import ThermoStatePoint

from ...ui.structured_result import PropertyRow
from .result_formatting import ResultFormatter

# （顯示名稱, UnitConverter 性質代碼, 小數位數）
_STATE_PROPERTIES = (
    ("溫度", "T", 2),
    ("絕對壓力", "P", 2),
    ("比焓 h", "H", 2),
    ("比熵 s", "S", 4),
    ("密度 ρ", "D", 3),
    ("比容 v", "V", 5),
)


def _state_values(point: ThermoStatePoint) -> dict[str, float]:
    """回傳狀態點的 canonical SI 性質值。

參數：
    point: 狀態點。

回傳：
    以性質代碼為鍵的 SI 數值。"""
    return {
        "T": point.temperature_k,
        "P": point.pressure_pa,
        "H": point.enthalpy_j_kg,
        "S": point.entropy_j_kgk,
        "D": point.density_kg_m3,
        "V": point.specific_volume_m3_kg,
    }


def state_point_rows(formatter: ResultFormatter, point: ThermoStatePoint) -> tuple[PropertyRow, ...]:
    """把狀態點轉成性質表列（已換算為目前輸出單位）。

參數：
    formatter: 決定輸出單位系統的格式化器。
    point: 狀態點。

回傳：
    性質表列。"""
    values = _state_values(point)
    return tuple(
        PropertyRow(label, *formatter.parts(prop_code, values[prop_code], digits))
        for label, prop_code, digits in _STATE_PROPERTIES
    )


def add_state_point_lines(formatter: ResultFormatter, title: str, point: ThermoStatePoint) -> None:
    """在結果文字中加入一個狀態點分組。

參數：
    formatter: 結果格式化器。
    title: 分組標題。
    point: 狀態點。

回傳：
    無。"""
    values = _state_values(point)
    formatter.section(title)
    for label, prop_code, digits in _STATE_PROPERTIES:
        formatter.add(label, prop_code, values[prop_code], digits)
