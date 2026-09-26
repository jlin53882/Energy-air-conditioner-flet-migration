"""工作區基礎設定與其保存服務。

設定只保存各工具開啟時的預設值；各頁面仍可各自調整（例如各頁自己的 Reference State），
設定不會覆寫頁面上已輸入的值。保存格式由具體的 :class:`DocumentStore` 實作決定，
由組合根注入；application 不直接依賴檔案系統。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import Enum
from typing import Protocol

from domain.schema import document_payload, require_exact_fields, versioned_document
from domain.state_points.base import finite_float, positive_float, text
from domain.thermodynamics.reference_state import ReferenceStatePolicy, normalize_reference_state_policy

SETTINGS_DOCUMENT_NAME = "settings"
SETTINGS_SCHEMA = "workspace_settings"
SETTINGS_VERSION = 1

STANDARD_ATMOSPHERE_PA = 101_325.0
UNIT_SYSTEMS = ("SI", "Imperial")
AUTO_REFERENCE_STATE = "Auto"


class PressureBasis(str, Enum):
    """壓力輸入預設使用的基準。"""

    GAUGE = "gauge"
    ABSOLUTE = "absolute"


class DocumentStore(Protocol):
    """以名稱讀寫 JSON 相容文件的儲存介面（由 infrastructure 實作）。"""

    def read(self, name: str) -> Mapping[str, object] | None:
        """讀取文件；不存在時回傳 None。"""

    def write(self, name: str, document: Mapping[str, object]) -> None:
        """寫入（覆蓋）文件。"""


def _reference_state_choice(value: object) -> str:
    """將預設 Reference State 正規化為 ``Auto`` 或明確的 policy code。

參數：
    value: ``Auto``（不分大小寫）或 policy code／別名。

回傳：
    ``Auto``、``DEF``、``ASHRAE``、``IIR`` 或 ``NBP``。

引發：
    ValueError：不是支援的選項（含 ``CURRENT``）時。"""
    choice = text("預設 Reference State", value).strip()
    if choice.casefold() == AUTO_REFERENCE_STATE.casefold():
        return AUTO_REFERENCE_STATE
    try:
        normalized = normalize_reference_state_policy(choice)
    except ValueError:
        raise ValueError(f"不支援的預設 Reference State：{value!r}。") from None
    if normalized == ReferenceStatePolicy.CURRENT.value:
        raise ValueError("預設 Reference State 不得為 CURRENT。")
    return normalized


@dataclass(frozen=True)
class WorkspaceSettings:
    """工作區基礎設定。

    屬性：
        default_fluid: 冷媒工具的預設流體。
        default_reference_state: 分析頁 Reference State 選單的預設值（``Auto`` 或 policy code）。
        unit_system: 輸出單位系統（``SI`` 或 ``Imperial``）。
        atmospheric_pressure_pa: 錶壓換算用的大氣絕對壓力（Pa）。
        altitude_m: 選填的海拔（m）；大氣壓力由頁面依海拔換算後保存於
            ``atmospheric_pressure_pa``，設定本身不重新計算。
        pressure_basis: 壓力輸入預設使用錶壓或絕對壓。
    """

    default_fluid: str = "R32"
    default_reference_state: str = AUTO_REFERENCE_STATE
    unit_system: str = "SI"
    atmospheric_pressure_pa: float = STANDARD_ATMOSPHERE_PA
    altitude_m: float | None = None
    pressure_basis: PressureBasis = PressureBasis.ABSOLUTE

    def __post_init__(self) -> None:
        """驗證並正規化欄位。

回傳：
    無。

引發：
    ValueError：任一欄位無效時。"""
        fluid = text("預設流體", self.default_fluid).strip()
        if not fluid:
            raise ValueError("預設流體不可空白。")
        unit_system = text("單位系統", self.unit_system)
        if unit_system not in UNIT_SYSTEMS:
            raise ValueError(f"不支援的單位系統：{unit_system!r}（可用：{', '.join(UNIT_SYSTEMS)}）。")
        try:
            pressure_basis = PressureBasis(self.pressure_basis)
        except ValueError:
            raise ValueError(f"不支援的壓力基準：{self.pressure_basis!r}。") from None
        values = {
            "default_fluid": fluid,
            "default_reference_state": _reference_state_choice(self.default_reference_state),
            "unit_system": unit_system,
            "atmospheric_pressure_pa": positive_float("大氣壓力", self.atmospheric_pressure_pa),
            "altitude_m": None if self.altitude_m is None else finite_float("海拔", self.altitude_m),
            "pressure_basis": pressure_basis,
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, object]:
        """回傳含 schema 標記、可保存為 JSON 的 dict。

回傳：
    dict。"""
        return versioned_document(SETTINGS_SCHEMA, SETTINGS_VERSION, {
            "default_fluid": self.default_fluid,
            "default_reference_state": self.default_reference_state,
            "unit_system": self.unit_system,
            "atmospheric_pressure_pa": self.atmospheric_pressure_pa,
            "altitude_m": self.altitude_m,
            "pressure_basis": self.pressure_basis.value,
        })

    @classmethod
    def from_dict(cls, data: object) -> "WorkspaceSettings":
        """由 :meth:`to_dict` 產生的 dict 還原設定。

參數：
    data: 文件 dict。

回傳：
    WorkspaceSettings。

引發：
    ValueError：schema 種類或版本不符、欄位缺漏或多出、數值無效時。"""
        payload = document_payload(data, kind=SETTINGS_SCHEMA, version=SETTINGS_VERSION)
        require_exact_fields(payload, {field.name for field in fields(cls)}, kind=SETTINGS_SCHEMA)
        return cls(**payload)  # type: ignore[arg-type]


class SettingsService:
    """讀取與保存工作區設定。"""

    def __init__(self, store: DocumentStore) -> None:
        """以注入的文件儲存建立服務。

參數：
    store: 文件儲存實作。

回傳：
    無。"""
        self._store = store

    def load(self) -> WorkspaceSettings:
        """讀取設定；尚未保存過時回傳預設值。

回傳：
    WorkspaceSettings。

引發：
    ValueError：已保存的設定內容無效或版本不符時（不默默改用預設值，避免覆蓋使用者的檔案）。"""
        document = self._store.read(SETTINGS_DOCUMENT_NAME)
        if document is None:
            return WorkspaceSettings()
        return WorkspaceSettings.from_dict(document)

    def save(self, settings: WorkspaceSettings) -> None:
        """保存設定。

參數：
    settings: 要保存的設定。

回傳：
    無。"""
        self._store.write(SETTINGS_DOCUMENT_NAME, settings.to_dict())
