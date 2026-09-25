"""濕空氣狀態點（canonical SI）。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from domain.schema import document_payload, require_exact_fields, versioned_document

from .base import StateSource, finite_float, parse_source, positive_float, text

AIR_STATE_POINT_SCHEMA = "air_state_point"
AIR_STATE_POINT_VERSION = 1

_FIELDS = {
    "altitude_m", "pressure_pa", "dry_bulb_k", "wet_bulb_k", "dew_point_k", "relative_humidity",
    "humidity_ratio_kg_kg", "enthalpy_j_kg", "specific_volume_m3_kg", "source", "label",
}


@dataclass(frozen=True)
class AirStatePoint:
    """一個濕空氣狀態點；比焓與比容以每公斤乾空氣為基準。

    濕空氣性質使用濕空氣模型固定的基準，與冷媒的 reference state 無關，因此與
    :class:`~domain.state_points.thermo.ThermoStatePoint` 是不同型別，不能互相比較。

    屬性：
        altitude_m: 海拔（m），決定大氣壓力。
        pressure_pa: 大氣絕對壓力（Pa）。
        dry_bulb_k: 乾球溫度（K）。
        wet_bulb_k: 濕球溫度（K）。
        dew_point_k: 露點溫度（K）。
        relative_humidity: 相對濕度（0–1 的分率）。
        humidity_ratio_kg_kg: 濕度比（kg 水蒸氣／kg 乾空氣）。
        enthalpy_j_kg: 比焓（J/kg 乾空氣）。
        specific_volume_m3_kg: 比容（m³/kg 乾空氣）。
        source: 產生此狀態點的工具。
        label: 顯示用名稱；可為空字串。
    """

    altitude_m: float
    pressure_pa: float
    dry_bulb_k: float
    wet_bulb_k: float
    dew_point_k: float
    relative_humidity: float
    humidity_ratio_kg_kg: float
    enthalpy_j_kg: float
    specific_volume_m3_kg: float
    source: StateSource
    label: str = ""

    def __post_init__(self) -> None:
        """驗證並正規化欄位。

回傳：
    無。

引發：
    ValueError：數值無效、相對濕度不在 0–1、濕度比為負或來源未知時。"""
        relative_humidity = finite_float("相對濕度", self.relative_humidity)
        if not 0.0 <= relative_humidity <= 1.0:
            raise ValueError("相對濕度必須介於 0 與 1 之間（分率）。")
        humidity_ratio = finite_float("濕度比", self.humidity_ratio_kg_kg)
        if humidity_ratio < 0:
            raise ValueError("濕度比不可為負。")
        values = {
            "altitude_m": finite_float("海拔", self.altitude_m),
            "pressure_pa": positive_float("大氣壓力", self.pressure_pa),
            "dry_bulb_k": positive_float("乾球溫度", self.dry_bulb_k),
            "wet_bulb_k": positive_float("濕球溫度", self.wet_bulb_k),
            "dew_point_k": positive_float("露點溫度", self.dew_point_k),
            "relative_humidity": relative_humidity,
            "humidity_ratio_kg_kg": humidity_ratio,
            "enthalpy_j_kg": finite_float("比焓", self.enthalpy_j_kg),
            "specific_volume_m3_kg": positive_float("比容", self.specific_volume_m3_kg),
            "source": parse_source(self.source),
            "label": text("顯示名稱", self.label),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @classmethod
    def from_state_mapping(
        cls, state: Mapping[str, object], *, source: StateSource | str, label: str = ""
    ) -> "AirStatePoint":
        """由 ``PsychrometricService`` 回傳的中立結果 dict 建立狀態點。

參數：
    state: 含 ``Altitude``、``P``、``Tdb``、``Twb``、``Tdp``、``RH``、``W``、``H``、``V`` 的 dict。
    source: 產生此狀態點的工具。
    label: 顯示用名稱。

回傳：
    AirStatePoint。

引發：
    ValueError：缺少性質或數值無效時。"""
        try:
            return cls(
                altitude_m=state["Altitude"],
                pressure_pa=state["P"],
                dry_bulb_k=state["Tdb"],
                wet_bulb_k=state["Twb"],
                dew_point_k=state["Tdp"],
                relative_humidity=state["RH"],
                humidity_ratio_kg_kg=state["W"],
                enthalpy_j_kg=state["H"],
                specific_volume_m3_kg=state["V"],
                source=source,
                label=label,
            )
        except KeyError as exc:
            raise ValueError(f"濕空氣狀態資料缺少性質 {exc.args[0]}。") from None

    def to_dict(self) -> dict[str, object]:
        """回傳含 schema 標記、可保存為 JSON 的 dict。

回傳：
    dict。"""
        return versioned_document(AIR_STATE_POINT_SCHEMA, AIR_STATE_POINT_VERSION, {
            "altitude_m": self.altitude_m,
            "pressure_pa": self.pressure_pa,
            "dry_bulb_k": self.dry_bulb_k,
            "wet_bulb_k": self.wet_bulb_k,
            "dew_point_k": self.dew_point_k,
            "relative_humidity": self.relative_humidity,
            "humidity_ratio_kg_kg": self.humidity_ratio_kg_kg,
            "enthalpy_j_kg": self.enthalpy_j_kg,
            "specific_volume_m3_kg": self.specific_volume_m3_kg,
            "source": self.source.value,
            "label": self.label,
        })

    @classmethod
    def from_dict(cls, data: object) -> "AirStatePoint":
        """由 :meth:`to_dict` 產生的 dict 還原狀態點。

參數：
    data: 文件 dict。

回傳：
    AirStatePoint。

引發：
    ValueError：schema 種類或版本不符、欄位缺漏或多出、數值無效時。"""
        payload = document_payload(data, kind=AIR_STATE_POINT_SCHEMA, version=AIR_STATE_POINT_VERSION)
        require_exact_fields(payload, _FIELDS, kind=AIR_STATE_POINT_SCHEMA)
        return cls(**payload)  # type: ignore[arg-type]
