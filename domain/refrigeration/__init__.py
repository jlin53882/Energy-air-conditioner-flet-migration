"""冷凍循環與冷媒飽和狀態的 domain 計算。"""

from .saturation import SaturationCheckResult, evaluate_superheat_subcooling
from .states import CycleState, ThermodynamicStateProvider
from .vapor_compression import (
    VaporCompressionInputs,
    VaporCompressionResult,
    solve_vapor_compression_cycle,
)

__all__ = [
    "CycleState",
    "SaturationCheckResult",
    "ThermodynamicStateProvider",
    "VaporCompressionInputs",
    "VaporCompressionResult",
    "evaluate_superheat_subcooling",
    "solve_vapor_compression_cycle",
]
