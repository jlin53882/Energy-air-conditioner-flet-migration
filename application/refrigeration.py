"""冷凍循環、冷媒飽和判讀與冷凝器㶲平衡的 application service。"""

from __future__ import annotations

from domain.refrigeration import (
    CondenserExergyResult,
    SaturationCheckResult,
    SaturationPropertiesResult,
    ThermodynamicStateProvider,
    VaporCompressionInputs,
    VaporCompressionResult,
    analyze_condenser_exergy,
    evaluate_superheat_subcooling,
    saturation_properties,
    solve_vapor_compression_cycle,
)
from domain.thermodynamics.fluid_policy import resolve_reference_state_policy
from domain.thermodynamics.reference_state import normalize_reference_state_policy

from .models import (
    CondenserExergyRequest,
    RefrigerationCycleRequest,
    SaturationPropertiesRequest,
    SuperheatCheckRequest,
)


class RefrigerationService:
    """決定 request 的 reference-state policy，並委派 domain 冷凍計算。"""

    def __init__(self, state_provider: ThermodynamicStateProvider) -> None:
        """以共用的 canonical SI 狀態服務初始化。

參數：
    state_provider: 例如 ThermodynamicStateService。

回傳：
    無。"""
        self.state_provider = state_provider

    @staticmethod
    def resolve_policy(fluid: str, requested: str | None) -> str:
        """回傳本次 request 使用的明確 policy；未指定或 Auto 時依流體決定。

參數：
    fluid: 流體名稱。
    requested: 使用者要求的 policy，可為 None 或 "Auto"。

回傳：
    正規化後的 policy code。

引發：
    ValueError：要求 CURRENT 或不支援的 policy 時。"""
        if requested is None or requested.strip().casefold() == "auto":
            policy = resolve_reference_state_policy(fluid)
        else:
            policy = resolve_reference_state_policy(fluid, requested)
        normalized = normalize_reference_state_policy(policy)
        if normalized == "CURRENT":
            raise ValueError("CURRENT cannot be used as an application requested policy")
        return normalized

    def solve_cycle(self, request: RefrigerationCycleRequest) -> VaporCompressionResult:
        """求解蒸氣壓縮循環。

參數：
    request: 循環 request。

回傳：
    VaporCompressionResult。"""
        return solve_vapor_compression_cycle(
            self.state_provider,
            VaporCompressionInputs(
                fluid=request.fluid,
                evaporating_temperature_k=request.evaporating_temperature_k,
                condensing_temperature_k=request.condensing_temperature_k,
                superheat_k=request.superheat_k,
                subcooling_k=request.subcooling_k,
                isentropic_efficiency=request.isentropic_efficiency,
                refrigeration_capacity_w=request.refrigeration_capacity_w,
                reference_state=self.resolve_policy(request.fluid, request.reference_state),
            ),
        )

    def saturation_properties(self, request: SaturationPropertiesRequest) -> SaturationPropertiesResult:
        """查詢飽和液體與飽和蒸氣狀態。

參數：
    request: 飽和性質 request。

回傳：
    SaturationPropertiesResult。"""
        return saturation_properties(
            self.state_provider,
            request.fluid,
            pressure_pa=request.pressure_pa,
            temperature_k=request.temperature_k,
            reference_state=self.resolve_policy(request.fluid, request.reference_state),
        )

    def check_superheat(self, request: SuperheatCheckRequest) -> SaturationCheckResult:
        """判讀量測點的過熱度／過冷度。

參數：
    request: 量測 request。

回傳：
    SaturationCheckResult。"""
        return evaluate_superheat_subcooling(
            self.state_provider,
            request.fluid,
            request.pressure_pa,
            request.measured_temperature_k,
            self.resolve_policy(request.fluid, request.reference_state),
        )

    def analyze_condenser_exergy(self, request: CondenserExergyRequest) -> CondenserExergyResult:
        """分析冷凝器的能量、熵與㶲平衡。

參數：
    request: 冷凝器㶲平衡 request。

回傳：
    CondenserExergyResult。"""
        return analyze_condenser_exergy(
            self.state_provider,
            request.fluid,
            request.pressure_pa,
            request.inlet_temperature_k,
            request.outlet_temperature_k,
            request.mass_flow_kg_s,
            request.dead_state_temperature_k,
            boundary_temperature_k=request.boundary_temperature_k,
            reference_state=self.resolve_policy(request.fluid, request.reference_state),
        )
