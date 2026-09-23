# ui_components/property_tab.py
"""
用來處理 熱力學查表相關工具內容

"""

import logging

import flet as ft
from math import isfinite
from collections.abc import Callable
# PropertyTab 繼承自 ft.Column，使其可以直接作為 Flet UI 中的一個垂直佈局容器。
# 導入新類別的 "合約" (interfaces)
from ..ui_components.unit.UnitConverter import UnitConverter
from ..ui_components.unit.PropertyFormatter import PropertyFormatter
from application.models import PropertyQueryRequest
from application.property_queries import PropertyQueryService
from domain.thermodynamics.fluid_policy import resolve_reference_state_policy
from ..ui.components.engineering_card import EngineeringCard
from ..ui.components.quantity_input import QuantityInput
from ..ui.components.result_panel import ResultPanel
from ..ui.theme import TOKENS
from ..ui.state import WorkspaceState

# PropertyTab 繼承自 ft.Column，使其可以直接作為 Flet UI 中的一個垂直佈局容器。
class PropertyTab(ft.Column):
    def __init__(self, unit_converter: UnitConverter, 
                 formatter: PropertyFormatter, 
                 page: ft.Page,
                 query_service: PropertyQueryService,
                 workspace_state: WorkspaceState | None = None):
        """建立查詢介面，並以外置欄名與預設隱藏的第三列維持欄位契約。

參數：
    unit_converter: 負責輸入與輸出單位轉換的服務。
    formatter: 將計算結果整理為使用者可讀內容的格式器。
    page: Flet 應用程式頁面。
    query_service: 執行熱力性質查詢並管理參考狀態的服務。
    workspace_state: 選用的工作區狀態；未提供時建立預設狀態。

回傳：
    無。"""
        # 初始化 ft.Column 的屬性：啟用垂直滾動，並展開佔滿可用空間
        super().__init__(expand=True, spacing=0)

        # 分別儲存所需的服務
        self.unit_converter = unit_converter 
        self.formatter = formatter
        self.query_service = query_service
        self.workspace_state = workspace_state or WorkspaceState()
        
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
        
        # 1. 模式/物質區塊 (Mode/Fluid Block)
        self.mode_dd = ft.Dropdown(
            label="計算模式", value="CoolProp (冷媒)",
            options=[ft.dropdown.Option("CoolProp (冷媒)"), ft.dropdown.Option("Water (水/水蒸氣)")],
            on_select=self.on_mode_change,
            expand=True, # 佔滿同行剩餘空間
        )
        self.fluid_tf = ft.TextField(label="物質名稱", value="R32", expand=True, on_change=self.on_fluid_change)
        # 理想氣體核取方塊 (僅在 Water 模式下可見)
        self.ideal_gas_cb = ft.Checkbox(label="理想氣體計算", value=False, visible=False)

        # --- 新增 1: 參考點區塊 (Reference State Block) ---
        self.ref_state_descriptions = {
            "ASHRAE": "常見 HVAC reference convention。",
            "IIR": "International Institute of Refrigeration convention。",
            "NBP": "Normal boiling point reference。",
            "Default": "CoolProp default reference state。",
        }
        self.ref_state_dd = ft.Dropdown(
            label="Reference State",
            value="ASHRAE",
            options=[
                ft.dropdown.Option("Default", "Default"),
                ft.dropdown.Option("IIR", "IIR"),
                ft.dropdown.Option("ASHRAE", "ASHRAE"),
                ft.dropdown.Option("NBP", "NBP"),
            ],
            on_select=self.on_ref_state_change,
            expand=True,
        )
        self.reference_state_helper = ft.Text(
            self.ref_state_descriptions["ASHRAE"],
            size=TOKENS.caption,
            color=ft.Colors.BLUE_GREY_600,
        )
        
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
        self.mass_tf = ft.TextField(label="總質量", expand=True, keyboard_type=ft.KeyboardType.NUMBER)
        # 總質量單位下拉選單
        self.mass_unit_dd = ft.Dropdown(label="單位", value="kg", options=[ft.dropdown.Option("kg"), ft.dropdown.Option("lbm")], width=100)

        # 5. 結果顯示區 (Result Display Block)
        self.output_unit_system = self.workspace_state.output_unit_system

        self.result_text = ft.Text(
            "點擊 '執行計算' 查看結果...", 
            selectable=True, 
            color=ft.Colors.GREY_600 # 初始提示文字使用灰色
        )
        self._has_calculated_result = False
        self._last_si_results: dict[str, object] | None = None
        self._last_result_metadata: dict[str, str] = {}

        # 初始化模式設定 (設定 fluid_tf 和 ideal_gas_cb 的初始狀態)
        self.on_mode_change_internal()

        self.controls = self._build_workspace_controls()
        self.scroll = None
        self.expand = True
        # --- 新增步驟：設定初始預設參考點 ---
        # 目的：確保程式啟動時，即使使用者沒有點擊下拉選單，參考點也已經是 ASHRAE。
        try:
            # 預設使用的流體 (例如 R134a 或 UI 預設的 R32)
            # 必須使用 self.fluid_tf.value 來獲取預設物質名稱
            default_fluid = self.fluid_tf.value 
            # 預設的標準，即下拉選單的初始值 "ASHRAE"
            default_ref_state = "ASHRAE" 
            
            self.query_service.set_reference_state(default_fluid, default_ref_state)
            
        except Exception as e:
            # 如果預設流體無效或設定參考點失敗，顯示錯誤 (但不應該阻礙程式啟動)
            # 這裡使用 print 或 logging，因為此時 UI 可能還未完全載入
            print(f"警告：初始化 CoolProp 參考點失敗 ({default_fluid} to {default_ref_state}): {e}")


    def _build_workspace_controls(self) -> list[ft.Control]:
        """以響應式欄位排列已知性質，並隱藏尚未支援的第三條件入口。

回傳：
    無。"""
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
            row["prop"].width = 190
            row["prop"].height = TOKENS.input_height
            row["val"].height = TOKENS.input_height
            row["unit"].height = TOKENS.input_height
            property_column = ft.Column(
                [
                    ft.Text("性質", size=TOKENS.body, weight=ft.FontWeight.W_500),
                    row["prop"],
                ],
                spacing=TOKENS.spacing_xs,
                tight=True,
            )
            condition_rows.append(
                ft.ResponsiveRow(
                    [
                        ft.Container(content=property_column, col={"xs": 12, "md": 4}),
                        ft.Container(content=quantity.control, col={"xs": 12, "md": 8}),
                    ],
                    spacing=TOKENS.spacing_md,
                    run_spacing=TOKENS.spacing_sm,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )
            )
        self.input_rows[2]["prop"].visible = False
        self.input_rows[2]["val"].visible = False
        self.input_rows[2]["unit"].visible = False
        condition_rows[2].visible = False
        self.condition_rows = condition_rows
        self.preset_buttons = ft.Row(
            [
                ft.OutlinedButton(label, on_click=lambda _event, pair=pair: self._apply_property_preset(pair))
                for label, pair in (("P + T", ("P", "T")), ("P + H", ("P", "H")),
                                    ("P + S", ("P", "S")), ("P + Q", ("P", "Q")),
                                    ("T + Q", ("T", "Q")))
            ], spacing=TOKENS.spacing_sm, wrap=True
        )
        self.extensive_toggle = ft.Checkbox(
            label="計算廣延性質", value=False, on_change=self._toggle_extensive
        )
        self.extensive_section = ft.Container(
            content=ft.Row([self.mass_tf, self.mass_unit_dd], spacing=TOKENS.spacing_sm),
            visible=False,
        )
        self.result_panel = ResultPanel()
        self.raw_output = self.result_text
        self.raw_output.visible = False
        self.details_button = ft.TextButton("查看詳細結果", on_click=self._toggle_raw_output)
        self.copy_result_button = ft.OutlinedButton(
            "複製結果", icon=ft.Icons.CONTENT_COPY, on_click=self._copy_result
        )
        configuration = EngineeringCard(
            "計算設定",
            ft.ResponsiveRow([
                ft.Container(content=self.mode_dd, col={"xs": 12, "md": 4}),
                ft.Container(content=self.fluid_tf, col={"xs": 12, "md": 4}),
                ft.Container(
                    content=ft.Column([self.ref_state_dd, self.reference_state_helper],
                                      spacing=TOKENS.spacing_xs),
                    col={"xs": 12, "md": 4},
                ),
            ], spacing=TOKENS.spacing_md, run_spacing=TOKENS.spacing_md),
            "選擇計算引擎、物質與 reference state。",
        )
        conditions = EngineeringCard(
            "已知條件（至少兩個）",
            ft.Column([
                self.preset_buttons,
                ft.Column(self.condition_rows, spacing=TOKENS.spacing_md),
                ft.Text(
                    "目前狀態查詢只接受兩個獨立性質；混合物組成、流速或高程等第三條件尚未支援，"
                    "因此暫不提供新增入口。",
                    size=TOKENS.caption,
                    color=ft.Colors.BLUE_GREY_600,
                ),
            ], spacing=TOKENS.spacing_md),
        )
        extensive = EngineeringCard(
            "廣延性質",
            ft.Column([self.extensive_toggle, self.extensive_section], spacing=TOKENS.spacing_sm),
            "需要總質量時才輸入。",
        )
        results = EngineeringCard(
            "計算結果",
            ft.Column([
                self.result_panel,
                ft.Row([self.details_button, self.copy_result_button]),
                self.raw_output,
            ], spacing=TOKENS.spacing_sm),
        )
        scroll_area = ft.Column(
            [configuration, conditions, extensive, results],
            spacing=TOKENS.spacing_md,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
        self.action_bar = ft.Container(
            content=ft.Row([
                ft.TextButton("重設", icon=ft.Icons.RESTART_ALT, on_click=self._reset_inputs),
                ft.Container(expand=True),
                ft.Text("Ctrl + Enter 執行", size=TOKENS.caption, color=ft.Colors.BLUE_GREY_600),
                ft.Button("執行計算", icon=ft.Icons.CALCULATE_OUTLINED,
                          on_click=self.perform_calculation, height=TOKENS.button_height),
            ], spacing=TOKENS.spacing_md),
            padding=ft.Padding.symmetric(horizontal=TOKENS.spacing_lg, vertical=TOKENS.spacing_sm),
            bgcolor=TOKENS.surface,
            border=ft.Border.only(top=ft.BorderSide(1, TOKENS.border)),
        )
        return [scroll_area, self.action_bar]

    def _apply_property_preset(self, property_codes: tuple[str, str]) -> None:
        """套用已知性質組合，並立即更新各列可用的單位選項。

參數：
    property_codes: 預設組合中的兩個性質代碼。

回傳：
    無。"""
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
        self.extensive_section.visible = bool(event.control.value)
        try:
            self.update()
        except RuntimeError:
            pass

    def _toggle_raw_output(self, _event: ft.ControlEvent | None) -> None:
        """按需顯示相容性原始文字輸出，不將其作為主要結果畫面。

參數：
    _event: Flet 點擊事件；此處不需讀取事件內容。

回傳：
    無。"""
        self.raw_output.visible = not self.raw_output.visible
        self.details_button.text = "隱藏詳細結果" if self.raw_output.visible else "查看詳細結果"
        try:
            self.update()
        except RuntimeError:
            pass

    async def _copy_result(self, _event: ft.ControlEvent | None) -> None:
        """透過 Flet 剪貼簿服務複製最近一次成功計算的結果。

參數：
    _event: Flet 點擊事件；此處不需讀取事件內容。

回傳：
    無。"""
        if not self._has_calculated_result:
            return
        await ft.Clipboard().set(self.result_text.value or "")

    def _reset_inputs(self, _event: ft.ControlEvent | None) -> None:
        """清除使用者輸入與結果，但保留目前流體及參考政策。

參數：
    _event: Flet 點擊事件；此處不需讀取事件內容。

回傳：
    無。"""
        for row in self.input_rows:
            row["val"].value = ""
        for quantity_input in self.quantity_inputs:
            quantity_input.set_error(None)
        self.mass_tf.value = ""
        self._has_calculated_result = False
        self._last_si_results = None
        self._last_result_metadata = {}
        self.result_panel.set_status("empty", "尚未計算", "輸入至少兩個獨立性質後執行計算。")
        self.raw_output.value = ""
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
        """將最近一次 SI 結果轉成所選輸出單位，不再呼叫領域計算服務。

回傳：
    無。"""
        if self._last_si_results is None:
            return
        use_imperial = self.output_unit_system == "Imperial"
        metadata = {
            **self._last_result_metadata,
            "Output": "Imperial" if use_imperial else "SI",
        }
        phase = self.formatter._get_phase_description(
            self._last_si_results.get("phase", "unknown")
        )
        self.result_panel.set_metrics(
            self._format_result_metrics(self._last_si_results, use_imperial),
            metadata,
            status_detail=phase,
        )
        self.raw_output.value = self.formatter.format_specific_properties(
            self._last_si_results, use_imperial
        )

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

    def on_fluid_change(self, e):
            """
            物質名稱輸入框改變事件處理器。
            負責檢查物質名稱是否在 CoolProp 資料庫中有效，並提供視覺反饋。
            
            ✨ [修改]：同時為新物質套用當前選定的參考點。
            
            :param e: Flet 事件物件
            """
            fluid_name = self.fluid_tf.value.strip() # 取得並去除物質名稱的空白
            is_valid = True # 用於追蹤物質是否有效
    
            # 僅在 CoolProp 模式下 (即非 Water 模式) 執行檢查
            if self.mode_dd.value.startswith("CoolProp"):
                if not self.query_service.is_fluid_valid(fluid_name):
                    # 物質無效：顯示紅色錯誤提示
                    self.fluid_tf.error_text = f"錯誤：CoolProp 資料庫中找不到物質 '{fluid_name}'"
                    self.fluid_tf.border_color = ft.Colors.RED_700
                    is_valid = False # 標記為無效
                else:
                    # 物質有效：清除錯誤提示，邊框恢復預設顏色
                    self.fluid_tf.error_text = None
                    self.fluid_tf.border_color = ft.Colors.OUTLINE
                    is_valid = True # 標記為有效
                
                # --- ✨ 關鍵修復：在物質名稱改變且有效時，重新套用當前選定的參考點 ---
                if is_valid:
                    try:
                        # 1. 獲取當前選定的參考點代碼
                        selected_option = self.ref_state_dd.value
                        ref_code = selected_option.split(' ')[0] # 例如： "ASHRAE"
                        
                        # 2. 為這個 *新的* 物質 (fluid_name) 套用參考點
                        self.query_service.set_reference_state(fluid_name, ref_code)
                    
                    except Exception as err:
                        # 即使設定參考點失敗 (例如某些流體不支援)，也應顯示錯誤
                        # 但不要阻礙 validation 的 UI 更新
                        self.show_error(f"為 {fluid_name} 設定參考點 {ref_code} 失敗: {err}")
                # --- 修復結束 ---
    
            self.update() # 更新 UI，讓錯誤提示或邊框變化立即顯示
    
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
        """
        模式切換的內部邏輯處理。根據模式調整物質名稱、輸入框狀態和核取方塊可見性。
        此方法不直接呼叫 self.update()。
        
        :param e: Flet 事件物件 (可選)
        """
        is_water = self.mode_dd.value == "Water (水/水蒸氣)"
        # 根據模式設定物質名稱和其是否可編輯
        self.fluid_tf.value = "Water" if is_water else "R32"
        self.fluid_tf.disabled = is_water
        # 水模式下才顯示理想氣體選項，並重設其值
        self.ideal_gas_cb.visible = is_water
        self.ideal_gas_cb.value = False
    
    def on_mode_change(self, e=None):
        """
        模式切換事件處理器 (例如：從 CoolProp 切換到 Water)。
        首先執行內部邏輯更新，然後觸發 UI 更新。
        """
        self.on_mode_change_internal(e) # 執行模式切換的邏輯 (如改變物質名稱、理想氣體核取方塊可見性等)
        if self.parent: self.update()      # 更新 UI，反映模式變更 (如物質名稱改變)

    def on_ref_state_change(self, e: ft.ControlEvent) -> None:
        """依目前流體套用所選的參考狀態政策。

參數：
    e: 參考狀態選單觸發的 Flet 控制事件。

回傳：
    無。"""
        ref_code = self.ref_state_dd.value
        self.reference_state_helper.value = self.ref_state_descriptions[ref_code]
        if self.mode_dd.value.startswith("CoolProp"):
            try:
                self.query_service.set_reference_state(self.fluid_tf.value, ref_code)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Unable to update thermodynamic reference state",
                    extra={"fluid": self.fluid_tf.value, "reference_state": ref_code},
                )
                self.show_error("無法套用此參考狀態，請確認物質與計算模式。")
        if self.parent:
            self.update()

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
        if hasattr(self, "quantity_inputs") and prop_code:
            row_label = self.prop_names_map[prop_code].split(",", 1)[0]
            quantity = self.quantity_inputs[row_index]
            quantity.property_code = prop_code
            quantity.label = row_label
            quantity.label_control.value = row_label
        units = self.unit_converter.get_available_units(prop_code)
        row["unit"].options = [ft.dropdown.Option(unit) for unit in units]

        default_unit = self.unit_converter.default_units.get(prop_code, "")
        new_unit = default_unit if default_unit in units else (units[0] if units else "")
        input_key = f"condition_{row_index}_{prop_code}"
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
        """換算變更列的數值，並同步相同性質輸入列的單位。

參數：
    changed_row_index: 觸發單位變更的輸入列索引。

回傳：
    無。"""
        # 1. 避免遞迴調用：如果正在執行單位更新，則立即返回
        if self._is_updating_units: return
        self._is_updating_units = True # 設置鎖定標記
        
        changed_row = self.input_rows[changed_row_index]
        prop_code_to_sync = self.get_prop_code(changed_row["prop"].value)
        # 獲取新舊單位
        new_unit, old_unit = changed_row["unit"].value, self._last_prop_units[changed_row_index]

        # 2. 判斷是否需要換算和同步 (單位確實改變且舊單位有效)
        if new_unit != old_unit and old_unit and prop_code_to_sync:
            # 遍歷所有輸入行，同步相同性質的單位和換算數值
            for i, row in enumerate(self.input_rows):
                if self.get_prop_code(row["prop"].value) == prop_code_to_sync:
                    row["unit"].value = new_unit # 同步單位下拉選單的值
                    
                    # 只有當輸入框有數值時才執行換算
                    if row["val"].value:
                        try:
                            # 換算三步驟：舊單位 -> SI 單位 -> 新單位
                            val_si = self.unit_converter.convert_to_si(prop_code_to_sync, float(row["val"].value), old_unit)
                            new_val = self.unit_converter.convert_from_si(prop_code_to_sync, val_si, new_unit)
                            
                            # 更新數值，使用 .7g 格式保留足夠精度
                            row["val"].value = f"{new_val:.7g}" 
                        except ValueError: 
                            # 忽略無效數值 (例如： 使用者輸入了非數字)
                            pass
                            
                    self._last_prop_units[i] = new_unit # 更新該行上次單位記錄為新單位
        for index, row in enumerate(self.input_rows):
            property_code = self.get_prop_code(row["prop"].value)
            if property_code:
                self.workspace_state.set_input_unit(
                    f"condition_{index}_{property_code}", row["unit"].value
                )
        self._is_updating_units = False # 釋放鎖定
        if self.parent: self.update() # 更新 UI

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
        try:
            canonical_value = self.unit_converter.convert_to_si(property_code, value, unit)
        except ValueError:
            return None, "目前性質不支援所選單位。"
        if property_code == "P" and canonical_value <= 0:
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
        self._has_calculated_result = False
        self.raw_output.value = ""
        fluid = self.fluid_tf.value.strip()

        # UI 重設：在每次計算開始前，將結果文本和容器邊框重設為預設顏色
        self.result_text.color = ft.Colors.BLACK 

        # 1. 檢查物質名稱是否有效
        if not self.query_service.is_fluid_valid(fluid):
            self.result_panel.set_error("找不到這個物質，請確認流體名稱。")
            # 物質無效時的錯誤處理和 UI 反饋
            self.show_error(f"錯誤：找不到流體 '{fluid}'") # 顯示 SnackBar 提示
            self.result_text.value = f"錯誤：找不到流體 '{fluid}'"
            self.result_text.color = ft.Colors.RED_700 # 錯誤訊息使用紅色
            self.update()
            return # 停止計算

        known_props, display_inputs = [], []
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
            known_props.append((prop_code, value, unit))
            display_inputs.append(f"{row['prop'].value}={raw_value} {unit}")

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
            self.result_text.value = "請至少輸入兩組有效的性質。"
            self.result_text.color = ft.Colors.ORANGE_700 # 使用警告色
            self.update()
            return # 停止計算
        
        # --- 新增 ---
        # 3.5. 根據 UI 切換按鈕，決定輸出單位
        # 讀取 SegmentedButton 的當前選定值 ("SI" 或 "Imperial")
        use_imperial = self.output_unit_system == "Imperial"
        # --- 新增結束 ---

        # 4. 設定計算模式 (CoolProp 實際流體 vs. 理想氣體)
        is_ideal = self.ideal_gas_cb.value and self.mode_dd.value.startswith("Water")
        calc_type = " (理想氣體模型)" if is_ideal else ""
        
        # 5. 顯示「計算中...」訊息 (提供即時反饋)
        self.result_panel.set_status("loading", "計算中", "正在查詢熱力性質。")
        self.result_text.value = f"--- 輸入 ---\n物質: {fluid}{calc_type}\n已知: {', '.join(display_inputs[:2])}\n\n計算中..."
        self.result_text.color = ft.Colors.BLUE_GREY # 計算中提示色
        self.update() # 立即更新 UI 顯示「計算中...」

        # 6. 執行核心熱力學計算
        try:
            # 執行計算，將前兩個輸入性質傳遞給核心計算器
            si_results = self.query_service.query(
                PropertyQueryRequest(
                    fluid,
                    tuple(known_props[:2]),
                    is_ideal,
                    resolve_reference_state_policy(
                        fluid, self.ref_state_dd.value.split(" ")[0]
                    ),
                )
            )
            
            self._last_si_results = si_results
            # 格式化比性質的輸出 (現在 use_imperial 來自 UI 切換按鈕)
            final_output = self.formatter.format_specific_properties(si_results, use_imperial)
            
            # 處理廣延性質計算 (如果輸入了總質量)
            if self.mass_tf.value.strip():
                # 將總質量值換算為 SI 單位 (kg)
                total_mass_kg = self.unit_converter.convert_to_si(
                    "Mass", float(self.mass_tf.value), self.mass_unit_dd.value
                )
                # 將廣延性質結果追加到輸出字串
                final_output += self.formatter.format_extensive_properties(si_results, total_mass_kg, use_imperial)
            
            # 7. 顯示成功結果
            self.result_text.value = f"--- 輸入 ---\n物質: {fluid}{calc_type}\n已知: {', '.join(display_inputs[:2])}\n\n{final_output}"
            self.result_text.color = ft.Colors.BLACK # 成功結果使用黑色
            self._has_calculated_result = True
            ref_code = self.ref_state_dd.value.split(" ")[0]
            metadata = {
                "Fluid": fluid,
                "Engine": "Ideal Gas" if is_ideal else "CoolProp",
                "Reference": ref_code,
                "Input units": ", ".join(item.rsplit(" ", 1)[-1] for item in display_inputs[:2]),
                "Output": "Imperial" if use_imperial else "SI",
            }
            self._last_result_metadata = metadata.copy()
            phase = self.formatter._get_phase_description(si_results.get("phase", "unknown"))
            self.result_panel.set_metrics(
                self._format_result_metrics(si_results, use_imperial), metadata, status_detail=phase
            )
            self.raw_output.value = final_output
            
        except Exception as err:
            # 8. 捕獲計算錯誤
            error_message = str(err) if isinstance(err, ValueError) else "無法使用目前條件完成計算。"
            self.result_panel.set_error(error_message)
            self.raw_output.value = ""
            self.show_error(error_message) # 顯示 SnackBar 提示
            self.result_text.value = error_message # 結果區顯示詳細錯誤
            self.result_text.color = ft.Colors.RED_700 # 錯誤訊息使用紅色
            
        finally:
            self.update() # 無論成功或失敗，確保 UI 最終狀態被更新