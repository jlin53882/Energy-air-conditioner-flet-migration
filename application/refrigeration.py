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
from domain.thermodynamics.thermo_policy import (
    CalculationModel,
    ResolvedThermoPolicy,
    Workflow,
    resolve_thermo_policy,
)

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
    def resolve(fluid: str, requested: str | None) -> ResolvedThermoPolicy:
        """解析冷凍工作流的模型與基準快照（真實流體；Auto 依集中規則）。

UI 應在建立 request 前呼叫一次，把 ``policy.reference_state`` 放入 request，並以同一份
快照顯示實際模型、基準與決策原因。

參數：
    fluid: 流體名稱（可為 CoolProp 別名）。
    requested: 使用者要求的基準，可為 None 或 "Auto"。

回傳：
    ResolvedThermoPolicy。

引發：
    ThermoPolicyError（ValueError）：流體不存在、手動基準不支援或要求 CURRENT 時。"""
        return resolve_thermo_policy(
            fluid,
            # 冷凍工作流不帶濕度條件，Auto 模型即 CoolProp 真實流體。
            model=CalculationModel.AUTO,
            reference=requested,
            workflow=Workflow.REFRIGERATION,
        )

    @classmethod
    def resolve_policy(cls, fluid: str, requested: str | None) -> str:
        """回傳本次 request 使用的明確 policy code（見 :meth:`resolve`）。

參數：
    fluid: 流體名稱。
    requested: 使用者要求的 policy，可為 None 或 "Auto"。

回傳：
    正規化後的 policy code。

引發：
    ValueError：要求 CURRENT、不支援的 policy，或流體不支援手動指定的 policy 時。"""
        policy = cls.resolve(fluid, requested)
        assert policy.reference_state is not None
        return policy.reference_state

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
