# ui_components/property_tab.py
"""
用來處理 熱力學查表相關工具內容

"""

import logging
from collections.abc import Callable
from math import isfinite

import flet as ft
# PropertyTab 繼承自 ft.Column，使其可以直接作為 Flet UI 中的一個垂直佈局容器。
# 導入新類別的 "合約" (interfaces)
from ..ui_components.unit.UnitConverter import (
    ABSOLUTE_TO_GAUGE_UNIT,
    GAUGE_PRESSURE,
    GAUGE_TO_ABSOLUTE_UNIT,
    UnitConverter,
)
from ..ui_components.unit.PropertyFormatter import PropertyFormatter
from .analysis_modules.result_formatting import ResultFormatter
from application.models import HumidAirQueryRequest, PropertyQueryRequest
from application.property_queries import PropertyQueryResult, PropertyQueryService
from domain.state_points import AirStatePoint, StateSource, ThermoStatePoint
from domain.thermodynamics.thermo_policy import (
    AUTO,
    MODEL_LABELS,
    REFERENCE_STATE_DESCRIPTIONS,
    CalculationModel,
    ResolvedThermoPolicy,
    ThermoPolicyError,
    Workflow,
    resolve_thermo_policy,
)
from ..ui.components.engineering_card import EngineeringCard
from ..ui.components.quantity_input import QuantityInput
from ..ui.components.result_panel import ResultPanel
from ..ui.components.state_save_menu import StateSaveMenu
from ..ui.theme import (
    TOKENS,
    card_shadow,
    chip_button_style,
    primary_button_style,
    secondary_button_style,
    style_dropdown,
    style_text_field,
)
from ..ui.state import WorkspaceState

# 計算模型選單：值為 CalculationModel 的值。模型與參考基準分開選擇（模型是第一層）。
MODEL_OPTIONS = tuple((model.value, MODEL_LABELS[model]) for model in (
    CalculationModel.AUTO, CalculationModel.REAL_FLUID, CalculationModel.IDEAL_GAS, CalculationModel.HUMID_AIR,
))
# 參考基準選單：Auto 規則集中於 domain/thermodynamics/thermo_policy.py。
REFERENCE_OPTIONS = (
    (AUTO, "Auto（推薦）"),
    ("IIR", "IIR"),
    ("ASHRAE", "ASHRAE"),
    ("NBP", "NBP"),
    ("DEF", "DEF（CoolProp 預設）"),
)
# 濕空氣模型的濕度條件：(代碼, 顯示名稱, 單位性質代碼)。
HUMIDITY_INPUTS = (
    ("RH", "相對濕度 RH", "RH"),
    ("Twb", "濕球溫度 Twb", "T"),
    ("W", "濕度比 W", "W"),
)
HUMID_AIR_FLUID = "Air"
# 錶壓換算預設使用的標準大氣壓力（Pa）；與分析頁一致。
STANDARD_ATMOSPHERE_PA = 101_325.0
PRESSURE_GAUGE = "Gauge"
PRESSURE_ABSOLUTE = "Absolute"


# PropertyTab 繼承自 ft.Column，使其可以直接作為 Flet UI 中的一個垂直佈局容器。
class PropertyTab(ft.Column):
    def __init__(self, unit_converter: UnitConverter, 
                 formatter: PropertyFormatter, 
                 page: ft.Page,
                 query_service: PropertyQueryService,
                 workspace_state: WorkspaceState | None = None,
                 pressure_from_altitude: Callable[[float], float] | None = None):
        """建立查詢介面，並以外置欄名與預設隱藏的第三列維持欄位契約。

參數：
    unit_converter: 負責輸入與輸出單位轉換的服務。
    formatter: 將計算結果整理為使用者可讀內容的格式器。
    page: Flet 應用程式頁面。
    query_service: 執行熱力性質查詢並管理參考狀態的服務。
    workspace_state: 選用的工作區狀態；未提供時建立預設狀態。
    pressure_from_altitude: 「海拔（m）→ 大氣壓力（Pa）」換算；未提供時使用共用濕空氣服務的公式。

回傳：
    無。"""
        # 初始化 ft.Column 的屬性：啟用垂直滾動，並展開佔滿可用空間
        super().__init__(expand=True, spacing=0)

        # 分別儲存所需的服務
        self.unit_converter = unit_converter 
        self.formatter = formatter
        self.query_service = query_service
        self.workspace_state = workspace_state or WorkspaceState()
        self._pressure_from_altitude_fn = pressure_from_altitude
        # 壓力輸入基準：與飽和性質等分析頁相同的錶壓／絕對壓切換；預設絕對壓（維持舊行為）。
        self.pressure_basis = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value=PRESSURE_ABSOLUTE, label=ft.Text("絕對壓力")),
                ft.Segment(value=PRESSURE_GAUGE, label=ft.Text("錶壓力")),
            ],
            selected=[PRESSURE_ABSOLUTE],
            # 窄版（320／375 px）時勾選圖示會擠壓標籤文字；選取狀態已由底色表示。
            show_selected_icon=False,
            expand=True,
            on_change=self._on_pressure_basis_change,
        )
        self.pressure_basis_hint = ft.Text("", size=TOKENS.caption, color=TOKENS.text_muted)
        self.altitude_tf = ft.TextField(
            label="海拔高度（選填，m）", hint_text="未填時使用 101.325 kPa",
            keyboard_type=ft.KeyboardType.NUMBER, expand=True, on_change=self._on_altitude_change,
        )
        self.atm_tf = ft.TextField(
            label="大氣壓力（絕對，kPa）", value="101.325",
            helper="填入海拔時自動計算；也可手動修改。",
            keyboard_type=ft.KeyboardType.NUMBER, expand=True, on_change=self._on_semantic_input_change,
        )
        
        # 性質代碼到名稱的映射 (用於下拉選單顯示)
        # 格式為: {代碼: "名稱 (中文), 代碼"} (例如: 'P' -> 'Pressure (壓力), P')
        self.prop_names_map = {
            # 將代碼 (code) 追加到現有名稱 (name) 的末尾
            code: f"{name}, {code}" 
            for code, name in self.formatter.prop_names.items()
        }
        # 追蹤上次的單位，用於單位轉換時的比對和換算 (每行一個)
        self._last_prop_units = ["", "", ""] 
        self._last_prop_codes = []
        # 防止單位同步換算時觸發無限循環的鎖定標記
        self._is_updating_units = False 

        # --- UI 控制項建立 ---
        
        # 1. 模型/物質區塊：模型（第一層）與參考基準（第二層）分開選擇。
        self.mode_dd = ft.Dropdown(
            label="計算模型", value=CalculationModel.AUTO.value,
            options=[ft.dropdown.Option(key, text) for key, text in MODEL_OPTIONS],
            on_select=self.on_mode_change,
            expand=True, # 佔滿同行剩餘空間
        )
        self.fluid_tf = ft.TextField(label="物質名稱", value="R32", expand=True, on_change=self.on_fluid_change)
        # 切到濕空氣模型時暫存原本的物質名稱，切回其他模型時還原（不靜默覆寫使用者輸入）。
        self._fluid_before_humid_air: str | None = None
        self.mode_notice = ft.Text("", size=TOKENS.caption, color=TOKENS.warning, visible=False)

        # --- 參考基準區塊 (Reference State Block) ---
        self.ref_state_descriptions = {
            AUTO: "依流體自動選擇：支援 IIR 的冷媒 → IIR；水 → DEF；其他 → DEF 並標示原因。",
            **{code: f"{code}：{text}" for code, text in REFERENCE_STATE_DESCRIPTIONS.items()},
        }
        self.ref_state_dd = ft.Dropdown(
            label="參考基準 (Reference State)",
            value=AUTO,
            options=[ft.dropdown.Option(key, text) for key, text in REFERENCE_OPTIONS],
            on_select=self.on_ref_state_change,
            expand=True,
        )
        self.reference_state_helper = ft.Text(
            self.ref_state_descriptions[AUTO],
            size=TOKENS.caption,
            color=TOKENS.text_secondary,
        )
        # 依目前輸入預覽實際模型與基準；計算時會重新解析一次並以那份快照為準。
        self.policy_preview = ft.Text(
            "", size=TOKENS.caption, color=TOKENS.text_secondary, selectable=True, expand=True,
        )

        # --- 濕空氣輸入（只在濕空氣模型顯示）---
        self.humid_dry_bulb_tf = ft.TextField(
            keyboard_type=ft.KeyboardType.NUMBER, expand=True, on_change=self._on_semantic_input_change,
        )
        self.humid_dry_bulb_unit = ft.Dropdown(
            options=[ft.dropdown.Option(unit) for unit in self.unit_converter.get_available_units("T")],
            value=self.unit_converter.default_units.get("T", "°C"), width=120,
            on_select=self._on_semantic_input_change,
        )
        self.humidity_type_dd = ft.Dropdown(
            label="濕度條件",
            value="RH",
            options=[ft.dropdown.Option(code, text) for code, text, _ in HUMIDITY_INPUTS],
            on_select=self._on_humidity_type_change,
            expand=True,
        )
        self.humidity_value_tf = ft.TextField(
            keyboard_type=ft.KeyboardType.NUMBER, expand=True, on_change=self._on_semantic_input_change,
        )
        self.humidity_unit_dd = ft.Dropdown(width=120, on_select=self._on_semantic_input_change)
        self.humid_altitude_tf = ft.TextField(
            label="海拔 (m)", value="0", keyboard_type=ft.KeyboardType.NUMBER, expand=True,
            on_change=self._on_semantic_input_change,
        )
        self._refresh_humidity_units()
        
        # 2. 性質輸入區塊 (Property Input Block)
        self.input_rows = [] # 儲存三行輸入控制項的字典列表
        for i in range(3):
            # 性質名稱下拉選單
            prop_dd = ft.Dropdown(
                label=None,
                height=TOKENS.input_height,
                value=self.prop_names_map[self.formatter.properties[i]], # 預設值, # 預設值
                options=[ft.dropdown.Option(name) for name in self.prop_names_map.values()],
                width=250, # 調整後的較寬度，確保顯示完整的性質名稱和代碼
            )
            # 數值輸入框，限制鍵盤輸入類型為數字
            val_tf = ft.TextField(
                label=None,
                expand=True,
                height=TOKENS.input_height,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=self._on_semantic_input_change,
            )
            # 單位下拉選單
            unit_dd = ft.Dropdown(label=None, width=120, height=TOKENS.input_height)
            
            # 設置事件處理器 (使用閉包確保傳遞正確的索引 i)
            prop_dd.on_select = self.create_prop_change_handler(i)
            unit_dd.on_select = self.create_unit_change_handler(i)

            self.input_rows.append({"prop": prop_dd, "val": val_tf, "unit": unit_dd})
            self._last_prop_codes.append(self.get_prop_code(prop_dd.value))
            # 初始化時為單位選單載入選項和預設值
            self.update_units_menu(i, update_view=False)
            
        # 3. 廣延性質區塊 (Extensive Property Block)
        # 總質量輸入框
        self.mass_tf = ft.TextField(
            label="總質量", expand=True, keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._on_mass_input_change,
        )
        # 總質量單位下拉選單
        self.mass_unit_dd = ft.Dropdown(
            label="單位", value="kg", options=[ft.dropdown.Option("kg"), ft.dropdown.Option("lbm")],
            width=100, on_select=self._on_mass_unit_change,
        )
        self._last_mass_unit = self.mass_unit_dd.value

        # 5. 結果顯示區 (Result Display Block)
        self.output_unit_system = self.workspace_state.output_unit_system

        self.result_text = ft.Text(
            "", selectable=True, visible=False, color=ft.Colors.GREY_600
        )
        self._has_calculated_result = False
        self._last_si_results: dict[str, object] | None = None
        self._last_policy: ResolvedThermoPolicy | None = None
        self._last_total_mass_kg: float | None = None
        self._last_result_metadata: dict[str, str] = {}
        self._last_input_summary = ""
        self._last_formatted_output = ""

        self.controls = self._build_workspace_controls()
        self.scroll = None
        self.expand = True
        # 初始化模型相關的欄位狀態與預覽。不在此設定 process-global reference state：
        # 每次查詢都在 calculation_scope 內以當次解析的 concrete 基準計算。
        self.on_mode_change_internal()


    def _build_workspace_controls(self) -> list[ft.Control]:
        """建立雙欄工作區：左側為設定與已知條件，右側為結果；底部操作列固定。

窄視窗時兩欄會依序堆疊。第三條件列維持隱藏，直到求解器支援第三個限制條件。

回傳：
    由可捲動內容區與固定操作列組成的控制項清單。"""
        for control in (self.mode_dd, self.ref_state_dd, self.mass_unit_dd, self.humid_dry_bulb_unit,
                        self.humidity_type_dd, self.humidity_unit_dd):
            style_dropdown(control)
        for control in (self.fluid_tf, self.mass_tf, self.humid_dry_bulb_tf, self.humidity_value_tf,
                        self.humid_altitude_tf):
            style_text_field(control)
        self.fluid_tf.prefix_icon = ft.Icons.PROPANE_TANK_OUTLINED
        self.mass_tf.hint_text = "例如 1.0"
        self.quantity_inputs = []
        condition_rows = []
        for index, row in enumerate(self.input_rows):
            prop_code = self.get_prop_code(row["prop"].value) or "P"
            row_label = self.prop_names_map[prop_code].split(",", 1)[0]
            quantity = QuantityInput(
                row_label,
                prop_code,
                value_control=row["val"],
                unit_control=row["unit"],
            )
            self.quantity_inputs.append(quantity)
            style_dropdown(row["prop"])
            row["prop"].width = None
            row["prop"].height = TOKENS.input_height
            row["val"].height = TOKENS.input_height
            row["unit"].height = TOKENS.input_height
            # 性質選單已顯示欄名，因此隱藏數量元件的重複標籤；欄位錯誤仍顯示在數值下方。
            quantity.label_control.visible = False
            row["prop"].expand = True
            condition_rows.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        content=ft.Text(str(index + 1), size=TOKENS.caption,
                                                        weight=ft.FontWeight.W_700,
                                                        color=ft.Colors.WHITE),
                                        width=24,
                                        height=24,
                                        alignment=ft.Alignment.CENTER,
                                        bgcolor=TOKENS.primary,
                                        border_radius=ft.BorderRadius.all(TOKENS.radius_pill),
                                        tooltip=f"已知性質 {index + 1}",
                                    ),
                                    row["prop"],
                                ],
                                spacing=TOKENS.spacing_sm + 4,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Container(content=quantity.control, padding=ft.Padding.only(left=36)),
                        ],
                        spacing=TOKENS.spacing_sm,
                    ),
                    padding=TOKENS.spacing_md,
                    bgcolor=TOKENS.surface_variant,
                    border=ft.Border.all(1, TOKENS.border),
                    border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
                )
            )
        self.input_rows[2]["prop"].visible = False
        self.input_rows[2]["val"].visible = False
        self.input_rows[2]["unit"].visible = False
        condition_rows[2].visible = False
        self.condition_rows = condition_rows
        self._preset_pairs = (("P", "T"), ("P", "H"), ("P", "S"), ("P", "Q"), ("T", "Q"))
        self.preset_buttons = ft.Row(
            [
                ft.OutlinedButton(
                    f"{first} + {second}",
                    on_click=lambda _event, pair=(first, second): self._apply_property_preset(pair),
                    tooltip=f"將已知條件設為 {self.prop_names_map[first].split(',', 1)[0]}"
                            f" 與 {self.prop_names_map[second].split(',', 1)[0]}",
                )
                for first, second in self._preset_pairs
            ],
            spacing=TOKENS.spacing_sm,
            run_spacing=TOKENS.spacing_sm,
            wrap=True,
        )
        self._refresh_preset_selection()
        self.extensive_toggle = ft.Switch(
            label="計算廣延性質（總焓、總熵、總體積…）",
            value=False,
            on_change=self._toggle_extensive,
            active_color=TOKENS.primary,
        )
        self.extensive_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text("總質量", size=TOKENS.body, weight=ft.FontWeight.W_500,
                            color=TOKENS.text_primary),
                    ft.Row([self.mass_tf, self.mass_unit_dd], spacing=TOKENS.spacing_sm),
                ],
                spacing=6,
            ),
            visible=False,
        )
        self.result_panel = ResultPanel()
        self.raw_output = ft.Text(
            "", selectable=True, visible=False, font_family=TOKENS.mono_font,
            size=TOKENS.caption + 1, color=TOKENS.text_primary,
        )
        self.result_text.size = TOKENS.caption + 1
        self.result_text.color = TOKENS.text_secondary
        self.details_button = ft.TextButton(
            "查看詳細結果", icon=ft.Icons.UNFOLD_MORE, on_click=self._toggle_raw_output, disabled=True
        )
        self.copy_result_button = ft.OutlinedButton(
            "複製結果", icon=ft.Icons.CONTENT_COPY, on_click=self._copy_result, disabled=True,
            style=secondary_button_style(),
        )
        # 「儲存狀態點」選單；連接 State Library 且有成功查詢結果時才顯示。
        self.save_menu = StateSaveMenu()
        self._last_state_point: ThermoStatePoint | None = None
        configuration = EngineeringCard(
            "計算設定",
            ft.Column(
                [
                    ft.ResponsiveRow([
                        ft.Container(content=self.mode_dd, col={"xs": 12, "md": 4}),
                        ft.Container(content=self.fluid_tf, col={"xs": 12, "md": 4}),
                        ft.Container(
                            content=ft.Column([self.ref_state_dd, self.reference_state_helper],
                                              spacing=TOKENS.spacing_xs),
                            col={"xs": 12, "md": 4},
                        ),
                    ], spacing=TOKENS.spacing_md, run_spacing=TOKENS.spacing_md,
                        vertical_alignment=ft.CrossAxisAlignment.START),
                    self.mode_notice,
                    ft.Row(
                        [ft.Icon(ft.Icons.RULE, size=14, color=TOKENS.text_muted), self.policy_preview],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                ],
                spacing=TOKENS.spacing_sm,
            ),
            "選擇計算模型、物質與參考基準；Auto 會顯示實際採用的模型、基準與原因。",
            icon=ft.Icons.SETTINGS_OUTLINED,
        )
        def labelled(label: str, *controls: ft.Control) -> ft.Column:
            """建立欄名在上、輸入在下的欄位（窄視窗時不會截斷欄名）。"""
            return ft.Column(
                [ft.Text(label, size=TOKENS.body, weight=ft.FontWeight.W_500, color=TOKENS.text_primary),
                 ft.Row(list(controls), spacing=TOKENS.spacing_sm)],
                spacing=6,
            )

        self.humid_air_card = EngineeringCard(
            "濕空氣條件（乾球溫度＋一個濕度條件）",
            ft.Column([
                ft.ResponsiveRow([
                    ft.Container(content=labelled("乾球溫度 Tdb", self.humid_dry_bulb_tf, self.humid_dry_bulb_unit),
                                 col={"xs": 12, "md": 6}),
                    ft.Container(content=self.humid_altitude_tf, col={"xs": 12, "md": 6}),
                ], spacing=TOKENS.spacing_md, run_spacing=TOKENS.spacing_md),
                self.humidity_type_dd,
                ft.Row([self.humidity_value_tf, self.humidity_unit_dd], spacing=TOKENS.spacing_sm),
                ft.Text(
                    "總壓由海拔依標準大氣換算；焓、比容以每 kg 乾空氣為基準，與乾空氣／冷媒的 kJ/kg 不可互比。",
                    size=TOKENS.caption, color=TOKENS.text_muted,
                ),
            ], spacing=TOKENS.spacing_md),
            icon=ft.Icons.WATER_DROP_OUTLINED,
        )
        self.humid_air_card.visible = False
        for control in (self.altitude_tf, self.atm_tf):
            style_text_field(control)
        self.atmosphere_section = ft.ResponsiveRow(
            [
                ft.Container(content=self.altitude_tf, col={"xs": 12, "md": 6}),
                ft.Container(content=self.atm_tf, col={"xs": 12, "md": 6}),
            ],
            spacing=TOKENS.spacing_md,
            run_spacing=TOKENS.spacing_md,
            visible=False,
        )
        self._refresh_pressure_basis_hint()
        conditions = EngineeringCard(
            "已知條件（兩個獨立性質）",
            ft.Column([
                ft.Column(
                    [
                        ft.Text("常用組合", size=TOKENS.caption, color=TOKENS.text_muted,
                                weight=ft.FontWeight.W_600),
                        self.preset_buttons,
                    ],
                    spacing=6,
                ),
                ft.Column(
                    [
                        ft.Text("壓力類型", size=TOKENS.caption, color=TOKENS.text_muted,
                                weight=ft.FontWeight.W_600),
                        ft.Row([self.pressure_basis]),
                        self.pressure_basis_hint,
                        self.atmosphere_section,
                    ],
                    spacing=6,
                ),
                ft.Column(self.condition_rows, spacing=TOKENS.spacing_sm + 4),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=14, color=TOKENS.text_muted),
                        ft.Text(
                            "目前狀態查詢只接受兩個獨立性質；混合物組成、流速或高程等第三條件尚未支援，"
                            "因此暫不提供新增入口。",
                            size=TOKENS.caption,
                            color=TOKENS.text_muted,
                            expand=True,
                        ),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ], spacing=TOKENS.spacing_md),
            icon=ft.Icons.TUNE,
        )
        self.conditions_card = conditions
        extensive = EngineeringCard(
            "廣延性質",
            ft.Column([self.extensive_toggle, self.extensive_section], spacing=TOKENS.spacing_sm),
            "需要總量時才開啟並輸入總質量。",
            icon=ft.Icons.SCALE_OUTLINED,
        )
        self.result_summary_box = ft.Container(
            content=ft.Column(
                [
                    ft.Text("輸入摘要", size=TOKENS.overline, weight=ft.FontWeight.W_600,
                            color=TOKENS.text_muted),
                    self.result_text,
                ],
                spacing=4,
            ),
            padding=TOKENS.spacing_sm + 4,
            bgcolor=TOKENS.surface_variant,
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
        )
        self.raw_output_box = ft.Container(
            content=self.raw_output,
            padding=TOKENS.spacing_sm + 4,
            bgcolor=TOKENS.surface_muted,
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
        )
        results = EngineeringCard(
            "計算結果",
            ft.Column([
                self.result_panel,
                self.result_summary_box,
                ft.Row([self.details_button, self.save_menu, ft.Container(expand=True),
                        self.copy_result_button],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.raw_output_box,
            ], spacing=TOKENS.spacing_sm + 4),
            "結果附實際計算模型與參考基準；切換輸出單位不會重新查詢。",
            icon=ft.Icons.INSIGHTS_OUTLINED,
            accent=TOKENS.accent,
        )
        self.results_card = results
        self.extensive_card = extensive
        self._sync_result_boxes()
        scroll_area = ft.Column(
            [
                configuration,
                ft.ResponsiveRow(
                    [
                        ft.Column(
                            [conditions, self.humid_air_card, extensive],
                            spacing=TOKENS.spacing_md,
                            col={"xs": 12, "lg": 6},
                        ),
                        ft.Column([results], spacing=TOKENS.spacing_md, col={"xs": 12, "lg": 6}),
                    ],
                    spacing=TOKENS.spacing_md,
                    run_spacing=TOKENS.spacing_md,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            spacing=TOKENS.spacing_md,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
        self.calculate_button = ft.Button(
            "執行計算", icon=ft.Icons.CALCULATE_OUTLINED,
            on_click=self.perform_calculation, height=TOKENS.button_height,
            style=primary_button_style(),
        )
        self.action_bar = ft.Container(
            content=ft.Row([
                ft.OutlinedButton("重設", icon=ft.Icons.RESTART_ALT, on_click=self._reset_inputs,
                                  style=secondary_button_style()),
                ft.Container(expand=True),
                ft.Text("Ctrl + Enter 執行", size=TOKENS.caption, color=TOKENS.text_muted),
                self.calculate_button,
            ], spacing=TOKENS.spacing_md, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_lg, vertical=TOKENS.spacing_sm + 4),
            margin=ft.Margin.only(top=TOKENS.spacing_md),
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
            shadow=card_shadow(),
        )
        return [scroll_area, self.action_bar]

    def _sync_result_boxes(self) -> None:
        """讓摘要與詳細文字外框的可見性跟隨其文字控制項。

回傳：
    無。"""
        if hasattr(self, "result_summary_box"):
            self.result_summary_box.visible = bool(self.result_text.visible)
            self.raw_output_box.visible = bool(self.raw_output.visible)

    def _refresh_preset_selection(self) -> None:
        """以目前前兩列的性質組合標示相符的常用組合按鈕。

回傳：
    無。"""
        if not hasattr(self, "preset_buttons"):
            return
        current = tuple(self.get_prop_code(row["prop"].value) for row in self.input_rows[:2])
        for button, pair in zip(self.preset_buttons.controls, self._preset_pairs):
            button.style = chip_button_style(current == pair)

    def _apply_property_preset(self, property_codes: tuple[str, str]) -> None:
        """套用性質組合、更新單位選項，並使舊計算結果失效。

參數：
    property_codes: 預設組合中的兩個性質代碼。

回傳：
    無。"""
        self._mark_calculated_result_stale()
        for index, code in enumerate(property_codes):
            row = self.input_rows[index]
            row["prop"].value = self.prop_names_map[code]
            self.update_units_menu(index, update_view=False)
        try:
            self.update()
        except RuntimeError:
            pass

    def _toggle_extensive(self, event: ft.ControlEvent) -> None:
        """只在使用者要求計算廣延性質時顯示總質量輸入欄位。

參數：
    event: 包含切換後狀態的 Flet 控制事件。

回傳：
    無。"""
        self._mark_calculated_result_stale()
        self.extensive_section.visible = bool(event.control.value)
        try:
            self.update()
        except RuntimeError:
            pass

    def _on_semantic_input_change(self, _event: ft.ControlEvent | None) -> None:
        """使目前輸入不再對應上次成功計算的結果快照。

        參數：
            _event: Flet 控制項變更事件；不需讀取其內容。

        回傳：
            無。
        """
        self._mark_calculated_result_stale()
        try:
            self.update()
        except RuntimeError:
            pass

    def _on_mass_input_change(self, event: ft.ControlEvent | None) -> None:
        """質量數值改變時清除欄位錯誤並使舊結果失效。

        參數：
            event: Flet 控制項變更事件。

        回傳：
            無。
        """
        self.mass_tf.error_text = None
        self._mark_calculated_result_stale()
        try:
            self.update()
        except RuntimeError:
            pass

    def _restore_mass_unit_selection(self, old_unit: str, message: str) -> None:
        """回復失敗換算的質量單位，保留尚未改寫的原始數值。

        參數：
            old_unit: 換算前有效的質量顯示單位。
            message: 顯示於質量欄位旁的錯誤說明。

        回傳：
            無。
        """
        self.mass_unit_dd.value = old_unit
        self._last_mass_unit = old_unit
        self.mass_tf.error_text = message
        try:
            self.update()
        except RuntimeError:
            pass

    def _on_mass_unit_change(self, _event: ft.ControlEvent | None) -> None:
        """換算質量欄位的顯示單位，並對失敗換算回復完整欄位狀態。

        參數：
            _event: 質量單位選單的 Flet 變更事件。

        回傳：
            無。
        """
        new_unit = self.mass_unit_dd.value
        old_unit = self._last_mass_unit
        if not new_unit or new_unit == old_unit:
            return
        raw_value = (self.mass_tf.value or "").strip()
        if raw_value:
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                self._mark_calculated_result_stale()
            else:
                try:
                    mass_kg = self.unit_converter.convert_to_si("Mass", value, old_unit)
                    converted = self.unit_converter.convert_from_si("Mass", mass_kg, new_unit)
                except (TypeError, ValueError):
                    self._restore_mass_unit_selection(
                        old_unit, "質量單位換算失敗，已恢復原單位。"
                    )
                    return
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Unexpected error while converting the extensive-property mass unit"
                    )
                    self._restore_mass_unit_selection(
                        old_unit, "質量單位換算發生非預期錯誤，已恢復原單位。"
                    )
                    raise
                self.mass_tf.value = f"{converted:.7g}"
        self._last_mass_unit = new_unit
        self.mass_tf.error_text = None
        try:
            self.update()
        except RuntimeError:
            pass

    def attach_state_library(self, service) -> None:
        """連接 State Library：成功查詢後可把狀態保存到狀態庫。

參數：
    service: :class:`~application.state_library.StateLibraryService`。

回傳：
    無。"""
        self.save_menu.attach(service)
        self.save_menu.show_points((self._last_state_point,) if self._last_state_point else ())

    @staticmethod
    def _state_point_from_results(
        si_results: dict[str, object], fluid: str, reference_state: str | None, is_ideal_gas: bool
    ) -> ThermoStatePoint | None:
        """由查詢結果建立可保存的狀態點；結果無法構成有效狀態點時回傳 None（不影響查詢結果顯示）。

參數：
    si_results: 查詢服務回傳的 canonical SI 結果。
    fluid: 流體名稱。
    reference_state: 本次解析的 concrete 基準；理想氣體為 None（記為 IDEAL_GAS）。
    is_ideal_gas: 是否為理想氣體模型（不提供比熵）。

回傳：
    ThermoStatePoint 或 None。"""
        try:
            return ThermoStatePoint.from_state_mapping(
                si_results, fluid=fluid, reference_state=reference_state or "DEF",
                source=StateSource.PROPERTY_QUERY, label="狀態查詢", is_ideal_gas=is_ideal_gas,
            )
        except ValueError:
            return None

    def _clear_result_presentation_snapshot(self) -> None:
        """清除結果快照及其所有可複製、摘要與詳細資料投影。

        回傳：
            無。
        """
        self._has_calculated_result = False
        self._last_si_results = None
        self._last_policy = None
        self._last_total_mass_kg = None
        self._last_result_metadata = {}
        self._last_input_summary = ""
        self._last_formatted_output = ""
        self.result_text.value = ""
        self.result_text.visible = False
        self.result_text.color = ft.Colors.GREY_600
        self.raw_output.value = ""
        self.raw_output.visible = False
        self.details_button.text = "查看詳細結果"
        self.details_button.icon = ft.Icons.UNFOLD_MORE
        self.details_button.disabled = True
        self.copy_result_button.disabled = True
        self._last_state_point = None
        self.save_menu.hide()
        self.result_panel.metrics = {}
        self.result_panel.metadata = {}
        self._sync_result_boxes()

    def _mark_calculated_result_stale(self) -> None:
        """清除不再對應目前語意輸入的結果與快取。

        回傳：
            無。
        """
        if not self._has_calculated_result:
            return
        self._clear_result_presentation_snapshot()
        self.result_panel.set_status(
            "warning", "輸入已變更", "舊結果已清除，請使用目前輸入重新執行計算。"
        )

    def _toggle_raw_output(self, _event: ft.ControlEvent | None) -> None:
        """按需顯示只含格式化性質的詳細文字，不改變摘要或快照資料。

參數：
    _event: Flet 點擊事件；此處不需讀取事件內容。

回傳：
    無。"""
        if not self._has_calculated_result:
            return
        self.raw_output.visible = not self.raw_output.visible
        self.details_button.text = "隱藏詳細結果" if self.raw_output.visible else "查看詳細結果"
        self.details_button.icon = (
            ft.Icons.UNFOLD_LESS if self.raw_output.visible else ft.Icons.UNFOLD_MORE
        )
        self._sync_result_boxes()
        try:
            self.update()
        except RuntimeError:
            pass

    def _compose_result_summary(self) -> str:
        """產生不重複格式化詳細結果的常駐摘要。

        :return: 輸入摘要及目前輸出單位；尚無有效輸入快照時回傳空字串。
        """
        if not self._last_input_summary:
            return ""
        output_label = "Imperial" if self.output_unit_system == "Imperial" else "SI"
        return f"{self._last_input_summary}\n輸出單位: {output_label}"

    def _compose_result_text(self) -> str:
        """組成供複製使用的輸入摘要與完整格式化結果。

        :return: 目前快照的完整純文字表示；快照已清除時回傳空字串。
        """
        if not self._last_formatted_output:
            return ""
        if not self._last_input_summary:
            return self._last_formatted_output
        return f"{self._last_input_summary}\n\n{self._last_formatted_output}"

    async def _copy_result(self, _event: ft.ControlEvent | None) -> None:
        """透過 Flet 剪貼簿服務複製最近一次成功計算的結果。

參數：
    _event: Flet 點擊事件；此處不需讀取事件內容。

回傳：
    無。"""
        if not self._has_calculated_result:
            return
        await ft.Clipboard().set(self._compose_result_text())

    def _reset_inputs(self, _event: ft.ControlEvent | None) -> None:
        """清除查詢值、錯誤、快取及選用區塊狀態，保留流體、模式、參考政策與輸出偏好。

參數：
    _event: Flet 點擊事件；此處不需讀取事件內容。

回傳：
    無。"""
        for row in self.input_rows:
            row["val"].value = ""
            row["val"].error_text = None
        for quantity_input in self.quantity_inputs:
            quantity_input.set_error(None)
        for control in self.input_rows[2].values():
            control.visible = False
        self.condition_rows[2].visible = False
        self.extensive_toggle.value = False
        self.extensive_section.visible = False
        self.mass_tf.value = ""
        self.mass_tf.error_text = None
        for control in (self.humid_dry_bulb_tf, self.humidity_value_tf):
            control.value = ""
            control.error_text = None
        self._clear_result_presentation_snapshot()
        self.result_panel.set_status("empty", "尚未計算", "輸入至少兩個獨立性質後執行計算。")
        try:
            self.update()
        except RuntimeError:
            pass

    def set_output_unit_system(self, unit_system: str) -> None:
        """以快取的計算結果重新呈現所選單位，不重跑熱力性質查詢。

參數：
    unit_system: 要使用的全域輸出單位系統。

回傳：
    無。"""
        self.workspace_state.set_output_unit_system(unit_system)
        self.output_unit_system = unit_system
        if self._has_calculated_result:
            self._render_cached_result()
            try:
                self.update()
            except RuntimeError:
                pass

    def _render_cached_result(self) -> None:
        """重新格式化快取中的 SI 結果及廣延性質，不再呼叫領域計算服務。

回傳：
    無。"""
        if self._last_si_results is None:
            return
        use_imperial = self.output_unit_system == "Imperial"
        metadata = {
            **self._last_result_metadata,
            "Output": "Imperial" if use_imperial else "SI",
        }
        if self._last_policy is not None and self._last_policy.model is CalculationModel.HUMID_AIR:
            formatter = ResultFormatter(self.unit_converter, use_imperial)
            self.result_panel.set_metrics(
                self._format_humid_air_metrics(formatter, self._last_si_results),
                metadata,
                status_detail="濕空氣（每 kg 乾空氣）",
            )
            formatter.section("濕空氣狀態（每 kg 乾空氣）")
            formatter.add("大氣壓力（絕對）", "P", self._last_si_results["P"])
            formatter.add_air_state(self._last_si_results)
            output = formatter.text()
        else:
            phase = self.formatter._get_phase_description(
                self._last_si_results.get("phase", "unknown")
            )
            self.result_panel.set_metrics(
                self._format_result_metrics(self._last_si_results, use_imperial),
                metadata,
                status_detail=phase,
            )
            output = self.formatter.format_specific_properties(self._last_si_results, use_imperial)
            if self._last_total_mass_kg is not None:
                output += self.formatter.format_extensive_properties(
                    self._last_si_results, self._last_total_mass_kg, use_imperial
                )
        if self._last_policy is not None:
            output += "\n\n--- 模型與基準 ---\n" + "\n".join(
                f"{label}: {value}" for label, value in self._last_policy.summary_rows()
            )
        self._last_formatted_output = output
        self.raw_output.value = output
        self.result_text.value = self._compose_result_summary()
        self.result_text.visible = True
        self.details_button.disabled = False
        self.copy_result_button.disabled = False
        self.save_menu.show_points((self._last_state_point,) if self._last_state_point else ())
        self._sync_result_boxes()

    @staticmethod
    def _format_humid_air_metrics(formatter: ResultFormatter, state: dict[str, object]) -> dict[str, str]:
        """濕空氣結果卡片指標；焓與比容標示每 kg 乾空氣。

參數：
    formatter: 決定輸出單位的格式化器。
    state: PsychrometricService 結果。

回傳：
    指標名稱與顯示文字。"""
        def quantity(code: str, value: float, digits: int = 2) -> str:
            text, unit = formatter.parts(code, value, digits)
            return f"{text} {unit}".strip()

        return {
            "乾球溫度": quantity("T", state["Tdb"]),
            "濕球溫度": quantity("T", state["Twb"]),
            "露點溫度": quantity("T", state["Tdp"]),
            "相對濕度": f"{state['RH'] * 100:.1f} %",
            "濕度比": quantity("W", state["W"], 3),
            "比焓 (每 kg 乾空氣)": quantity("H", state["H"]),
            "比容 (每 kg 乾空氣)": quantity("V", state["V"], 4),
        }

    def _format_result_metrics(self, si_results: dict[str, object], use_imperial: bool) -> dict[str, str]:
        """將計算結果中可用的數值格式化為結果卡片指標。

參數：
    si_results: 以 SI 為基準的計算結果。
    use_imperial: 是否將輸出格式化為英制。

回傳：
    指標名稱與顯示文字的對應字典。"""
        unit_map = self.unit_converter.imperial_units if use_imperial else self.unit_converter.default_units
        labels = {"T": "Temperature", "P": "Pressure", "H": "Enthalpy", "S": "Entropy",
                  "D": "Density", "V": "Specific Volume", "Q": "Quality"}
        metrics = {}
        for code in ("T", "P", "H", "S", "D", "V", "Q"):
            if code not in si_results:
                continue
            value = si_results[code]
            if code == "Q":
                if not 0 <= value <= 1:
                    continue
                display_value, unit = value, ""
            else:
                unit = unit_map.get(code)
                if not unit:
                    continue
                display_value = self.unit_converter.convert_from_si(code, value, unit)
            precision = 3 if code in {"T", "P", "D", "V"} else 4
            metrics[labels[code]] = f"{display_value:.{precision}f}{f' {unit}' if unit else ''}"
        return metrics

    def get_prop_code(self, formatted_name: str) -> str | None:
        """
        根據下拉選單中格式化的性質名稱 (例如： 'Pressure (壓力), P')，
        逆向查找並返回其單一字母的代碼 (例如： 'P')。

        :param formatted_name: 下拉選單中顯示的名稱字串
        :return: 性質代碼 (str) 或 None
        """
        # 遍歷 prop_names_map (性質代碼到名稱的映射字典)
        for code, name in self.prop_names_map.items():
            # 檢查映射值 (name) 是否與傳入的格式化名稱 (formatted_name) 匹配
            if name == formatted_name: 
                return code # 找到匹配項，返回性質代碼
        return None # 未找到匹配項

    @property
    def selected_model(self) -> CalculationModel:
        """目前選擇的計算模型。"""
        try:
            return CalculationModel(self.mode_dd.value)
        except ValueError:
            return CalculationModel.AUTO

    def _refresh_policy_preview(self) -> ResolvedThermoPolicy | None:
        """依目前輸入預覽實際模型與基準；無法解析時顯示原因，不改動使用者輸入。

回傳：
    解析結果；無法解析時為 None。"""
        model = self.selected_model
        try:
            policy = resolve_thermo_policy(
                self.fluid_tf.value or "",
                model=model,
                reference=self.ref_state_dd.value,
                workflow=Workflow.PROPERTY_QUERY,
                humidity_specified=model is CalculationModel.HUMID_AIR,
            )
        except ThermoPolicyError as exc:
            self.policy_preview.value = f"無法解析：{exc}"
            self.policy_preview.color = TOKENS.error
            return None
        preview = f"實際採用：{policy.model_label}／參考基準 {policy.reference_label}\n{policy.reason}"
        if policy.fallback_reason:
            preview += f"\n{policy.fallback_reason}"
        self.policy_preview.value = preview
        self.policy_preview.color = TOKENS.warning if policy.fallback_reason else TOKENS.text_secondary
        return policy

    def on_fluid_change(self, e: ft.ControlEvent) -> None:
        """驗證流體名稱、更新模型／基準預覽，並使先前計算結果失效。

        不設定 process-global reference state；每次查詢都以當次解析的 concrete 基準計算。

        參數：
            e: 流體名稱欄位觸發的 Flet 控制事件。

        回傳：
            無。
        """
        self._mark_calculated_result_stale()
        fluid_name = self.fluid_tf.value.strip()
        if self.selected_model is not CalculationModel.HUMID_AIR:
            if self.query_service.is_fluid_valid(fluid_name):
                self.fluid_tf.error_text = None
                self.fluid_tf.border_color = ft.Colors.OUTLINE
            else:
                self.fluid_tf.error_text = f"錯誤：CoolProp 資料庫中找不到物質 '{fluid_name}'"
                self.fluid_tf.border_color = ft.Colors.RED_700
        self._refresh_policy_preview()
        self.update()

    def show_error(self, message):
        """
        在 Flet 頁面底部以 SnackBar 的形式顯示錯誤訊息。

        :param message: 要顯示的錯誤字串
        """
        snack = ft.SnackBar(ft.Text(message), bgcolor=ft.Colors.ERROR)
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()

    def on_mode_change_internal(self, e=None):
        """依模型調整欄位可用性；不靜默覆寫使用者輸入的物質。

        只有濕空氣模型會把物質設為 ``Air``（並明確提示、暫存原輸入）；切回其他模型時還原。
        理想氣體與濕空氣沒有 CoolProp reference state，參考基準固定為 Auto 並停用。

        :param e: Flet 事件物件 (可選)
        """
        model = self.selected_model
        is_humid = model is CalculationModel.HUMID_AIR
        notice = ""
        if is_humid:
            current = (self.fluid_tf.value or "").strip()
            if current != HUMID_AIR_FLUID:
                self._fluid_before_humid_air = current
                self.fluid_tf.value = HUMID_AIR_FLUID
                notice = f"濕空氣模型只適用 Air：物質已設為 Air（原輸入「{current}」已保留，切回其他模型時還原）。"
        elif self._fluid_before_humid_air is not None:
            restored = self._fluid_before_humid_air
            self._fluid_before_humid_air = None
            if (self.fluid_tf.value or "").strip() == HUMID_AIR_FLUID:
                self.fluid_tf.value = restored
                notice = f"已還原切換到濕空氣前的物質「{restored}」。"
        self.fluid_tf.disabled = is_humid
        self.fluid_tf.error_text = None
        self.mode_notice.value = notice
        self.mode_notice.visible = bool(notice)
        reference_applicable = model in (CalculationModel.AUTO, CalculationModel.REAL_FLUID)
        if not reference_applicable:
            self.ref_state_dd.value = AUTO
        self.ref_state_dd.disabled = not reference_applicable
        self.reference_state_helper.value = (
            self.ref_state_descriptions.get(self.ref_state_dd.value, "")
            if reference_applicable
            else f"{MODEL_LABELS[model]}沒有 CoolProp reference state，參考基準不適用。"
        )
        if hasattr(self, "conditions_card"):
            self.conditions_card.visible = not is_humid
            self.extensive_card.visible = not is_humid
            self.humid_air_card.visible = is_humid
        self._refresh_policy_preview()

    def on_mode_change(self, e: ft.ControlEvent | None = None) -> None:
        """使先前結果失效，並更新計算模型衍生的控制項狀態。

        參數：
            e: 模型選單觸發的 Flet 控制事件；程式初始化時可省略。

        回傳：
            無。
        """
        self._mark_calculated_result_stale()
        self.on_mode_change_internal(e)
        if self.parent:
            self.update()

    def on_ref_state_change(self, e: ft.ControlEvent) -> None:
        """更新所選參考基準的說明與預覽，並使舊結果失效（不設定 process-global 狀態）。

參數：
    e: 參考狀態選單觸發的 Flet 控制事件。

回傳：
    無。"""
        self._mark_calculated_result_stale()
        ref_code = self.ref_state_dd.value
        self.reference_state_helper.value = self.ref_state_descriptions.get(ref_code, "")
        self._refresh_policy_preview()
        if self.parent:
            self.update()

    def _refresh_humidity_units(self) -> None:
        """依濕度條件種類更新單位選單。

回傳：
    無。"""
        unit_code = next(code for key, _, code in HUMIDITY_INPUTS if key == self.humidity_type_dd.value)
        units = self.unit_converter.get_available_units(unit_code)
        self.humidity_unit_dd.options = [ft.dropdown.Option(unit) for unit in units]
        default = self.unit_converter.default_units.get(unit_code, units[0] if units else "")
        self.humidity_unit_dd.value = default if default in units else (units[0] if units else "")

    def _on_humidity_type_change(self, _event: ft.ControlEvent | None) -> None:
        """切換濕度條件種類：清除數值（不同物理量不可沿用），更新單位並使舊結果失效。

參數：
    _event: Flet 事件。

回傳：
    無。"""
        self._mark_calculated_result_stale()
        self.humidity_value_tf.value = ""
        self.humidity_value_tf.error_text = None
        self._refresh_humidity_units()
        try:
            self.update()
        except RuntimeError:
            pass

    @property
    def is_gauge_pressure(self) -> bool:
        """壓力輸入是否為錶壓力。"""
        return PRESSURE_GAUGE in (self.pressure_basis.selected or [])

    def _unit_code(self, prop_code: str | None) -> str | None:
        """回傳輸入列實際使用的單位性質代碼：錶壓模式下壓力為 ``PGauge``。"""
        if prop_code == "P" and self.is_gauge_pressure:
            return GAUGE_PRESSURE
        return prop_code

    def _read_atmospheric_pa(self) -> float:
        """讀取大氣壓力（絕對，Pa）。

引發：
    ValueError：欄位不是正的有限數值時。"""
        value = float((self.atm_tf.value or "").strip())
        if not isfinite(value) or value <= 0:
            raise ValueError("大氣壓力必須大於 0。")
        return value * 1000.0

    def _refresh_pressure_basis_hint(self) -> None:
        """更新壓力類型說明與大氣壓力欄位可見性。"""
        gauge = self.is_gauge_pressure
        self.atmosphere_section.visible = gauge
        self.pressure_basis_hint.value = (
            "錶壓力：計算前加上大氣壓力換成絕對壓力（例：152 kPag + 101.325 kPa = 253.325 kPa）。"
            if gauge
            else "絕對壓力：輸入值直接用於計算，不會加大氣壓力（蒸氣表通常為絕對壓）。"
        )

    def _on_pressure_basis_change(self, _event: ft.ControlEvent | None) -> None:
        """切換錶壓／絕對壓：壓力列改用對應單位並換算為同一個實際壓力，不使結果失效。

大氣壓力無效而需要換算時，恢復原模式並在大氣壓力欄位提示。

參數：
    _event: Flet 事件。

回傳：
    無。"""
        to_gauge = self.is_gauge_pressure
        new_code = GAUGE_PRESSURE if to_gauge else "P"
        old_code = "P" if to_gauge else GAUGE_PRESSURE
        unit_map = ABSOLUTE_TO_GAUGE_UNIT if to_gauge else GAUGE_TO_ABSOLUTE_UNIT
        pressure_rows = [
            index for index, row in enumerate(self.input_rows)
            if self.get_prop_code(row["prop"].value) == "P"
        ]
        values: dict[int, float] = {}
        for index in pressure_rows:
            try:
                value = float((self.input_rows[index]["val"].value or "").strip())
            except ValueError:
                continue
            if isfinite(value):
                values[index] = value
        atmospheric_pa = 0.0
        if values:
            try:
                atmospheric_pa = self._read_atmospheric_pa()
            except ValueError:
                self.pressure_basis.selected = [PRESSURE_GAUGE if not to_gauge else PRESSURE_ABSOLUTE]
                self.atm_tf.error_text = "請輸入有效的大氣壓力，才能在錶壓與絕對壓力間換算"
                self._refresh_pressure_basis_hint()
                self._safe_update()
                return
        self.atm_tf.error_text = None
        for index in pressure_rows:
            row = self.input_rows[index]
            old_unit = row["unit"].value
            new_unit = unit_map.get(old_unit, self.unit_converter.default_units.get(new_code, ""))
            if index in values:
                current_si = self.unit_converter.convert_to_si(old_code, values[index], old_unit)
                new_si = current_si - atmospheric_pa if to_gauge else current_si + atmospheric_pa
                row["val"].value = f"{self.unit_converter.convert_from_si(new_code, new_si, new_unit):.7g}"
            units = self.unit_converter.get_available_units(new_code)
            row["unit"].options = [ft.dropdown.Option(unit) for unit in units]
            row["unit"].value = new_unit
            self._last_prop_units[index] = new_unit
            self.workspace_state.set_input_unit(f"condition_{index}_{new_code}", new_unit)
        self._refresh_pressure_basis_hint()
        # 實際壓力不變：只換表示方式，不使舊結果失效。
        self._safe_update()

    def _on_altitude_change(self, _event: ft.ControlEvent | None) -> None:
        """依海拔更新大氣壓力；錶壓模式下大氣壓力改變會改變絕對壓力，因此使舊結果失效。"""
        raw_value = (self.altitude_tf.value or "").strip()
        atmospheric_pa = STANDARD_ATMOSPHERE_PA
        if raw_value:
            try:
                altitude = float(raw_value)
                if not isfinite(altitude):
                    raise ValueError("海拔必須是有限數值。")
                atmospheric_pa = self._altitude_to_pressure()(altitude)
                if isinstance(atmospheric_pa, complex) or not isfinite(atmospheric_pa) or atmospheric_pa <= 0:
                    raise ValueError("海拔超出標準大氣公式的適用範圍。")
            except (ValueError, TypeError, OverflowError) as error:
                self.altitude_tf.error_text = str(error) if str(error) else "請輸入有效海拔。"
                self._safe_update()
                return
        self.altitude_tf.error_text = None
        self.atm_tf.value = f"{atmospheric_pa / 1000:.6g}"
        self.atm_tf.error_text = None
        self._on_semantic_input_change(None)

    def _altitude_to_pressure(self) -> Callable[[float], float]:
        """回傳「海拔 → 大氣壓力（Pa）」換算；未注入時使用共用濕空氣服務的公式。"""
        if self._pressure_from_altitude_fn is None:
            from .unit.PsychrometricCalculator import PsychrometricCalculator

            self._pressure_from_altitude_fn = PsychrometricCalculator().service.calculate_pressure_from_altitude
        return self._pressure_from_altitude_fn

    def _safe_update(self) -> None:
        """已掛載時更新畫面；未掛載時略過。"""
        try:
            self.update()
        except RuntimeError:
            pass

    def update_units_menu(self, row_index: int, *, update_view: bool = True) -> None:
        """依輸入列的性質更新單位選項、預設值與追蹤狀態。

參數：
    row_index: 要更新的輸入列索引。
    update_view: 是否在更新控制項後刷新已掛載的畫面。

回傳：
    無。"""
        row = self.input_rows[row_index]
        prop_code = self.get_prop_code(row["prop"].value)
        previous_code = self._last_prop_codes[row_index]
        if previous_code and previous_code != prop_code:
            row["val"].value = ""
            row["val"].error_text = None
            if hasattr(self, "quantity_inputs"):
                self.quantity_inputs[row_index].set_error(None)
        self._last_prop_codes[row_index] = prop_code
        self._refresh_preset_selection()
        if hasattr(self, "quantity_inputs") and prop_code:
            row_label = self.prop_names_map[prop_code].split(",", 1)[0]
            quantity = self.quantity_inputs[row_index]
            quantity.property_code = prop_code
            quantity.label = row_label
            quantity.label_control.value = row_label
        unit_code = self._unit_code(prop_code)
        units = self.unit_converter.get_available_units(unit_code)
        row["unit"].options = [ft.dropdown.Option(unit) for unit in units]

        default_unit = self.unit_converter.default_units.get(unit_code, "")
        new_unit = default_unit if default_unit in units else (units[0] if units else "")
        input_key = f"condition_{row_index}_{unit_code}"
        saved_unit = self.workspace_state.input_units.get(input_key)
        if saved_unit in units:
            new_unit = saved_unit
        row["unit"].value = new_unit
        if prop_code:
            self.workspace_state.set_input_unit(input_key, new_unit)
        self._last_prop_units[row_index] = new_unit

        if update_view and self.parent:
            self.update()

    def create_prop_change_handler(self, index: int) -> Callable[[ft.ControlEvent], None]:
        """建立閉包，讓各性質選單的事件能保留所屬輸入列索引。

參數：
    index: 此事件處理器所屬的輸入列索引。

回傳：
    接收 Flet 控制事件並更新對應單位選項的處理函式。"""
        def handler(e: ft.ControlEvent) -> None:
            """更新此輸入列的性質對應單位選項。

            參數：
                e: 性質選單觸發的 Flet 控制事件。

            回傳：
                無。
            """
            self._mark_calculated_result_stale()
            self.update_units_menu(index)
        return handler

    def create_unit_change_handler(self, index: int) -> Callable[[ft.ControlEvent], None]:
        """建立閉包，讓各單位選單的事件能保留所屬輸入列索引。

參數：
    index: 此事件處理器所屬的輸入列索引。

回傳：
    接收 Flet 控制事件並處理單位換算的處理函式。"""
        def handler(e: ft.ControlEvent) -> None:
            """轉送此輸入列的單位變更事件。

            參數：
                e: 單位選單觸發的 Flet 控制事件。

            回傳：
                無。
            """
            self.on_property_unit_change(index)
        return handler

    def on_property_unit_change(self, changed_row_index: int) -> None:
        """只換算變更列的數值，並獨立保存該列的單位選擇。

        參數：
            changed_row_index: 觸發單位變更的輸入列索引。

        回傳：
            無。
        """
        if self._is_updating_units:
            return
        self._is_updating_units = True
        try:
            changed_row = self.input_rows[changed_row_index]
            property_code = self._unit_code(self.get_prop_code(changed_row["prop"].value))
            new_unit = changed_row["unit"].value
            old_unit = self._last_prop_units[changed_row_index]
            raw_value = changed_row["val"].value

            if new_unit != old_unit and old_unit and property_code:
                if raw_value:
                    try:
                        numeric_value = float(raw_value)
                    except (TypeError, ValueError):
                        self._mark_calculated_result_stale()
                    else:
                        try:
                            value_si = self.unit_converter.convert_to_si(
                                property_code, numeric_value, old_unit
                            )
                            converted_value = self.unit_converter.convert_from_si(
                                property_code, value_si, new_unit
                            )
                        except Exception:
                            changed_row["unit"].value = old_unit
                            self._last_prop_units[changed_row_index] = old_unit
                            self.workspace_state.set_input_unit(
                                f"condition_{changed_row_index}_{property_code}", old_unit
                            )
                            raise
                        changed_row["val"].value = f"{converted_value:.7g}"
                self._last_prop_units[changed_row_index] = new_unit
                if property_code:
                    self.workspace_state.set_input_unit(
                        f"condition_{changed_row_index}_{property_code}", new_unit
                    )
        finally:
            self._is_updating_units = False

        if self.parent:
            self.update()

    def _validate_known_input(
        self, property_code: str | None, raw_value: str, unit: str
    ) -> tuple[float | None, str | None]:
        """建立領域查詢前，先驗證一筆使用者輸入的熱力性質。

參數：
    property_code: 選定性質的標準代碼。
    raw_value: 尚未換算單位的輸入數值文字。
    unit: 此筆輸入所選的單位。

回傳：
    有效數值與空錯誤，或 None 與欄位錯誤訊息組成的 二元組。"""
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None, "請輸入有效數值。"
        if not isfinite(value):
            return None, "數值必須是有限數字。"
        if property_code is None:
            return None, "請選擇有效的熱力性質。"
        unit_code = self._unit_code(property_code)
        try:
            canonical_value = self.unit_converter.convert_to_si(unit_code, value, unit)
        except ValueError:
            return None, "目前性質不支援所選單位。"
        if unit_code == GAUGE_PRESSURE:
            try:
                atmospheric_pa = self._read_atmospheric_pa()
            except ValueError:
                return None, "錶壓換算需要有效的大氣壓力。"
            try:
                absolute_pa = self.unit_converter.gauge_to_absolute_pa(canonical_value, atmospheric_pa)
            except ValueError:
                absolute_pa = 0.0
            if absolute_pa <= 0:
                return None, "換算後的絕對壓力必須大於 0。"
        elif property_code == "P" and canonical_value <= 0:
            return None, "絕對壓力必須大於 0。"
        if property_code == "T" and canonical_value <= 0:
            return None, "絕對溫度必須大於 0 K。"
        if property_code == "Q" and not 0 <= value <= 1:
            return None, "乾度必須介於 0–1。"
        if property_code == "RH" and not 0 <= value <= 100:
            return None, "相對濕度必須介於 0–100%。"
        return value, None

    def perform_calculation(self, e: ft.ControlEvent | None) -> None:
        """驗證已知條件、呼叫熱力性質查詢服務並更新結果狀態。

參數：
    e: Flet 計算按鈕事件；由快捷鍵或測試呼叫時可為 None。

回傳：
    無。"""
        self._clear_result_presentation_snapshot()
        fluid = self.fluid_tf.value.strip()
        if self.selected_model is CalculationModel.HUMID_AIR:
            self._perform_humid_air_calculation()
            return

        # 1. 檢查物質名稱是否有效
        if not self.query_service.is_fluid_valid(fluid):
            self.result_panel.set_error("找不到這個物質，請確認流體名稱。")
            self.show_error(f"錯誤：找不到流體 '{fluid}'")
            self.update()
            return # 停止計算

        known_props, display_inputs = [], []
        gauge_notes: list[str] = []
        has_field_errors = False


        for index, row in enumerate(self.input_rows):
            raw_value = row["val"].value.strip()
            self.quantity_inputs[index].set_error(None)
            if not raw_value:
                continue
            prop_code = self.get_prop_code(row["prop"].value)
            unit = row["unit"].value
            value, error = self._validate_known_input(prop_code, raw_value, unit)
            self.quantity_inputs[index].set_error(error)
            if error:
                has_field_errors = True
                continue
            display_inputs.append(f"{row['prop'].value}={raw_value} {unit}")
            if self._unit_code(prop_code) == GAUGE_PRESSURE:
                # 錶壓只存在於 UI 邊界：送入計算前一律換成絕對壓力 Pa。
                atmospheric_pa = self._read_atmospheric_pa()
                absolute_pa = self.unit_converter.gauge_to_absolute_pa(
                    self.unit_converter.convert_to_si(GAUGE_PRESSURE, value, unit), atmospheric_pa
                )
                known_props.append(("P", absolute_pa, "Pa"))
                gauge_notes.append(
                    f"壓力換算: {raw_value} {unit} + 大氣 {atmospheric_pa / 1000:.6g} kPa"
                    f" = {absolute_pa / 1000:.6g} kPa（絕對）"
                )
            else:
                known_props.append((prop_code, value, unit))

        if has_field_errors:
            self.result_panel.set_error("請先修正欄位旁的錯誤，再執行計算。")
            self.raw_output.value = ""
            self.update()
            return

        if len(known_props) > 2:
            self.result_panel.set_error("目前只接受兩個獨立性質；第三列限制條件尚未支援，請移除該值。")
            self.update()
            return

        # 3. 檢查已知性質數量 (CoolProp 核心要求至少兩個獨立性質)
        if len(known_props) < 2:
            self.result_panel.set_status("warning", "輸入不足", "請至少輸入兩組有效的獨立性質。")
            # 輸入不足時的錯誤處理和 UI 反饋
            self.show_error("請至少輸入兩組有效的性質。")
            self.update()
            return # 停止計算

        total_mass_kg = None
        self.mass_tf.error_text = None
        if self.extensive_toggle.value:
            try:
                mass_value = float(self.mass_tf.value.strip())
            except (TypeError, ValueError):
                self.mass_tf.error_text = "請輸入有效的總質量。"
                self.result_panel.set_error(self.mass_tf.error_text)
                self.update()
                return
            if not isfinite(mass_value) or mass_value <= 0:
                self.mass_tf.error_text = "總質量必須是大於 0 的有限數值。"
                self.result_panel.set_error(self.mass_tf.error_text)
                self.update()
                return
            try:
                total_mass_kg = self.unit_converter.convert_to_si(
                    "Mass", mass_value, self.mass_unit_dd.value
                )
            except ValueError:
                self.mass_tf.error_text = "目前不支援所選的質量單位。"
                self.result_panel.set_error(self.mass_tf.error_text)
                self.update()
                return


        # 4. 依目前模型／基準建立 request；計算時只解析一次，結果與顯示使用同一份快照。
        model = self.selected_model
        ref_code = self.ref_state_dd.value
        input_summary = [
            "--- 輸入 ---",
            f"計算模型: {MODEL_LABELS[model]}",
            f"物質: {fluid}",
            f"參考狀態（選擇）: {ref_code}",
            f"已知: {', '.join(display_inputs[:2])}",
            f"壓力類型: {'錶壓力（計算時加大氣壓力）' if self.is_gauge_pressure else '絕對壓力'}",
            *gauge_notes,
        ]
        if total_mass_kg is not None:
            input_summary.append(f"總質量: {self.mass_tf.value.strip()} {self.mass_unit_dd.value}")
        self._last_input_summary = "\n".join(input_summary)

        # 5. 顯示「計算中」狀態；完整摘要只在成功快照建立後呈現。
        self.result_panel.set_status("loading", "計算中", "正在查詢熱力性質。")
        self.update()
        # 6. 執行核心熱力學計算
        try:
            outcome = self.query_service.query_with_policy(
                PropertyQueryRequest(
                    fluid,
                    tuple(known_props[:2]),
                    model is CalculationModel.IDEAL_GAS,
                    ref_code,
                    model=model.value,
                )
            )
            policy = outcome.policy
            si_results = outcome.values
            self._last_state_point = self._state_point_from_results(
                si_results, fluid, policy.reference_state, policy.is_ideal_gas
            )
            self._store_success(outcome, total_mass_kg, ", ".join(
                item.rsplit(" ", 1)[-1] for item in display_inputs[:2]
            ))
            self._render_cached_result()

        except Exception as err:
            error_message = str(err) if isinstance(err, ValueError) else "無法使用目前條件完成計算。"
            self._clear_result_presentation_snapshot()
            self.result_panel.set_error(error_message)
            self.show_error(error_message)
        finally:
            self.update() # 無論成功或失敗，確保 UI 最終狀態被更新
    def _store_success(
        self, outcome: PropertyQueryResult, total_mass_kg: float | None, input_units: str
    ) -> None:
        """保存成功查詢的快照；中繼資料顯示實際模型與 concrete 基準，而不是只顯示 Auto。

參數：
    outcome: 查詢結果與解析快照。
    total_mass_kg: 廣延性質總質量；未啟用時為 None。
    input_units: 輸入單位摘要。

回傳：
    無。"""
        policy = outcome.policy
        self._last_policy = policy
        self._last_si_results = outcome.values
        self._last_total_mass_kg = total_mass_kg
        self._has_calculated_result = True
        metadata = {
            "Fluid": policy.fluid if policy.canonical_fluid == policy.fluid else f"{policy.fluid}（{policy.canonical_fluid}）",
            "Engine": policy.model_label,
            "Reference": policy.reference_label,
            "Basis": "kJ/kg_dry_air" if policy.model is CalculationModel.HUMID_AIR else "kJ/kg",
            "Input units": input_units,
            "Output": "Imperial" if self.output_unit_system == "Imperial" else "SI",
        }
        if policy.fallback_reason:
            metadata["Fallback"] = policy.fallback_reason
        self._last_result_metadata = metadata

    def _perform_humid_air_calculation(self) -> None:
        """以濕空氣模型計算：乾球溫度＋一個濕度條件＋海拔；結果為每 kg 乾空氣。

回傳：
    無。"""
        errors = False
        values: dict[str, float] = {}
        for key, control, code, unit in (
            ("Tdb", self.humid_dry_bulb_tf, "T", self.humid_dry_bulb_unit.value),
            ("humidity", self.humidity_value_tf,
             next(c for k, _, c in HUMIDITY_INPUTS if k == self.humidity_type_dd.value), self.humidity_unit_dd.value),
        ):
            control.error_text = None
            raw = (control.value or "").strip()
            if not raw:
                control.error_text = "必填。"
                errors = True
                continue
            try:
                number = float(raw)
                if not isfinite(number):
                    raise ValueError
                values[key] = self.unit_converter.convert_to_si(code, number, unit)
            except (TypeError, ValueError):
                control.error_text = "請輸入有效數值。"
                errors = True
        try:
            altitude = float((self.humid_altitude_tf.value or "0").strip() or "0")
            if not isfinite(altitude):
                raise ValueError
            self.humid_altitude_tf.error_text = None
        except ValueError:
            self.humid_altitude_tf.error_text = "請輸入有效海拔（m）。"
            errors = True
        if errors:
            self.result_panel.set_error("濕空氣模型需要乾球溫度與一個濕度條件（RH、濕球溫度或濕度比），請修正欄位。")
            self.update()
            return
        kind = self.humidity_type_dd.value
        request = HumidAirQueryRequest(
            dry_bulb_k=values["Tdb"],
            altitude_m=altitude,
            relative_humidity=values["humidity"] if kind == "RH" else None,
            wet_bulb_k=values["humidity"] if kind == "Twb" else None,
            humidity_ratio=values["humidity"] if kind == "W" else None,
        )
        label = next(text for k, text, _ in HUMIDITY_INPUTS if k == kind)
        self._last_input_summary = "\n".join([
            "--- 輸入 ---",
            f"計算模型: {MODEL_LABELS[CalculationModel.HUMID_AIR]}",
            "物質: Air（濕空氣）",
            f"乾球溫度: {self.humid_dry_bulb_tf.value} {self.humid_dry_bulb_unit.value}",
            f"{label}: {self.humidity_value_tf.value} {self.humidity_unit_dd.value}",
            f"海拔: {altitude:g} m",
        ])
        try:
            outcome = self.query_service.query_humid_air(request)
            self._last_state_point = AirStatePoint.from_state_mapping(
                outcome.values, source=StateSource.PROPERTY_QUERY, label="濕空氣狀態查詢"
            )
            self._store_success(outcome, None, f"{self.humid_dry_bulb_unit.value}, {self.humidity_unit_dd.value}")
            self._render_cached_result()
        except Exception as err:
            error_message = str(err) if isinstance(err, ValueError) else "無法使用目前條件完成計算。"
            self._clear_result_presentation_snapshot()
            self.result_panel.set_error(error_message)
            self.show_error(error_message)
        finally:
            self.update()
