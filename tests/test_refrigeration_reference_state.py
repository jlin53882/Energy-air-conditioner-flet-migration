"""冷凍循環的 reference-state 只解析一次：求解與 P-h 圖使用同一個 policy。"""

from __future__ import annotations

import pytest

from application.models import RefrigerationCycleRequest
from application.refrigeration import RefrigerationService
from domain.refrigeration import VaporCompressionInputs, solve_vapor_compression_cycle
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter
from Flet_ui.ui_components.analysis_modules import refrigeration_cycle_module
from Flet_ui.ui_components.analysis_modules.refrigeration_cycle_module import RefrigerationCycleModule
from Flet_ui.ui_components.unit.UnitConverter import UnitConverter


class DummyPage:
    """提供模組建構所需的最小 page 介面。"""

    def __init__(self) -> None:
        """初始化 overlay。

回傳：
    無。"""
        self.overlay = []

    def update(self) -> None:
        """接受更新呼叫。

回傳：
    無。"""


def _state_service() -> ThermodynamicStateService:
    """建立 canonical SI 狀態服務。

回傳：
    ThermodynamicStateService。"""
    return ThermodynamicStateService(CanonicalUnitConverter())


@pytest.mark.parametrize("policy", ["ASHRAE", "NBP", "IIR"])
def test_cycle_result_carries_the_policy_used_by_the_solver(policy) -> None:
    """domain 結果攜帶求解時實際使用的 policy code。

參數：
    policy: 要求使用的 reference-state policy。

回傳：
    無。"""
    result = solve_vapor_compression_cycle(
        _state_service(),
        VaporCompressionInputs("R134a", 263.15, 313.15, 5.0, 5.0, 0.7, reference_state=policy),
    )

    assert result.reference_state == policy


def test_application_resolves_auto_once_and_reports_it() -> None:
    """application 解析 Auto 後，結果的 policy 就是解析值。

回傳：
    無。"""
    service = RefrigerationService(_state_service())

    result = service.solve_cycle(RefrigerationCycleRequest("R32", 278.15, 318.15, 5.0, 5.0, 0.7, 10_000.0))

    assert result.reference_state == service.resolve_policy("R32", None)
    assert result.reference_state != "Auto"


class ForcedPolicyService(RefrigerationService):
    """把 policy 固定為 NBP，模擬與 Auto 解析結果不同的 policy。"""

    @staticmethod
    def resolve_policy(fluid: str, requested: str | None) -> str:
        """忽略要求，固定回傳 NBP。

參數：
    fluid: 流體名稱。
    requested: 要求的 policy。

回傳：
    "NBP"。"""
        return "NBP"


def test_ph_chart_uses_the_solver_policy_not_auto(monkeypatch) -> None:
    """P-h 圖收到的 policy 必須是求解實際使用的 policy，而不是重新解析的 Auto。

回傳：
    無。"""
    received: list[str] = []

    def spy_generate_thermo_diagram(**kwargs) -> str:
        """記錄圖表收到的 reference-state。

參數：
    kwargs: generate_thermo_diagram 的參數。

回傳：
    成功訊息。"""
        received.append(kwargs["ref_state"])
        return "ok"

    monkeypatch.setattr(refrigeration_cycle_module, "generate_thermo_diagram", spy_generate_thermo_diagram)
    service = ForcedPolicyService(_state_service())
    module = RefrigerationCycleModule(UnitConverter(), DummyPage(), service)
    assert service.resolve_policy("R32", None) != RefrigerationService.resolve_policy("R32", None)

    module.calculate_cycle(False)

    assert received == ["NBP"]
