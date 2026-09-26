"""冷凍循環與冷媒飽和狀態的 domain 計算。"""

from .condenser_exergy import (
    CondenserExergyBalance,
    CondenserExergyResult,
    analyze_condenser_exergy,
    condenser_exergy_balance,
    coolant_mean_temperature_k,
)
from .saturation import (
    SaturationCheckResult,
    SaturationPropertiesResult,
    evaluate_superheat_subcooling,
    saturation_properties,
)
from .states import ThermodynamicStateProvider
from .vapor_compression import (
    VaporCompressionInputs,
    VaporCompressionResult,
    solve_vapor_compression_cycle,
)

__all__ = [
    "CondenserExergyBalance",
    "CondenserExergyResult",
    "SaturationCheckResult",
    "SaturationPropertiesResult",
    "ThermodynamicStateProvider",
    "VaporCompressionInputs",
    "VaporCompressionResult",
    "analyze_condenser_exergy",
    "condenser_exergy_balance",
    "coolant_mean_temperature_k",
    "evaluate_superheat_subcooling",
    "saturation_properties",
    "solve_vapor_compression_cycle",
]
