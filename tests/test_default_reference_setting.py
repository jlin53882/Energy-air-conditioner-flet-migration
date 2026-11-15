"""工作區設定的預設 Reference State 套用到各頁選單，以及物性頁的 Air 濕度提示。"""

from __future__ import annotations

from types import SimpleNamespace

import matplotlib.pyplot as plt
import pytest

from application.settings import SETTINGS_DOCUMENT_NAME, SettingsService, WorkspaceSettings
from domain.thermodynamics.reference_state import ReferenceStateService
from domain.thermodynamics.state_service import ThermodynamicStateService
from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui.reference_state_default import default_reference_choice
from infrastructure.storage import JsonDocumentStore

# 擁有 Reference State 選單的分析頁：(路由, 選單屬性)。
ANALYSIS_DROPDOWNS = (
    ("saturation", "sat_ref_state"),
    ("superheat_subcooling", "sh_ref_state"),
    ("refrigeration_cycle", "cyc_ref_state"),
    ("condenser", "cx_ref_state"),
)


class DummyPage:
    """沒有 Flet session 時的最小頁面替身。"""

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
    """建構完整工作區；物性頁未掛載時略過 update／SnackBar。

回傳：
    AppShell。"""
    page = DummyPage()
    flet_main(page)
    shell = page.controls[0]
    view = shell.views["thermo_properties"]
    view.update = lambda: None
    view.show_error = lambda _message: None
    return shell


@pytest.fixture
def build_shell():
    """回傳建構工作區的函式，測試結束時關閉圖表。

回傳：
    建構函式。"""
    yield _build_shell
    plt.close("all")


def _save_default(workspace, value: str) -> None:
    """以設定服務保存預設 Reference State。

參數：
    workspace: 測試用工作區資料夾。
    value: 預設值。

回傳：
    無。"""
    SettingsService(JsonDocumentStore(workspace)).save(WorkspaceSettings(default_reference_state=value))


def _module(shell, route_key: str):
    """回傳分析頁的模組。

參數：
    shell: 工作區外殼。
    route_key: 路由鍵。

回傳：
    模組。"""
    return shell.views[route_key].adapter.modules[0]


def _reference_values(shell) -> dict[str, str]:
    """回傳各頁 Reference State 選單目前的值。

參數：
    shell: 工作區外殼。

回傳：
    頁面 → 選單值。"""
    values = {key: getattr(_module(shell, key), attribute).value for key, attribute in ANALYSIS_DROPDOWNS}
    values["thermo_properties"] = shell.views["thermo_properties"].ref_state_dd.value
    values["ph_chart"] = shell.views["ph_chart"].module.ref_state_dd.value
    return values


def _user_select(dropdown, value: str) -> None:
    """模擬使用者在選單上選取。

參數：
    dropdown: 選單。
    value: 選取值。

回傳：
    無。"""
    dropdown.value = value
    dropdown.on_select(SimpleNamespace(control=dropdown, data=value))


# ======================================================
# 設定值正規化
# ======================================================
@pytest.mark.parametrize(
    ("value", "expected"),
    [("ASHRAE", "ASHRAE"), ("iir", "IIR"), ("auto", "Auto"), ("CURRENT", "Auto"), ("XYZ", "Auto"),
     (None, "Auto"), (3, "Auto")],
)
def test_default_reference_choice_falls_back_to_auto(value, expected) -> None:
    """有效值正規化為選單選項；無效值（含 CURRENT）一律改用 Auto。"""
    assert default_reference_choice(value) == expected


# ======================================================
# 設定作為各頁初始值
# ======================================================
def test_without_saved_settings_every_page_starts_at_auto(build_shell) -> None:
    """尚未保存設定時各頁維持 Auto。"""
    shell = build_shell()
    assert set(_reference_values(shell).values()) == {"Auto"}


def test_saved_setting_is_the_initial_value_on_every_page(build_shell, isolated_workspace) -> None:
    """保存的預設值成為每一頁 Reference State 選單的初始值，計算也實際採用它。"""
    _save_default(isolated_workspace, "ASHRAE")
    shell = build_shell()
    assert set(_reference_values(shell).values()) == {"ASHRAE"}

    property_view = shell.views["thermo_properties"]
    assert "ASHRAE" in property_view.reference_state_helper.value
    assert "參考基準 ASHRAE" in property_view.policy_preview.value

    shell.navigate("saturation")
    view = shell.views["saturation"]
    view.perform_calculation(None)
    assert view.adapter.result_panel.status == "success", view.adapter.result_panel.message
    assert _module(shell, "saturation").last_policy.reference_state == "ASHRAE"


def test_invalid_saved_setting_falls_back_to_auto(build_shell, isolated_workspace) -> None:
    """設定檔中的預設值無效時，工作區仍可開啟且各頁使用 Auto。"""
    document = WorkspaceSettings().to_dict()
    document["default_reference_state"] = "XYZ"
    JsonDocumentStore(isolated_workspace).write(SETTINGS_DOCUMENT_NAME, document)

    shell = build_shell()
    assert set(_reference_values(shell).values()) == {"Auto"}


# ======================================================
# 使用者的選擇優先
# ======================================================
def test_applying_a_new_setting_keeps_user_choices(build_shell, isolated_workspace, monkeypatch) -> None:
    """使用者選過的選單不被新設定改動；未選過的選單跟著更新，且不設定 process-global 基準。"""
    _save_default(isolated_workspace, "IIR")
    shell = build_shell()
    property_view = shell.views["thermo_properties"]
    saturation = _module(shell, "saturation")
    superheat = _module(shell, "superheat_subcooling")
    diagram = shell.views["ph_chart"].module

    _user_select(saturation.sat_ref_state, "NBP")
    _user_select(diagram.ref_state_dd, "DEF")
    _user_select(property_view.ref_state_dd, "NBP")

    def forbid(*_args, **_kwargs):
        raise AssertionError("套用設定不得呼叫 process-global set_reference_state()")

    monkeypatch.setattr(ReferenceStateService, "set", forbid)
    monkeypatch.setattr(ThermodynamicStateService, "set_reference_state", forbid)
    for target in (property_view, saturation, superheat, diagram):
        target.apply_default_reference_state("ASHRAE")

    assert saturation.sat_ref_state.value == "NBP"
    assert diagram.ref_state_dd.value == "DEF"
    assert property_view.ref_state_dd.value == "NBP"
    assert superheat.sh_ref_state.value == "ASHRAE"


def test_applied_setting_is_not_mistaken_for_a_user_choice(build_shell) -> None:
    """程式套用的預設值不算使用者選擇：之後的設定仍可更新該選單，且舊結果會失效。"""
    shell = build_shell()
    shell.navigate("saturation")
    view = shell.views["saturation"]
    module = _module(shell, "saturation")
    view.perform_calculation(None)
    assert view.adapter.result_panel.status == "success"

    module.apply_default_reference_state("ASHRAE")
    assert module.sat_ref_state.value == "ASHRAE"
    assert view.adapter.result_panel.status == "warning"

    module.apply_default_reference_state("NBP")
    assert module.sat_ref_state.value == "NBP"


def test_property_page_restores_default_after_non_reference_model(build_shell, isolated_workspace) -> None:
    """理想氣體／濕空氣時固定 Auto 並停用；切回適用模型時，未自行選過基準就恢復設定值。"""
    _save_default(isolated_workspace, "IIR")
    shell = build_shell()
    view = shell.views["thermo_properties"]

    def select_model(model: str) -> None:
        view.mode_dd.value = model
        view.mode_dd.on_select(SimpleNamespace(control=view.mode_dd))

    select_model("ideal_gas")
    assert view.ref_state_dd.value == "Auto" and view.ref_state_dd.disabled is True
    view.apply_default_reference_state("ASHRAE")
    assert view.ref_state_dd.value == "Auto"
    select_model("real_fluid")
    assert view.ref_state_dd.value == "ASHRAE" and view.ref_state_dd.disabled is False

    _user_select(view.ref_state_dd, "NBP")
    select_model("ideal_gas")
    assert view.ref_state_dd.value == "Auto" and view.ref_state_dd.disabled is True
    select_model("real_fluid")
    # 使用者選過的基準照原樣還原，之後套用新的設定也不覆寫。
    assert view.ref_state_dd.value == "NBP"
    view.apply_default_reference_state("DEF")
    assert view.ref_state_dd.value == "NBP"


# ======================================================
# 工作區預設只是偏好：流體不支援時退回 Auto 規則
# ======================================================
def test_property_page_default_falls_back_to_auto_for_unsupported_fluids(build_shell, isolated_workspace) -> None:
    """預設 IIR 時 Water 改用 Auto 規則（DEF）並說明；R32 標示「工作區預設」而不是「手動」。"""
    _save_default(isolated_workspace, "IIR")
    shell = build_shell()
    view = shell.views["thermo_properties"]

    view.fluid_tf.value = "Water"
    policy = view._refresh_policy_preview()
    assert policy is not None and policy.reference_state == "DEF"
    assert "不支援工作區預設 IIR" in view.policy_preview.value

    view.fluid_tf.value = "R32"
    policy = view._refresh_policy_preview()
    assert policy is not None and policy.reference_label == "IIR（工作區預設）"

    # 使用者自行選的 IIR 是手動指定：不支援時照樣明確報錯，不靜默改用其他基準。
    _user_select(view.ref_state_dd, "IIR")
    view.fluid_tf.value = "Water"
    assert view._refresh_policy_preview() is None
    assert "手動指定" in view.policy_preview.value


@pytest.mark.parametrize(("route_key", "attribute"), ANALYSIS_DROPDOWNS)
def test_analysis_default_falls_back_to_auto_for_unsupported_fluids(
    build_shell, isolated_workspace, route_key, attribute
) -> None:
    """分析頁同樣把工作區預設當成偏好；使用者選過後才是手動指定。"""
    _save_default(isolated_workspace, "IIR")
    module = _module(build_shell(), route_key)
    dropdown = getattr(module, attribute)

    water = module.resolve_reference_policy("Water", dropdown)
    assert water.reference_state == "DEF" and "不支援工作區預設 IIR" in water.fallback_reason
    assert module.resolve_reference_policy("R32", dropdown).reference_label == "IIR（工作區預設）"

    _user_select(dropdown, "IIR")
    assert module.resolve_reference_policy("R32", dropdown).reference_label == "IIR（手動）"
    with pytest.raises(ValueError, match="手動指定"):
        module.resolve_reference_policy("Water", dropdown)


# ======================================================
# 物性頁：Air 的濕度提示
# ======================================================
@pytest.mark.parametrize("fluid", ["Air", "R729", "air"])
def test_air_hint_shows_for_air_aliases_without_switching_model(build_shell, fluid) -> None:
    """物質為 Air（含別名）且模型不是濕空氣時顯示提示，不自動切換模型。"""
    view = _build_shell_view(build_shell)
    view.fluid_tf.value = fluid
    view.on_fluid_change(None)

    assert view.air_humidity_hint.visible is True
    assert "濕空氣" in view.air_humidity_hint.value
    assert view.mode_dd.value == "auto"


def test_air_hint_hides_for_other_fluids_and_humid_air_model(build_shell) -> None:
    """其他物質或濕空氣模型時隱藏提示。"""
    view = _build_shell_view(build_shell)
    assert view.air_humidity_hint.visible is False

    view.fluid_tf.value = "R729"
    view.on_fluid_change(None)
    view.mode_dd.value = "humid_air"
    view.mode_dd.on_select(SimpleNamespace(control=view.mode_dd))
    assert view.air_humidity_hint.visible is False

    view.mode_dd.value = "real_fluid"
    view.mode_dd.on_select(SimpleNamespace(control=view.mode_dd))
    assert view.fluid_tf.value == "R729" and view.air_humidity_hint.visible is True

    view.fluid_tf.value = "Nitrogen"
    view.on_fluid_change(None)
    assert view.air_humidity_hint.visible is False


def _build_shell_view(build_shell):
    """建構工作區並回傳物性頁。

參數：
    build_shell: 建構函式。

回傳：
    PropertyTab。"""
    shell = build_shell()
    shell.navigate("thermo_properties")
    return shell.views["thermo_properties"]
