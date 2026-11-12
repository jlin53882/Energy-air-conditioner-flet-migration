"""提供中立 thermodynamic property query 的 application service。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.psychrometrics.service import PsychrometricService
from domain.thermodynamics.reference_state import normalize_reference_state_policy
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.thermodynamics.thermo_policy import (
    CalculationModel,
    ResolvedThermoPolicy,
    ThermoPolicyError,
    Workflow,
    resolve_thermo_policy,
)

from .models import HumidAirQueryRequest, PropertyQueryRequest


@dataclass(frozen=True)
class PropertyQueryResult:
    """一次查詢的結果與其模型／基準解析快照。

    屬性：
        values: canonical SI 結果；理想氣體不含 ``S``；濕空氣為 PsychrometricService 的結果 dict。
        policy: 本次 request 唯一一次解析的模型與基準。
    """

    values: dict[str, Any]
    policy: ResolvedThermoPolicy


class PropertyQueryService:
    """驗證並協調 property request，不依賴 channel concern。"""

    def __init__(
        self,
        state_service: ThermodynamicStateService,
        psychrometric_service: PsychrometricService | None = None,
    ) -> None:
        """使用明確的 shared thermodynamic service 初始化。

參數：
    state_service (ThermodynamicStateService): 純流體／理想氣體計算服務。
    psychrometric_service: 濕空氣計算服務；未提供時濕空氣查詢會明確失敗。

回傳：
    無。"""
        self.state_service = state_service
        self.psychrometric_service = psychrometric_service
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

    def resolve(self, request: PropertyQueryRequest) -> ResolvedThermoPolicy:
        """解析 request 的模型與基準（不計算）。

參數：
    request: 查詢 request。

回傳：
    ResolvedThermoPolicy。

引發：
    ThermoPolicyError（ValueError）：流體、模型或基準無法解析時。"""
        model = request.model
        reference = request.reference_state
        if model is None:
            model = CalculationModel.IDEAL_GAS if request.is_ideal_gas else CalculationModel.AUTO
            if request.is_ideal_gas:
                # 舊語意：is_ideal_gas=True 時 reference_state（預設 DEF）一律被忽略，
                # 理想氣體沒有 CoolProp reference state。
                reference = None
        elif request.is_ideal_gas and str(model) not in (CalculationModel.IDEAL_GAS, "ideal_gas"):
            raise ThermoPolicyError("is_ideal_gas 與 model 互相矛盾。")
        return resolve_thermo_policy(
            request.fluid,
            model=model,
            reference=reference,
            workflow=Workflow.PROPERTY_QUERY,
        )

    def query_with_policy(self, request: PropertyQueryRequest) -> PropertyQueryResult:
        """驗證 request、解析一次模型與基準，並在該快照下計算。

參數：
    request: 查詢 request。

回傳：
    PropertyQueryResult。

引發：
    ValueError：輸入或模型／基準無效時。
    RuntimeError：CoolProp 無法計算時。"""
        if not request.fluid.strip():
            raise ValueError("fluid is required")
        if len(request.known_properties) < 2:
            raise ValueError("at least two known properties are required")
        policy = self.resolve(request)
        if policy.model is CalculationModel.HUMID_AIR:  # pragma: no cover - resolve 不會在無濕度條件時路由
            raise ThermoPolicyError("濕空氣查詢請使用 query_humid_air。")
        is_ideal = policy.model is CalculationModel.IDEAL_GAS
        if policy.reference_state is not None:
            self._requested_reference_states[request.fluid.strip().casefold()] = policy.reference_state
        values = self.state_service.calculate_properties(
            request.fluid.strip(),
            request.known_properties,
            is_ideal,
            policy.reference_state or "DEF",
        )
        return PropertyQueryResult(values=values, policy=policy)

    def query(self, request: PropertyQueryRequest) -> dict[str, float | str]:
        """驗證 request 並回傳中立 thermodynamic result（見 :meth:`query_with_policy`）。

參數：
    request (PropertyQueryRequest): 函數輸入值。

回傳：
    dict[str, float | str]：函數計算或處理後的結果。"""
        return self.query_with_policy(request).values

    def query_humid_air(self, request: HumidAirQueryRequest) -> PropertyQueryResult:
        """以既有 PsychrometricService 計算濕空氣狀態（焓為每 kg 乾空氣）。

參數：
    request: 濕空氣 request；乾球溫度之外必須且只能提供一個濕度條件。

回傳：
    PropertyQueryResult；values 含 ``RH``（0–1）、``W``（kg/kg_dry_air）、``H``（J/kg_dry_air）、
    ``V``（m³/kg_dry_air）、``P``（Pa，絕對）等。

引發：
    ValueError：濕度條件缺漏、重複或超出範圍，或未設定濕空氣服務時。"""
        given = [
            name
            for name, value in (
                ("RH", request.relative_humidity),
                ("Twb", request.wet_bulb_k),
                ("W", request.humidity_ratio),
            )
            if value is not None
        ]
        if len(given) != 1:
            raise ThermoPolicyError(
                "濕空氣狀態需要乾球溫度，加上 RH、濕球溫度或濕度比其中「一個」條件"
                f"（目前提供：{'、'.join(given) or '無'}）。"
            )
        policy = resolve_thermo_policy(
            request.fluid,
            model=CalculationModel.HUMID_AIR,
            reference=None,
            workflow=Workflow.PROPERTY_QUERY,
            humidity_specified=True,
        )
        if self.psychrometric_service is None:
            raise ValueError("未設定濕空氣計算服務。")
        if not request.dry_bulb_k > 0:
            raise ValueError("乾球溫度必須大於 0 K。")
        service = self.psychrometric_service
        if request.relative_humidity is not None:
            if not 0.0 <= request.relative_humidity <= 1.0:
                raise ValueError("相對濕度必須介於 0–1（0–100 %）。")
            values = service.calculate_from_tdb_rh(request.dry_bulb_k, request.relative_humidity, request.altitude_m)
        elif request.wet_bulb_k is not None:
            if request.wet_bulb_k > request.dry_bulb_k:
                raise ValueError("濕球溫度不可高於乾球溫度。")
            values = service.calculate_from_tdb_twb(request.dry_bulb_k, request.wet_bulb_k, request.altitude_m)
        else:
            if not request.humidity_ratio >= 0.0:
                raise ValueError("濕度比不可為負值。")
            values = service.calculate_from_tdb_w(request.dry_bulb_k, request.humidity_ratio, request.altitude_m)
        return PropertyQueryResult(values=dict(values), policy=policy)
