"""Phase 6C 的 explicit analysis dispatch metadata test。"""

from __future__ import annotations

from pathlib import Path

from Flet_ui.flet_app import main as flet_main


class DummyPage:
    """提供建立 analysis 所需的最小 page surface。"""

    def __init__(self) -> None:
        self.overlay = []
        self.controls = []

    def add(self, *controls) -> None:
        """收集進入點新增的控制項。

參數：
    controls: 要加入頁面的控制項。

回傳：
    無。"""
        self.controls.extend(controls)

    def update(self) -> None:
        """接受 headless update。

回傳：
    無。"""


def test_analysis_definitions_have_stable_ids_without_label_dispatch() -> None:
    """Analysis dispatch metadata 以穩定 ID 為準，不依賴 display-label prefix。

回傳：
    無。"""
    page = DummyPage()
    flet_main(page)
    definitions = [
        definition
        for view in page.controls[0].views.values()
        if hasattr(view, "adapter")
        for definition in view.adapter.definitions
    ]
    assert definitions
    assert all(definition.key and definition.key != definition.label for definition in definitions)

    for path in (Path(__file__).parents[2] / "Flet_ui").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert 'startswith("濕空氣性質")' not in source, path
