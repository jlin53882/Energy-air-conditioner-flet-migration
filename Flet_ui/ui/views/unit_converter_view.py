"""冷凍空調常用單位換算工具。

換算完全委派給 `UnitConverter`（其核心性質再委派給 domain 的 canonical converter），
畫面不自行定義換算係數；「常用換算」卡片的數值也在執行時由換算器計算。
"""

from __future__ import annotations

from math import isfinite

import flet as ft

from ...ui_components.unit.UnitConverter import UnitConverter
from ..components.engineering_card import EngineeringCard
from ..components.metric_tile import MetricTile
from ..theme import TOKENS, style_dropdown, style_text_field

# 可換算的物理量：(UnitConverter 性質代碼, 顯示名稱, 預設輸入單位)
QUANTITIES: tuple[tuple[str, str, str], ...] = (
    ("P", "壓力", "kPa"),
    ("T", "溫度", "°C"),
    ("DeltaT", "溫差", "K"),
    ("Power", "功率／冷凍能力", "kW"),
    ("VolumeFlow", "風量／體積流率", "m³/h"),
    ("MassFlow", "質量流率", "kg/s"),
    ("H", "比焓", "kJ/kg"),
    ("S", "比熵", "kJ/(kg.K)"),
    ("D", "密度", "kg/m³"),
    ("V", "比容", "m³/kg"),
    ("W", "濕度比", "g/kg"),
    ("E", "能量", "kJ"),
    ("L", "長度", "m"),
    ("Area", "面積", "m²"),
    ("Velocity", "風速", "m/s"),
    ("Mass", "質量", "kg"),
)
# 常用換算：(性質代碼, 數值, 來源單位, 目標單位)
REFERENCE_CONVERSIONS: tuple[tuple[str, float, str, str], ...] = (
    ("Power", 1.0, "RT", "kW"),
    ("Power", 1.0, "kW", "Btu/h"),
    ("Power", 1.0, "kW", "kcal/h"),
    ("VolumeFlow", 1.0, "ft³/min", "m³/h"),
    ("P", 1.0, "bar", "psia"),
    ("DeltaT", 1.0, "K", "°F"),
)


class UnitConverterView(ft.Column):
    """選擇物理量與來源單位，即時列出所有可用單位的換算值。"""

    def __init__(self, unit_converter: UnitConverter) -> None:
        """建立換算表單、結果卡片與常用換算參考。

參數：
    unit_converter: 共用單位轉換器。

回傳：
    無。"""
        self.unit_converter = unit_converter
        self.quantity_dd = style_dropdown(ft.Dropdown(
            options=[ft.dropdown.Option(code, label) for code, label, _unit in QUANTITIES],
            value=QUANTITIES[0][0],
            on_select=self._on_quantity_change,
            expand=True,
        ))
        self.value_tf = style_text_field(ft.TextField(
            value="1",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda _event: self.convert(),
            expand=True,
            height=TOKENS.input_height,
        ))
        self.unit_dd = style_dropdown(ft.Dropdown(
            width=150,
            height=TOKENS.input_height,
            on_select=lambda _event: self.convert(),
        ))
        self.results = ft.ResponsiveRow(spacing=TOKENS.spacing_sm, run_spacing=TOKENS.spacing_sm)
        self.status_text = ft.Text("", size=TOKENS.caption, color=TOKENS.text_muted)

        def labelled(label: str, control: ft.Control) -> ft.Column:
            """以框外欄名包裝控制項。

參數：
    label: 欄名。
    control: 控制項。

回傳：
    欄名與控制項組成的直欄。"""
            return ft.Column([ft.Text(label, size=TOKENS.body, weight=ft.FontWeight.W_500,
                                      color=TOKENS.text_primary), control], spacing=6)

        form = EngineeringCard(
            "輸入",
            ft.ResponsiveRow(
                [
                    ft.Container(labelled("物理量", self.quantity_dd), col={"xs": 12, "md": 4}),
                    ft.Container(labelled("數值", self.value_tf), col={"xs": 12, "md": 5}),
                    ft.Container(labelled("單位", self.unit_dd), col={"xs": 12, "md": 3}),
                ],
                spacing=TOKENS.spacing_md,
                run_spacing=TOKENS.spacing_md,
            ),
            "輸入後即時換算；溫度為絕對溫度，溫差請選「溫差」。",
            icon=ft.Icons.EDIT_OUTLINED,
        )
        result_card = EngineeringCard(
            "換算結果",
            ft.Column([self.status_text, self.results], spacing=TOKENS.spacing_sm),
            icon=ft.Icons.SWAP_HORIZ,
            accent=TOKENS.accent,
        )
        reference_card = EngineeringCard(
            "冷凍空調常用換算",
            ft.ResponsiveRow(
                [
                    MetricTile(f"1 {source} =", self._reference_value(code, value, source, target),
                               col={"xs": 12, "sm": 6, "xl": 4})
                    for code, value, source, target in REFERENCE_CONVERSIONS
                ],
                spacing=TOKENS.spacing_sm,
                run_spacing=TOKENS.spacing_sm,
            ),
            "數值由換算器即時計算（RT 為美制冷凍噸）。",
            icon=ft.Icons.MENU_BOOK_OUTLINED,
        )
        super().__init__([form, result_card, reference_card], spacing=TOKENS.spacing_md,
                         expand=True, scroll=ft.ScrollMode.AUTO)
        self._on_quantity_change(None)

    def _reference_value(self, code: str, value: float, source: str, target: str) -> str:
        """以換算器計算一筆常用換算。

參數：
    code: 性質代碼。
    value: 來源數值。
    source: 來源單位。
    target: 目標單位。

回傳：
    「數值 單位」文字。"""
        si_value = self.unit_converter.convert_to_si(code, value, source)
        return f"{self.unit_converter.convert_from_si(code, si_value, target):.5g} {target}"

    def _on_quantity_change(self, _event: ft.ControlEvent | None) -> None:
        """切換物理量時更新可選單位並重新換算。

參數：
    _event: Flet 事件；初始化時為 None。

回傳：
    無。"""
        code = self.quantity_dd.value
        units = self.unit_converter.get_available_units(code)
        default_unit = next(unit for quantity, _label, unit in QUANTITIES if quantity == code)
        self.unit_dd.options = [ft.dropdown.Option(unit) for unit in units]
        self.unit_dd.value = default_unit if default_unit in units else units[0]
        self.convert()

    def convert(self) -> None:
        """依目前輸入列出所有單位的換算值；無效輸入時在欄位旁提示。

回傳：
    無。"""
        code = self.quantity_dd.value
        try:
            value = float((self.value_tf.value or "").strip())
        except ValueError:
            value = float("nan")
        if not isfinite(value):
            self._show_error("請輸入有效數值。")
            return
        value_si = self.unit_converter.convert_to_si(code, value, self.unit_dd.value)
        if code == "T" and value_si < 0:
            self._show_error("溫度低於絕對零度，請確認數值與單位。")
            return
        self.value_tf.error_text = None
        self.status_text.value = f"{value:g} {self.unit_dd.value} 等於："
        self.results.controls = [
            MetricTile(unit, f"{self.unit_converter.convert_from_si(code, value_si, unit):.6g} {unit}",
                       emphasis=unit == self.unit_dd.value, col={"xs": 12, "sm": 6, "xl": 4})
            for unit in self.unit_converter.get_available_units(code)
        ]
        self._safe_update()

    def _show_error(self, message: str) -> None:
        """在數值欄位旁顯示錯誤並清除舊結果。

參數：
    message: 錯誤訊息。

回傳：
    無。"""
        self.value_tf.error_text = message
        self.status_text.value = ""
        self.results.controls = []
        self._safe_update()

    def _safe_update(self) -> None:
        """只在已掛載時更新畫面。

回傳：
    無。"""
        try:
            self.update()
        except RuntimeError:
            pass
