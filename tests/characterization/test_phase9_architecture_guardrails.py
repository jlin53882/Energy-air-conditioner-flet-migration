"""Phase 9 architecture guardrails."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[2]


def _python_sources(relative_dir: str) -> list[Path]:
    """Return Python source files under a project layer."""
    return sorted((ROOT / relative_dir).rglob("*.py"))


def _imports(source_path: Path) -> set[str]:
    """Extract imported module names without matching display strings."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_has_no_channel_or_rendering_imports() -> None:
    """Domain code remains independent of Flet, Telegram, and Matplotlib UI."""
    forbidden_prefixes = ("flet", "telegram", "matplotlib")
    for source_path in _python_sources("domain"):
        assert not any(
            module == prefix or module.startswith(f"{prefix}.")
            for module in _imports(source_path)
            for prefix in forbidden_prefixes
        ), source_path


def test_application_has_no_channel_object_dependencies() -> None:
    """Application services do not accept channel controls or updates."""
    forbidden_prefixes = ("flet", "telegram")
    for source_path in _python_sources("application"):
        assert not any(
            module == prefix or module.startswith(f"{prefix}.")
            for module in _imports(source_path)
            for prefix in forbidden_prefixes
        ), source_path


def test_selected_adapters_do_not_call_coolprop_directly() -> None:
    """Migrated adapters use services instead of direct property queries."""
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
