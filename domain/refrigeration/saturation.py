"""冷媒飽和性質與現場過熱度／過冷度判讀。

露點（飽和蒸氣，Q = 1）用於計算過熱度，泡點（飽和液體，Q = 0）用於計算過冷度；
非共沸冷媒兩者差值即為溫度滑移。所有量為 canonical SI，飽和狀態以
:class:`~domain.state_points.ThermoStatePoint` 表示。
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.state_points import StateSource, ThermoStatePoint, enthalpy_difference
from domain.thermodynamics.reference_state import ReferenceStatePolicy, normalize_reference_state_policy

from .states import StateAmbiguityError, ThermodynamicStateProvider, query_state

REGION_SUPERHEATED = "superheated_vapor"
REGION_SUBCOOLED = "subcooled_liquid"
REGION_TWO_PHASE = "two_phase"

KNOWN_PRESSURE = "pressure"
KNOWN_TEMPERATURE = "temperature"


@dataclass(frozen=True)
class SaturationPropertiesResult:
    """已知壓力或已知溫度下的飽和液體（泡點）與飽和蒸氣（露點）狀態。

    已知壓力時兩個狀態壓力相同，溫度差即溫度滑移；已知溫度時兩個狀態溫度相同，
    壓力差為泡點與露點壓力差。純冷媒的兩者皆約為 0。

    蒸發潛熱只在已知壓力時提供：非共沸冷媒在同一溫度下的泡點與露點壓力不同，
    兩個不同壓力狀態的焓差不是潛熱。
    """

    fluid: str
    known: str
    liquid: ThermoStatePoint
    vapor: ThermoStatePoint

    @property
    def reference_state(self) -> str:
        """求解時實際使用的 reference-state policy code。

回傳：
    policy code。"""
        return self.liquid.reference_state

    @property
    def latent_heat_j_kg(self) -> float | None:
        """同壓下飽和液→飽和蒸氣的焓差 h_vapor − h_liquid（J/kg），經基準防護相減。

只有已知壓力時兩個狀態同壓，焓差才是蒸發潛熱；已知溫度時（非共沸冷媒的泡點與
露點壓力不同）不提供，回傳 None。

回傳：
    潛熱；已知溫度時為 None。"""
        if self.known != KNOWN_PRESSURE:
            return None
        return enthalpy_difference(self.vapor, self.liquid)

    @property
    def temperature_glide_k(self) -> float:
        """溫度滑移：露點溫度 − 泡點溫度（K）。

回傳：
    溫度差。"""
        return self.vapor.temperature_k - self.liquid.temperature_k

    @property
    def pressure_difference_pa(self) -> float:
        """泡點壓力 − 露點壓力（Pa）；已知溫度時的非共沸差異。

回傳：
    壓力差。"""
        return self.liquid.pressure_pa - self.vapor.pressure_pa


def saturation_properties(
    provider: ThermodynamicStateProvider,
    fluid: str,
    *,
    pressure_pa: float | None = None,
    temperature_k: float | None = None,
    reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.ASHRAE,
) -> SaturationPropertiesResult:
    """以已知絕對壓力或已知溫度（擇一）計算飽和液體與飽和蒸氣狀態。

參數：
    provider: canonical SI 狀態服務。
    fluid: CoolProp 流體名稱。
    pressure_pa: 已知絕對壓力（Pa）。
    temperature_k: 已知飽和溫度（K）。
    reference_state: 已解析的 reference-state policy；決定焓、熵的基準。

回傳：
    SaturationPropertiesResult。

引發：
    ValueError：流體空白、壓力與溫度未恰好提供一個、數值不為正，或超出飽和範圍
    （例如高於臨界點）時。"""
    fluid = fluid.strip()
    if not fluid:
        raise ValueError("請輸入冷媒名稱。")
    if (pressure_pa is None) == (temperature_k is None):
        raise ValueError("請只提供飽和壓力或飽和溫度其中一個。")
    if pressure_pa is not None:
        if pressure_pa <= 0:
            raise ValueError("壓力必須是大於 0 的絕對壓力。")
        known, known_property = KNOWN_PRESSURE, ("P", pressure_pa)
    else:
        if temperature_k <= 0:
            raise ValueError("溫度必須是大於 0 的絕對溫度。")
        known, known_property = KNOWN_TEMPERATURE, ("T", temperature_k)
    resolved_policy = normalize_reference_state_policy(reference_state)

    def point(quality: float, key: str, label: str) -> ThermoStatePoint:
        """查詢一個飽和狀態並包成狀態點。

參數：
    quality: 乾度（0 或 1）。
    key: 狀態鍵。
    label: 顯示名稱。

回傳：
    ThermoStatePoint。"""
        state = query_state(provider, fluid, [known_property, ("Q", quality)], reference_state, label)
        return ThermoStatePoint.from_state_mapping(
            state, fluid=fluid, reference_state=resolved_policy, source=StateSource.SATURATION,
            key=key, label=label,
        )

    return SaturationPropertiesResult(
        fluid=fluid,
        known=known,
        liquid=point(0.0, "liquid", "飽和液體（泡點）"),
        vapor=point(1.0, "vapor", "飽和蒸氣（露點）"),
    )


@dataclass(frozen=True)
class SaturationCheckResult:
    """量測點相對於飽和狀態的判讀。

    ``dew_state``／``bubble_state`` 是量測壓力下的飽和蒸氣與飽和液體狀態點；
    ``measured_state`` 是量測壓力與管溫對應的狀態點，量測點落在兩相區，或壓力與溫度
    落在飽和邊界而無法唯一決定狀態（``StateAmbiguityError``）時為 None；其他查詢失敗
    （``StateQueryError``）與狀態資料不合法（``ValueError``）照常引發，不降級為 None。
    """

    fluid: str
    pressure_pa: float
    measured_temperature_k: float
    region: str
    superheat_k: float | None
    subcooling_k: float | None
    dew_state: ThermoStatePoint
    bubble_state: ThermoStatePoint
    measured_state: ThermoStatePoint | None

    @property
    def dew_point_k(self) -> float:
        """露點（飽和蒸氣）溫度（K）。

回傳：
    溫度。"""
        return self.dew_state.temperature_k

    @property
    def bubble_point_k(self) -> float:
        """泡點（飽和液體）溫度（K）。

回傳：
    溫度。"""
        return self.bubble_state.temperature_k

    @property
    def temperature_glide_k(self) -> float:
        """回傳相變溫度滑移（露點 − 泡點）。

回傳：
    溫度滑移（K）；純冷媒約為 0。"""
        return self.dew_point_k - self.bubble_point_k

    @property
    def reference_state(self) -> str:
        """狀態點使用的 reference-state policy code。

回傳：
    policy code。"""
        return self.dew_state.reference_state


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
    reference_state: reference-state policy（飽和溫度與此無關，只影響狀態點的焓、熵基準）。

回傳：
    判讀結果。

引發：
    ValueError：壓力或溫度不為正，或壓力超出飽和範圍（例如高於臨界壓力）時。"""
    fluid = fluid.strip()
    if not fluid:
        raise ValueError("請輸入冷媒名稱。")
    if pressure_pa <= 0 or measured_temperature_k <= 0:
        raise ValueError("壓力與溫度必須是有效的絕對值（壓力請使用絕對壓力）。")
    resolved_policy = normalize_reference_state_policy(reference_state)

    def point(state, key: str, label: str) -> ThermoStatePoint:
        """把查詢結果包成判讀用的狀態點。

參數：
    state: 狀態服務回傳的 dict。
    key: 狀態鍵。
    label: 顯示名稱。

回傳：
    ThermoStatePoint。"""
        return ThermoStatePoint.from_state_mapping(
            state, fluid=fluid, reference_state=resolved_policy, source=StateSource.SUPERHEAT_CHECK,
            key=key, label=label,
        )

    dew_state = point(query_state(provider, fluid, [("P", pressure_pa), ("Q", 1.0)], reference_state,
                                  "露點飽和溫度"), "dew", "露點（飽和蒸氣）")
    bubble_state = point(query_state(provider, fluid, [("P", pressure_pa), ("Q", 0.0)], reference_state,
                                     "泡點飽和溫度"), "bubble", "泡點（飽和液體）")
    dew_k, bubble_k = dew_state.temperature_k, bubble_state.temperature_k
    if measured_temperature_k > dew_k:
        region, superheat, subcooling = REGION_SUPERHEATED, measured_temperature_k - dew_k, None
    elif measured_temperature_k < bubble_k:
        region, superheat, subcooling = REGION_SUBCOOLED, None, bubble_k - measured_temperature_k
    else:
        region, superheat, subcooling = REGION_TWO_PHASE, None, None
    measured_state = None
    if region != REGION_TWO_PHASE:
        try:
            measured_mapping = query_state(
                provider, fluid, [("P", pressure_pa), ("T", measured_temperature_k)], reference_state,
                "量測狀態")
        except StateAmbiguityError:
            # 只容許壓力與溫度落在飽和邊界、無法唯一決定狀態；判讀結果不受影響。
            # 其他查詢失敗（StateQueryError）與狀態資料不合法（ValueError）照常引發。
            measured_mapping = None
        if measured_mapping is not None:
            measured_state = point(measured_mapping, "measured", "量測點")
    return SaturationCheckResult(
        fluid=fluid,
        pressure_pa=pressure_pa,
        measured_temperature_k=measured_temperature_k,
        region=region,
        superheat_k=superheat,
        subcooling_k=subcooling,
        dew_state=dew_state,
        bubble_state=bubble_state,
        measured_state=measured_state,
    )
