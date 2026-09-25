# ui_components/analysis_modules/base_analysis_module.py
# (新介面 - 支援功能群組)

import flet as ft
from ..unit.UnitConverter import UnitConverter
from ...ui.theme import TOKENS, style_dropdown, style_text_field

class BaseAnalysisModule:
    """
    這是一個 "規範" 或 "合約" (新版)。
    一個模組可以提供 *多個* 相關的分析功能。
    例如：CompressorModule 可以同時提供 "壓縮比" 和 "壓縮機功率"。
    """
    def __init__(self, unit_converter: UnitConverter, page: ft.Page, **kwargs):
        """
        :param unit_converter: 必要的服務
        :param page: 必要的服務
        :param kwargs: 其他服務, 例如 'analyzer' 或 'psy_calculator'
        """
        self.unit_converter = unit_converter
        self.page = page
        # 舊版處理器使用 ``parent`` 作為附加標記；請保留它
        # 明確保留，因為此服務物件本身不是 Flet Control。
        self.parent = page
        
        # 儲存傳入的其他服務 (例如 self.analyzer)
        self.services = kwargs
        
        # --- 單位同步邏輯 (從舊 analysis_tab 搬移) ---
        self.all_entries = {} # 儲存此模組 *所有* 的 UI 元件 (跨功能)
        self._is_updating_units = False
        self._last_units = {}
        # ---

    def get_analysis_definitions(self) -> dict:
        """
        子類別必須實作此方法。
        
        返回一個字典，定義此模組提供的所有功能。
        
        格式:
        {
            "功能顯示名稱 1": {
                "ui": ft.Container(...),
                "calc_func": self.calculate_function_1
            },
            "功能顯示名稱 2": {
                "ui": ft.Container(...),
                "calc_func": self.calculate_function_2
            }
        }
        """
        raise NotImplementedError

    # --- 輔助函式：從舊 analysis_tab 搬移過來 ---
    
    def create_input_row(
        self,
        key: str,
        label: str,
        default_val: str | int | float,
        prop_code: str,
        default_unit: str | None = None,
    ) -> dict[str, object]:
        """建立單位輸入列，讓標籤與欄位外框分開呈現。

        參數：
            key: 此輸入值在模組中的識別鍵。
            label: 數值欄位的說明文字。
            default_val: 欄位初始值。
            prop_code: 單位轉換器使用的性質代碼。
            default_unit: 選用的初始單位；未提供時採用預設單位。

        回傳：
            包含輸入欄位、單位選單、標籤與列控制項的字典。
        """
        units = self.unit_converter.get_available_units(prop_code)
        
        if default_unit and default_unit in units:
            final_default_unit = default_unit
        else:
            final_default_unit = self.unit_converter.default_units.get(prop_code)
            if final_default_unit not in units:
                final_default_unit = units[0] if units else ""

        self._last_units[key] = final_default_unit

        label_control = ft.Text(
            label, size=TOKENS.body, weight=ft.FontWeight.W_500, color=TOKENS.text_primary
        )
        val_tf = style_text_field(ft.TextField(
            value=str(default_val),
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
            height=TOKENS.input_height,
            hint_text="輸入數值",
        ))

        unit_label_control = ft.Text("單位", size=TOKENS.caption, color=TOKENS.text_muted)
        unit_dd = style_dropdown(ft.Dropdown(
            value=final_default_unit,
            options=[ft.dropdown.Option(u) for u in units],
            width=124,
            height=TOKENS.input_height,
            disabled=(prop_code == "RH" or prop_code == "Q")
        ))

        value_column = ft.Column(
            controls=[label_control, val_tf],
            spacing=6,
            expand=True
        )
        unit_column = ft.Column(
            controls=[unit_label_control, unit_dd],
            spacing=6,
            width=124,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )
        input_row = ft.Row(
            controls=[value_column, unit_column],
            alignment=ft.MainAxisAlignment.START,
            spacing=TOKENS.spacing_sm + 2,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )

        self.all_entries[key] = {
            "val": val_tf,
            "unit": unit_dd,
            "ui_row": input_row,
            "prop_code": prop_code,
            "label_control": label_control,
            "unit_label_control": unit_label_control,
        }
        return self.all_entries[key] # 返回字典

    def _create_unit_sync_handler(self, prop_code, sync_group):
        """建立單位同步處理器

參數：
    prop_code (未指定型別): 函數輸入值。
    sync_group (未指定型別): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
        def on_change(e):
            if self._is_updating_units:
                return
            self._is_updating_units = True
            
            try:
                new_unit = e.control.value

                for item_key in sync_group:
                    controls = self.all_entries.get(item_key)
                    if not controls: continue
                    
                    val_tf = controls["val"]
                    unit_dd = controls["unit"]
                    
                    current_old_unit = self._last_units.get(item_key)
                    
                    if new_unit == current_old_unit or not current_old_unit:
                        self._last_units[item_key] = new_unit
                        unit_dd.value = new_unit
                        continue
                    
                    unit_dd.value = new_unit
                    
                    if val_tf.value:
                        try:
                            val = float(val_tf.value)
                            val_si = self.unit_converter.convert_to_si(prop_code, val, current_old_unit)
                            new_val = self.unit_converter.convert_from_si(prop_code, val_si, new_unit)
                            val_tf.value = f"{new_val:.7g}"
                            try:
                                attached_page = val_tf.page
                            except RuntimeError:
                                attached_page = None
                            if attached_page:
                                val_tf.update()
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    
                    self._last_units[item_key] = new_unit

            finally:
                self._is_updating_units = False
                if self.parent:
                    self.page.update()

        return on_change

    def show_error(self, message):
        """輔助方法：顯示 SnackBar

參數：
    message (未指定型別): 函數輸入值。

回傳：
    無。"""
        snack = ft.SnackBar(ft.Text(message), bgcolor=ft.Colors.ERROR)
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()