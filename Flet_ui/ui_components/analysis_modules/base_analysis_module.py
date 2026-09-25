# ui_components/analysis_modules/base_analysis_module.py
# (新介面 - 支援功能群組)

from math import isfinite

import flet as ft
from ..unit.UnitConverter import UnitConverter
from ...ui.theme import TOKENS, mono_style, style_text_field

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
            label, size=TOKENS.body, weight=ft.FontWeight.W_500, color=TOKENS.text_secondary
        )
        # 數值與單位合成同一個外框：單位選單放在欄位尾端，仍可逐欄切換。
        val_tf = ft.TextField(
            value=str(default_val),
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
            hint_text="輸入數值",
            border=ft.InputBorder.NONE,
            text_size=TOKENS.body + 1,
            text_style=mono_style(),
            cursor_color=TOKENS.primary,
            content_padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        )
        unit_dd = ft.Dropdown(
            value=final_default_unit,
            options=[ft.dropdown.Option(u) for u in units],
            width=96,
            border=ft.InputBorder.NONE,
            text_size=TOKENS.body - 1,
            text_align=ft.TextAlign.RIGHT,
            color=TOKENS.text_muted,
            trailing_icon=ft.Icon(ft.Icons.EXPAND_MORE, size=16, color=TOKENS.text_muted),
            selected_trailing_icon=ft.Icon(ft.Icons.EXPAND_LESS, size=16, color=TOKENS.text_muted),
            content_padding=ft.Padding.only(left=4, right=0),
            disabled=(prop_code == "RH" or prop_code == "Q"),
        )
        field_box = ft.Container(
            content=ft.Row(
                controls=[val_tf, unit_dd],
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            height=TOKENS.input_height,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border_strong),
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
        )

        def set_focused(focused: bool) -> None:
            """以外框顏色與粗細標示目前聚焦的欄位。

            參數：
                focused: 欄位是否取得焦點。

            回傳：
                無。
            """
            field_box.border = ft.Border.all(
                2 if focused else 1, TOKENS.primary if focused else TOKENS.border_strong
            )
            try:
                field_box.update()
            except RuntimeError:
                pass

        val_tf.on_focus = lambda _event: set_focused(True)
        val_tf.on_blur = lambda _event: set_focused(False)
        input_row = ft.Column(controls=[label_control, field_box], spacing=6)

        self.all_entries[key] = {
            "val": val_tf,
            "unit": unit_dd,
            "ui_row": input_row,
            "prop_code": prop_code,
            "label_control": label_control,
            "field_box": field_box,
        }
        return self.all_entries[key] # 返回字典

    def create_text_row(self, key: str, label: str, default_val: str, hint: str = "") -> ft.TextField:
        """建立框外欄名的文字輸入列（例如流體名稱），儲存在 ``self.text_entries``。

參數：
    key: 此輸入在模組中的識別鍵。
    label: 欄位名稱。
    default_val: 預設文字。
    hint: 選用的提示文字。

回傳：
    建立的 TextField；外層列控制項可由 ``self.text_entries[key]["ui_row"]`` 取得。"""
        field = style_text_field(ft.TextField(
            value=default_val,
            hint_text=hint or None,
            expand=True,
            height=TOKENS.input_height,
        ))
        label_control = ft.Text(label, size=TOKENS.body, weight=ft.FontWeight.W_500,
                                color=TOKENS.text_primary)
        if not hasattr(self, "text_entries"):
            self.text_entries = {}
        self.text_entries[key] = {
            "val": field,
            "label_control": label_control,
            "ui_row": ft.Column([label_control, field], spacing=6),
        }
        return field

    def read_text(self, key: str) -> str:
        """讀取文字輸入列，空白時以欄名提示錯誤。

參數：
    key: create_text_row 使用的識別鍵。

回傳：
    去除前後空白的文字。

引發：
    ValueError：欄位空白時。"""
        entry = self.text_entries[key]
        text = (entry["val"].value or "").strip()
        if not text:
            raise ValueError(f"請輸入「{entry['label_control'].value}」。")
        return text

    def read_si(self, key: str) -> float:
        """讀取一個輸入列並換算為 canonical SI；無效數值以欄名提示錯誤。

參數：
    key: create_input_row 使用的識別鍵。

回傳：
    SI 數值。

引發：
    ValueError：欄位空白或不是有限數字時。"""
        entry = self.all_entries[key]
        label = entry["label_control"].value
        raw_value = (entry["val"].value or "").strip()
        try:
            value = float(raw_value)
        except ValueError:
            raise ValueError(f"「{label}」請輸入有效數值。") from None
        if not isfinite(value):
            raise ValueError(f"「{label}」必須是有限數字。")
        return self.unit_converter.convert_to_si(entry["prop_code"], value, entry["unit"].value)

    def read_si_list(self, key: str) -> list[float]:
        """讀取以逗號分隔的多筆數值並換算為 SI。

參數：
    key: create_input_row 使用的識別鍵。

回傳：
    SI 數值清單（至少一筆）。

引發：
    ValueError：沒有數值或任一筆不是有限數字時。"""
        entry = self.all_entries[key]
        label = entry["label_control"].value
        values = []
        for raw_value in (entry["val"].value or "").split(","):
            raw_value = raw_value.strip()
            if not raw_value:
                continue
            try:
                value = float(raw_value)
            except ValueError:
                raise ValueError(f"「{label}」包含無效數值：{raw_value}") from None
            if not isfinite(value):
                raise ValueError(f"「{label}」必須是有限數字。")
            values.append(self.unit_converter.convert_to_si(entry["prop_code"], value, entry["unit"].value))
        if not values:
            raise ValueError(f"「{label}」請至少輸入一筆數值。")
        return values

    def bind_independent_unit_sync(self, keys: list[str]) -> None:
        """讓每個輸入列的單位選單獨立換算自己的數值。

參數：
    keys: 要綁定的輸入列識別鍵。

回傳：
    無。"""
        for key in keys:
            entry = self.all_entries[key]
            entry["unit"].on_select = self._create_unit_sync_handler(entry["prop_code"], [key])

    def retarget_input_row(self, key: str, prop_code: str, unit_code: str) -> None:
        """把一個獨立換算的輸入列改為另一個物理量（例如錶壓力 ↔ 絕對壓力）。

只更新性質代碼、單位選項、目前單位與單位換算處理器；數值由呼叫端決定如何
換算，本方法不改動欄位數值。

參數：
    key: create_input_row 使用的識別鍵。
    prop_code: 新的 UnitConverter 性質代碼。
    unit_code: 新的目前單位，必須是該性質已註冊的單位。

回傳：
    無。

引發：
    ValueError：單位不屬於該性質時。"""
        units = self.unit_converter.get_available_units(prop_code)
        if unit_code not in units:
            raise ValueError(f"Unknown unit '{unit_code}' for property '{prop_code}'")
        entry = self.all_entries[key]
        entry["prop_code"] = prop_code
        entry["unit"].options = [ft.dropdown.Option(unit) for unit in units]
        entry["unit"].value = unit_code
        self._last_units[key] = unit_code
        entry["unit"].on_select = self._create_unit_sync_handler(prop_code, [key])

    def bind_multi_value_unit_sync(self, keys: list[str]) -> None:
        """讓逗號分隔多筆數值的輸入列在切換單位時逐筆換算。

無法解析的片段保持原樣，由計算時的驗證提示使用者。

參數：
    keys: 要綁定的輸入列識別鍵。

回傳：
    無。"""
        for key in keys:
            entry = self.all_entries[key]

            def on_select(event, key=key, entry=entry) -> None:
                """逐筆換算數值並記錄新單位。

參數：
    event: 單位選單的 Flet 事件。
    key: 輸入列識別鍵。
    entry: 輸入列控制項。

回傳：
    無。"""
                old_unit = self._last_units.get(key)
                new_unit = entry["unit"].value
                if old_unit and new_unit and old_unit != new_unit:
                    converted = []
                    for part in (entry["val"].value or "").split(","):
                        text = part.strip()
                        try:
                            value_si = self.unit_converter.convert_to_si(entry["prop_code"], float(text), old_unit)
                            converted.append(f"{self.unit_converter.convert_from_si(entry['prop_code'], value_si, new_unit):.6g}")
                        except ValueError:
                            converted.append(text)
                    entry["val"].value = ", ".join(item for item in converted if item)
                self._last_units[key] = new_unit
                try:
                    entry["val"].update()
                except RuntimeError:
                    pass

            entry["unit"].on_select = on_select

    @staticmethod
    def section_label(text: str) -> ft.Control:
        """建立表單中的小節標題。

參數：
    text: 小節名稱。

回傳：
    小節標題控制項。"""
        return ft.Container(
            content=ft.Text(text, size=TOKENS.caption, weight=ft.FontWeight.W_600,
                            color=TOKENS.text_muted),
            padding=ft.Padding.only(top=TOKENS.spacing_xs),
        )

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
                    if not controls:
                        continue
                    
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