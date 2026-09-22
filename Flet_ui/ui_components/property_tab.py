# ui_components/property_tab.py
"""
用來處理 熱力學查表相關工具內容

"""

import flet as ft
# PropertyTab 繼承自 ft.Column，使其可以直接作為 Flet UI 中的一個垂直佈局容器。
# 導入新類別的 "合約" (interfaces)
from ..ui_components.unit.UnitConverter import UnitConverter
from ..ui_components.unit.PropertyFormatter import PropertyFormatter
from application.models import PropertyQueryRequest
from application.property_queries import PropertyQueryService
from domain.thermodynamics.reference_state import ReferenceStatePolicy

# PropertyTab 繼承自 ft.Column，使其可以直接作為 Flet UI 中的一個垂直佈局容器。
def resolve_property_reference_state(
    fluid: str, selected_policy: str
) -> ReferenceStatePolicy | str:
    """Resolve the explicit policy for an ordinary PropertyTab request."""
    if fluid == "Water":
        return ReferenceStatePolicy.DEFAULT
    return selected_policy


class PropertyTab(ft.Column):
    def __init__(self, unit_converter: UnitConverter, 
                 formatter: PropertyFormatter, 
                 page: ft.Page,
                 query_service: PropertyQueryService):
        """
        初始化 PropertyTab，設定 UI 組件和數據綁定。

        :param calculator: 核心計算邏輯實例 (ThermoCalculator)
        :param page: Flet 頁面實例
        """
        # 初始化 ft.Column 的屬性：啟用垂直滾動，並展開佔滿可用空間
        super().__init__(scroll=ft.ScrollMode.AUTO, expand=True) 
        
        # 分別儲存所需的服務
        self.unit_converter = unit_converter 
        self.formatter = formatter
        self.query_service = query_service
        
        # 性質代碼到名稱的映射 (用於下拉選單顯示)
        # 格式為: {代碼: "名稱 (中文), 代碼"} (例如: 'P' -> 'Pressure (壓力), P')
        self.prop_names_map = {
            # 將代碼 (code) 追加到現有名稱 (name) 的末尾
            code: f"{name}, {code}" 
            for code, name in self.formatter.prop_names.items()
        }
        # 追蹤上次的單位，用於單位轉換時的比對和換算 (每行一個)
        self._last_prop_units = ["", "", ""] 
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
        self.ref_state_dd = ft.Dropdown(
            label="參考點標準", 
            value="ASHRAE (美國暖通空調學會標準)", 
            options=[
                ft.dropdown.Option("Default (內建預設值)"),
                ft.dropdown.Option("IIR (國際冷藏協會)"),
                ft.dropdown.Option("ASHRAE (美國暖通空調學會標準)"), # 預設值
                ft.dropdown.Option("NBP (正常沸點)"),
            ],
            on_select=self.on_ref_state_change,
            expand=True, # 佔滿同行剩餘空間
            width=250, # 調整寬度以容納長名稱
        )
        
        # 2. 性質輸入區塊 (Property Input Block)
        self.input_rows = [] # 儲存三行輸入控制項的字典列表
        for i in range(3):
            # 性質名稱下拉選單
            prop_dd = ft.Dropdown(
                label=f"性質 {i+1}",
                value=self.prop_names_map[self.formatter.properties[i]], # 預設值, # 預設值
                options=[ft.dropdown.Option(name) for name in self.prop_names_map.values()],
                width=250, # 調整後的較寬度，確保顯示完整的性質名稱和代碼
            )
            # 數值輸入框，限制鍵盤輸入類型為數字
            val_tf = ft.TextField(label="數值", expand=True, keyboard_type=ft.KeyboardType.NUMBER) 
            # 單位下拉選單
            unit_dd = ft.Dropdown(label="單位", width=120) 
            
            # 設置事件處理器 (使用閉包確保傳遞正確的索引 i)
            prop_dd.on_change = self.create_prop_change_handler(i)
            unit_dd.on_change = self.create_unit_change_handler(i)

            self.input_rows.append({"prop": prop_dd, "val": val_tf, "unit": unit_dd})
            # 初始化時為單位選單載入選項和預設值
            self._update_units_menu_content(i) 
            
        # 3. 廣延性質區塊 (Extensive Property Block)
        # 總質量輸入框
        self.mass_tf = ft.TextField(label="總質量", expand=True, keyboard_type=ft.KeyboardType.NUMBER)
        # 總質量單位下拉選單
        self.mass_unit_dd = ft.Dropdown(label="單位", value="kg", options=[ft.dropdown.Option("kg"), ft.dropdown.Option("lbm")], width=100)

        # 4. 計算按鈕 (Calculation Button)
        self.calc_button = ft.Button(
            content="執行計算",
            on_click=self.perform_calculation, 
            icon=ft.Icons.CALCULATE_OUTLINED, # 使用計算圖標
            height=40,
        ) 
        
        # 5. 結果顯示區 (Result Display Block)
        # --- 新增 ---
        # 5a. 輸出單位切換 (Output Unit Toggle)
        self.output_unit_toggle = ft.SegmentedButton(
            allow_empty_selection=False, # 不允許空選
            segments=[
                ft.Segment(value="SI", label=ft.Text("SI (公制)")),
                ft.Segment(value="Imperial", label=ft.Text("Imperial (英制)")),
            ],
            selected=["SI"], # 預設選中 SI
        )
        # --- 新增結束 ---


        self.result_text = ft.Text(
            "點擊 '執行計算' 查看結果...", 
            font_family="Courier New", # 為了結果對齊，使用等寬字體
            selectable=True, 
            color=ft.Colors.GREY_600 # 初始提示文字使用灰色
        )
        self.result_container = ft.Container(
            content=self.result_text,
            # 結果區視覺優化：增加邊框和圓角
            border=ft.Border.all(1, ft.Colors.BLUE_GREY_200),
            border_radius=ft.BorderRadius.all(8),
            padding=ft.Padding.all(15), # 內邊距
            alignment=ft.Alignment.TOP_LEFT # 文字靠左上對齊
        )

        # 初始化模式設定 (設定 fluid_tf 和 ideal_gas_cb 的初始狀態)
        self.on_mode_change_internal()

        # 6. 結構化 UI 佈局 (將所有控制項組織到 ft.Column 中)
        self.controls = [
            # 模式和物質輸入 (並排佈局)
            ft.Container(
                content=ft.Row(controls=[self.mode_dd, self.fluid_tf, self.ideal_gas_cb], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=ft.Padding.only(top=10, bottom=5)
            ),
            # --- 新增 3: 參考點下拉選單佈局 ---            
            ft.Row(controls=[self.ref_state_dd], alignment=ft.MainAxisAlignment.START),
            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
            
            # 性質輸入區塊標題
            ft.Text("熱力學性質輸入 (至少兩組)", theme_style=ft.TextThemeStyle.TITLE_MEDIUM, weight=ft.FontWeight.W_600),
            
            # 性質輸入行 (垂直堆疊三行輸入 Row)
            ft.Column(controls=[
                ft.Row(controls=[row["prop"], row["val"], row["unit"]]) 
                for row in self.input_rows
            ], spacing=10), 

            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
            
            # 廣延性質區塊標題
            ft.Text("廣延性質 (可選)", theme_style=ft.TextThemeStyle.TITLE_MEDIUM, weight=ft.FontWeight.W_600),
            ft.Row(controls=[self.mass_tf, self.mass_unit_dd]),
            
            # 計算按鈕容器 (居中顯示按鈕)
            ft.Container(
                content=self.calc_button,
                padding=ft.Padding.only(top=15, bottom=15),
                alignment=ft.Alignment.CENTER
            ),

            
            
            # --- 修改 ---
            # 結果區塊標題 和 單位切換
            ft.Row(
                controls=[
                    ft.Text(
                        "計算結果", 
                        theme_style=ft.TextThemeStyle.TITLE_LARGE,
                        weight=ft.FontWeight.W_900,     
                        color=ft.Colors.BLUE_GREY_900,
                        expand=True, # 讓標題佔用多餘空間
                    ),
                    self.output_unit_toggle, # 將切換按鈕放在標題旁邊
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN, # 讓標題和按鈕左右對齊
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            # --- 修改結束 --
            # 結果顯示容器
            self.result_container
        ]
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

    # --- 邏輯方法維持不變，僅為保持完整性 ---

    def get_prop_code(self, formatted_name):
        """
        根據下拉選單中格式化的性質名稱 (e.g., 'Pressure (壓力), P')，
        逆向查找並返回其單一字母的代碼 (e.g., 'P')。

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
                        ref_code = selected_option.split(' ')[0] # e.g., "ASHRAE"
                        
                        # 2. 為這個 *新的* 物質 (fluid_name) 套用參考點
                        self.query_service.set_reference_state(fluid_name, ref_code)
                    
                    except Exception as err:
                        # 即使設定參考點失敗 (例如某些流體不支援)，也應顯示錯誤
                        # 但不要阻礙 validation 的 UI 更新
                        self.show_error(f"為 {fluid_name} 設定參考點 {ref_code} 失敗: {err}")
                # --- 修復結束 ---
    
            self.update() # 更新 UI，讓錯誤提示或邊框變化立即顯示
    
    def _update_units_menu_content(self, row_index):
        """
        內部輔助方法：根據當前選定的性質，初始化或更新該行單位選單的選項和預設值。
        此方法通常在 __init__ 或性質改變時被呼叫，且不觸發外部 UI 更新。
        
        :param row_index: 輸入行索引
        """
        row = self.input_rows[row_index]
        prop_code = self.get_prop_code(row["prop"].value)
        
        # 獲取該性質的所有可用單位列表
        units = self.unit_converter.get_available_units(prop_code) 
        
        # 更新單位下拉選單的選項
        row["unit"].options = [ft.dropdown.Option(u) for u in units]
        
        # 處理單位選單的預設值設定
        if not units:
             # 如果沒有可用單位 (e.g., 乾度 Q)，設置為預設的空字串
             default_val = self.unit_converter.default_units.get(prop_code, "")
             row["unit"].value = default_val
             self._last_prop_units[row_index] = default_val # 記錄上次單位
        else:
             # 嘗試使用定義的預設單位
             default_unit = self.unit_converter.default_units.get(prop_code)
             # 選擇新的單位：如果預設單位存在於可用列表中，則使用；否則使用列表中的第一個
             new_unit = default_unit if default_unit in units else units[0]
             row["unit"].value = new_unit
             self._last_prop_units[row_index] = new_unit # 記錄上次單位

    # 輔助方法：顯示錯誤訊息 SnackBar
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

# --- 新增 2: 參考點變更事件處理器 ---
    def on_ref_state_change(self, e):
        """
        處理參考點下拉選單變更事件，並設定 CoolProp 的參考點。
        這裡我們以 R134a 為範例物質來設定參考點。
        
        :param e: Flet 事件物件
        """
        # 提取選單值中的代碼部分，例如 'ASHRAE (美國...)' -> 'ASHRAE'
        selected_option = self.ref_state_dd.value
        # 使用正則表達式或簡單分割來獲取代碼
        # 'ASHRAE (美國暖通空調學會標準)' -> 'ASHRAE'
        ref_code = selected_option.split(' ')[0] 
        
        # 只有在 CoolProp 模式下才需要設定參考點
        if self.mode_dd.value.startswith("CoolProp"):
            try:
                # Application service owns the process-global CoolProp boundary.
                
                # 執行關鍵步驟：設置 R134a 的參考點
                self.query_service.set_reference_state(self.fluid_tf.value, ref_code)
                
                # 可選：顯示成功的 SnackBar 提示
                #self.page.snack_bar = ft.SnackBar(ft.Text(f"參考點已設定為: {ref_code} {self.fluid_tf.value}"))
                #self.page.snack_bar.open = True
                
            except Exception as err:
                self.show_error(f"設定參考點錯誤: {err}")
                
            finally:
                if self.parent: self.update() # 更新 UI
        
    def update_units_menu(self, row_index):
        """
        當性質下拉選單 (prop_dd) 改變時，更新對應的單位下拉選單內容和預設值。
        
        :param row_index: 變動的輸入行索引 (0, 1, 2)
        """
        row = self.input_rows[row_index]
        # 根據選單中顯示的名稱獲取性質代碼 (e.g., 'Pressure (壓力), P' -> 'P')
        prop_code = self.get_prop_code(row["prop"].value)
        
        # 從核心計算器獲取該性質的所有可用單位列表
        units = self.unit_converter.get_available_units(prop_code) 
        
        # 更新單位下拉選單的選項
        row["unit"].options = [ft.dropdown.Option(u) for u in units]
        
        # 處理沒有單位或設置預設單位的情況
        if not units:
             # 如果沒有可用單位 (例如乾度 Q)，則設置為空值
             row["unit"].value = ""
             self._last_prop_units[row_index] = "" # 記錄上次單位為空
        else:
             # 獲取該性質的預設單位 (e.g., 'kPa')
             default_unit = self.unit_converter.default_units.get(prop_code)
             # 選擇新的單位：優先使用預設單位，否則使用列表中的第一個單位
             new_unit = default_unit if default_unit in units else units[0]
             row["unit"].value = new_unit               # 設定單位下拉選單的值
             self._last_prop_units[row_index] = new_unit # 記錄本次單位，供下次換算使用
            
        if self.parent: self.update() # 更新 UI，顯示新的單位選單內容和選定值

    def create_prop_change_handler(self, index):
        """
        使用閉包為每個性質下拉選單創建 on_change 事件處理器。
        
        :param index: 輸入行索引
        :return: 處理函數 (handler)
        """
        # 當性質改變時，呼叫 update_units_menu 來更新單位
        def handler(e): self.update_units_menu(index) 
        return handler

    def create_unit_change_handler(self, index):
        """
        使用閉包為每個單位下拉選單創建 on_change 事件處理器。
        
        :param index: 輸入行索引
        :return: 處理函數 (handler)
        """
        # 當單位改變時，呼叫 on_property_unit_change 來處理數值換算和單位同步
        def handler(e): self.on_property_unit_change(index)
        return handler

    def on_property_unit_change(self, changed_row_index):
        """
        單位變更的核心處理邏輯：執行數值換算並同步相同性質的單位。
        
        :param changed_row_index: 觸發變更的輸入行索引
        """
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
                            # 忽略無效數值 (e.g., 使用者輸入了非數字)
                            pass
                            
                    self._last_prop_units[i] = new_unit # 更新該行上次單位記錄為新單位
        
        self._is_updating_units = False # 釋放鎖定
        if self.parent: self.update() # 更新 UI

    def perform_calculation(self, e):
        """
        執行熱力學性質計算的主方法。
        負責輸入驗證、錯誤處理、UI 反饋和結果展示。
        """
        fluid = self.fluid_tf.value.strip()
        
        # UI 重設：在每次計算開始前，將結果文本和容器邊框重設為預設顏色
        self.result_text.color = ft.Colors.BLACK 
        self.result_container.border_color = ft.Colors.BLUE_GREY_200 

        # 1. 檢查物質名稱是否有效
        if not self.query_service.is_fluid_valid(fluid):
            # 物質無效時的錯誤處理和 UI 反饋
            self.show_error(f"錯誤：找不到流體 '{fluid}'") # 顯示 SnackBar 提示
            self.result_text.value = f"錯誤：找不到流體 '{fluid}'"
            self.result_text.color = ft.Colors.RED_700 # 錯誤訊息使用紅色
            self.result_container.border_color = ft.Colors.RED_700 # 邊框使用紅色
            self.update()
            return # 停止計算

        known_props, display_inputs= [], []
        
        # 2. 收集輸入的性質 (只取前兩個有數值的作為計算依據)
        for row in self.input_rows:
            if row["val"].value.strip():
                try:
                    prop_code = self.get_prop_code(row["prop"].value)
                    unit = row["unit"].value
                    
                    # 存儲為 (屬性代碼, 數值, 單位) 格式
                    known_props.append((prop_code, float(row["val"].value), unit))
                    # 存儲用於顯示的輸入摘要
                    display_inputs.append(f"{row['prop'].value}={row['val'].value} {unit}")
                except (ValueError, TypeError): 
                    # 忽略無效的數值輸入
                    pass 

        # 3. 檢查已知性質數量 (CoolProp 核心要求至少兩個獨立性質)
        if len(known_props) < 2:
            # 輸入不足時的錯誤處理和 UI 反饋
            self.show_error("請至少輸入兩組有效的性質。")
            self.result_text.value = "請至少輸入兩組有效的性質。"
            self.result_text.color = ft.Colors.ORANGE_700 # 使用警告色
            self.result_container.border_color = ft.Colors.ORANGE_700
            self.update()
            return # 停止計算
        
        # --- 新增 ---
        # 3.5. 根據 UI 切換按鈕，決定輸出單位
        # 讀取 SegmentedButton 的當前選定值 ("SI" 或 "Imperial")
        use_imperial = ("Imperial" in self.output_unit_toggle.selected)
        # --- 新增結束 ---

        # 4. 設定計算模式 (CoolProp 實際流體 vs. 理想氣體)
        is_ideal = self.ideal_gas_cb.value and self.mode_dd.value.startswith("Water")
        calc_type = " (理想氣體模型)" if is_ideal else ""
        
        # 5. 顯示「計算中...」訊息 (提供即時反饋)
        self.result_text.value = f"--- 輸入 ---\n物質: {fluid}{calc_type}\n已知: {', '.join(display_inputs[:2])}\n\n計算中..."
        self.result_text.color = ft.Colors.BLUE_GREY # 計算中提示色
        self.result_container.border_color = ft.Colors.BLUE_GREY_400
        self.update() # 立即更新 UI 顯示「計算中...」

        # 6. 執行核心熱力學計算
        try:
            # 執行計算，將前兩個輸入性質傳遞給核心計算器
            si_results = self.query_service.query(
                PropertyQueryRequest(
                    fluid,
                    tuple(known_props[:2]),
                    is_ideal,
                    resolve_property_reference_state(
                        fluid, self.ref_state_dd.value.split(" ")[0]
                    ),
                )
            )
            
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
            self.result_container.border_color = ft.Colors.GREEN_700 # 成功邊框色
            
        except Exception as err:
            # 8. 捕獲計算錯誤
            error_message = f"計算錯誤: {err}"
            self.show_error(error_message) # 顯示 SnackBar 提示
            self.result_text.value = error_message # 結果區顯示詳細錯誤
            self.result_text.color = ft.Colors.RED_700 # 錯誤訊息使用紅色
            self.result_container.border_color = ft.Colors.RED_700 # 錯誤邊框色
            
        finally:
            self.update() # 無論成功或失敗，確保 UI 最終狀態被更新