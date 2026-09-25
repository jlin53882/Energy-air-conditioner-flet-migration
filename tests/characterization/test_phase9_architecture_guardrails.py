"""階段 9 architecture guardrail test。"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[2]


def _python_sources(relative_dir: str) -> list[Path]:
    """回傳 project layer 下的 Python source file。

參數：
    relative_dir (str): 函數輸入值。

回傳：
    list[Path]：函數計算或處理後的結果。"""
    return sorted((ROOT / relative_dir).rglob("*.py"))


def _imports(source_path: Path) -> set[str]:
    """擷取 imported module name，不要誤判 display string。

參數：
    source_path (Path): 函數輸入值。

回傳：
    set[str]：函數計算或處理後的結果。"""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_has_no_channel_or_rendering_imports() -> None:
    """Domain code 維持獨立於 Flet、Telegram 與 Matplotlib UI。

回傳：
    無。"""
    forbidden_prefixes = ("flet", "telegram", "matplotlib")
    for source_path in _python_sources("domain"):
        assert not any(
            module == prefix or module.startswith(f"{prefix}.")
            for module in _imports(source_path)
            for prefix in forbidden_prefixes
        ), source_path


def test_application_has_no_channel_object_dependencies() -> None:
    """Application service 不接受 channel control 或 update。

回傳：
    無。"""
    forbidden_prefixes = ("flet", "telegram")
    for source_path in _python_sources("application"):
        assert not any(
            module == prefix or module.startswith(f"{prefix}.")
            for module in _imports(source_path)
            for prefix in forbidden_prefixes
        ), source_path


def test_selected_adapters_do_not_call_coolprop_directly() -> None:
    """已遷移的 adapter 使用 service，不直接執行 property query。

回傳：
    無。"""
    for relative_path in (
        "Flet_ui/ui_components/property_tab.py",
        "Flet_ui/ui_components/analysis_modules/hvac_compressor_module.py",
    ):
        source_path = ROOT / relative_path
        assert not any(module.startswith("CoolProp") for module in _imports(source_path))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"PropsSI", "AbstractState"}
            for node in ast.walk(tree)
        )


def test_new_domain_calculations_use_service_boundaries() -> None:
    """冷凍循環與空氣處理只能透過狀態服務協定取得性質，不得直接呼叫 CoolProp 或舊版濕空氣 model。

回傳：
    無。"""
    sources = _python_sources("domain/refrigeration") + [
        ROOT / "domain/psychrometrics/processes.py",
        ROOT / "chart/psychrometric.py",
    ]
    for source_path in sources:
        modules = _imports(source_path)
        assert not any(module.startswith("CoolProp") for module in modules), source_path
        assert not any("PsychrometricChart" in module for module in modules), source_path
        assert not any(module.startswith(("Flet_ui", "flet", "matplotlib")) for module in modules), source_path
