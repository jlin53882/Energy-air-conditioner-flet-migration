"""現場過熱度／過冷度判讀工具（支援錶壓力輸入）。

計算委派給 `RefrigerationService.check_superheat`；露點、泡點與量測點以
:class:`~domain.state_points.ThermoStatePoint` 回傳。錶壓力只在此通道層換算，
application／domain 一律收到絕對壓力。
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from application.models import SuperheatCheckRequest
from application.refrigeration import RefrigerationService
from domain.refrigeration.saturation import REGION_SUBCOOLED, REGION_SUPERHEATED, SaturationCheckResult

from ...ui.structured_result import PropertyGroup, PropertyRow, ResultMetric, StructuredResult
from ...ui.theme import TOKENS
from ..unit.UnitConverter import GAUGE_PRESSURE, UnitConverter
from .base_analysis_module import BaseAnalysisModule
from .result_formatting import ResultFormatter
from .thermo_state_presentation import state_point_rows

REGION_LABELS = {
    REGION_SUPERHEATED: "過熱蒸氣",
    REGION_SUBCOOLED: "過冷液體",
}
TWO_PHASE_LABEL = "兩相（飽和區）"


class SuperheatSubcoolingModule(BaseAnalysisModule):
    """現場過熱度／過冷度判讀。"""

    def __init__(self, unit_converter: UnitConverter, page: ft.Page,
                 refrigeration_service: RefrigerationService,
                 pressure_from_altitude: Callable[[float], float] | None = None) -> None:
        """建立過熱度／過冷度判讀表單。

參數：
    unit_converter: 共用單位轉換器。
    page: Flet 頁面。
    refrigeration_service: 冷凍 application service。
    pressure_from_altitude: 選用的「海拔（m）→ 大氣壓力（Pa）」換算；未提供時使用預設濕空氣服務。

回傳：
    無。"""
        super().__init__(unit_converter, page, refrigeration_service=refrigeration_service,
                         pressure_from_altitude=pressure_from_altitude)
        self.refrigeration = refrigeration_service
        self.last_structured_result: StructuredResult | None = None
        self.superheat_ui = self._build_superheat_ui()
        self.bind_independent_unit_sync(list(self.all_entries))
        self.on_pressure_type_change(None)

    def get_analysis_definitions(self) -> dict:
        """回報過熱度／過冷度判讀分析。

回傳：
    以分析名稱為鍵的註冊定義。"""
        return {
            "過熱度／過冷度判讀": {
                "analysis_id": "refrigerant.superheat_subcooling",
                "ui": self.superheat_ui,
                "calc_func": self.calculate_superheat,
                "structured_result": lambda: self.last_structured_result,
            },
        }

    # ======================================================
    # 表單
    # ======================================================
    def _build_superheat_ui(self) -> ft.Container:
        """建立過熱度／過冷度判讀表單（支援錶壓力輸入）。

回傳：
    預設隱藏的表單容器。"""
        fluid_row = self.create_fluid_row("sh_fluid", "冷媒", "R32", "例如 R32、R410A、R134a")
        reference_state_row, self.sh_ref_state = self.create_reference_state_row()
        self.sh_pressure_type = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value="Gauge", label=ft.Text("錶壓力 (Gauge)")),
                ft.Segment(value="Absolute", label=ft.Text("絕對壓力 (Absolute)")),
            ],
            selected=["Gauge"],
            on_change=self.on_pressure_type_change,
        )
        controls: list[ft.Control] = [
            fluid_row,
            reference_state_row,
            self.section_label("現場量測"),
            ft.Column([
                ft.Text("壓力類型", size=TOKENS.body, weight=ft.FontWeight.W_500,
                        color=TOKENS.text_primary),
                self.sh_pressure_type,
            ], spacing=6),
            # 預設為錶壓力模式，因此量測壓力以錶壓單位（kPag、psig…）輸入。
            self.create_input_row("sh_p", "量測壓力", "900", GAUGE_PRESSURE, "kPag")["ui_row"],
            *self.create_atmosphere_rows("sh_alt", "sh_atm"),
            self.create_input_row("sh_t", "量測管溫", "20", "T", "°C")["ui_row"],
        ]
        return ft.Container(content=ft.Column(controls, spacing=12), visible=False)

    def on_pressure_type_change(self, _event: ft.ControlEvent | None) -> None:
        """切換錶壓力／絕對壓力：量測壓力改用對應語意的單位，並維持相同的實際壓力。

錶壓力模式使用錶壓單位（kPag、psig…）並顯示海拔與大氣壓力欄位；絕對壓力模式
使用絕對單位（kPa、psia…）。大氣壓力無法解析而無法換算時，維持原模式並在大氣
壓力欄位提示（換算規則見 ``BaseAnalysisModule.switch_pressure_basis``）。

參數：
    _event: Flet 事件；初始化時為 None。

回傳：
    無。"""
        self.apply_pressure_basis(self.sh_pressure_type, ["sh_p"], "sh_alt", "sh_atm", self.superheat_ui)

    # ======================================================
    # 計算
    # ======================================================
    def calculate_superheat(self, use_imperial: bool) -> str:
        """依量測壓力與管溫判讀過熱度或過冷度。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        self.last_structured_result = None
        # 錶壓力只在通道層處理：application／domain 一律收到絕對壓力 Pa。
        pressure = self.read_absolute_pressure_pa("sh_p", "sh_atm")
        result = self.refrigeration.check_superheat(SuperheatCheckRequest(
            fluid=self.read_text("sh_fluid"),
            pressure_pa=pressure,
            measured_temperature_k=self.read_si("sh_t"),
            reference_state=self.sh_ref_state.value,
        ))
        self.last_structured_result = self._build_structured(result, use_imperial)
        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section("判讀")
        formatter.add_text("狀態", REGION_LABELS.get(result.region, TWO_PHASE_LABEL))
        if result.superheat_k is not None:
            formatter.add("過熱度", "DeltaT", result.superheat_k, 1)
        if result.subcooling_k is not None:
            formatter.add("過冷度", "DeltaT", result.subcooling_k, 1)
        formatter.section("飽和溫度")
        formatter.add("露點（飽和蒸氣）", "T", result.dew_point_k, 1)
        formatter.add("泡點（飽和液體）", "T", result.bubble_point_k, 1)
        formatter.add("溫度滑移", "DeltaT", result.temperature_glide_k, 2)
        formatter.add("絕對壓力", "P", result.pressure_pa)
        return formatter.text()

    def _build_structured(self, result: SaturationCheckResult, use_imperial: bool) -> StructuredResult:
        """由判讀結果與狀態點建立結構化結果。

參數：
    result: 判讀結果。
    use_imperial: 是否以英制輸出。

回傳：
    StructuredResult。"""
        formatter = ResultFormatter(self.unit_converter, use_imperial)
        region_label = REGION_LABELS.get(result.region, TWO_PHASE_LABEL)
        if result.superheat_k is not None:
            degree = ResultMetric("過熱度", *formatter.parts("DeltaT", result.superheat_k, 1))
        elif result.subcooling_k is not None:
            degree = ResultMetric("過冷度", *formatter.parts("DeltaT", result.subcooling_k, 1))
        else:
            degree = ResultMetric("過熱度／過冷度", "—")
        key_metrics = (
            ResultMetric("狀態", region_label),
            degree,
            ResultMetric("絕對壓力", *formatter.parts("P", result.pressure_pa)),
            ResultMetric("溫度滑移", *formatter.parts("DeltaT", result.temperature_glide_k, 2)),
        )
        inputs = PropertyGroup("量測", (
            PropertyRow("冷媒", result.fluid),
            PropertyRow("絕對壓力", *formatter.parts("P", result.pressure_pa)),
            PropertyRow("量測管溫", *formatter.parts("T", result.measured_temperature_k, 1)),
            PropertyRow("參考狀態", result.reference_state),
        ), highlighted=True)
        groups = [
            inputs,
            PropertyGroup(result.dew_state.label, state_point_rows(formatter, result.dew_state)),
            PropertyGroup(result.bubble_state.label, state_point_rows(formatter, result.bubble_state)),
        ]
        if result.measured_state is not None:
            groups.append(PropertyGroup(result.measured_state.label,
                                        state_point_rows(formatter, result.measured_state)))
        return StructuredResult(key_metrics=key_metrics, groups=tuple(groups))
