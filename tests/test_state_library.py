"""State Library：domain 模型、狀態比較、application service、儲存位置與工作區畫面。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt
import pytest

from application.state_library import STATE_LIBRARY_DOCUMENT_NAME, StateLibraryService
from domain.state_library import (
    COPY_SUFFIX,
    MAX_NAME_LENGTH,
    SavedState,
    StateLibrary,
    default_state_name,
)
from domain.state_points import (
    AirStatePoint,
    StateBasisMismatchError,
    StateSource,
    ThermoStatePoint,
    compare_states,
    enthalpy_difference,
    entropy_difference,
)
from domain.state_points.comparison import (
    BASIS_MISMATCH_NOTE,
    IDEAL_GAS_ENTROPY_NOTE,
    SINGLE_PHASE_QUALITY_NOTE,
)
from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui.navigation import ROUTES
from infrastructure.storage import WORKSPACE_DIR_ENV, JsonDocumentStore, workspace_directory


def _thermo(**overrides) -> ThermoStatePoint:
    """建立冷媒狀態點。

參數：
    overrides: 要覆寫的欄位。

回傳：
    ThermoStatePoint。"""
    values = dict(
        fluid="R32", reference_state="ASHRAE", pressure_pa=1_000_000.0, temperature_k=280.0,
        enthalpy_j_kg=400_000.0, entropy_j_kgk=1_700.0, density_kg_m3=30.0, quality=-1.0,
        source=StateSource.MANUAL, label="A",
    )
    values.update(overrides)
    return ThermoStatePoint(**values)


def _air(**overrides) -> AirStatePoint:
    """建立濕空氣狀態點。

參數：
    overrides: 要覆寫的欄位。

回傳：
    AirStatePoint。"""
    values = dict(
        altitude_m=0.0, pressure_pa=101_325.0, dry_bulb_k=298.15, wet_bulb_k=291.15, dew_point_k=288.15,
        relative_humidity=0.5, humidity_ratio_kg_kg=0.01, enthalpy_j_kg=50_000.0,
        specific_volume_m3_kg=0.86, source=StateSource.PSYCHROMETRICS, label="室內",
    )
    values.update(overrides)
    return AirStatePoint(**values)


def _ids():
    """回傳依序產生 id-1、id-2… 的識別碼工廠。

回傳：
    無參數函式。"""
    counter = iter(range(1, 1000))
    return lambda: f"id-{next(counter)}"


# ======================================================
# domain：StateLibrary
# ======================================================
def test_library_add_rename_duplicate_delete_are_pure() -> None:
    """新增、改名、複製、刪除都回傳新清單，不改動原清單；複本緊接在原項目之後。

回傳：
    無。"""
    empty = StateLibrary()
    first = empty.with_added(SavedState("a", "蒸發器出口", _thermo()))
    second = first.with_added(SavedState("b", "室內", _air()))

    renamed = second.renamed("a", "  壓縮機吸入  ")
    duplicated = renamed.duplicated("a", "c")
    removed = duplicated.removed("b")

    assert empty.entries == () and len(first.entries) == 1
    assert second.get("a").name == "蒸發器出口"
    assert renamed.get("a").name == "壓縮機吸入"
    assert [entry.id for entry in duplicated.entries] == ["a", "c", "b"]
    assert duplicated.get("c").name == f"壓縮機吸入{COPY_SUFFIX}"
    assert duplicated.get("c").point == duplicated.get("a").point
    assert [entry.id for entry in removed.entries] == ["a", "c"]
    assert [entry.kind for entry in second.entries] == ["thermo", "air"]


@pytest.mark.parametrize(("name", "message"), [("   ", "空白"), ("x" * (MAX_NAME_LENGTH + 1), "最多"), (3, "文字")])
def test_invalid_state_names_are_rejected(name, message) -> None:
    """名稱空白、過長或不是字串時明確失敗。

參數：
    name: 名稱。
    message: 錯誤訊息應包含的文字。

回傳：
    無。"""
    with pytest.raises(ValueError, match=message):
        SavedState("a", name, _thermo())


def test_duplicate_of_long_name_stays_within_limit() -> None:
    """名稱已達上限時，複本名稱仍不超過上限並保留「（複本）」。

回傳：
    無。"""
    library = StateLibrary((SavedState("a", "x" * MAX_NAME_LENGTH, _thermo()),))

    copy = library.duplicated("a", "b").get("b")

    assert len(copy.name) == MAX_NAME_LENGTH and copy.name.endswith(COPY_SUFFIX)


def test_library_rejects_duplicate_ids_and_unknown_ids() -> None:
    """識別碼重複時無法建立清單；找不到識別碼時引發 KeyError。

回傳：
    無。"""
    with pytest.raises(ValueError, match="重複"):
        StateLibrary((SavedState("a", "x", _thermo()), SavedState("a", "y", _thermo())))
    library = StateLibrary((SavedState("a", "x", _thermo()),))
    for operation in (lambda: library.get("zz"), lambda: library.renamed("zz", "n"),
                      lambda: library.duplicated("zz", "b"), lambda: library.removed("zz")):
        with pytest.raises(KeyError):
            operation()


def test_library_round_trips_through_standard_json() -> None:
    """冷媒與濕空氣項目都可經標準 JSON 往返，文件帶 schema 標記。

回傳：
    無。"""
    library = StateLibrary((
        SavedState("a", "蒸發器出口", _thermo(is_ideal_gas=False, key="1")),
        SavedState("b", "室內", _air()),
    ))

    document = json.loads(json.dumps(library.to_dict(), allow_nan=False))

    assert document["schema"] == "state_library" and document["schema_version"] == 1
    assert StateLibrary.from_dict(document) == library


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda doc: doc.update(schema_version=2), "較新的版本"),
        (lambda doc: doc.update(schema="workspace_settings"), "文件種類不符"),
        (lambda doc: doc.update(extra=1), "未知欄位"),
        (lambda doc: doc.update(entries={}), "陣列"),
        (lambda doc: doc["entries"][0].update(note="x"), "未知欄位"),
        (lambda doc: doc["entries"][0].pop("name"), "缺少欄位"),
        (lambda doc: doc["entries"][0]["point"].update(quality=5.0), "乾度"),
        (lambda doc: doc["entries"][0]["point"].update(schema="unknown"), "未知的狀態點"),
        (lambda doc: doc["entries"].append(dict(doc["entries"][0])), "重複"),
    ],
)
def test_invalid_library_documents_fail_explicitly(mutate, message) -> None:
    """版本、種類、欄位不符或內容無效的狀態庫文件明確失敗。

參數：
    mutate: 修改文件的函式。
    message: 錯誤訊息應包含的文字。

回傳：
    無。"""
    document = StateLibrary((SavedState("a", "x", _thermo()),)).to_dict()
    mutate(document)
    with pytest.raises(ValueError, match=message):
        StateLibrary.from_dict(document)


def test_default_state_names() -> None:
    """預設名稱：冷媒為「流體 · 顯示名稱」，濕空氣為「濕空氣 · 顯示名稱」。

回傳：
    無。"""
    assert default_state_name(_thermo(label="飽和蒸氣（露點）")) == "R32 · 飽和蒸氣（露點）"
    assert default_state_name(_thermo(label="")) == "R32"
    assert default_state_name(_air(label="室內")) == "濕空氣 · 室內"
    assert len(default_state_name(_thermo(label="x" * 200))) == MAX_NAME_LENGTH


# ======================================================
# domain：比較
# ======================================================
def _row(comparison, key):
    """取出比較列。

參數：
    comparison: StateComparison。
    key: 列鍵。

回傳：
    PropertyComparison。"""
    return next(row for row in comparison.rows if row.key == key)


def test_same_basis_thermo_comparison_uses_guarded_differences() -> None:
    """同基準的冷媒狀態：焓、熵差經基準防護相減，其他性質直接相減，差值為 B − A。

回傳：
    無。"""
    a = _thermo(quality=0.0, enthalpy_j_kg=250_000.0, entropy_j_kgk=1_200.0, density_kg_m3=1_000.0)
    b = _thermo(quality=1.0, temperature_k=281.0, pressure_pa=1_050_000.0)

    comparison = compare_states(a, b)

    assert comparison.kind == "thermo" and comparison.same_basis
    assert "R32／ASHRAE" in comparison.basis_note
    assert _row(comparison, "h").difference == enthalpy_difference(b, a)
    assert _row(comparison, "s").difference == entropy_difference(b, a)
    assert _row(comparison, "t").difference == pytest.approx(1.0)
    assert _row(comparison, "p").difference == pytest.approx(50_000.0)
    assert _row(comparison, "d").difference == pytest.approx(30.0 - 1_000.0)
    assert _row(comparison, "v").difference == pytest.approx(1 / 30.0 - 1 / 1_000.0)
    assert _row(comparison, "q").difference == pytest.approx(1.0)
    assert [row.key for row in comparison.rows] == ["t", "p", "h", "s", "d", "v", "q"]


@pytest.mark.parametrize("override", [{"reference_state": "IIR"}, {"fluid": "R134a"}])
def test_different_basis_does_not_subtract_enthalpy_or_entropy(override) -> None:
    """流體或 reference state 不同：焓、熵不相減並說明原因；溫度、壓力仍可相減。

參數：
    override: B 與 A 不同的欄位。

回傳：
    無。"""
    a, b = _thermo(), _thermo(temperature_k=290.0, **override)

    comparison = compare_states(a, b)

    assert not comparison.same_basis
    for key in ("h", "s"):
        row = _row(comparison, key)
        assert row.difference is None and row.note == BASIS_MISMATCH_NOTE
        assert row.a is not None and row.b is not None
    assert _row(comparison, "t").difference == pytest.approx(10.0)
    assert "A：R32／ASHRAE" in comparison.basis_note and "B：" in comparison.basis_note


def test_ideal_gas_state_has_no_entropy_comparison() -> None:
    """理想氣體模型未提供比熵：熵列不相減；同為理想氣體時焓照常相減。

回傳：
    無。"""
    a = _thermo(fluid="Water", reference_state="DEF", is_ideal_gas=True, entropy_j_kgk=0.0)
    b = replace(a, temperature_k=300.0, enthalpy_j_kg=410_000.0)

    comparison = compare_states(a, b)

    entropy = _row(comparison, "s")
    assert entropy.a is None and entropy.b is None and entropy.difference is None
    assert entropy.note == IDEAL_GAS_ENTROPY_NOTE
    assert _row(comparison, "h").difference == pytest.approx(10_000.0)
    assert "理想氣體" in comparison.basis_note


def test_single_phase_quality_is_not_compared() -> None:
    """單相狀態（乾度 -1）沒有乾度可比較。

回傳：
    無。"""
    row = _row(compare_states(_thermo(quality=-1.0), _thermo(quality=0.5)), "q")

    assert row.a is None and row.b == 0.5 and row.difference is None
    assert row.note == SINGLE_PHASE_QUALITY_NOTE


def test_air_comparison() -> None:
    """濕空氣比較：各性質直接相減，基準固定。

回傳：
    無。"""
    a = _air()
    b = _air(dry_bulb_k=286.15, relative_humidity=0.9, humidity_ratio_kg_kg=0.008, enthalpy_j_kg=33_000.0)

    comparison = compare_states(a, b)

    assert comparison.kind == "air" and comparison.same_basis
    assert _row(comparison, "tdb").difference == pytest.approx(-12.0)
    assert _row(comparison, "rh").difference == pytest.approx(0.4)
    assert _row(comparison, "w").difference == pytest.approx(-0.002)
    assert _row(comparison, "h").difference == pytest.approx(-17_000.0)


def test_thermo_and_air_states_cannot_be_compared() -> None:
    """冷媒與濕空氣狀態不能互相比較；其他型別明確失敗。

回傳：
    無。"""
    with pytest.raises(StateBasisMismatchError, match="不同型別"):
        compare_states(_thermo(), _air())
    with pytest.raises(StateBasisMismatchError):
        compare_states(_air(), _thermo())
    with pytest.raises(TypeError):
        compare_states(_thermo(), object())


# ======================================================
# application：StateLibraryService
# ======================================================
def test_service_persists_every_change_and_reloads(tmp_path) -> None:
    """每次變更都寫入檔案；以新的服務讀回相同內容。

回傳：
    無。"""
    store = JsonDocumentStore(tmp_path)
    service = StateLibraryService(store, id_factory=_ids())

    saved = service.save(_thermo(label="飽和蒸氣（露點）"))
    service.save(_air(), name="  室內  ")
    service.rename(saved.id, "蒸發器出口")
    copy = service.duplicate(saved.id)
    service.delete("id-2")

    assert saved.name == "R32 · 飽和蒸氣（露點）"
    assert copy.id == "id-3" and copy.name == f"蒸發器出口{COPY_SUFFIX}"
    reloaded = StateLibraryService(JsonDocumentStore(tmp_path))
    assert reloaded.entries == service.entries
    assert [entry.name for entry in reloaded.entries] == ["蒸發器出口", f"蒸發器出口{COPY_SUFFIX}"]
    assert (tmp_path / f"{STATE_LIBRARY_DOCUMENT_NAME}.json").exists()


def test_service_notifies_listeners_after_successful_changes(tmp_path) -> None:
    """清單變更成功後通知訂閱者；失敗時不通知。

回傳：
    無。"""
    service = StateLibraryService(JsonDocumentStore(tmp_path), id_factory=_ids())
    calls = []
    service.add_listener(lambda: calls.append(len(service.entries)))

    service.save(_thermo())
    with pytest.raises(ValueError):
        service.rename("id-1", " ")

    assert calls == [1]


def test_service_compare_uses_saved_points(tmp_path) -> None:
    """比較使用保存的狀態點；找不到項目時引發 KeyError。

回傳：
    無。"""
    service = StateLibraryService(JsonDocumentStore(tmp_path), id_factory=_ids())
    service.save(_thermo(temperature_k=280.0))
    service.save(_thermo(temperature_k=285.0))

    assert _row(service.compare("id-1", "id-2"), "t").difference == pytest.approx(5.0)
    with pytest.raises(KeyError):
        service.compare("id-1", "missing")


class _FailingStore:
    """寫入時失敗的儲存。"""

    def __init__(self, document=None) -> None:
        """記錄要讀回的文件。

參數：
    document: read() 回傳的文件。

回傳：
    無。"""
        self.document = document

    def read(self, name):
        """回傳預設文件。

參數：
    name: 文件名稱。

回傳：
    文件或 None。"""
        return self.document

    def write(self, name, document):
        """一律失敗。

參數：
    name: 文件名稱。
    document: 內容。

回傳：
    無（一律引發例外）。"""
        raise OSError("disk full")


def test_failed_write_keeps_the_library_unchanged() -> None:
    """寫入失敗時以 ValueError 回報，記憶體中的清單維持原狀。

回傳：
    無。"""
    existing = StateLibrary((SavedState("a", "x", _thermo()),)).to_dict()
    service = StateLibraryService(_FailingStore(existing))

    with pytest.raises(ValueError, match="寫入失敗"):
        service.save(_thermo())
    with pytest.raises(ValueError, match="寫入失敗"):
        service.delete("a")

    assert [entry.id for entry in service.entries] == ["a"]


def test_invalid_library_file_is_never_overwritten(tmp_path) -> None:
    """狀態庫檔案無效時記錄錯誤、清單為空，並拒絕所有寫入，保留使用者的檔案。

回傳：
    無。"""
    path = tmp_path / f"{STATE_LIBRARY_DOCUMENT_NAME}.json"
    path.write_text('{"schema": "state_library", "schema_version": 9, "entries": []}', encoding="utf-8")
    original = path.read_bytes()

    service = StateLibraryService(JsonDocumentStore(tmp_path))

    assert service.entries == ()
    assert service.load_error and "較新的版本" in service.load_error
    with pytest.raises(ValueError, match="暫停儲存"):
        service.save(_thermo())
    assert path.read_bytes() == original


# ======================================================
# infrastructure：工作區位置
# ======================================================
def test_workspace_directory_defaults_to_home_and_honours_override(tmp_path) -> None:
    """預設為家目錄下的 .hvac_workspace；環境變數可改用其他資料夾，空白值忽略。

回傳：
    無。"""
    home = Path("/home/someone")

    assert workspace_directory({}, home) == home / ".hvac_workspace"
    assert workspace_directory({WORKSPACE_DIR_ENV: "  "}, home) == home / ".hvac_workspace"
    assert workspace_directory({WORKSPACE_DIR_ENV: str(tmp_path)}, home) == tmp_path


# ======================================================
# UI
# ======================================================
class DummyPage:
    """提供建構完整工作區所需的最小 page 介面。"""

    def __init__(self) -> None:
        """初始化控制項與 overlay 容器。

回傳：
    無。"""
        self.controls = []
        self.overlay = []

    def add(self, *controls) -> None:
        """收集進入點新增的控制項。

參數：
    controls: 要加入頁面的控制項。

回傳：
    無。"""
        self.controls.extend(controls)

    def update(self) -> None:
        """在沒有 Flet session 時接受更新呼叫。

回傳：
    無。"""


def _build_shell():
    """建構完整工作區（使用 conftest 指定的暫存工作區資料夾）。

回傳：
    AppShell。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    property_view = shell.views["thermo_properties"]
    property_view.update = lambda: None
    property_view.show_error = lambda _message: None
    return shell


@pytest.fixture
def shell():
    """建構完整工作區。

回傳：
    AppShell。"""
    yield _build_shell()
    plt.close("all")


def _menu_labels(view) -> list[str]:
    """回傳儲存選單的項目文字。

參數：
    view: 分析頁或狀態查詢頁。

回傳：
    項目文字清單。"""
    return [item.content.value for item in view.save_menu.menu.items]


def _click_menu(view, label: str) -> None:
    """點選儲存選單中的項目。

參數：
    view: 分析頁或狀態查詢頁。
    label: 項目文字。

回傳：
    無。"""
    item = next(item for item in view.save_menu.menu.items if item.content.value == label)
    item.on_click(SimpleNamespace(control=item))


def _calculate(shell, route: str, analysis: str | None = None):
    """切到頁面（與分析項目）並以預設輸入計算。

參數：
    shell: 工作區外殼。
    route: 路由鍵。
    analysis: 分析項目 key。

回傳：
    分析頁。"""
    shell.navigate(route)
    view = shell.views[route]
    if analysis:
        view._handle_tool_change(analysis)
    view.perform_calculation(None)
    assert view.result_panel.status == "success", view.result_panel.message
    return view


def _calculate_property(shell):
    """在狀態查詢頁以 1000 kPa、0 °C 查詢 R32。

參數：
    shell: 工作區外殼。

回傳：
    狀態查詢頁。"""
    shell.navigate("thermo_properties")
    view = shell.views["thermo_properties"]
    view.input_rows[0]["val"].value = "1000"
    view.input_rows[1]["val"].value = "0"
    view.perform_calculation(None)
    assert view.result_panel.status == "success"
    return view


def test_state_library_route_is_registered() -> None:
    """狀態庫出現在工作區分區。

回傳：
    無。"""
    route = next(route for route in ROUTES if route.key == "state_library")
    assert route.section == "工作區" and route.label == "狀態庫"


@pytest.mark.parametrize(
    ("route", "analysis", "labels"),
    [
        ("saturation", None, ["R32 · 飽和液體（泡點）", "R32 · 飽和蒸氣（露點）", "全部儲存"]),
        ("superheat_subcooling", None,
         ["R32 · 露點（飽和蒸氣）", "R32 · 泡點（飽和液體）", "R32 · 量測點", "全部儲存"]),
        ("refrigeration_cycle", None,
         ["R32 · 壓縮機入口", "R32 · 等熵壓縮出口", "R32 · 壓縮機出口", "R32 · 冷凝器出口", "R32 · 蒸發器入口",
          "全部儲存"]),
        ("condenser", "condenser.exergy", ["R134a · 冷凝器入口", "R134a · 冷凝器出口", "全部儲存"]),
        ("psychrometrics", None, ["濕空氣 · 性質查詢"]),
    ],
)
def test_analysis_pages_offer_their_state_points_only_after_success(shell, route, analysis, labels) -> None:
    """可保存的頁面在成功計算後才顯示儲存選單，列出 domain 回傳的狀態點。

參數：
    shell: 工作區外殼。
    route: 路由鍵。
    analysis: 分析項目 key。
    labels: 預期的選單項目。

回傳：
    無。"""
    shell.navigate(route)
    view = shell.views[route]
    if analysis:
        view._handle_tool_change(analysis)
    assert view.save_menu.visible is False

    view.perform_calculation(None)

    assert view.save_menu.visible is True
    assert _menu_labels(view) == labels


def test_saving_all_points_adds_them_to_the_library_page(shell) -> None:
    """「全部儲存」把每個狀態點依序存入狀態庫，狀態庫頁立即顯示。

回傳：
    無。"""
    view = _calculate(shell, "refrigeration_cycle")

    _click_menu(view, "全部儲存")

    library = shell.views["state_library"]
    assert [entry.name for entry in library.service.entries] == _menu_labels(view)[:-1]
    assert "已儲存到狀態庫" in view.save_menu.feedback.value
    assert set(library.entry_rows) == {entry.id for entry in library.service.entries}
    stored = [entry.point for entry in library.service.entries]
    assert stored == list(shell.views["refrigeration_cycle"].active_definition.state_points())


def test_invalidated_result_hides_the_save_menu(shell) -> None:
    """修改輸入使結果失效時隱藏儲存選單，避免保存舊結果。

回傳：
    無。"""
    view = _calculate(shell, "saturation")
    field = view.adapter.modules[0].text_entries["sat_fluid"]["val"]

    field.value = "R134a"
    field.on_change(SimpleNamespace(control=field))

    assert view.result_panel.status == "warning"
    assert view.save_menu.visible is False


def test_analysis_without_state_points_has_no_save_menu(shell) -> None:
    """沒有提供狀態點的分析（例如冷凝器交換率）不顯示儲存選單。

回傳：
    無。"""
    view = _calculate(shell, "condenser", "condenser.heat_rate")

    assert view.save_menu.visible is False


def test_property_query_can_be_saved(shell) -> None:
    """狀態查詢頁成功查詢後可保存，狀態點帶查詢時實際使用的 reference state。

回傳：
    無。"""
    view = _calculate_property(shell)
    assert _menu_labels(view) == ["R32 · 狀態查詢"]

    _click_menu(view, "R32 · 狀態查詢")

    point = shell.views["state_library"].service.entries[0].point
    assert point.source is StateSource.PROPERTY_QUERY
    assert point.reference_state == "ASHRAE"
    assert point.pressure_pa == pytest.approx(1_000_000.0)
    assert point.temperature_k == pytest.approx(273.15)


def test_ideal_gas_water_query_is_saved_without_entropy(shell) -> None:
    """水的理想氣體模式可保存；比較時熵不相減。

回傳：
    無。"""
    shell.navigate("thermo_properties")
    view = shell.views["thermo_properties"]
    view.mode_dd.value = next(option.key for option in view.mode_dd.options if option.key.startswith("Water"))
    view.mode_dd.on_select(SimpleNamespace(control=view.mode_dd))
    view.ideal_gas_cb.value = True
    view.input_rows[0]["val"].value = "100"
    view.input_rows[1]["val"].value = "200"
    view.perform_calculation(None)
    assert view.result_panel.status == "success", view.result_panel.message

    view.save_menu.save(view.save_menu.points)
    view.save_menu.save(view.save_menu.points)

    library = shell.views["state_library"]
    assert all(entry.point.is_ideal_gas for entry in library.service.entries)
    rows = dict((row[0], row) for row in library.comparison_rows())
    assert rows["比熵 s"][3] == IDEAL_GAS_ENTROPY_NOTE


def test_library_page_rename_duplicate_and_confirmed_delete(shell) -> None:
    """狀態庫頁：改名（空白名稱拒絕）、複製、刪除需要再次確認。

回傳：
    無。"""
    view = _calculate(shell, "saturation")
    _click_menu(view, "全部儲存")
    library = shell.views["state_library"]
    shell.navigate("state_library")
    liquid, vapor = (entry.id for entry in library.service.entries)

    library.start_rename(liquid)
    library.rename_field.value = "   "
    library.confirm_rename(liquid)
    assert "操作失敗" in library.message.value
    assert library.service.get(liquid).name == "R32 · 飽和液體（泡點）"

    library.start_rename(liquid)
    library.rename_field.value = "冷凝器出口（泡點）"
    library.confirm_rename(liquid)
    assert library.service.get(liquid).name == "冷凝器出口（泡點）"
    assert library.renaming_id is None

    library.request_delete(liquid)
    library.duplicate(vapor)
    assert len(library.service.entries) == 3
    assert library.pending_delete_id is None

    library.request_delete(vapor)
    library.cancel_edit()
    assert len(library.service.entries) == 3
    library.request_delete(vapor)
    library.confirm_delete(vapor)
    assert vapor not in {entry.id for entry in library.service.entries}
    assert len(library.service.entries) == 2


def test_library_page_compares_selected_states_in_output_units(shell) -> None:
    """比較 A、B：差值為 B − A；切換英制時溫度差以溫差換算（1 K = 1.8 °F，無零點偏移）。

回傳：
    無。"""
    view = _calculate(shell, "saturation")
    _click_menu(view, "全部儲存")
    library = shell.views["state_library"]
    liquid, vapor = library.service.entries

    assert (library.a_id, library.b_id) == (liquid.id, vapor.id)
    rows = {row[0]: row for row in library.comparison_rows()}
    latent = (vapor.point.enthalpy_j_kg - liquid.point.enthalpy_j_kg) / 1000
    assert rows["比焓 h"][3] == f"{latent:.2f} kJ/kg"
    assert rows["乾度 Q"][1:] == ("0.0000", "1.0000", "1.0000")

    library.a_dropdown.value = vapor.id
    library.a_dropdown.on_select(SimpleNamespace(control=library.a_dropdown))
    library.b_dropdown.value = liquid.id
    library.b_dropdown.on_select(SimpleNamespace(control=library.b_dropdown))
    rows = {row[0]: row for row in library.comparison_rows()}
    assert rows["比焓 h"][3] == f"{-latent:.2f} kJ/kg"

    library.service.save(replace(liquid.point, temperature_k=liquid.point.temperature_k + 1.0))
    library.b_dropdown.value = library.service.entries[-1].id
    library.b_dropdown.on_select(SimpleNamespace(control=library.b_dropdown))
    library.a_dropdown.value = liquid.id
    library.a_dropdown.on_select(SimpleNamespace(control=library.a_dropdown))
    shell.unit_toggle.selected = ["Imperial"]
    shell.unit_toggle.on_change(SimpleNamespace(control=shell.unit_toggle))
    rows = {row[0]: row for row in library.comparison_rows()}
    assert rows["溫度"][3] == "1.80 °F"
    assert rows["溫度"][1].endswith("°F") and rows["絕對壓力"][1].endswith("psia")


def test_library_page_explains_basis_mismatch_and_kind_mismatch(shell) -> None:
    """不同 Reference State 時焓、熵不相減並說明；冷媒與濕空氣不能比較。

回傳：
    無。"""
    view = _calculate(shell, "saturation")
    _click_menu(view, "R32 · 飽和蒸氣（露點）")
    module = view.adapter.modules[0]
    module.sat_ref_state.value = "IIR"
    module.sat_ref_state.on_select(SimpleNamespace(control=module.sat_ref_state))
    view.perform_calculation(None)
    _click_menu(view, "R32 · 飽和蒸氣（露點）")
    library = shell.views["state_library"]

    rows = {row[0]: row for row in library.comparison_rows()}
    assert rows["比焓 h"][3] == BASIS_MISMATCH_NOTE
    assert rows["溫度"][3] == "0.00 K"
    assert "A：R32／ASHRAE" in library.comparison_note.value and "B：R32／IIR" in library.comparison_note.value

    psychrometrics = _calculate(shell, "psychrometrics")
    _click_menu(psychrometrics, "濕空氣 · 性質查詢")
    library.b_dropdown.value = library.service.entries[-1].id
    library.b_dropdown.on_select(SimpleNamespace(control=library.b_dropdown))
    assert library.comparison_rows() == []
    assert "不能互相比較" in library.comparison_note.value


def test_saved_states_survive_an_application_restart(isolated_workspace) -> None:
    """狀態保存在工作區資料夾；重新啟動程式後仍在。

參數：
    isolated_workspace: conftest 提供的暫存工作區。

回傳：
    無。"""
    first = _build_shell()
    view = _calculate(first, "saturation")
    _click_menu(view, "全部儲存")
    names = [entry.name for entry in first.views["state_library"].service.entries]
    plt.close("all")

    second = _build_shell()

    assert [entry.name for entry in second.views["state_library"].service.entries] == names
    assert (isolated_workspace / "state_library.json").exists()
    plt.close("all")


def test_unreadable_library_file_blocks_saving_and_is_reported(isolated_workspace) -> None:
    """狀態庫檔案損壞時：狀態庫頁顯示原因，儲存選單回報失敗，不覆蓋檔案。

參數：
    isolated_workspace: conftest 提供的暫存工作區。

回傳：
    無。"""
    path = isolated_workspace / "state_library.json"
    path.write_text("{broken", encoding="utf-8")

    shell = _build_shell()
    library = shell.views["state_library"]
    assert library.load_error.visible is True
    view = _calculate(shell, "saturation")
    _click_menu(view, "R32 · 飽和液體（泡點）")

    assert "儲存失敗" in view.save_menu.feedback.value
    assert library.service.entries == ()
    assert path.read_text(encoding="utf-8") == "{broken"
    plt.close("all")


# ======================================================
# Review hardening：讀檔失敗、批次保存、訂閱者隔離、state_points 契約
# ======================================================
class _UnreadableStore:
    """讀取時發生檔案系統錯誤的儲存；記錄是否被寫入。"""

    def __init__(self, error: OSError) -> None:
        """記錄要引發的讀取錯誤。

參數：
    error: 讀取時引發的例外。

回傳：
    無。"""
        self.error = error
        self.writes = 0

    def read(self, name):
        """一律引發讀取錯誤。

參數：
    name: 文件名稱。

回傳：
    無（一律引發例外）。"""
        raise self.error

    def write(self, name, document):
        """記錄寫入次數（不應被呼叫）。

參數：
    name: 文件名稱。
    document: 內容。

回傳：
    無。"""
        self.writes += 1


@pytest.mark.parametrize(
    "error",
    [PermissionError("permission denied"), IsADirectoryError("is a directory"), OSError("I/O error")],
    ids=["permission", "directory", "io"],
)
def test_filesystem_read_failure_makes_library_unavailable_not_fatal(error) -> None:
    """讀取狀態庫時的檔案系統錯誤不讓服務建立失敗：清單為空、記錄原因、拒絕所有寫入。

參數：
    error: 讀取時的錯誤。

回傳：
    無。"""
    store = _UnreadableStore(error)

    service = StateLibraryService(store)

    assert service.entries == ()
    assert service.load_error is not None and str(error) in service.load_error
    for mutation in (lambda: service.save(_thermo()), lambda: service.save_many([_thermo(), _air()])):
        with pytest.raises(ValueError, match="暫停儲存"):
            mutation()
    assert store.writes == 0


class _RecordingStore:
    """記錄寫入內容與次數的記憶體儲存；可設定寫入失敗。"""

    def __init__(self, document=None, *, fail: bool = False) -> None:
        """設定初始文件與是否寫入失敗。

參數：
    document: 初始文件。
    fail: True 時寫入引發 OSError。

回傳：
    無。"""
        self.document = document
        self.fail = fail
        self.writes = 0

    def read(self, name):
        """回傳目前文件。

參數：
    name: 文件名稱。

回傳：
    文件或 None。"""
        return self.document

    def write(self, name, document):
        """寫入（或模擬失敗）。

參數：
    name: 文件名稱。
    document: 內容。

回傳：
    無。"""
        if self.fail:
            raise OSError("disk full")
        self.writes += 1
        self.document = json.loads(json.dumps(document))


def test_save_many_writes_once_and_notifies_once() -> None:
    """批次保存只寫入一次、通知一次，依序新增全部項目並使用預設名稱。

回傳：
    無。"""
    store = _RecordingStore()
    service = StateLibraryService(store, id_factory=_ids())
    notifications = []
    service.add_listener(lambda: notifications.append(len(service.entries)))

    created = service.save_many([_thermo(label="1"), _thermo(label="2"), _air(label="室內")])

    assert store.writes == 1
    assert notifications == [3]
    assert [state.id for state in created] == ["id-1", "id-2", "id-3"]
    assert [entry.name for entry in service.entries] == ["R32 · 1", "R32 · 2", "濕空氣 · 室內"]
    assert StateLibrary.from_dict(store.document).entries == service.entries


def test_save_many_write_failure_adds_nothing() -> None:
    """批次保存寫入失敗時一筆都不新增：檔案、記憶體不變，不通知訂閱者。

回傳：
    無。"""
    existing = StateLibrary((SavedState("a", "既有", _thermo()),)).to_dict()
    store = _RecordingStore(existing, fail=True)
    service = StateLibraryService(store, id_factory=_ids())
    notifications = []
    service.add_listener(lambda: notifications.append(True))

    with pytest.raises(ValueError, match="寫入失敗"):
        service.save_many([_thermo(), _thermo(), _air()])

    assert [entry.id for entry in service.entries] == ["a"]
    assert store.document == existing
    assert notifications == []


def test_save_many_rejects_invalid_point_before_writing() -> None:
    """批次中任一項不是狀態點時整批拒絕，不寫入；空批次不寫入也不通知。

回傳：
    無。"""
    store = _RecordingStore()
    service = StateLibraryService(store, id_factory=_ids())
    notifications = []
    service.add_listener(lambda: notifications.append(True))

    with pytest.raises(ValueError, match="只支援"):
        service.save_many([_thermo(), object()])
    assert service.save_many([]) == ()

    assert store.writes == 0 and service.entries == () and notifications == []


def test_listener_failure_does_not_fail_a_committed_mutation(tmp_path, caplog) -> None:
    """訂閱者失敗不讓已保存的變更看起來失敗，也不阻止後續訂閱者；錯誤記錄在 log。

參數：
    tmp_path: pytest 暫存資料夾。
    caplog: pytest log 擷取。

回傳：
    無。"""
    service = StateLibraryService(JsonDocumentStore(tmp_path), id_factory=_ids())
    later = []

    def broken_listener():
        """模擬畫面重新整理失敗。

回傳：
    無（一律引發例外）。"""
        raise RuntimeError("refresh failed")

    service.add_listener(broken_listener)
    service.add_listener(lambda: later.append(len(service.entries)))

    with caplog.at_level("ERROR"):
        saved = service.save(_thermo())
        service.rename(saved.id, "新名稱")

    assert later == [1, 1]
    assert service.get(saved.id).name == "新名稱"
    assert StateLibraryService(JsonDocumentStore(tmp_path)).get(saved.id).name == "新名稱"
    assert sum("訂閱者更新失敗" in record.getMessage() for record in caplog.records) == 2


def test_app_starts_when_library_file_cannot_be_read(isolated_workspace) -> None:
    """狀態庫檔案無法讀取（路徑是資料夾，讀取時引發 IsADirectoryError）時應用程式仍可啟動：
狀態庫顯示原因且不可寫入，其他工具照常計算，原路徑不被覆蓋。

參數：
    isolated_workspace: conftest 提供的暫存工作區。

回傳：
    無。"""
    blocked = isolated_workspace / "state_library.json"
    blocked.mkdir()
    (blocked / "keep.txt").write_text("user data", encoding="utf-8")

    shell = _build_shell()

    library = shell.views["state_library"]
    assert library.load_error.visible is True
    assert library.service.entries == ()
    assert {"state_library", "saturation", "refrigeration_cycle", "psychrometrics"} <= set(shell.views)
    shell.navigate("state_library")
    view = _calculate(shell, "saturation")
    _click_menu(view, "全部儲存")
    assert "儲存失敗" in view.save_menu.feedback.value
    assert blocked.is_dir() and (blocked / "keep.txt").read_text(encoding="utf-8") == "user data"
    plt.close("all")


def test_save_all_failure_in_ui_saves_nothing(shell, monkeypatch) -> None:
    """「全部儲存」寫入失敗時狀態庫不新增任何一筆，並提示失敗；之後重試成功也不會重複。

參數：
    shell: 工作區外殼。
    monkeypatch: pytest monkeypatch。

回傳：
    無。"""
    view = _calculate(shell, "refrigeration_cycle")
    library = shell.views["state_library"]
    store = library.service._store
    real_write = store.write
    writes = []

    def failing_write(name, document):
        """前兩筆以內的文件照常寫入，第三筆起磁碟寫入失敗（逐筆保存會留下部分結果）。

參數：
    name: 文件名稱。
    document: 內容。

回傳：
    無。"""
        writes.append(len(document["entries"]))
        if len(document["entries"]) >= 3:
            raise OSError("disk full")
        real_write(name, document)

    monkeypatch.setattr(store, "write", failing_write)
    _click_menu(view, "全部儲存")

    assert writes == [5]
    assert library.service.entries == ()
    assert StateLibraryService(JsonDocumentStore(store.root)).entries == ()
    assert library.entry_rows == {}
    assert "儲存失敗" in view.save_menu.feedback.value

    monkeypatch.setattr(store, "write", real_write)
    _click_menu(view, "全部儲存")
    assert len(library.service.entries) == len(view.save_menu.points) == 5


def test_invalid_state_points_fail_fast_in_save_menu(shell) -> None:
    """分析定義回傳非狀態點時，在顯示儲存選單時就以 TypeError 失敗，不延後到保存。

回傳：
    無。"""
    view = shell.views["saturation"]

    with pytest.raises(TypeError, match="state_points 只能回傳"):
        view.save_menu.show_points([_thermo(), {"T": 300.0}])

    module = view.adapter.modules[0]
    shell.navigate("saturation")
    view.perform_calculation(None)
    original = module.last_result
    module.last_result = SimpleNamespace(liquid="not a state", vapor=original.vapor)
    with pytest.raises(TypeError, match="str"):
        view._show_result()
