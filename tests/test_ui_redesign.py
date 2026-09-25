"""工作區 UI 重新設計的行為與呈現契約測試。"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import flet as ft

from Flet_ui.flet_app import main as flet_main
from Flet_ui.ui.analysis_presentation import ANALYSIS_PRESENTATION
from Flet_ui.ui.components.metric_tile import split_value_and_unit
from Flet_ui.ui.structured_result import parse_result_text, structured_from_text
from Flet_ui.ui.components.sidebar import Sidebar
from Flet_ui.ui.components.status_badge import StatusBadge
from Flet_ui.ui.navigation import ROUTES
from Flet_ui.ui.structured_result import PropertyRow
from Flet_ui.ui.theme import TOKENS
from Flet_ui.ui.views.home_view import HomeView


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
    """建構完整工作區並回傳外殼。

回傳：
    掛載於 DummyPage 的 AppShell。"""
    page = DummyPage()
    flet_main(page)
    return page.controls[0]


def test_parse_result_text_keeps_module_values_and_sections() -> None:
    """結果投影只拆分既有文字，不改寫數值，並保留分組與順序。

回傳：
    無。"""
    text = (
        "--- 主要性質 ---\n"
        "海拔高度 (Altitude)          : 0.00 m\n"
        "相對濕度 (Relative Humidity) : 63.48 %\n"
        "\n--- 中間過程壓力值 ---\n"
        "水蒸氣分壓 (Vapor Pressure)  : 2013.4512 Pa\n"
    )

    sections = parse_result_text(text)

    assert [section.title for section in sections] == ["主要性質", "中間過程壓力值"]
    assert sections[0].items == [
        ("海拔高度 (Altitude)", "0.00 m"),
        ("相對濕度 (Relative Humidity)", "63.48 %"),
    ]
    assert sections[1].items == [("水蒸氣分壓 (Vapor Pressure)", "2013.4512 Pa")]


def test_parse_result_text_single_line_and_notes() -> None:
    """單行結果成為一個指標；無法配對的文字保留為說明。

回傳：
    無。"""
    sections = parse_result_text("壓縮比 (CR): 5.0000 (無單位)\n備註文字")

    assert len(sections) == 1
    assert sections[0].title is None
    assert sections[0].items == [("壓縮比 (CR)", "5.0000 (無單位)")]
    assert sections[0].notes == ["備註文字"]


def test_split_value_and_unit_only_splits_leading_number() -> None:
    """數值與單位只在開頭可解析為數字時拆開。

回傳：
    無。"""
    assert split_value_and_unit("405.2173 kJ/kg") == ("405.2173", "kJ/kg")
    assert split_value_and_unit("0.8800") == ("0.8800", "")
    assert split_value_and_unit("R134a") == ("R134a", "")


def _analysis_views(shell) -> dict:
    """回傳所有具備 AnalysisModuleAdapter 的 dedicated analysis view。

參數：
    shell: 已建立的 AppShell。

回傳：
    路由鍵對應 view 的字典。"""
    return {key: view for key, view in shell.views.items() if hasattr(view, "adapter")}


def test_every_registered_analysis_has_presentation_copy() -> None:
    """每個已註冊分析都有說明文字，且說明表不含不存在的分析。

回傳：
    無。"""
    shell = _build_shell()
    registered_ids = {
        definition.key
        for view in _analysis_views(shell).values()
        for definition in view.adapter.definitions
    }

    assert registered_ids == set(ANALYSIS_PRESENTATION)


def test_home_view_shows_registry_backed_counts_only() -> None:
    """首頁只顯示呼叫端提供的分析數量，且每張卡片以路由鍵導覽。

回傳：
    無。"""
    visited: list[str] = []
    home = HomeView(visited.append, analysis_counts={"compressor": 11, "evaporator": 1},
                    total_analyses=16)

    assert set(home.tool_cards) == {route.key for route in ROUTES if route.key != "home"}
    home.tool_cards["psychrometrics"].on_click(SimpleNamespace())
    assert visited == ["psychrometrics"]

    def texts(control) -> list[str]:
        """收集控制項樹中的所有文字值。

參數：
    control: 搜尋起點。

回傳：
    文字值清單。"""
        found = [control.value] if isinstance(control, ft.Text) else []
        content = getattr(control, "content", None)
        if content is not None and not isinstance(content, str):
            found.extend(texts(content))
        for child in getattr(control, "controls", None) or []:
            found.extend(texts(child))
        return found

    assert "11 種分析" in texts(home.tool_cards["compressor"])
    assert not any("種分析" in value for value in texts(home.tool_cards["evaporator"]))
    assert "16" in texts(home)


def test_shell_home_counts_match_analysis_registry() -> None:
    """外殼組合根傳給首頁的數量必須來自各 dedicated view 的分析定義。

回傳：
    無。"""
    shell = _build_shell()
    home = shell.views["home"]
    views = _analysis_views(shell)

    assert home.analysis_counts == {key: len(view.adapter.definitions) for key, view in views.items()}
    assert home.total_analyses == sum(home.analysis_counts.values())


def test_sidebar_highlights_only_the_selected_route() -> None:
    """側邊導覽只醒目提示目前路由，並在精簡模式隱藏文字。

回傳：
    無。"""
    sidebar = Sidebar(lambda _key: None, "compressor")

    selected = [key for key, item in sidebar.items.items() if item.bgcolor == TOKENS.nav_selected]
    assert selected == ["compressor"]

    sidebar.set_selected("ph_chart")
    selected = [key for key, item in sidebar.items.items() if item.bgcolor == TOKENS.nav_selected]
    assert selected == ["ph_chart"]

    sidebar.set_compact(True)
    assert all(label.visible is False for label in sidebar._labels.values())
    assert sidebar.footer.visible is False


def test_shell_header_and_breadcrumb_follow_route() -> None:
    """頁首標題、說明與麵包屑隨路由更新，頂端列的單位切換反映輸出偏好。

回傳：
    無。"""
    shell = _build_shell()
    shell.navigate("psychrometrics")

    assert shell.route_header.controls[0].value == "濕空氣性質"
    assert shell.breadcrumb_section.value == "空氣處理"
    assert shell.breadcrumb_label.value == "濕空氣性質"

    shell.set_output_unit_system("Imperial")
    assert shell.unit_toggle.selected == ["Imperial"]


def test_property_preset_chip_tracks_current_property_pair() -> None:
    """常用組合按鈕只標示與前兩列性質相符的組合。

回傳：
    無。"""
    shell = _build_shell()
    tab = shell.views["thermo_properties"]
    tab.update = lambda: None

    def selected_labels() -> list[str]:
        """回傳目前被標示的組合。

回傳：
    被標示組合的顯示文字。"""
        return [
            button.content
            for button in tab.preset_buttons.controls
            if button.style.bgcolor == TOKENS.primary
        ]

    assert selected_labels() == ["P + T"]
    tab._apply_property_preset(("P", "H"))
    assert selected_labels() == ["P + H"]
    tab.input_rows[1]["prop"].value = tab.prop_names_map["S"]
    tab.input_rows[1]["prop"].on_select(None)
    assert selected_labels() == ["P + S"]


def test_ideal_gas_option_is_part_of_property_layout() -> None:
    """水模式的理想氣體選項必須實際放入畫面，而不只是存在於物件上。

回傳：
    無。"""
    shell = _build_shell()
    tab = shell.views["thermo_properties"]

    def contains(root, target) -> bool:
        """深度搜尋控制項樹。

參數：
    root: 搜尋起點。
    target: 目標控制項。

回傳：
    是否找到目標。"""
        if root is target:
            return True
        content = getattr(root, "content", None)
        children = [content] if content is not None and not isinstance(content, str) else []
        children.extend(getattr(root, "controls", None) or [])
        return any(contains(child, target) for child in children)

    assert contains(tab, tab.ideal_gas_cb)


def test_analysis_result_renders_metric_tiles_and_error_state() -> None:
    """成功結果投影為指標卡片；模組回報的失敗文字以錯誤狀態呈現。

回傳：
    無。"""
    shell = _build_shell()
    shell.navigate("compressor")
    view = shell.views["compressor"]
    result_view = view.workspace.result_view
    view._handle_tool_change("compressor.work")

    view.perform_calculation(None)

    assert view.result_panel.status == "success"
    (tile,) = result_view.kpi_row.controls
    assert tile.label_control.value == "壓縮機功 (W_in)"
    assert (tile.value_control.value, tile.unit_control.value) == ("5.0000", "kW")
    # 唯一的結果已是關鍵數值，不再重複列出性質表。
    assert result_view.table_column.visible is False
    assert result_view.copy_button.disabled is False

    view.adapter._by_key["compressor.work"] = replace(
        view.adapter.active_definition, calculate=lambda _use_imperial: "計算錯誤: 無效流體"
    )
    view.perform_calculation(None)
    assert view.result_panel.status == "error"
    assert result_view.kpi_row.visible is False
    assert result_view.body_row.visible is False
    assert result_view.copy_button.disabled is True

    view._handle_tool_change("compressor.compression_ratio")
    assert view.result_panel.status == "empty"
    assert result_view.details_button.disabled is True


def test_analysis_invalid_input_shows_error_without_metrics() -> None:
    """無效輸入會顯示錯誤狀態，且不留下舊指標。

回傳：
    無。"""
    shell = _build_shell()
    shell.navigate("compressor")
    view = shell.views["compressor"]
    entries = view.adapter.modules[0].all_entries
    entries["cr_pe"]["val"].value = "0.3"
    entries["cr_pc"]["val"].value = "1.2"
    view.perform_calculation(None)
    assert view.workspace.result_view.kpi_row.controls

    entries["cr_pe"]["val"].value = "abc"
    view.perform_calculation(None)

    assert view.result_panel.status == "error"
    assert view.workspace.result_view.kpi_row.controls == []
    assert view.adapter.result_text is None


def test_single_analysis_views_hide_tool_card_and_show_formula() -> None:
    """只有一項分析的畫面隱藏工具選取卡片，但保留說明與公式。

回傳：
    無。"""
    shell = _build_shell()

    compressor = shell.views["compressor"].workspace
    assert compressor.tool_selector.visible is True
    assert compressor.formula_box.visible is True

    evaporator = shell.views["evaporator"].workspace
    assert evaporator.tool_selector.visible is False
    assert evaporator.analysis_title.value
    assert evaporator.formula_box.visible is True


def test_status_badge_uses_icon_text_and_color() -> None:
    """狀態標籤同時提供圖示與文字，並拒絕未知狀態。

回傳：
    無。"""
    badge = StatusBadge("warning")
    assert badge.label_control.value == "注意"
    assert badge.icon_control.icon == ft.Icons.WARNING_AMBER_OUTLINED

    badge.set_status("success", "完成計算")
    assert badge.label_control.value == "完成計算"

    try:
        badge.set_status("unknown")
    except ValueError:
        pass
    else:  # pragma: no cover - 防止未知狀態被默默接受
        raise AssertionError("unknown status should raise")


def test_structured_from_text_promotes_declared_key_metrics() -> None:
    """文字轉結構化結果時，依宣告的名稱挑選關鍵數值，性質表保留全部結果。

回傳：
    無。"""
    text = (
        "--- 性能 ---\n"
        "冷房 COP: 3.87\n"
        "壓縮功 w: 63.82 kJ/kg\n"
        "--- 系統 ---\n"
        "壓縮機功率: 2.582 kW\n"
    )

    result = structured_from_text(text, key_labels=("壓縮機功率", "不存在的名稱", "冷房 COP"),
                                  chart_title="P-h 圖")

    assert [(m.label, m.value, m.unit) for m in result.key_metrics] == [
        ("壓縮機功率", "2.582", "kW"),
        ("冷房 COP", "3.87", ""),
    ]
    assert [group.title for group in result.groups] == ["性能", "系統"]
    assert result.groups[0].rows[1] == PropertyRow("壓縮功 w", "63.82", "kJ/kg")
    assert result.chart_title == "P-h 圖"


def test_structured_from_text_defaults_and_single_result() -> None:
    """未宣告時取前四個結果；只有一個結果時不重複列出性質表。

回傳：
    無。"""
    many = "\n".join(f"項目{i}: {i}.0 kW" for i in range(6))
    assert [m.label for m in structured_from_text(many).key_metrics] == ["項目0", "項目1", "項目2", "項目3"]
    assert len(structured_from_text(many).groups[0].rows) == 6

    single = structured_from_text("壓縮比 (CR): 4.0000")
    assert [m.value for m in single.key_metrics] == ["4.0000"]
    assert single.groups == ()


def test_every_analysis_with_declared_key_metrics_finds_them() -> None:
    """每個宣告關鍵數值的分析，以預設輸入計算後至少能找到一個宣告的名稱。

回傳：
    無。"""
    shell = _build_shell()
    for view in _analysis_views(shell).values():
        for definition in view.adapter.definitions:
            presentation = ANALYSIS_PRESENTATION[definition.key]
            if not presentation.key_metrics or definition.structured_result:
                continue
            if view.active_key != definition.key:
                view._handle_tool_change(definition.key)
            view.perform_calculation(None)
            assert view.result_panel.status == "success", (definition.key, view.result_panel.message)
            labels = [tile.label_control.value for tile in view.workspace.result_view.kpi_row.controls]
            assert labels and set(labels) <= set(presentation.key_metrics), (definition.key, labels)
