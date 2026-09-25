"""冷凍循環與冷媒飽和狀態的 domain 計算。"""

from .condenser_exergy import (
    CondenserExergyBalance,
    CondenserExergyResult,
    analyze_condenser_exergy,
    condenser_exergy_balance,
)
from .saturation import SaturationCheckResult, evaluate_superheat_subcooling
from .states import CycleState, ThermodynamicStateProvider
from .vapor_compression import (
    VaporCompressionInputs,
    VaporCompressionResult,
    solve_vapor_compression_cycle,
)

__all__ = [
    "CondenserExergyBalance",
    "CondenserExergyResult",
    "CycleState",
    "SaturationCheckResult",
    "ThermodynamicStateProvider",
    "VaporCompressionInputs",
    "VaporCompressionResult",
    "analyze_condenser_exergy",
    "condenser_exergy_balance",
    "evaluate_superheat_subcooling",
    "solve_vapor_compression_cycle",
]
