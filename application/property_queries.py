"""提供中立 thermodynamic property query 的 application service。"""

from __future__ import annotations

from domain.thermodynamics.reference_state import normalize_reference_state_policy
from domain.thermodynamics.state_service import ThermodynamicStateService

from .models import PropertyQueryRequest


class PropertyQueryService:
    """驗證並協調 property request，不依賴 channel concern。"""

    def __init__(self, state_service: ThermodynamicStateService) -> None:
        """使用明確的 shared thermodynamic service 初始化。

參數：
    state_service (ThermodynamicStateService): 函數輸入值。

回傳：
    無。"""
        self.state_service = state_service
        self._requested_reference_states: dict[str, str] = {}

    def is_fluid_valid(self, fluid_name: str) -> bool:
        """透過 shared thermodynamic service 驗證流體。

參數：
    fluid_name (str): 函數輸入值。

回傳：
    bool：函數計算或處理後的結果。"""
        return self.state_service.is_fluid_valid(fluid_name)

    @property
    def reference_state(self):
        """提供由 service 擁有的 reference-state registry，供 composition 與測試使用。

回傳：
    未指定型別：函數計算或處理後的結果。"""
        return self.state_service.reference_state

    def set_reference_state(self, fluid_name: str, ref_state: str) -> None:
        """透過 shared service 套用並記錄要求的 policy。

參數：
    fluid_name (str): 函數輸入值。
    ref_state (str): 函數輸入值。

回傳：
    無。"""
        normalized_fluid = fluid_name.strip()
        normalized_policy = normalize_reference_state_policy(ref_state)
        if normalized_policy == "CURRENT":
            raise ValueError("CURRENT cannot be stored as an application requested policy")
        self.state_service.set_reference_state(normalized_fluid, normalized_policy)
        self._requested_reference_states[normalized_fluid.casefold()] = normalized_policy

    def requested_reference_state(
        self, fluid_name: str, default: str = "ASHRAE"
    ) -> str:
        """回傳 application 擁有的流體要求 policy。

        這不同於 `ReferenceStateService.current()` 回報的觀察到 process state；
        此方法回傳的是使用者要求的 policy。
        """
        normalized_default = normalize_reference_state_policy(default)
        if normalized_default == "CURRENT":
            raise ValueError("CURRENT cannot be used as an application requested policy")
        return self._requested_reference_states.get(
            fluid_name.strip().casefold(), normalized_default
        )

    def query(self, request: PropertyQueryRequest) -> dict[str, float | str]:
        """驗證 request 並回傳中立 thermodynamic result。

參數：
    request (PropertyQueryRequest): 函數輸入值。

回傳：
    dict[str, float | str]：函數計算或處理後的結果。"""
        if not request.fluid.strip():
            raise ValueError("fluid is required")
        if len(request.known_properties) < 2:
            raise ValueError("at least two known properties are required")
        normalized_policy = normalize_reference_state_policy(request.reference_state)
        if normalized_policy == "CURRENT":
            raise ValueError("CURRENT cannot be used as an application requested policy")
        self._requested_reference_states[request.fluid.strip().casefold()] = normalized_policy
        return self.state_service.calculate_properties(
            request.fluid.strip(),
            request.known_properties,
            request.is_ideal_gas,
            normalized_policy,
        )
