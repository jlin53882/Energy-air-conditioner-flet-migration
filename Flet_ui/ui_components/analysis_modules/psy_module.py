# ui_components/analysis_modules/psy_module.py

import flet as ft
from .base_analysis_module import BaseAnalysisModule
from ..unit.PsychrometricCalculator import PsychrometricCalculator
from ..unit.UnitConverter import UnitConverter
from ...ui.theme import TOKENS
from .psy_result_view import (
    KNOWN_RELATIVE_HUMIDITY,
    KNOWN_WET_BULB,
    PsychrometricResultBuilder,
)

class PsyModule(BaseAnalysisModule):
    # 穩定的分析模式 key，routing / dispatch 一律使用這兩個常數；
    # 顯示文字（見 get_analysis_definitions 的 dict key）只用於 UI 呈現，
    # 可自由改文案或翻譯而不影響下面的計算/UI 切換邏輯。
    MODE_TDB_TWB = "psychrometrics.tdb_twb"
    MODE_TDB_RH = "psychrometrics.tdb_rh"

    # Legacy AnalysisTab（以及既有直接呼叫 configure_ui_for_mode /
    # calculate_psy 的測試）仍可能傳入顯示 label 而非穩定 key；
    # _resolve_mode_key() 用這張表把 label 正規化為 key，dispatch 本身
    # 只比對正規化後的 key。
    _LEGACY_LABEL_TO_KEY = {
        "濕空氣性質 (已知乾濕球)": MODE_TDB_TWB,
        "濕空氣性質 (已知乾球與相對濕度)": MODE_TDB_RH,
    }

    def __init__(self, unit_converter: UnitConverter, page: ft.Page, psy_calculator: PsychrometricCalculator):
        super().__init__(unit_converter, page, psy_calculator=psy_calculator)
        
        self.psy_calculator: PsychrometricCalculator = self.services.get("psy_calculator")
        
        # --- 建立 UI ---
        self._build_ui_components()
        self._setup_unit_sync()
        self.result_builder = PsychrometricResultBuilder(unit_converter, self.psy_calculator.service)
        self.last_structured_result = None
        # 海拔輸入即時換算大氣壓力，讓使用者在計算前就看到推導值。
        self.pressure_hint = ft.Text("", size=TOKENS.caption, color=TOKENS.text_muted,
                                     font_family=TOKENS.mono_font)
        self.all_entries["psy_alt"]["val"].on_change = self.update_pressure_hint
        convert_altitude_unit = self.all_entries["psy_alt"]["unit"].on_select

        def on_altitude_unit_change(event) -> None:
            """換算海拔數值後同步更新大氣壓力提示。

參數：
    event: 單位選單的 Flet 事件。

回傳：
    無。"""
            convert_altitude_unit(event)
            self.update_pressure_hint(None)

        self.all_entries["psy_alt"]["unit"].on_select = on_altitude_unit_change
        self.update_pressure_hint(None)
        
        # --- 建立 UI 容器 ---
        # 兩種模式共用 *同一個* UI 容器實例
        self.ui_container = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Column([self.all_entries["psy_alt"]["ui_row"], self.pressure_hint], spacing=4),
                    self.all_entries["psy_tdb"]["ui_row"],
                    self.all_entries["psy_twb"]["ui_row"],
                    self.all_entries["psy_rh"]["ui_row"],
                ],
                spacing=15,
            ),
            visible=False
        )

    def get_analysis_definitions(self) -> dict:
        """回報此模組提供的 *兩種* 濕空氣計算模式。

        ``calc_func`` 一律指向本模組已綁定對應 mode 的統一簽章方法
        （``Callable[[bool], str]``），呼叫端（新架構的
        :func:`~Flet_ui.ui.analysis_definition.definitions_from_module`
        與 legacy ``AnalysisTab``）都不需要知道 ``mode_key`` 這個參數的
        存在——module-specific 的呼叫慣例完全由 ``PsyModule`` 自己吸收。

        ``calculation_mode`` 這個 key 只保留給 legacy ``AnalysisTab``
        （狀態文字顯示 / 既有 characterization test）使用；新架構的
        generic factory 不讀取也不依賴這個欄位。

回傳：
    dict：函數計算或處理後的結果。"""
        return {
            "濕空氣性質 (已知乾濕球)": {
                "analysis_id": self.MODE_TDB_TWB,
                "result_chart": self.result_builder.chart_panel,
                "structured_result": lambda: self.last_structured_result,
                "ui": self.ui_container,
                "calc_func": self._calculate_tdb_twb,
                "calculation_mode": "psychrometric"
            },
            "濕空氣性質 (已知乾球與相對濕度)": {
                "analysis_id": self.MODE_TDB_RH,
                "result_chart": self.result_builder.chart_panel,
                "structured_result": lambda: self.last_structured_result,
                "ui": self.ui_container,
                "calc_func": self._calculate_tdb_rh,
                "calculation_mode": "psychrometric"
            }
        }

    def _calculate_tdb_twb(self, use_imperial: bool) -> str:
        """已綁定「已知乾濕球」模式的統一簽章計算入口。

        參數：
            use_imperial: 是否以 Imperial 單位呈現結果。

        回傳：
            str：格式化後的計算結果文字。
        """
        return self.calculate_psy(use_imperial, mode_key=self.MODE_TDB_TWB)

    def _calculate_tdb_rh(self, use_imperial: bool) -> str:
        """已綁定「已知乾球與相對濕度」模式的統一簽章計算入口。

        參數：
            use_imperial: 是否以 Imperial 單位呈現結果。

        回傳：
            str：格式化後的計算結果文字。
        """
        return self.calculate_psy(use_imperial, mode_key=self.MODE_TDB_RH)
        
    def _build_ui_components(self):
        """僅建立元件

回傳：
    無。"""
        self.create_input_row("psy_alt", "高度 (Altitude)", "0", "L", "m")
        self.create_input_row("psy_tdb", "乾球溫度 (Dry-Bulb)", "25", "T", "°C")
        self.create_input_row("psy_twb", "濕球溫度 (Wet-Bulb)", "20", "T", "°C")
        self.create_input_row("psy_rh", "相對濕度 (Rel. Humidity)", "50", "RH", "%")

    def _setup_unit_sync(self):
        """設定單位同步

回傳：
    無。"""
        psy_t_sync_group = ["psy_tdb", "psy_twb"]
        self.all_entries["psy_tdb"]["unit"].on_select = self._create_unit_sync_handler("T", psy_t_sync_group)
        self.all_entries["psy_twb"]["unit"].on_select = self._create_unit_sync_handler("T", psy_t_sync_group)
        self.all_entries["psy_alt"]["unit"].on_select = self._create_unit_sync_handler("L", ["psy_alt"])

    def update_pressure_hint(self, _event: ft.ControlEvent | None) -> None:
        """依目前海拔輸入顯示推算的大氣壓力；輸入無效時提示而不拋錯。

參數：
    _event: 海拔欄位的 Flet 變更事件；初始化時為 None。

回傳：
    無。"""
        entry = self.all_entries["psy_alt"]
        try:
            altitude_m = self.unit_converter.convert_to_si("L", float(entry["val"].value), entry["unit"].value)
            pressure_kpa = self.psy_calculator.calculate_pressure_from_altitude(altitude_m) / 1000.0
            self.pressure_hint.value = f"→ 大氣壓力 {pressure_kpa:.3f} kPa"
        except (TypeError, ValueError):
            self.pressure_hint.value = "→ 輸入有效海拔後顯示大氣壓力"
        try:
            self.pressure_hint.update()
        except RuntimeError:
            pass

    def _resolve_mode_key(self, mode: str) -> str:
        """將呼叫端傳入值正規化為穩定的 mode key。

        新的 dedicated view / adapter（見 ``PsychrometricsView`` /
        ``AnalysisModuleAdapter``）一律傳入穩定 key（``self.MODE_TDB_TWB`` /
        ``self.MODE_TDB_RH``）；為了不破壞仍直接傳入舊版顯示文字的呼叫端
        （legacy ``AnalysisTab`` 與既有直接呼叫此方法的測試），保留 label
        → key 的相容對照表。實際的模式判斷（見下方 if/elif）只比對正規化
        後的 key，不比對 label 字串本身。

        參數：
            mode: 穩定 key 或舊版顯示 label。

        回傳：
            str：正規化後的穩定 mode key；無法辨識時原樣傳回，交由呼叫端
            的既有錯誤處理路徑判斷。
        """
        if mode in (self.MODE_TDB_TWB, self.MODE_TDB_RH):
            return mode
        return self._LEGACY_LABEL_TO_KEY.get(mode, mode)

    def configure_ui_for_mode(self, mode: str):
        """
        由 PsychrometricsView（傳入穩定 key）或 legacy AnalysisTab（傳入
        label，經 ``_resolve_mode_key`` 正規化）呼叫，配置 UI 顯示模式。
        這是一個 *特定* 方法，僅供 PsyModule 使用。
        """
        mode_key = self._resolve_mode_key(mode)
        if mode_key == self.MODE_TDB_TWB:
            self.all_entries["psy_twb"]["ui_row"].visible = True
            self.all_entries["psy_rh"]["ui_row"].visible = False
        elif mode_key == self.MODE_TDB_RH:
            self.all_entries["psy_twb"]["ui_row"].visible = False
            self.all_entries["psy_rh"]["ui_row"].visible = True
        
        # Flet 在 ``page`` 尚未附加時讀取它會引發 RuntimeError；
        # 建構期間的測試與 headless 呼叫端確實可能走到這條路徑。
        try:
            attached_page = self.ui_container.page
        except RuntimeError:
            attached_page = None
        if attached_page:
            self.ui_container.update()

    def calculate_psy(self, use_imperial: bool, mode_key: str) -> str:
        """
        實作濕空氣計算。

        參數：
            use_imperial: 是否以 Imperial 單位呈現結果。
            mode_key: 穩定的計算模式 key（``self.MODE_TDB_TWB`` /
                ``self.MODE_TDB_RH``）；為相容仍可傳入舊版顯示 label，
                會經 :meth:`_resolve_mode_key` 正規化為 key 後才用於
                dispatch，label 本身永遠不直接參與判斷。

        回傳：
            str：格式化後的計算結果文字。
        """
        mode_key = self._resolve_mode_key(mode_key)
        # 1. 讀取通用值和單位
        alt_val = float(self.all_entries["psy_alt"]["val"].value)
        alt_unit = self.all_entries["psy_alt"]["unit"].value
        tdb_val = float(self.all_entries["psy_tdb"]["val"].value)
        tdb_unit = self.all_entries["psy_tdb"]["unit"].value

        # 2. 轉換為 SI (m 和 K)
        alt_m = self.unit_converter.convert_to_si("L", alt_val, alt_unit)
        tdb_k = self.unit_converter.convert_to_si("T", tdb_val, tdb_unit)

        psy_results = {}
        
        # 3. 根據正規化後的 mode_key 決定計算路徑；label 不參與判斷。
        if mode_key == self.MODE_TDB_TWB:
            twb_val = float(self.all_entries["psy_twb"]["val"].value)
            twb_unit = self.all_entries["psy_twb"]["unit"].value
            twb_k = self.unit_converter.convert_to_si("T", twb_val, twb_unit)
            psy_results = self.psy_calculator.calculate_from_tdb_twb(tdb_k, twb_k, alt_m)

        elif mode_key == self.MODE_TDB_RH:
            rh_val = float(self.all_entries["psy_rh"]["val"].value)
            rh_si = self.unit_converter.convert_to_si("RH", rh_val, "%") 
            psy_results = self.psy_calculator.calculate_from_tdb_rh(tdb_k, rh_si, alt_m)

        # 4. 格式化輸出；結構化畫面與文字結果來自同一份狀態
        if psy_results:
            known_input = KNOWN_WET_BULB if mode_key == self.MODE_TDB_TWB else KNOWN_RELATIVE_HUMIDITY
            self.last_structured_result = self.result_builder.build(
                psy_results, known_input=known_input, use_imperial=use_imperial
            )
            result_lines = self._format_psy_results(psy_results, use_imperial)
            return "\n".join(result_lines)
        else:
            return "計算失敗。"

    def _format_psy_results(self, si_results, use_imperial):
        """
        輔助方法：將濕空氣的 *大型* SI 結果字典
        格式化為您指定的詳細字串列表，並支援 SI/Imperial 轉換。
        (此函式從舊的 analysis_tab.py 完整搬移過來)
        """
        lines = []
        
        # 1. 決定目標單位
        if use_imperial:
            l_unit = self.unit_converter.imperial_units["L"]
            p_unit = self.unit_converter.imperial_units["P"]
            t_unit = self.unit_converter.imperial_units["T"]
            w_unit = self.unit_converter.imperial_units["W"]
            h_unit = self.unit_converter.imperial_units["H"]
            v_unit = self.unit_converter.imperial_units["V"]
        else:
            l_unit = self.unit_converter.default_units["L"]
            p_unit = "Pa"     
            t_unit = self.unit_converter.default_units["T"]
            w_unit = "kg/kg"  
            h_unit = self.unit_converter.default_units["H"]
            v_unit = self.unit_converter.default_units["V"]

        # 2. 獲取所有 SI 基礎單位數值 (省略... 如同您原始碼)
        alt_si = si_results['Altitude']
        p_si = si_results['P']
        tdb_si = si_results['Tdb']
        twb_si = si_results['Twb']
        tdp_si = si_results['Tdp']
        rh_si = si_results['RH']
        w_si = si_results['W']
        h_si = si_results['H']
        v_si = si_results['V']
        pw_si = si_results['Pw']
        pws_db_si = si_results['Pws_db']
        pws_wd_si = si_results['Pws_wd']
        ws_si = si_results['Ws']
        wss_si = si_results['Wss']
        rh_val = self.unit_converter.convert_from_si("RH", rh_si, "%")

        # 3. 將所有數值轉換為目標顯示單位 (省略... 如同您原始碼)
        alt_val = self.unit_converter.convert_from_si("L", alt_si, l_unit)
        p_val = self.unit_converter.convert_from_si("P", p_si, p_unit)
        tdb_val = self.unit_converter.convert_from_si("T", tdb_si, t_unit)
        twb_val = self.unit_converter.convert_from_si("T", twb_si, t_unit)
        tdp_val = self.unit_converter.convert_from_si("T", tdp_si, t_unit)
        w_val = self.unit_converter.convert_from_si("W", w_si, w_unit)
        h_val = self.unit_converter.convert_from_si("H", h_si, h_unit)
        v_val = self.unit_converter.convert_from_si("V", v_si, v_unit)
        pw_val = self.unit_converter.convert_from_si("P", pw_si, p_unit)
        pws_db_val = self.unit_converter.convert_from_si("P", pws_db_si, p_unit)
        pws_wd_val = self.unit_converter.convert_from_si("P", pws_wd_si, p_unit)
        ws_val = self.unit_converter.convert_from_si("W", ws_si, w_unit)
        wss_val = self.unit_converter.convert_from_si("W", wss_si, w_unit)
        
        # 4. 依照您要求的格式，建立字串列表 (省略... 如同您原始碼)
        title_width = 48
        lines.append("--- 主要性質 ---")
        lines.append(f"{'海拔高度 (Altitude)':<{title_width}}: {alt_val:.2f} {l_unit}")
        lines.append(f"{'大氣壓力 (Atmospheric Pressure)':<{title_width}}: {p_val:.4f} {p_unit}")
        lines.append(f"{'乾球溫度 (Dry-Bulb Temperature)':<{title_width}}: {tdb_val:.2f} {t_unit}")
        lines.append(f"{'計算濕球溫度 (Calculated Wet-Bulb Temp)':<{title_width}}: {twb_val:.2f} {t_unit}")
        lines.append(f"{'露點溫度 (Dew Point Temperature)':<{title_width}}: {tdp_val:.2f} {t_unit}")
        lines.append(f"{'相對濕度 (Relative Humidity)':<{title_width}}: {rh_val:.2f} %")
        lines.append(f"{'濕度比 (Humidity Ratio)':<{title_width}}: {w_val:.6f} {w_unit}")
        lines.append(f"{'濕空氣之焓值 (Enthalpy)':<{title_width}}: {h_val:.4f} {h_unit}")
        lines.append(f"{'濕空氣之比容 (Specific Volume)':<{title_width}}: {v_val:.4f} {v_unit}")
        lines.append("\n--- 中間過程壓力值 ---")
        lines.append(f"{'水蒸氣分壓 (Vapor Pressure)':<{title_width}}: {pw_val:.4f} {p_unit}")
        lines.append(f"{'飽和狀態之水蒸氣分壓 (Saturation Pressure at Tdb)':<{title_width}}: {pws_db_val:.4f} {p_unit}")
        lines.append(f"{'濕球溫度下，飽和狀態之水蒸氣分壓 (Saturation Pressure at Twb)':<{title_width}}: {pws_wd_val:.4f} {p_unit}")
        lines.append("\n--- 中間過程濕度比 ---")
        lines.append(f"{'飽和濕空氣之濕度比 (Saturation Humidity Ratio at Tdb)':<{title_width}}: {ws_val:.6f} {w_unit}")
        lines.append(f"{'濕球溫度下，飽和狀態之濕度比 (Saturation Humidity Ratio at Twb)':<{title_width}}: {wss_val:.6f} {w_unit}")
        
        return lines