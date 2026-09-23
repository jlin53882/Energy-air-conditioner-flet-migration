# ui_components/analysis_tab.py (最終重構版 - 功能群組載入器)

import flet as ft
from .unit.UnitConverter import UnitConverter
from .unit.HVACAnalyzer import HVACAnalyzer
from .unit.PsychrometricCalculator import PsychrometricCalculator
# --- ✨ 新增這一行 ---
from .unit.ThermoStateCalculator import ThermoStateCalculator
from application.property_queries import PropertyQueryService
# --- 新增結束 ---

# --- 1. 匯入您所有的 "功能群組" 模組 ---
from .analysis_modules.hvac_compressor_module import CompressorModule
from .analysis_modules.hvac_evaporator_module import EvaporatorModule
from .analysis_modules.hvac_condenser_module import CondenserModule
from .analysis_modules.psy_module import PsyModule
from .analysis_modules.thermo_diagram_module import ThermoDiagramModule


# --- 導入未來的新模組 ---
# from .analysis_modules.hvac_condenser_module import CondenserModule
# from .analysis_modules.hvac_expansion_valve_module import ExpansionValveModule

class AnalysisTab(ft.Column):
    def __init__(self, unit_converter: UnitConverter, page: ft.Page, 
                 analyzer: HVACAnalyzer, psy_calculator: PsychrometricCalculator,
                 state_calculator: ThermoStateCalculator,
                 property_query_service: PropertyQueryService | None = None):
        
        """建立分析模組與分類控制項，並避免共用容器重複繪製。

參數：
    unit_converter: 分析模組共用的單位轉換器。
    page: Flet 應用程式頁面。
    analyzer: HVAC 分析服務。
    psy_calculator: 濕空氣計算服務。
    state_calculator: 熱力狀態計算服務。
    property_query_service: 選用的熱力性質查詢服務。

回傳：
    無。"""
        super().__init__(scroll=ft.ScrollMode.AUTO, expand=True)
        
        # --- 2. 實例化所有 "功能群組" 模組 ---
        self.modules_to_load = [
            CompressorModule(
                unit_converter=unit_converter,
                page=page,
                analyzer=analyzer,
                state_calculator=state_calculator,
                property_query_service=property_query_service,
            ),
            EvaporatorModule(unit_converter=unit_converter, page=page, analyzer=analyzer),
            CondenserModule(unit_converter=unit_converter, page=page, analyzer=analyzer,state_calculator=state_calculator),
            PsyModule(unit_converter=unit_converter, page=page, psy_calculator=psy_calculator),
            ThermoDiagramModule(unit_converter, page, analyzer, state_calculator),
            
            
            
            # 未來新增功能群組，只需在這裡加一行
            # CondenserModule(unit_converter=unit_converter, page=page, analyzer=analyzer),
        ]
        
        # --- 3. 建立 "名稱" -> "功能" 的全域映射 ---
        self.analysis_map = {}
        all_ui_controls = []
        seen_ui_control_ids = set()
        
        for module in self.modules_to_load:
            definitions = module.get_analysis_definitions()
            for name, raw_definition in definitions.items():
                definition = dict(raw_definition)
                definition.setdefault("calculation_mode", "standard")
                analysis_id = definition.get("analysis_id")
                if not isinstance(analysis_id, str) or not analysis_id.strip():
                    raise ValueError(f"Analysis '{name}' is missing analysis_id")
                if any(
                    existing.get("analysis_id") == analysis_id
                    for existing in self.analysis_map.values()
                ):
                    raise ValueError(f"Duplicate analysis_id: {analysis_id}")
                self.analysis_map[name] = definition
                ui_control = definition["ui"]
                if id(ui_control) not in seen_ui_control_ids:
                    all_ui_controls.append(ui_control)
                    seen_ui_control_ids.add(id(ui_control))

        # --- 4. 動態建立下拉選單 ---
        self.analysis_dd = ft.Dropdown(
            label="分析項目",
            # 從映射的鍵動態產生選項
            options=[ft.dropdown.Option(name) for name in self.analysis_map.keys()],
            value=list(self.analysis_map.keys())[0], # 預設選中第一個
            on_select=self.on_analysis_change
        )
        
        # --- 5. 動態建立 UI 容器 (Stack) ---
        self.controls_stack = ft.Stack(
            controls=all_ui_controls
        )
        
        # --- 6. 建立統一的計算按鈕和結果區 (同上一個版本) ---
        self.calc_button = ft.Button(
            content="執行分析",
            on_click=self.calculate_analysis, 
            icon=ft.Icons.ANALYTICS_OUTLINED
        )
        
        self.output_unit_toggle = ft.SegmentedButton(
            allow_empty_selection=False,
            segments=[
                ft.Segment(value="SI", label=ft.Text("SI (公制)")),
                ft.Segment(value="Imperial", label=ft.Text("Imperial (英制)")),
            ],
            selected=["SI"],
            on_change=self.on_output_unit_change,
        )

        self.analysis_mode_status = ft.Text(
            "", color=ft.Colors.BLUE_700, visible=False, weight=ft.FontWeight.W_600
        )
        self.result_text = ft.Text("請選擇分析項目並點擊執行...", font_family="Courier New", selectable=True, color=ft.Colors.GREY_600)
        self._has_calculated_result = False
        self.result_container = ft.Container(
            content=self.result_text,
            border=ft.Border.all(1, ft.Colors.BLUE_GREY_200),
            border_radius=ft.BorderRadius.all(8),
            padding=ft.Padding.all(15),
            expand=True,
            alignment=ft.Alignment.TOP_LEFT
        )

        # --- 7. 組合 AnalysisTab 自己的 UI ---
        self.calc_button_container = ft.Container(
            content=self.calc_button,
            padding=ft.Padding.only(top=15, bottom=15),
            alignment=ft.Alignment.CENTER,
        )
        self.controls = [
            ft.Container(
                content=self.analysis_dd,
                padding=ft.Padding.only(top=10, bottom=5)
            ),
            ft.Divider(height=1),
            ft.Text("參數輸入", theme_style=ft.TextThemeStyle.TITLE_MEDIUM, weight=ft.FontWeight.W_600),
            
            self.controls_stack, # 包含所有模組 UI 的容器
            
            self.calc_button_container,
            
            ft.Row(
                controls=[
                    ft.Text("分析結果", theme_style=ft.TextThemeStyle.TITLE_LARGE, weight=ft.FontWeight.W_900, expand=True),
                    self.output_unit_toggle,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            self.result_container
        ]

        # --- 8. 初始化第一個模組的 UI ---
        self.on_analysis_change(None) 
        self.on_output_unit_change(None)
        self._configure_workspace_layout()
        self.set_category("compressor")

    def set_category(self, category: str) -> None:
        """切換工程分類，並同步更新可用分析選項與選取狀態。

參數：
    category: 既有分析模組使用的分類代碼。

回傳：
    無。"""
        self.active_category = category
        prefix = "thermodynamics" if category == "charts" else category
        self._active_analysis_names = [
            name for name, definition in self.analysis_map.items()
            if definition["analysis_id"].startswith(prefix + ".")
        ]
        if not self._active_analysis_names:
            raise KeyError(f"No registered analysis route: {category}")
        self.analysis_dd.value = self._active_analysis_names[0]
        self.module_nav.controls = [
            ft.OutlinedButton(
                name,
                on_click=lambda _event, selected=name: self.select_analysis(selected),
            )
            for name in self._active_analysis_names
        ]
        self.on_analysis_change(None)

    def select_analysis(self, name: str) -> None:
        """在目前分析分類中選取一項已實作的計算。

參數：
    name: 既有分析註冊表中的計算名稱。

回傳：
    無。"""
        if name not in self._active_analysis_names:
            raise KeyError(f"Analysis is not part of {self.active_category}: {name}")
        self.analysis_dd.value = name
        self.on_analysis_change(None)

    def _configure_workspace_layout(self) -> None:
        """排列分析模式、目前模式提示、輸入區與共用結果控制項。

回傳：
    無。"""
        self.module_nav = ft.Row(controls=[], spacing=8, wrap=True)
        self.result_header_row = ft.Row([
            ft.Text("分析結果", theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                    weight=ft.FontWeight.W_600, expand=True),
            self.output_unit_toggle,
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        self.controls = [
            ft.Text("分析模式", theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                    weight=ft.FontWeight.W_600),
            self.module_nav,
            self.analysis_mode_status,
            self.controls_stack,
            self.calc_button_container,
            self.result_header_row,
            self.result_container,
        ]

    def on_output_unit_change(self, e):
        """切換輸出單位時，通知 *所有* 模組更新大氣壓力預設值

參數：
    e (未指定型別): 函數輸入值。

回傳：
    無。"""
        use_imperial = ("Imperial" in self.output_unit_toggle.selected)
        
        # 遍歷 *所有* 載入的模組，並安全地呼叫
        for module in self.modules_to_load:
            # 檢查模組是否有 'update_atm_pressure_default' 方法
            if hasattr(module, 'update_atm_pressure_default') and callable(module.update_atm_pressure_default):
                module.update_atm_pressure_default(use_imperial)
        
        if self._has_calculated_result:
            self.calculate_analysis(None)
        elif e is not None:
            try:
                attached_page = self.page
            except RuntimeError:
                attached_page = None
            if attached_page:
                self.update()

    def on_analysis_change(self, e):
            """切換唯一可見分析面板，並更新濕空氣模式的選取提示。

參數：
    e: Flet 控制項變更事件；程式直接切換時可為 None。

回傳：
    無。"""
            self._has_calculated_result = False
            selected_name = self.analysis_dd.value

            # --- 新邏輯 ---

            # 1. 取得所有 *獨特* 的 UI 容器
            #    (使用 set comprehension 來自動去除重複的 UI)
            all_unique_uis = {definition["ui"] for definition in self.analysis_map.values()}

            # 2. 隱藏 *所有* 容器
            for ui in all_unique_uis:
                ui.visible = False

            # 3. 取得 *選中* 的 UI 容器...
            selected_definition = self.analysis_map[selected_name]
            selected_ui = selected_definition["ui"]

            # 4. ...並 *只顯示* 它
            selected_ui.visible = True
            is_psychrometric = selected_definition["calculation_mode"] == "psychrometric"
            self.analysis_mode_status.visible = is_psychrometric
            self.analysis_mode_status.value = (
                f"目前模式：{selected_name}" if is_psychrometric else ""
            )
            if hasattr(self, "module_nav"):
                for button, name in zip(self.module_nav.controls, self._active_analysis_names):
                    is_selected = name == selected_name
                    button.style = ft.ButtonStyle(
                        color=ft.Colors.WHITE if is_selected else ft.Colors.BLUE_GREY_800,
                        bgcolor=ft.Colors.BLUE_700 if is_selected else ft.Colors.WHITE,
                        side=ft.BorderSide(
                        1,
                        ft.Colors.BLUE_700 if is_selected else ft.Colors.BLUE_GREY_300,
                    ),
                    )

            # --- 新邏輯結束 ---

            # --- 模組專屬能力由明確 metadata 表示，而不是由標籤前綴表示。 ---
            # 熱力圖有專屬繪圖操作，因此不顯示重複的共用執行按鈕。
            self.calc_button_container.visible = selected_definition.get("show_execute_button", True)
            if hasattr(self, "result_header_row"):
                show_result_panel = selected_definition.get("show_result_panel", True)
                self.result_header_row.visible = show_result_panel
                self.result_container.visible = show_result_panel
            if selected_definition["calculation_mode"] == "psychrometric":
                for module in self.modules_to_load:
                    if isinstance(module, PsyModule):
                        module.configure_ui_for_mode(selected_name)
                        break
                    
            # --- 重置結果區域 ---
            self.result_text.value = "請選擇分析項目並點擊執行..."
            self.result_text.color = ft.Colors.GREY_600 
            self.result_container.border_color = ft.Colors.BLUE_GREY_200 

            # 只有在 Flet 頁面存在時 (即非 __init__ 期間) 才更新
            if self.parent:
                self.update()

    def calculate_analysis(self, e):
        """
        執行計算
        *** 程式碼永不需修改 ***
        """
        self._has_calculated_result = False
        try:
            # 1. 找到當前選中的功能定義
            selected_name = self.analysis_dd.value
            current_definition = self.analysis_map[selected_name]
            
            # 2. 獲取要呼叫的特定計算函式
            calc_func = current_definition["calc_func"]
            
            # 3. 獲取輸出單位
            use_imperial = ("Imperial" in self.output_unit_toggle.selected)
            
            # 4. 呼叫宣告的計算模式；標籤永遠不控制 dispatch。
            if current_definition["calculation_mode"] == "psychrometric":
                result_string = calc_func(use_imperial, mode_name=selected_name)
            else:
                result_string = calc_func(use_imperial)
            
            # 5. 顯示結果
            self.result_text.value = result_string
            self.result_text.color = ft.Colors.BLACK
            self.result_container.border_color = ft.Colors.GREEN_700
            self._has_calculated_result = True

        except ValueError as ve: 
            error_message = f"輸入/計算錯誤: {ve}" 
            self.result_text.value = error_message
            self.result_text.color = ft.Colors.RED_700
            self.result_container.border_color = ft.Colors.RED_700
        except Exception as err: 
            error_message = f"計算錯誤: {err}"
            self.result_text.value = error_message
            self.result_text.color = ft.Colors.RED_700
            self.result_container.border_color = ft.Colors.RED_700
            
        try:
            attached_page = self.page
        except RuntimeError:
            attached_page = None
        if attached_page:
            self.update()

    def show_error(self, message):
        """在已掛載的 Flet 頁面中顯示全域 SnackBar 錯誤提示。

參數：
    message: 要向使用者顯示的錯誤摘要。

回傳：
    無。"""
        snack = ft.SnackBar(ft.Text(message), bgcolor=ft.Colors.ERROR)
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()