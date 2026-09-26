"""冷媒飽和性質工具：已知壓力或已知溫度，查詢飽和液體（泡點）與飽和蒸氣（露點）。

計算委派給 `RefrigerationService.saturation_properties`；兩個飽和狀態以
:class:`~domain.state_points.ThermoStatePoint` 回傳，結構化結果與文字結果皆由
同一組狀態點產生。錶壓力只在此通道層換算，application／domain 一律收到絕對壓力。
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from application.models import SaturationPropertiesRequest
from application.refrigeration import RefrigerationService
from domain.refrigeration.saturation import KNOWN_PRESSURE, KNOWN_TEMPERATURE, SaturationPropertiesResult

from ...ui.structured_result import PropertyGroup, PropertyRow, ResultMetric, StructuredResult
from ...ui.theme import TOKENS
from ..unit.UnitConverter import GAUGE_PRESSURE, UnitConverter
from .base_analysis_module import BaseAnalysisModule
from .result_formatting import ResultFormatter
from .thermo_state_presentation import add_state_point_lines, state_point_rows

KNOWN_LABELS = {
    KNOWN_PRESSURE: "已知壓力",
    KNOWN_TEMPERATURE: "已知溫度",
}
# 分段按鈕位於窄輸入欄，使用短標籤；欄名已說明為「已知飽和條件」。
KNOWN_SEGMENT_LABELS = {
    KNOWN_PRESSURE: "壓力",
    KNOWN_TEMPERATURE: "溫度",
}


class SaturationModule(BaseAnalysisModule):
    """冷媒飽和性質查詢。"""

    def __init__(self, unit_converter: UnitConverter, page: ft.Page,
                 refrigeration_service: RefrigerationService,
                 pressure_from_altitude: Callable[[float], float] | None = None) -> None:
        """建立飽和性質表單。

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
        self.saturation_ui = self._build_ui()
        self.bind_independent_unit_sync(list(self.all_entries))
        self.on_pressure_type_change(None)

    def get_analysis_definitions(self) -> dict:
        """回報飽和性質分析。

回傳：
    以分析名稱為鍵的註冊定義。"""
        return {
            "飽和性質": {
                "analysis_id": "refrigerant.saturation",
                "ui": self.saturation_ui,
                "calc_func": self.calculate_saturation,
                "structured_result": lambda: self.last_structured_result,
            },
        }

    # ======================================================
    # 表單
    # ======================================================
    def _build_ui(self) -> ft.Container:
        """建立飽和性質表單：冷媒、Reference State、已知條件與對應輸入列。

回傳：
    預設隱藏的表單容器。"""
        fluid_row = self.create_fluid_row("sat_fluid", "冷媒", "R32", "例如 R32、R410A、R134a")
        reference_state_row, self.sat_ref_state = self.create_reference_state_row()
        # 已知條件改變計算語意，屬於會使結果失效的輸入。
        self.sat_known = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value=KNOWN_PRESSURE, label=ft.Text(KNOWN_SEGMENT_LABELS[KNOWN_PRESSURE])),
                ft.Segment(value=KNOWN_TEMPERATURE, label=ft.Text(KNOWN_SEGMENT_LABELS[KNOWN_TEMPERATURE])),
            ],
            selected=[KNOWN_PRESSURE],
            on_change=self.on_known_change,
        )
        self.sat_pressure_type = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value="Gauge", label=ft.Text("錶壓力 (Gauge)")),
                ft.Segment(value="Absolute", label=ft.Text("絕對壓力 (Absolute)")),
            ],
            selected=["Gauge"],
            on_change=self.on_pressure_type_change,
        )
        self.sat_pressure_type_row = ft.Column([
            ft.Text("壓力類型", size=TOKENS.body, weight=ft.FontWeight.W_500, color=TOKENS.text_primary),
            self.sat_pressure_type,
        ], spacing=6)
        controls: list[ft.Control] = [
            self.section_label("冷媒"),
            fluid_row,
            reference_state_row,
            self.section_label("已知條件"),
            ft.Column([
                ft.Text("已知飽和條件", size=TOKENS.body, weight=ft.FontWeight.W_500,
                        color=TOKENS.text_primary),
                self.sat_known,
            ], spacing=6),
            self.sat_pressure_type_row,
            # 預設為錶壓力模式，因此飽和壓力以錶壓單位（kPag、psig…）輸入。
            self.create_input_row("sat_p", "飽和壓力", "900", GAUGE_PRESSURE, "kPag")["ui_row"],
            *self.create_atmosphere_rows("sat_alt", "sat_atm"),
            self.create_input_row("sat_t", "飽和溫度", "5", "T", "°C")["ui_row"],
        ]
        return ft.Container(content=ft.Column(controls, spacing=12), visible=False)

    @property
    def known(self) -> str:
        """目前選取的已知條件（``pressure`` 或 ``temperature``）。

回傳：
    已知條件代碼。"""
        return KNOWN_TEMPERATURE if KNOWN_TEMPERATURE in self.sat_known.selected else KNOWN_PRESSURE

    def _refresh_known_rows(self) -> None:
        """依已知條件與壓力類型顯示對應的輸入列。

已知壓力時顯示壓力類型與飽和壓力（錶壓模式另顯示海拔與大氣壓力）；已知溫度時只顯示
飽和溫度。

回傳：
    無。"""
        pressure_mode = self.known == KNOWN_PRESSURE
        is_gauge = "Gauge" in self.sat_pressure_type.selected
        self.sat_pressure_type_row.visible = pressure_mode
        self.all_entries["sat_p"]["ui_row"].visible = pressure_mode
        self.all_entries["sat_alt"]["ui_row"].visible = pressure_mode and is_gauge
        self.all_entries["sat_atm"]["ui_row"].visible = pressure_mode and is_gauge
        self.all_entries["sat_t"]["ui_row"].visible = not pressure_mode
        self._update_controls(self.saturation_ui)

    def on_known_change(self, _event: ft.ControlEvent | None) -> None:
        """切換已知壓力／已知溫度。

參數：
    _event: Flet 事件。

回傳：
    無。"""
        self._refresh_known_rows()

    def on_pressure_type_change(self, _event: ft.ControlEvent | None) -> None:
        """切換錶壓力／絕對壓力：飽和壓力改用對應語意的單位，並維持相同的實際壓力。

換算規則見 ``BaseAnalysisModule.switch_pressure_basis``；切換不使結果失效。

參數：
    _event: Flet 事件；初始化時為 None。

回傳：
    無。"""
        self.apply_pressure_basis(self.sat_pressure_type, ["sat_p"], "sat_alt", "sat_atm")
        self._refresh_known_rows()

    # ======================================================
    # 計算
    # ======================================================
    def calculate_saturation(self, use_imperial: bool) -> str:
        """計算飽和液體與飽和蒸氣狀態。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        self.last_structured_result = None
        known = self.known
        if known == KNOWN_PRESSURE:
            request = SaturationPropertiesRequest(
                fluid=self.read_text("sat_fluid"),
                pressure_pa=self.read_absolute_pressure_pa("sat_p", "sat_atm"),
                reference_state=self.sat_ref_state.value,
            )
        else:
            request = SaturationPropertiesRequest(
                fluid=self.read_text("sat_fluid"),
                temperature_k=self.read_si("sat_t"),
                reference_state=self.sat_ref_state.value,
            )
        result = self.refrigeration.saturation_properties(request)
        self.last_structured_result = self._build_structured(result, use_imperial)
        return self._format_text(result, use_imperial)

    @staticmethod
    def _summary_items(result: SaturationPropertiesResult) -> list[tuple[str, str, float, int]]:
        """回傳摘要結果（名稱, 性質代碼, SI 值, 位數），文字與關鍵數值共用。

參數：
    result: 飽和性質結果。

回傳：
    摘要項目。"""
        if result.known == KNOWN_PRESSURE:
            return [
                ("泡點溫度", "T", result.liquid.temperature_k, 2),
                ("露點溫度", "T", result.vapor.temperature_k, 2),
                ("溫度滑移", "DeltaT", result.temperature_glide_k, 2),
                ("蒸發潛熱 h_fg", "H", result.latent_heat_j_kg, 2),
            ]
        return [
            ("泡點壓力", "P", result.liquid.pressure_pa, 2),
            ("露點壓力", "P", result.vapor.pressure_pa, 2),
            ("泡點－露點壓力差", "P", result.pressure_difference_pa, 2),
            ("蒸發潛熱 h_fg", "H", result.latent_heat_j_kg, 2),
        ]

    def _build_structured(self, result: SaturationPropertiesResult, use_imperial: bool) -> StructuredResult:
        """由飽和狀態點建立結構化結果。

參數：
    result: 飽和性質結果。
    use_imperial: 是否以英制輸出。

回傳：
    StructuredResult。"""
        formatter = ResultFormatter(self.unit_converter, use_imperial)
        key_metrics = tuple(
            ResultMetric(label, *formatter.parts(prop_code, value, digits))
            for label, prop_code, value, digits in self._summary_items(result)
        )
        # 數值欄使用等寬數字字型，只放數值與代碼；中文說明放在名稱欄。
        if result.known == KNOWN_PRESSURE:
            known_row = PropertyRow("已知飽和壓力（絕對）", *formatter.parts("P", result.liquid.pressure_pa))
        else:
            known_row = PropertyRow("已知飽和溫度", *formatter.parts("T", result.liquid.temperature_k))
        inputs = PropertyGroup("輸入", (
            PropertyRow("冷媒", result.fluid),
            known_row,
            PropertyRow("參考狀態", result.reference_state),
        ), highlighted=True)
        return StructuredResult(
            key_metrics=key_metrics,
            groups=(
                inputs,
                PropertyGroup(result.liquid.label, state_point_rows(formatter, result.liquid)),
                PropertyGroup(result.vapor.label, state_point_rows(formatter, result.vapor)),
            ),
        )

    def _format_text(self, result: SaturationPropertiesResult, use_imperial: bool) -> str:
        """由飽和狀態點產生結果文字。

參數：
    result: 飽和性質結果。
    use_imperial: 是否以英制輸出。

回傳：
    多行結果文字。"""
        formatter = ResultFormatter(self.unit_converter, use_imperial)
        formatter.section("摘要")
        formatter.add_text("冷媒", result.fluid)
        formatter.add_text("已知條件", KNOWN_LABELS[result.known])
        formatter.add_text("參考狀態", result.reference_state)
        for label, prop_code, value, digits in self._summary_items(result):
            formatter.add(label, prop_code, value, digits)
        add_state_point_lines(formatter, result.liquid.label, result.liquid)
        add_state_point_lines(formatter, result.vapor.label, result.vapor)
        return formatter.text()
