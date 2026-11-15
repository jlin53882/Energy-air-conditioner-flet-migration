"""計算模型與 reference state 的集中解析（Auto 的唯一政策入口）。

解析分兩層，順序固定：

1. **模型層**：決定以 CoolProp 真實流體、理想氣體或濕空氣模型計算。Reference state
   不參與這一層的判斷（不以基準決定 Air 是否為濕空氣）。
2. **基準層**：只有 CoolProp 真實流體才有 reference state；理想氣體與濕空氣標示為不適用。

Auto 基準規則（不維護冷媒白名單，以 CoolProp 能力探測為準）：

* ``Water``（含 CoolProp 別名）→ ``DEF``：沿用 IAPWS-95 慣例（三相點飽和液 u = 0、s = 0）；
  IIR／ASHRAE 對水在物理上不可用（三相點 273.16 K 高於 0 °C）。
* ``Air`` 乾空氣真實流體 → ``DEF``：0 °C 與 −40 °C 都沒有飽和液，IIR／ASHRAE 不適用。
* 其他單一流體：CoolProp 支援 ``IIR``（0 °C 存在飽和液）時採 ``IIR``，即冷凍工程 SI 慣例
  （0 °C 飽和液 h = 200 kJ/kg、s = 1 kJ/(kg·K)）；不支援時改用 ``DEF``，並在
  ``fallback_reason`` 明示原因。

手動指定的基準若 CoolProp 不支援，一律引發 :class:`ThermoPolicyError`，不靜默改用其他基準。
同一個 request 只解析一次，結果 :class:`ResolvedThermoPolicy` 是不可變快照，之後的計算、
顯示、圖表與保存都使用這份快照，不再讀取 process-global 的目前基準。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .ideal_gas import IDEAL_GAS_CONSTANTS, IDEAL_GAS_ENTHALPY_BASIS
from .reference_state import (
    ReferenceStatePolicy,
    ReferenceStateService,
    canonical_fluid_name,
    coolprop_version,
    normalize_reference_state_policy,
)

AUTO = "Auto"

WATER = "Water"
AIR = "Air"


class ThermoPolicyError(ValueError):
    """模型或基準無法依要求解析（流體不存在、手動基準不支援、模型不相容等）。"""


class CalculationModel(str, Enum):
    """計算模型。``AUTO`` 只能出現在要求端，解析結果一定是具體模型。"""

    AUTO = "auto"
    REAL_FLUID = "real_fluid"
    IDEAL_GAS = "ideal_gas"
    HUMID_AIR = "humid_air"


class Workflow(str, Enum):
    """發出 request 的工作流程；記錄在解析結果中供追溯，不改變 Auto 基準規則。"""

    PROPERTY_QUERY = "property_query"
    REFRIGERATION = "refrigeration"
    CHART = "chart"
    BATCH = "batch"
    LEGACY = "legacy"


class PropertyBasis(str, Enum):
    """比性質的質量基準。"""

    PER_KG = "per_kg"
    PER_KG_DRY_AIR = "per_kg_dry_air"


MODEL_LABELS = {
    CalculationModel.AUTO: "Auto（推薦）",
    CalculationModel.REAL_FLUID: "真實流體（CoolProp）",
    CalculationModel.IDEAL_GAS: "理想氣體（常數 cp）",
    CalculationModel.HUMID_AIR: "濕空氣（Psychrometrics）",
}

PROPERTY_BASIS_LABELS = {
    PropertyBasis.PER_KG: "每 kg 工質（kJ/kg）",
    PropertyBasis.PER_KG_DRY_AIR: "每 kg 乾空氣（kJ/kg_dry_air）",
}

REFERENCE_STATE_DESCRIPTIONS = {
    "IIR": "0 °C 飽和液體 h = 200 kJ/kg、s = 1 kJ/(kg·K)",
    "ASHRAE": "−40 °C 飽和液體 h = 0、s = 0",
    "NBP": "正常沸點（101.325 kPa）飽和液體 h = 0、s = 0",
    "DEF": "CoolProp 該流體狀態方程的預設基準（各流體不同）",
}

HUMID_AIR_BASIS = "濕空氣焓以 0 °C 乾空氣與 0 °C 飽和液態水為零點（ASHRAE psychrometrics），每 kg 乾空氣"


@dataclass(frozen=True)
class ResolvedThermoPolicy:
    """一次 request 的模型與基準解析快照。

    屬性：
        fluid: 使用者輸入的流體名稱（去除前後空白）；計算時傳給 CoolProp 的仍是此名稱。
        canonical_fluid: CoolProp canonical 名稱（別名已解析）；濕空氣為 ``Air``。
        workflow: 發出 request 的工作流程。
        requested_model: 使用者要求的模型（可為 ``AUTO``）。
        model: 實際計算模型（不會是 ``AUTO``）。
        requested_reference: 使用者要求的基準（``Auto`` 或 policy code）。
        reference_state: 實際 CoolProp reference state code；模型不適用時為 None。
        reason: 模型與基準的決策原因。
        fallback_reason: Auto 改用備援基準的原因；沒有備援時為空字串。
        property_basis: 比性質的質量基準。
        backend: 實際計算後端說明。
        library_version: CoolProp 版本。
    """

    fluid: str
    canonical_fluid: str
    workflow: Workflow
    requested_model: CalculationModel
    model: CalculationModel
    requested_reference: str
    reference_state: str | None
    reason: str
    fallback_reason: str
    property_basis: PropertyBasis
    backend: str
    library_version: str

    @property
    def is_auto_reference(self) -> bool:
        """基準是否由 Auto 解析。"""
        return self.requested_reference == AUTO

    @property
    def is_ideal_gas(self) -> bool:
        """是否為理想氣體模型。"""
        return self.model is CalculationModel.IDEAL_GAS

    @property
    def model_label(self) -> str:
        """實際模型的顯示名稱。"""
        if self.model is CalculationModel.REAL_FLUID and self.canonical_fluid == AIR:
            return "乾空氣真實流體（CoolProp）"
        return MODEL_LABELS[self.model]

    @property
    def reference_label(self) -> str:
        """實際基準的顯示文字，例如 ``IIR（Auto）`` 或 ``不適用``。"""
        if self.reference_state is None:
            return "不適用"
        suffix = "（Auto）" if self.is_auto_reference else "（手動）"
        return f"{self.reference_state}{suffix}"

    @property
    def enthalpy_basis(self) -> str:
        """焓、熵零點的說明。"""
        if self.model is CalculationModel.IDEAL_GAS:
            return IDEAL_GAS_ENTHALPY_BASIS
        if self.model is CalculationModel.HUMID_AIR:
            return HUMID_AIR_BASIS
        return REFERENCE_STATE_DESCRIPTIONS.get(self.reference_state or "", "")

    def summary_rows(self) -> tuple[tuple[str, str], ...]:
        """供結果卡片、匯出文字使用的 (名稱, 值) 列。"""
        rows = [
            ("計算模型", self.model_label),
            ("參考基準", self.reference_label),
            ("焓／熵基準", self.enthalpy_basis),
            ("比性質基準", PROPERTY_BASIS_LABELS[self.property_basis]),
            ("決策原因", self.reason),
        ]
        if self.fallback_reason:
            rows.append(("備援說明", self.fallback_reason))
        rows.append(("計算後端", self.backend))
        return tuple(rows)


def normalize_reference_selection(requested: object) -> str:
    """把使用者的基準選擇正規化為 ``Auto`` 或明確 policy code。

參數：
    requested: None、``Auto``（不分大小寫）、``Default``、policy code 或列舉。

回傳：
    ``Auto``、``DEF``、``ASHRAE``、``IIR`` 或 ``NBP``。

引發：
    ThermoPolicyError：無效值或 ``CURRENT``。"""
    if requested is None:
        return AUTO
    if isinstance(requested, str) and requested.strip().casefold() == AUTO.casefold():
        return AUTO
    if not isinstance(requested, (str, ReferenceStatePolicy)):
        raise ThermoPolicyError(f"不支援的參考基準：{requested!r}")
    try:
        code = normalize_reference_state_policy(requested)
    except ValueError:
        raise ThermoPolicyError(f"不支援的參考基準：{requested!r}") from None
    if code == ReferenceStatePolicy.CURRENT.value:
        raise ThermoPolicyError("CURRENT 不能作為 request 的參考基準；請選 Auto 或明確基準。")
    return code


def normalize_model_selection(requested: object) -> CalculationModel:
    """把模型選擇正規化為 :class:`CalculationModel`。

引發：
    ThermoPolicyError：無效值。"""
    if requested is None:
        return CalculationModel.AUTO
    if isinstance(requested, CalculationModel):
        return requested
    try:
        return CalculationModel(str(requested).strip().casefold())
    except ValueError:
        raise ThermoPolicyError(f"不支援的計算模型：{requested!r}") from None


class ThermoPolicyResolver:
    """以 CoolProp 能力探測解析模型與基準；能力結果由 :class:`ReferenceStateService` 快取。"""

    def __init__(self, reference_state: ReferenceStateService | None = None) -> None:
        self.reference_state = reference_state or ReferenceStateService()

    def resolve(
        self,
        fluid: str,
        *,
        model: CalculationModel | str | None = None,
        reference: object = None,
        workflow: Workflow = Workflow.PROPERTY_QUERY,
        humidity_specified: bool = False,
    ) -> ResolvedThermoPolicy:
        """解析一次 request 的模型與基準。

參數：
    fluid: 流體名稱（可為 CoolProp 別名）。
    model: 要求的模型；None 視為 Auto。
    reference: 要求的基準；None 視為 Auto。
    workflow: 工作流程。
    humidity_specified: request 是否帶有明確且足以定義濕空氣的濕度條件（RH、Twb、W 等）。
        只有 Auto + Air + 此旗標為 True 才會自動路由到濕空氣模型。

回傳：
    ResolvedThermoPolicy。

引發：
    ThermoPolicyError：流體空白／不存在、模型不相容、手動基準不支援時。"""
        name = (fluid or "").strip()
        if not name:
            raise ThermoPolicyError("請輸入流體名稱。")
        requested_model = normalize_model_selection(model)
        requested_reference = normalize_reference_selection(reference)
        canonical = canonical_fluid_name(name)
        if canonical is None:
            raise ThermoPolicyError(
                f"CoolProp 找不到單一流體 '{name}'（混合物字串不支援 reference state 解析）。"
            )
        version = coolprop_version()

        resolved_model, model_reason = self._resolve_model(
            name, canonical, requested_model, humidity_specified
        )
        common = dict(
            fluid=name,
            canonical_fluid=canonical,
            workflow=workflow,
            requested_model=requested_model,
            model=resolved_model,
            requested_reference=requested_reference,
            library_version=version,
        )
        if resolved_model is not CalculationModel.REAL_FLUID:
            if requested_reference != AUTO:
                raise ThermoPolicyError(
                    f"{MODEL_LABELS[resolved_model]}沒有 CoolProp reference state；"
                    f"請將參考基準設為 Auto（目前為 {requested_reference}）。"
                )
            if resolved_model is CalculationModel.IDEAL_GAS:
                basis, backend = PropertyBasis.PER_KG, "理想氣體（常數 cp）"
            else:
                basis, backend = PropertyBasis.PER_KG_DRY_AIR, "既有 PsychrometricService（ASHRAE 濕空氣公式）"
            return ResolvedThermoPolicy(
                reference_state=None,
                reason=model_reason,
                fallback_reason="",
                property_basis=basis,
                backend=backend,
                **common,
            )

        reference_state, reference_reason, fallback = self._resolve_reference(
            name, canonical, requested_reference
        )
        return ResolvedThermoPolicy(
            reference_state=reference_state,
            reason=f"{model_reason}；{reference_reason}",
            fallback_reason=fallback,
            property_basis=PropertyBasis.PER_KG,
            backend=f"CoolProp {version} PropsSI",
            **common,
        )

    @staticmethod
    def _resolve_model(
        name: str,
        canonical: str,
        requested: CalculationModel,
        humidity_specified: bool,
    ) -> tuple[CalculationModel, str]:
        """解析模型層；回傳 (模型, 原因)。"""
        if requested is CalculationModel.HUMID_AIR:
            if canonical != AIR:
                raise ThermoPolicyError(f"濕空氣模型只適用於 Air，'{name}' 不適用。")
            if not humidity_specified:
                raise ThermoPolicyError("濕空氣模型需要乾球溫度與 RH、濕球溫度或濕度比其中之一。")
            return CalculationModel.HUMID_AIR, "手動選擇濕空氣模型"
        if requested is CalculationModel.IDEAL_GAS:
            if humidity_specified:
                raise ThermoPolicyError("濕度條件只適用於濕空氣模型。")
            if canonical not in IDEAL_GAS_CONSTANTS:
                supported = "、".join(IDEAL_GAS_CONSTANTS)
                raise ThermoPolicyError(f"理想氣體模型目前只提供 {supported} 的常數，'{name}' 不適用。")
            return CalculationModel.IDEAL_GAS, "手動選擇理想氣體模型"
        if requested is CalculationModel.REAL_FLUID:
            if humidity_specified:
                raise ThermoPolicyError("濕度條件只適用於濕空氣模型；真實流體模型的 Air 為乾空氣。")
            return CalculationModel.REAL_FLUID, "手動選擇真實流體模型"
        # Auto
        if humidity_specified:
            if canonical != AIR:
                raise ThermoPolicyError(f"濕度條件只適用於 Air 的濕空氣模型，'{name}' 不適用。")
            return CalculationModel.HUMID_AIR, "Auto：Air 且提供明確濕度條件 → 濕空氣模型"
        if canonical == AIR:
            return CalculationModel.REAL_FLUID, "Auto：Air 未提供濕度條件 → 乾空氣真實流體（不猜測濕度）"
        return CalculationModel.REAL_FLUID, "Auto：CoolProp 真實流體"

    def _resolve_reference(
        self, name: str, canonical: str, requested: str
    ) -> tuple[str, str, str]:
        """解析基準層；回傳 (policy code, 原因, 備援說明)。"""
        if requested != AUTO:
            reason = self.reference_state.unsupported_reason(canonical, requested)
            if reason is not None:
                raise ThermoPolicyError(
                    f"{name} 不支援手動指定的參考基準 {requested}：{reason}"
                )
            return requested, f"手動指定 {requested}", ""
        if canonical == WATER:
            return (
                ReferenceStatePolicy.DEFAULT.value,
                "Auto：水沿用 IAPWS-95 慣例（DEF：三相點飽和液 u = 0、s = 0）",
                "",
            )
        if canonical == AIR:
            return (
                ReferenceStatePolicy.DEFAULT.value,
                "Auto：乾空氣沒有 0 °C 飽和液，使用 CoolProp 預設 DEF",
                "",
            )
        iir_reason = self.reference_state.unsupported_reason(canonical, ReferenceStatePolicy.IIR)
        if iir_reason is None:
            return (
                ReferenceStatePolicy.IIR.value,
                "Auto：冷凍工程 SI 慣例 IIR（0 °C 飽和液 h = 200 kJ/kg、s = 1 kJ/(kg·K)）",
                "",
            )
        def_reason = self.reference_state.unsupported_reason(canonical, ReferenceStatePolicy.DEFAULT)
        if def_reason is not None:
            raise ThermoPolicyError(f"{name} 無法設定任何 reference state：{def_reason}")
        return (
            ReferenceStatePolicy.DEFAULT.value,
            "Auto：IIR 不適用，改用 CoolProp 預設 DEF",
            f"{canonical} 不支援 IIR（{iir_reason}）；焓、熵改以 DEF 表示，不能與 IIR 表格直接比較。",
        )


_DEFAULT_RESOLVER: ThermoPolicyResolver | None = None


def default_resolver() -> ThermoPolicyResolver:
    """回傳共用的 resolver（共用 process-wide 能力快取）。"""
    global _DEFAULT_RESOLVER
    if _DEFAULT_RESOLVER is None:
        _DEFAULT_RESOLVER = ThermoPolicyResolver()
    return _DEFAULT_RESOLVER


def resolve_thermo_policy(
    fluid: str,
    *,
    model: CalculationModel | str | None = None,
    reference: object = None,
    workflow: Workflow = Workflow.PROPERTY_QUERY,
    humidity_specified: bool = False,
) -> ResolvedThermoPolicy:
    """以共用 resolver 解析（見 :meth:`ThermoPolicyResolver.resolve`）。"""
    return default_resolver().resolve(
        fluid, model=model, reference=reference, workflow=workflow, humidity_specified=humidity_specified
    )
