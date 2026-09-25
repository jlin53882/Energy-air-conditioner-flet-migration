"""分析模組共用的結果格式化：把 canonical SI 數值轉為「名稱: 數值 單位」文字行。

輸出格式與 `ui.components.result_sections.parse_result_text` 對應，
`--- 標題 ---` 會成為結果分組。
"""

from __future__ import annotations

from ..unit.UnitConverter import UnitConverter

# 冷凍空調實務慣用的輸出單位；未列出的性質沿用 UnitConverter 的預設單位。
_PREFERRED_UNITS = {
    "SI": {"VolumeFlow": "m³/h", "P": "kPa"},
    "Imperial": {"VolumeFlow": "ft³/min"},
}


class ResultFormatter:
    """依目前輸出單位系統格式化結果文字。"""

    def __init__(self, unit_converter: UnitConverter, use_imperial: bool) -> None:
        """建立格式化器。

參數：
    unit_converter: 共用單位轉換器。
    use_imperial: True 表示輸出英制。

回傳：
    無。"""
        self.unit_converter = unit_converter
        self.system = "Imperial" if use_imperial else "SI"
        self.lines: list[str] = []

    def unit(self, prop_code: str) -> str:
        """回傳性質在目前單位系統的輸出單位。

參數：
    prop_code: UnitConverter 性質代碼。

回傳：
    單位文字。"""
        preferred = _PREFERRED_UNITS[self.system].get(prop_code)
        if preferred:
            return preferred
        units = (
            self.unit_converter.imperial_units
            if self.system == "Imperial"
            else self.unit_converter.default_units
        )
        return units[prop_code]

    def parts(self, prop_code: str, value_si: float, digits: int = 2) -> tuple[str, str]:
        """將 SI 數值轉為目前單位系統的（數值文字, 單位）。

參數：
    prop_code: UnitConverter 性質代碼。
    value_si: canonical SI 數值。
    digits: 小數位數。

回傳：
    數值文字與單位文字。"""
        unit = self.unit(prop_code)
        value = self.unit_converter.convert_from_si(prop_code, value_si, unit)
        return f"{value:.{digits}f}", unit

    def quantity(self, prop_code: str, value_si: float, digits: int = 2) -> str:
        """將 SI 數值轉為目前單位系統的「數值 單位」文字。

參數：
    prop_code: UnitConverter 性質代碼。
    value_si: canonical SI 數值。
    digits: 小數位數。

回傳：
    格式化文字。"""
        number, unit = self.parts(prop_code, value_si, digits)
        return f"{number} {unit}"

    def section(self, title: str) -> "ResultFormatter":
        """新增一個結果分組標題。

參數：
    title: 分組標題。

回傳：
    self，方便串接。"""
        self.lines.append(f"--- {title} ---")
        return self

    def add(self, label: str, prop_code: str, value_si: float, digits: int = 2) -> "ResultFormatter":
        """新增一行帶單位的結果。

參數：
    label: 結果名稱。
    prop_code: UnitConverter 性質代碼。
    value_si: canonical SI 數值。
    digits: 小數位數。

回傳：
    self。"""
        self.lines.append(f"{label}: {self.quantity(prop_code, value_si, digits)}")
        return self

    def add_text(self, label: str, text: str) -> "ResultFormatter":
        """新增一行已格式化的結果（例如無因次值或百分比）。

參數：
    label: 結果名稱。
    text: 顯示文字。

回傳：
    self。"""
        self.lines.append(f"{label}: {text}")
        return self

    def add_air_state(self, state: dict) -> "ResultFormatter":
        """新增濕空氣狀態的常用性質（乾球、濕球、露點、RH、濕度比、焓、比容）。

參數：
    state: PsychrometricService 回傳的中立狀態。

回傳：
    self。"""
        self.add("乾球溫度 Tdb", "T", state["Tdb"])
        self.add("濕球溫度 Twb", "T", state["Twb"])
        self.add("露點溫度 Tdp", "T", state["Tdp"])
        self.add_text("相對濕度 RH", f"{state['RH'] * 100:.1f} %")
        self.add("濕度比 W", "W", state["W"], 3 if self.system == "SI" else 2)
        self.add("比焓 h", "H", state["H"])
        self.add("比容 v", "V", state["V"], 4)
        return self

    def text(self) -> str:
        """回傳組合後的結果文字。

回傳：
    多行結果文字。"""
        return "\n".join(self.lines)
