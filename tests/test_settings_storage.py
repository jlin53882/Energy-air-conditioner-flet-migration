"""基礎 Settings 與 JSON 文件儲存的測試。"""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from application.settings import (
    SETTINGS_DOCUMENT_NAME,
    PressureBasis,
    SettingsService,
    WorkspaceSettings,
)
from domain.state_points import StateSource, ThermoStatePoint
from infrastructure.storage import JsonDocumentStore

ROOT = Path(__file__).resolve().parents[1]


# ======================================================
# WorkspaceSettings
# ======================================================
def test_default_settings_match_current_workspace_defaults() -> None:
    """預設設定與目前工作區的預設一致。

回傳：
    無。"""
    settings = WorkspaceSettings()

    assert settings.default_fluid == "R32"
    assert settings.default_reference_state == "Auto"
    assert settings.unit_system == "SI"
    assert settings.atmospheric_pressure_pa == pytest.approx(101_325.0)
    assert settings.altitude_m is None
    assert settings.pressure_basis is PressureBasis.ABSOLUTE


@pytest.mark.parametrize(
    ("value", "expected"),
    [("auto", "Auto"), ("Default", "DEF"), ("ashrae", "ASHRAE"), ("IIR", "IIR"), ("NBP", "NBP")],
)
def test_reference_state_choice_is_normalized(value, expected) -> None:
    """預設 Reference State 正規化為 Auto 或 canonical policy code。

參數：
    value: 輸入值。
    expected: 正規化結果。

回傳：
    無。"""
    assert WorkspaceSettings(default_reference_state=value).default_reference_state == expected


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"default_fluid": " "}, "預設流體"),
        ({"default_reference_state": "CURRENT"}, "CURRENT"),
        ({"default_reference_state": "XYZ"}, "Reference State"),
        ({"unit_system": "metric"}, "單位系統"),
        ({"atmospheric_pressure_pa": 0.0}, "大氣壓力"),
        ({"atmospheric_pressure_pa": float("inf")}, "大氣壓力"),
        ({"altitude_m": float("nan")}, "海拔"),
        ({"pressure_basis": "psig"}, "壓力基準"),
    ],
)
def test_invalid_settings_fail_explicitly(overrides, message) -> None:
    """無效設定明確失敗並指出欄位。

參數：
    overrides: 要替換成無效值的欄位。
    message: 錯誤訊息應包含的文字。

回傳：
    無。"""
    with pytest.raises(ValueError, match=message):
        replace(WorkspaceSettings(), **overrides)


def test_settings_round_trip_through_dict() -> None:
    """設定可經 to_dict／from_dict 往返，並帶 schema 標記。

回傳：
    無。"""
    settings = WorkspaceSettings(
        default_fluid="R134a", default_reference_state="IIR", unit_system="Imperial",
        atmospheric_pressure_pa=89_874.5, altitude_m=1000.0, pressure_basis="gauge",
    )

    document = settings.to_dict()

    assert document["schema"] == "workspace_settings"
    assert document["schema_version"] == 1
    assert document["pressure_basis"] == "gauge"
    assert WorkspaceSettings.from_dict(json.loads(json.dumps(document, allow_nan=False))) == settings


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda doc: doc.update(schema_version=2), "較新的版本"),
        (lambda doc: doc.update(schema="thermo_state_point"), "文件種類不符"),
        (lambda doc: doc.pop("unit_system"), "缺少欄位"),
        (lambda doc: doc.update(theme="dark"), "未知欄位"),
        (lambda doc: doc.update(unit_system="metric"), "單位系統"),
    ],
)
def test_invalid_settings_documents_fail_explicitly(mutate, message) -> None:
    """版本、種類、欄位不符或內容無效的設定文件明確失敗。

參數：
    mutate: 修改文件的函式。
    message: 錯誤訊息應包含的文字。

回傳：
    無。"""
    document = WorkspaceSettings().to_dict()
    mutate(document)
    with pytest.raises(ValueError, match=message):
        WorkspaceSettings.from_dict(document)


# ======================================================
# JsonDocumentStore
# ======================================================
def test_store_returns_none_for_missing_document_without_creating_folder(tmp_path) -> None:
    """文件不存在時回傳 None，且讀取不會建立資料夾。

參數：
    tmp_path: pytest 暫存資料夾。

回傳：
    無。"""
    root = tmp_path / "data"
    store = JsonDocumentStore(root)

    assert store.read("settings") is None
    assert not root.exists()


def test_store_write_read_round_trip_is_atomic(tmp_path) -> None:
    """寫入後可讀回相同內容，資料夾中只留下目標檔（沒有暫存檔）。

參數：
    tmp_path: pytest 暫存資料夾。

回傳：
    無。"""
    store = JsonDocumentStore(tmp_path / "data")
    document = {"schema": "x", "schema_version": 1, "名稱": "冷媒", "values": [1.5, 2]}

    store.write("state-library_1", document)
    store.write("state-library_1", {**document, "values": [3]})

    assert store.read("state-library_1") == {**document, "values": [3]}
    assert sorted(path.name for path in (tmp_path / "data").iterdir()) == ["state-library_1.json"]
    assert "冷媒" in (tmp_path / "data" / "state-library_1.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["../settings", "Settings", "a/b", "", "a b", "x" * 65, ".hidden"])
def test_store_rejects_unsafe_document_names(tmp_path, name) -> None:
    """文件名稱只允許小寫英數、底線與連字號，拒絕路徑穿越。

參數：
    tmp_path: pytest 暫存資料夾。
    name: 不合法名稱。

回傳：
    無。"""
    store = JsonDocumentStore(tmp_path)
    with pytest.raises(ValueError, match="不合法的文件名稱"):
        store.read(name)
    with pytest.raises(ValueError, match="不合法的文件名稱"):
        store.write(name, {})


def test_store_rejects_non_standard_json_and_leaves_no_file(tmp_path) -> None:
    """含 NaN 或無法序列化的內容不寫入，也不留下暫存檔。

參數：
    tmp_path: pytest 暫存資料夾。

回傳：
    無。"""
    store = JsonDocumentStore(tmp_path)

    for value in (float("nan"), float("inf"), float("-inf"), object()):
        with pytest.raises(ValueError, match="標準 JSON"):
            store.write("bad", {"value": value})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(("content", "message"), [("{not json", "標準 JSON"), ("[1, 2]", "JSON 物件")])
def test_store_reports_corrupt_files(tmp_path, content, message) -> None:
    """損壞或最外層不是物件的檔案明確失敗並指出檔案。

參數：
    tmp_path: pytest 暫存資料夾。
    content: 檔案內容。
    message: 錯誤訊息應包含的文字。

回傳：
    無。"""
    (tmp_path / "settings.json").write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        JsonDocumentStore(tmp_path).read("settings")


@pytest.mark.parametrize(
    "content",
    ['{"value": NaN}', '{"value": Infinity}', '{"value": -Infinity}', '{"nested": [1, {"x": NaN}]}'],
)
def test_store_rejects_non_standard_json_constants_on_read(tmp_path, content) -> None:
    """讀取也只接受標準 JSON：NaN／Infinity 以 ValueError 拒絕，與寫入契約一致。

參數：
    tmp_path: pytest 暫存資料夾。
    content: 含非標準常數的檔案內容。

回傳：
    無。"""
    (tmp_path / "settings.json").write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="標準 JSON") as error:
        JsonDocumentStore(tmp_path).read("settings")
    assert type(error.value) is ValueError


def test_store_reports_non_utf8_file_as_value_error(tmp_path) -> None:
    """不是 UTF-8 的檔案同樣以 ValueError 回報，不讓解碼細節傳到上層。

參數：
    tmp_path: pytest 暫存資料夾。

回傳：
    無。"""
    (tmp_path / "settings.json").write_bytes('{"名稱": "冷媒"}'.encode("big5"))
    with pytest.raises(ValueError, match="UTF-8") as error:
        JsonDocumentStore(tmp_path).read("settings")
    assert type(error.value) is ValueError


def test_store_reads_standard_json_numbers(tmp_path) -> None:
    """標準 JSON 的數值（含小數、指數與負數）照常讀取。

參數：
    tmp_path: pytest 暫存資料夾。

回傳：
    無。"""
    (tmp_path / "settings.json").write_text('{"value": 1.5, "big": 1e300, "neg": -2}', encoding="utf-8")

    assert JsonDocumentStore(tmp_path).read("settings") == {"value": 1.5, "big": 1e300, "neg": -2}


def test_state_point_documents_can_be_stored(tmp_path) -> None:
    """狀態點文件可經 JSON 儲存往返。

參數：
    tmp_path: pytest 暫存資料夾。

回傳：
    無。"""
    store = JsonDocumentStore(tmp_path)
    point = ThermoStatePoint(
        fluid="R32", reference_state="ASHRAE", pressure_pa=1e6, temperature_k=330.0,
        enthalpy_j_kg=450_000.0, entropy_j_kgk=1_800.0, density_kg_m3=30.0, quality=-1.0,
        source=StateSource.MANUAL, label="A",
    )

    store.write("state-a", point.to_dict())

    assert ThermoStatePoint.from_dict(store.read("state-a")) == point


# ======================================================
# SettingsService
# ======================================================
def test_settings_service_loads_defaults_then_persists(tmp_path) -> None:
    """尚未保存時讀到預設值；保存後以新的服務實例讀回相同設定。

參數：
    tmp_path: pytest 暫存資料夾。

回傳：
    無。"""
    store = JsonDocumentStore(tmp_path)
    service = SettingsService(store)
    assert service.load() == WorkspaceSettings()

    changed = replace(WorkspaceSettings(), unit_system="Imperial", pressure_basis=PressureBasis.GAUGE)
    service.save(changed)

    assert SettingsService(JsonDocumentStore(tmp_path)).load() == changed
    assert store.path_for(SETTINGS_DOCUMENT_NAME).exists()


def test_settings_service_does_not_silently_replace_invalid_file(tmp_path) -> None:
    """已保存的設定無效時明確失敗，不改用預設值覆蓋使用者的檔案。

參數：
    tmp_path: pytest 暫存資料夾。

回傳：
    無。"""
    store = JsonDocumentStore(tmp_path)
    newer = {**WorkspaceSettings().to_dict(), "schema_version": 2}
    store.write(SETTINGS_DOCUMENT_NAME, newer)

    with pytest.raises(ValueError, match="較新的版本"):
        SettingsService(store).load()
    assert store.read(SETTINGS_DOCUMENT_NAME) == newer


# ======================================================
# 相依方向
# ======================================================
def _imported_modules(path: Path) -> set[str]:
    """回傳 Python 檔案匯入的模組名稱。

參數：
    path: 原始碼路徑。

回傳：
    模組名稱集合。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("layer", ["domain", "application"])
def test_domain_and_application_do_not_import_infrastructure(layer) -> None:
    """domain 與 application 不得匯入 infrastructure；儲存實作由組合根注入。

參數：
    layer: 要檢查的層。

回傳：
    無。"""
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / layer).rglob("*.py")
        if any(module.split(".")[0] == "infrastructure" for module in _imported_modules(path))
    ]
    assert offenders == []
