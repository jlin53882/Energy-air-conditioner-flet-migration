"""Headless thermodynamic property 的計算服務。"""

from __future__ import annotations

from typing import Iterable, Sequence

import CoolProp.CoolProp as CP

from domain.units.converter import CanonicalUnitConverter
from .reference_state import ReferenceStatePolicy, ReferenceStateService


KnownProperty = tuple[str, float, str]

# 壓力與溫度落在飽和邊界的判定容差（相對壓力差）。CoolProp 在 |p_sat(T) − p| / p 小於
# 1e-6（「within 1e-4 %」）時拒絕以 (P, T) 求解；此處放寬為 1e-5，只作為失敗後的分類依據。
PT_SATURATION_RELATIVE_TOLERANCE = 1e-5


class IndeterminateStateError(RuntimeError):
    """已知性質無法唯一決定狀態：目前只有「壓力與溫度落在飽和邊界」一種。

    繼承 ``RuntimeError``，維持狀態服務「無法計算時引發 RuntimeError」的既有契約；
    其他計算失敗仍是一般 ``RuntimeError``。
    """


class CoolPropStateCalculationError(RuntimeError):
    """CoolProp 無法由已知性質求出熱力狀態（內部使用）。

    只包裝狀態求解本身（``PropsSI``／``PhaseSI``）引發的 ``ValueError``；reference-state 設定、
    同步鎖與其他內部錯誤不屬於此類。只有此類失敗才會交給飽和邊界分類判斷。
    """


class ThermodynamicStateService:
    """使用 canonical SI inputs 與 outputs 計算 thermodynamic states。"""

    PROPERTIES = ("P", "T", "H", "S", "D", "Q", "V", "U")

    def __init__(
        self,
        unit_converter: CanonicalUnitConverter,
        reference_state: ReferenceStateService | None = None,
    ) -> None:
        """以明確的 conversion 與 state policy 初始化 service。

參數：
    unit_converter (CanonicalUnitConverter): 函數輸入值。
    reference_state (ReferenceStateService | None): 函數輸入值。

回傳：
    無。"""
        self.unit_converter = unit_converter
        self.reference_state = reference_state or ReferenceStateService()
        self.ideal_gas_props = {
            "Air": {"R": 287.058, "Cp": 1005.0},
            "Water": {"R": 461.5, "Cp": 1870.0},
        }

    def is_fluid_valid(self, fluid_name: str) -> bool:
        """回傳 CoolProp 是否辨識指定的流體識別字。

參數：
    fluid_name (str): 函數輸入值。

回傳：
    bool：函數計算或處理後的結果。"""
        try:
            with self.reference_state.calculation_scope(fluid_name):
                CP.PropsSI("Tcrit", fluid_name)
        except ValueError:
            return False
        return True

    def set_reference_state(self, fluid_name: str, ref_state: str) -> None:
        """透過集中管理的機制套用 reference state。

參數：
    fluid_name (str): 函數輸入值。
    ref_state (str): 函數輸入值。

回傳：
    無。"""
        self.reference_state.set(fluid_name, ref_state)

    def calculate_properties(
        self,
        fluid: str,
        known_props: Iterable[KnownProperty],
        is_ideal_gas: bool = False,
        reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT,
    ) -> dict[str, float | str]:
        """由至少兩個已知性質計算狀態。

        Args:
            fluid: CoolProp fluid or supported ideal-gas name.
            known_props: Property code, display value and unit triples.
            is_ideal_gas: Select the built-in ideal-gas model.

        回傳：
            A dictionary of canonical SI values plus ``phase``.

        Raises:
            ValueError: If fewer than two properties are supplied or input
                conversion/model requirements are invalid.
            RuntimeError: If CoolProp cannot calculate the requested state.
        """
        properties = list(known_props)
        if len(properties) < 2:
            raise ValueError("請至少提供兩組已知的性質。")

        processed: list[tuple[str, float, str]] = []
        for prop, value, unit in properties:
            if prop == "V":
                if value == 0:
                    raise ValueError("比容 (V) 不能為零。")
                specific_volume = self.unit_converter.convert_to_si(prop, value, unit)
                processed.append(("D", 1.0 / specific_volume, "kg/m³"))
            else:
                processed.append((prop, value, unit))

        known_si = [
            (prop, self.unit_converter.convert_to_si(prop, value, unit))
            for prop, value, unit in processed
        ]
        try:
            if is_ideal_gas:
                return self._calculate_ideal_gas(fluid, dict(known_si))
            return self._calculate_coolprop(fluid, known_si, reference_state)
        except Exception as exc:
            raise RuntimeError(f"在計算 '{fluid}' 的性質時發生錯誤: {exc}") from exc

    def calculate_state_si(
        self,
        fluid: str,
        known_si: Sequence[tuple[str, float]],
        reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT,
    ) -> dict[str, float | str]:
        """以 canonical SI 已知性質直接計算 CoolProp 狀態，不經顯示單位轉換。

供 domain 內部的循環／飽和計算使用；每次呼叫都在共用的 reference-state
transaction 中完成。

參數：
    fluid: CoolProp 流體名稱。
    known_si: 至少兩組 (CoolProp 性質代碼, SI 數值)，例如 ("P", Pa)、("Q", 1.0)。
    reference_state: 本次查詢要求的 reference-state policy。

回傳：
    canonical SI 性質與 ``phase`` 的 dict。

引發：
    ValueError：已知性質少於兩組時。
    IndeterminateStateError：CoolProp 狀態求解本身失敗，且已知性質為壓力與溫度、經物理條件確認
    兩者落在飽和邊界（無法唯一決定狀態）時。
    RuntimeError：其他計算失敗時，包括 reference-state 設定失敗等內部錯誤；即使輸入剛好接近
    飽和也不歸類為 IndeterminateStateError。"""
        known = list(known_si)
        if len(known) < 2:
            raise ValueError("請至少提供兩組已知的性質。")
        fluid = fluid.strip()
        try:
            return self._calculate_coolprop(fluid, known[:2], reference_state)
        except Exception as exc:
            message = f"在計算 '{fluid}' 的性質時發生錯誤: {exc}"
            # 只有「狀態求解本身失敗」且 (P, T) 經物理條件確認落在飽和邊界，才是無法唯一決定狀態；
            # reference-state 設定或其他內部錯誤即使輸入剛好接近飽和，也不重新分類。
            if isinstance(exc, CoolPropStateCalculationError) and self._is_pt_on_saturation_boundary(
                fluid, known[:2]
            ):
                raise IndeterminateStateError(message) from exc
            raise RuntimeError(message) from exc

    def _is_pt_on_saturation_boundary(self, fluid: str, known_si: Sequence[tuple[str, float]]) -> bool:
        """判斷一次失敗的 (P, T) 查詢是否因兩者落在飽和邊界（無法唯一決定狀態）。

以物理條件判斷，不解析 CoolProp 的錯誤文字：該溫度的泡點（Q = 0）或露點（Q = 1）
飽和壓力與給定壓力的相對差在 ``PT_SATURATION_RELATIVE_TOLERANCE`` 之內。飽和壓力與
reference state 無關。

參數：
    fluid: CoolProp 流體名稱。
    known_si: 查詢使用的兩組 (性質代碼, SI 數值)。

回傳：
    是飽和邊界歧義時為 True；其他情況（含無法計算飽和壓力，例如流體無效或高於臨界溫度）為 False。"""
        values = dict(known_si)
        if set(values) != {"P", "T"}:
            return False
        pressure, temperature = values["P"], values["T"]
        if not pressure > 0 or not temperature > 0:
            return False
        try:
            with self.reference_state.calculation_scope(fluid):
                saturation_pressures = [CP.PropsSI("P", "T", temperature, "Q", q, fluid) for q in (0, 1)]
        except Exception:
            return False
        return any(
            abs(saturation - pressure) <= PT_SATURATION_RELATIVE_TOLERANCE * pressure
            for saturation in saturation_pressures
        )

    def _calculate_coolprop(
        self,
        fluid: str,
        known_props_si: list[tuple[str, float]],
        reference_state: ReferenceStatePolicy | str = ReferenceStatePolicy.DEFAULT,
    ) -> dict[str, float | str]:
        """在單一同步 transaction 中計算所有已設定的性質。

參數：
    fluid (str): 函數輸入值。
    known_props_si (list[tuple[str, float]]): 函數輸入值。
    reference_state (ReferenceStatePolicy | str): 函數輸入值。

回傳：
    dict[str, float | str]：函數計算或處理後的結果。"""
        with self.reference_state.calculation_scope(fluid, reference_state):
            prop1, value1 = known_props_si[0]
            prop2, value2 = known_props_si[1]
            result: dict[str, float | str] = {}
            try:
                for property_code in self.PROPERTIES:
                    if property_code == "V":
                        density = CP.PropsSI("D", prop1, value1, prop2, value2, fluid)
                        result[property_code] = 1.0 / density if density else float("inf")
                    else:
                        result[property_code] = CP.PropsSI(
                            property_code, prop1, value1, prop2, value2, fluid
                        )
                result["phase"] = CP.PhaseSI(prop1, value1, prop2, value2, fluid)
            except ValueError as exc:
                # CoolProp 以 ValueError 回報無法求解；只包裝狀態求解本身，reference-state
                # 設定（calculation_scope 進入時）與其他例外維持原樣。
                raise CoolPropStateCalculationError(str(exc)) from exc
            return result

    def _calculate_ideal_gas(
        self,
        fluid: str,
        input_values: dict[str, float],
    ) -> dict[str, float | str]:
        """計算支援的 ideal-gas 狀態組合。

參數：
    fluid (str): 函數輸入值。
    input_values (dict[str, float]): 函數輸入值。

回傳：
    dict[str, float | str]：函數計算或處理後的結果。"""
        try:
            constants = self.ideal_gas_props[fluid]
        except KeyError as exc:
            raise ValueError(f"找不到 {fluid} 的理想氣體常數。") from exc

        gas_constant = constants["R"]
        heat_capacity = constants["Cp"]
        cv = heat_capacity - gas_constant
        result: dict[str, float | str]
        if "P" in input_values and "T" in input_values:
            result = {"P": input_values["P"], "T": input_values["T"]}
            result["D"] = result["P"] / (gas_constant * result["T"])
        elif "P" in input_values and "D" in input_values:
            result = {"P": input_values["P"], "D": input_values["D"]}
            result["T"] = result["P"] / (result["D"] * gas_constant)
        elif "T" in input_values and "D" in input_values:
            result = {"T": input_values["T"], "D": input_values["D"]}
            result["P"] = result["D"] * gas_constant * result["T"]
        else:
            raise ValueError("理想氣體計算需要 P&T, P&D 或 T&D 的組合。")

        result["H"] = heat_capacity * result["T"]
        result["U"] = cv * result["T"]
        result["V"] = 1.0 / result["D"] if result["D"] else float("inf")
        result["S"] = 0.0
        result["Q"] = -1.0
        result["phase"] = "gas"
        return result
