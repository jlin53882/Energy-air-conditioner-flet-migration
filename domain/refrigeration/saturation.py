"""由量測壓力與溫度判斷冷媒過熱度／過冷度（現場檢修常用）。

露點（飽和蒸氣，Q = 1）用於計算過熱度，泡點（飽和液體，Q = 0）用於計算過冷度；
非共沸冷媒兩者差值即為溫度滑移。所有量為 canonical SI。
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.thermodynamics.reference_state import ReferenceStatePolicy

from .states import ThermodynamicStateProvider, query_state

REGION_SUPERHEATED = "superheated_vapor"
REGION_SUBCOOLED = "subcooled_liquid"
REGION_TWO_PHASE = "two_phase"


@dataclass(frozen=True)
class SaturationCheckResult:
    """量測點相對於飽和狀態的判讀。"""

    fluid: str
    pressure_pa: float
    measured_temperature_k: float
    dew_point_k: float
    bubble_point_k: float
    region: str
    superheat_k: float | None
    subcooling_k: float | None

    @property
    def temperature_glide_k(self) -> float:
        """回傳相變溫度滑移（露點 − 泡點）。

回傳：
    溫度滑移（K）；純冷媒約為 0。"""
        return self.dew_point_k - self.bubble_point_k


def evaluate_superheat_subcooling(
    provider: ThermodynamicStateProvider,
    fluid: str,
    pressure_pa: float,
    measured_temperature_k: float,
    reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT,
) -> SaturationCheckResult:
    """依量測壓力與溫度判斷過熱、過冷或兩相，並計算過熱度／過冷度。

參數：
    provider: canonical SI 狀態服務。
    fluid: CoolProp 流體名稱。
    pressure_pa: 量測絕對壓力（Pa）。
    measured_temperature_k: 量測管溫（K）。
    reference_state: reference-state policy（飽和溫度與此無關，只影響查詢交易）。

回傳：
    判讀結果。

引發：
    ValueError：壓力或溫度不為正，或壓力超出飽和範圍（例如高於臨界壓力）時。"""
    fluid = fluid.strip()
    if not fluid:
        raise ValueError("請輸入冷媒名稱。")
    if pressure_pa <= 0 or measured_temperature_k <= 0:
        raise ValueError("壓力與溫度必須是有效的絕對值（壓力請使用絕對壓力）。")
    dew = query_state(provider, fluid, [("P", pressure_pa), ("Q", 1.0)], reference_state, "露點飽和溫度")
    bubble = query_state(provider, fluid, [("P", pressure_pa), ("Q", 0.0)], reference_state, "泡點飽和溫度")
    dew_k, bubble_k = float(dew["T"]), float(bubble["T"])
    if measured_temperature_k > dew_k:
        region, superheat, subcooling = REGION_SUPERHEATED, measured_temperature_k - dew_k, None
    elif measured_temperature_k < bubble_k:
        region, superheat, subcooling = REGION_SUBCOOLED, None, bubble_k - measured_temperature_k
    else:
        region, superheat, subcooling = REGION_TWO_PHASE, None, None
    return SaturationCheckResult(
        fluid=fluid,
        pressure_pa=pressure_pa,
        measured_temperature_k=measured_temperature_k,
        dew_point_k=dew_k,
        bubble_point_k=bubble_k,
        region=region,
        superheat_k=superheat,
        subcooling_k=subcooling,
    )
