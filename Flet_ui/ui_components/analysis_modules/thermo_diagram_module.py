import flet as ft
import matplotlib.pyplot as plt
import flet_charts as fch
from .base_analysis_module import BaseAnalysisModule
from ..unit.thermo_draw.coolprop_utils import generate_thermo_diagram, safe_props, check_coolprop_fluid 
import traceback # 用於印出詳細錯誤

class ThermoDiagramModule(BaseAnalysisModule):
    """
    熱力圖繪製模組
    """

    def __init__(self, unit_converter, page, analyzer, state_calculator):
        super().__init__(unit_converter, page, analyzer=analyzer, state_calculator=state_calculator)
        self._build_thermo_diagram_ui()
        self._setup_unit_sync() # (修改) 現在會呼叫我們覆寫的 _setup_unit_sync

    # ======================================================
    # 模組登錄：讓 analysis_tab 自動載入
    # ======================================================
    def get_analysis_definitions(self):
        return {
            "熱力圖繪製": {
                "ui": self.thermo_diagram_ui_container,
                "calc_func": self.calculate_thermo_diagram
            }
        }

    # ======================================================
    # 1️⃣ UI 建構區 (與前版相同)
    # ======================================================
    def _build_thermo_diagram_ui(self):
        """建立熱力圖輸入與繪圖區"""
        #單位處理
        temp_unit = self.unit_converter.default_units["T"]
        press_unit = self.unit_converter.default_units["P"]
        enthalpy_unit = self.unit_converter.default_units["H"]
        entropy_unit = self.unit_converter.default_units["S"]
        volume_unit = self.unit_converter.default_units["V"] 


        # --- 冷媒 TextField + 驗證按鈕 ---
        self.fluid_tf = ft.TextField(
            label="冷媒 (例如 R134a, Water, Air)", 
            value="R134a", 
            width=200
        )
        self.check_fluid_btn = ft.IconButton(
            icon=ft.Icons.CHECK_CIRCLE_OUTLINE, 
            on_click=self._on_check_fluid, 
            tooltip="檢查冷媒名稱"
        )
        self.fluid_check_result = ft.Text(value="", size=11, color="grey", offset=ft.Offset(0.1, 0))


        self.diagram_dd = ft.Dropdown(
            label="圖表類型",
            options=[ft.dropdown.Option(x) for x in ["P-h", "T-s", "P-v", "T-v"]],
            value="P-h",
            width=160,
        )
        
        # --- 參考狀態選項 ---
        self.ref_state_dd = ft.Dropdown(
            label="參考狀態 (Reference State)",
            options=[
                ft.dropdown.Option("Auto", "自動 (冷媒:ASHRAE, 水:IAPWS)"),
                ft.dropdown.Option("ASHRAE", "ASHRAE (冷媒常用)"),
                ft.dropdown.Option("IAPWS", "IAPWS (水/水蒸氣標準)"),
                ft.dropdown.Option("NBP", "NBP (常壓沸點為 0)"),
                ft.dropdown.Option("IIR", "IIR (0°C 飽和液體為基準)"),
            ],
            value="Auto", 
            width=250 
        )
        
        # --- 壓力軸單位選項 ---
        self.pressure_unit_dd = ft.Dropdown(
            label="壓力軸單位 (P-h/P-v)",
            options=[
                ft.dropdown.Option("MPa"),
                ft.dropdown.Option("kPa"),
            ],
            value="MPa",
            width=190, 
        )


        # --- 輸入組合選項 ---
        self.input_pair_dd = ft.Dropdown(
            label="輸入模式",
            options=[
                ft.dropdown.Option("Compressor", "壓縮機分析 (T1,P1 ; T2,P2)"), 
                ft.dropdown.Option("T-P", "溫度 (T) - 壓力 (P)"),
                ft.dropdown.Option("P-h", "壓力 (P) - 焓 (h)"),
                ft.dropdown.Option("T-s", "溫度 (T) - 熵 (s)"),
                ft.dropdown.Option("P-s", "壓力 (P) - 熵 (s)"),
                ft.dropdown.Option("P-v", "壓力 (P) - 比容 (v)"),
            ],
            value="Compressor", 
            width=390, 
            on_select=self._on_input_mode_change
        )

        # --- 建立所有輸入欄 ---
        # (修改) 確保 label 包含單位，以便稍後解析
        self.create_input_row("td_T", f"溫度 T ({temp_unit})", "10, 50", "T", temp_unit)
        self.create_input_row("td_P", f"壓力 P ({press_unit})", "0.16, 0.7", "P", press_unit)
        self.create_input_row("td_H", f"焓 H ({enthalpy_unit})", "", "H", enthalpy_unit)
        self.create_input_row("td_S", f"熵 S ({entropy_unit})", "", "S", entropy_unit)
        self.create_input_row("td_V", f"比容 V ({volume_unit})", "", "V", volume_unit)
        
        self.all_entries["td_H"]["ui_row"].visible = False
        self.all_entries["td_S"]["ui_row"].visible = False
        self.all_entries["td_V"]["ui_row"].visible = False

        # --- 結果輸出與按鈕 ---
        self.result_text = ft.Text("請輸入參數並點擊繪圖。", selectable=True)
        self.plot_btn = ft.Button("繪圖", icon=ft.Icons.AUTO_GRAPH, on_click=self._on_plot_click)
        self.connect_points_cb = ft.Checkbox(label="連接狀態點", value=True)

        # --- 初始空圖 ---
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, "尚未繪製", ha="center", va="center", color="gray")
        self.chart = fch.MatplotlibChart(figure=fig, expand=True)
        chart_container = ft.Container(self.chart, expand=True, height=480)

        # --- 版面配置 ---
        self.info_text = ft.Text(
            "請輸入 T1, T2 (用 , 分隔) 和 P1, P2 (用 , 分隔)。將自動繪製 s1, s2s, s2 三點。", 
            size=11, color="grey")

        layout = ft.Column([
            ft.Row( 
                [self.fluid_tf, self.check_fluid_btn, self.diagram_dd], 
                spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER
            ),
            ft.Row([self.fluid_check_result]), 
            ft.Row([self.ref_state_dd, self.pressure_unit_dd], spacing=15), 
            ft.Row([self.input_pair_dd], spacing=15),
            self.info_text, 
            self.all_entries["td_T"]["ui_row"],
            self.all_entries["td_P"]["ui_row"],
            self.all_entries["td_H"]["ui_row"],
            self.all_entries["td_S"]["ui_row"],
            self.all_entries["td_V"]["ui_row"],
            ft.Row([self.plot_btn, self.connect_points_cb], spacing=15, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(self.result_text, padding=ft.Padding.only(top=5)),
            ft.Divider(),
            chart_container
        ], spacing=5) 

        self.thermo_diagram_ui_container = ft.Container(layout, expand=True)

    # ======================================================
    # 1a. 冷媒驗證事件 (無變更)
    # ======================================================
    def _on_check_fluid(self, e):
        """使用者按下 [驗證] 按鈕時"""
        fluid_name = self.fluid_tf.value.strip()
        if not fluid_name:
            self.fluid_check_result.value = "請輸入冷媒名稱"
            self.fluid_check_result.color = "red"
            if self.parent: self.page.update()
            return

        is_valid, msg = check_coolprop_fluid(fluid_name)
        
        if is_valid:
            self.fluid_check_result.value = f"'{fluid_name}' 驗證成功"
            self.fluid_check_result.color = "green"
        else:
            self.fluid_check_result.value = f"'{fluid_name}' 無效: {msg}"
            self.fluid_check_result.color = "red"
        
        if self.parent: self.page.update()

    # ======================================================
    # 1b. UI 模式切換 (無變更)
    # ======================================================
    def _on_input_mode_change(self, e):
        mode = self.input_pair_dd.value
        
        self.all_entries["td_T"]["ui_row"].visible = False
        self.all_entries["td_P"]["ui_row"].visible = False
        self.all_entries["td_H"]["ui_row"].visible = False
        self.all_entries["td_S"]["ui_row"].visible = False
        self.all_entries["td_V"]["ui_row"].visible = False 

        if mode == "Compressor":
            self.info_text.value = "請輸入 T1, T2 (用 , 分隔) 和 P1, P2 (用 , 分隔)。將自動繪製 s1, s2s, s2 三點。"
            self.all_entries["td_T"]["ui_row"].visible = True
            self.all_entries["td_P"]["ui_row"].visible = True
        elif mode == "T-P":
            self.info_text.value = "請輸入多組 T 和 P (用 , 分隔)。"
            self.all_entries["td_T"]["ui_row"].visible = True
            self.all_entries["td_P"]["ui_row"].visible = True
        elif mode == "P-h":
            self.info_text.value = "請輸入多組 P 和 H (用 , 分隔)。"
            self.all_entries["td_P"]["ui_row"].visible = True
            self.all_entries["td_H"]["ui_row"].visible = True
        elif mode == "T-s":
            self.info_text.value = "請輸入多組 T 和 S (用 , 分隔)。"
            self.all_entries["td_T"]["ui_row"].visible = True
            self.all_entries["td_S"]["ui_row"].visible = True
        elif mode == "P-s":
            self.info_text.value = "請輸入多組 P 和 S (用 , 分隔)。"
            self.all_entries["td_P"]["ui_row"].visible = True
            self.all_entries["td_S"]["ui_row"].visible = True
        elif mode == "P-v":
            self.info_text.value = "請輸入多組 P 和 V (用 , 分隔)。"
            self.all_entries["td_P"]["ui_row"].visible = True
            self.all_entries["td_V"]["ui_row"].visible = True
            
        
        if self.parent: self.page.update()

    # ======================================================
    # 2️⃣ 繪圖邏輯：事件觸發 (無變更)
    # ======================================================
    def _on_plot_click(self, e):
        """使用者按下 [繪圖] 按鈕時"""
        
        self.result_text.value = "繪製中..."
        self.result_text.color = "blue"
        self.plot_btn.disabled = True
        if self.parent: self.page.update()

        try:
            result_str = self.calculate_thermo_diagram(use_imperial=False)
            self.result_text.value = result_str
            self.result_text.color = "green" if "成功" in result_str else "red"

        except Exception as ex:
            print(f"Error in _on_plot_click: {ex}")
            traceback.print_exc()
            self.result_text.value = f"計算時發生未預期的錯誤: {ex}"
            self.result_text.color = "red"
        
        finally:
            self.plot_btn.disabled = False
            if self.parent: self.page.update()

    # ======================================================
    # 3️⃣ 核心邏輯：計算並繪製圖形 (無變更)
    # ======================================================
    def calculate_thermo_diagram(self, use_imperial: bool) -> str:
        """
        呼叫 coolprop_utils.generate_thermo_diagram() 執行繪圖
        """
        try:
            # --- 繪圖前驗證冷媒 ---
            fluid = self.fluid_tf.value.strip()
            if not fluid:
                raise ValueError("冷媒名稱不可為空")

            is_valid, msg = check_coolprop_fluid(fluid)
            if not is_valid:
                self.fluid_check_result.value = f"'{fluid}' 無效: {msg}"
                self.fluid_check_result.color = "red"
                if self.parent: self.page.update()
                raise ValueError(f"冷媒 '{fluid}' 無效: {msg}")
            else:
                self.fluid_check_result.value = f"'{fluid}' 驗證成功"
                self.fluid_check_result.color = "green"
                if self.parent: self.page.update()
            # --- 驗證結束 ---

            # 取得 UI 選項
            diagram = self.diagram_dd.value
            ref_state = self.ref_state_dd.value  
            pressure_unit_y_axis = self.pressure_unit_dd.value 
            input_mode = self.input_pair_dd.value 
            connect_points = self.connect_points_cb.value

            state_points_si = []

            # ==================================================
            # 壓縮機分析模式
            # ==================================================
            if input_mode == "Compressor":
                T_val_str = self.all_entries["td_T"]["val"].value
                P_val_str = self.all_entries["td_P"]["val"].value
                T_unit = self.all_entries["td_T"]["unit"].value
                P_unit = self.all_entries["td_P"]["unit"].value
                T_vals_str_list = [v.strip() for v in T_val_str.split(',') if v.strip()]
                P_vals_str_list = [v.strip() for v in P_val_str.split(',') if v.strip()]
                if len(T_vals_str_list) != 2 or len(P_vals_str_list) != 2:
                    raise ValueError("壓縮機分析模式需要 T1, T2 (共 2 筆溫度) 和 P1, P2 (共 2 筆壓力)。")
                T1_K = self.unit_converter.convert_to_si("T", float(T_vals_str_list[0]), T_unit)
                T2_K = self.unit_converter.convert_to_si("T", float(T_vals_str_list[1]), T_unit)
                P1_Pa = self.unit_converter.convert_to_si("P", float(P_vals_str_list[0]), P_unit)
                P2_Pa = self.unit_converter.convert_to_si("P", float(P_vals_str_list[1]), P_unit)

                s1_J_kgK = safe_props("S", "T", T1_K, "P", P1_Pa, fluid, ref_state)
                if s1_J_kgK is None or s1_J_kgK != s1_J_kgK:
                    raise ValueError(f"無法計算 s1 (T1={T_vals_str_list[0]}, P1={P_vals_str_list[0]})")
                
                state_points_si.append({
                    "input_type": "T-P", "T_K": T1_K, "P_Pa": P1_Pa,
                    "label": "點 1 (s1)", "xytext": (5, -15) 
                })
                state_points_si.append({
                    "input_type": "P-s", "P_Pa": P2_Pa, "S_J_kgK": s1_J_kgK,
                    "label": "點 2s (s=s1)", "xytext": (-70, -5)
                })
                state_points_si.append({
                    "input_type": "T-P", "T_K": T2_K, "P_Pa": P2_Pa,
                    "label": "點 2 (s2)", "xytext": (5, 5)
                })

            # ==================================================
            # 標準輸入模式
            # ==================================================
            else:
                input_map = {
                    "T-P": {"val1_key": "td_T", "val2_key": "td_P", "type1": "T", "type2": "P", "si_key1": "T_K", "si_key2": "P_Pa"},
                    "P-h": {"val1_key": "td_P", "val2_key": "td_H", "type1": "P", "type2": "H", "si_key1": "P_Pa", "si_key2": "H_J_kg"},
                    "T-s": {"val1_key": "td_T", "val2_key": "td_S", "type1": "T", "type2": "S", "si_key1": "T_K", "si_key2": "S_J_kgK"},
                    "P-s": {"val1_key": "td_P", "val2_key": "td_S", "type1": "P", "type2": "S", "si_key1": "P_Pa", "si_key2": "S_J_kgK"},
                    "P-v": {"val1_key": "td_P", "val2_key": "td_V", "type1": "P", "type2": "V", "si_key1": "P_Pa", "si_key2": "V_m3_kg"}, 
                }
                if input_mode not in input_map:
                    raise ValueError(f"不支援的輸入組合: {input_mode}")

                config = input_map[input_mode]
                entry1 = self.all_entries[config["val1_key"]]
                entry2 = self.all_entries[config["val2_key"]]
                val1_str = entry1["val"].value
                val2_str = entry2["val"].value
                unit1 = entry1["unit"].value
                unit2 = entry2["unit"].value
                vals1_str_list = [v.strip() for v in val1_str.split(',') if v.strip()]
                vals2_str_list = [v.strip() for v in val2_str.split(',') if v.strip()]
                if len(vals1_str_list) != len(vals2_str_list):
                    raise ValueError(f"輸入 {config['type1']} ({len(vals1_str_list)} 筆) 和 {config['type2']} ({len(vals2_str_list)} 筆) 的數量必須相同。")

                for v1_str, v2_str in zip(vals1_str_list, vals2_str_list):
                    v1_val_si = self.unit_converter.convert_to_si(config["type1"], float(v1_str), unit1)
                    v2_val_si = self.unit_converter.convert_to_si(config["type2"], float(v2_str), unit2)
                    state_points_si.append({
                        "input_type": input_mode,
                        config["si_key1"]: v1_val_si,
                        config["si_key2"]: v2_val_si
                    })
            
            # ==================================================
            # 呼叫繪圖
            # ==================================================
            fig = generate_thermo_diagram(
                fluid=fluid,
                diagram=diagram,
                state_points_si=state_points_si, 
                connect_points=connect_points,   
                input_mode=input_mode,           
                ref_state=ref_state,             
                target_P_unit=pressure_unit_y_axis, 
                unit_converter=self.unit_converter
            )

            self.chart.figure = fig
            # A headless calculation can produce a figure before the chart is
            # attached to a page; only push a UI update when attachment exists.
            try:
                chart_page = self.chart.page
            except RuntimeError:
                chart_page = None
            if chart_page:
                self.chart.update()

            point_count = len(state_points_si)
            if point_count == 0:
                 return f"成功繪製 {fluid} 的 {diagram} 圖 (無狀態點)。"
            if input_mode == "Compressor":
                return f"成功繪製壓縮機分析 (3 個點)。"
            else:
                return f"成功繪製 {fluid} 的 {diagram} 圖 ({point_count} 個點)。"

        except Exception as ex:
            print(f"Error in calculate_thermo_diagram: {ex}")
            traceback.print_exc() 
            return f"熱力圖繪製失敗: {ex}"
        

    # ======================================================
    # (修正) 12a. 多數值單位同步處理器
    # ======================================================
    def _create_multi_value_unit_sync_handler(self, unit_type, sync_group):
        """
        (覆寫)
        Factory function to create an on_change handler that supports
        comma-separated values (例如 "-10, 50") for unit conversion.
        """
        def on_change_handler(e):
            # 1. 找到是哪個輸入框觸發了事件
            trigger_key = None
            for key, entry in self.all_entries.items():
                if entry.get("unit") == e.control:
                    trigger_key = key
                    break
            
            if not trigger_key:
                print(f"Could not find entry for control {e.control}")
                return

            new_unit = e.control.value
            # 獲取變更前的單位 (儲存在 control 物件上)
            old_unit = getattr(e.control, "previous_unit", new_unit) 
            
            # --- 2. 更新同步群組中所有其他的「單位下拉選單」 ---
            for key in sync_group:
                if key != trigger_key and key in self.all_entries:
                    if self.all_entries[key].get("unit"):
                        self.all_entries[key]["unit"].value = new_unit

            # --- 3. (核心修改) 轉換觸發事件的「輸入框」中的值 ---
            try:
                val_str = self.all_entries[trigger_key]["val"].value
                if val_str:
                    # 將 "-10, 50" 分割為 ["-10", " 50"]
                    values_in = val_str.split(',')
                    values_out = []
                    
                    for v_in_str in values_in:
                        v_in_str_stripped = v_in_str.strip()
                        if not v_in_str_stripped:
                            values_out.append("")
                            continue
                        
                        try:
                            v_in_float = float(v_in_str_stripped)
                            
                            # (修正 Error 1: 使用 2-step 轉換)
                            si_value = self.unit_converter.convert_to_si(unit_type, v_in_float, old_unit)
                            v_out_float = self.unit_converter.convert_from_si(unit_type, si_value, new_unit)
                            
                            values_out.append(f"{v_out_float:g}") # 使用通用格式
                        except ValueError:
                            # 如果不是數字 (例如空字串或錯誤輸入)，保持原樣
                            values_out.append(v_in_str_stripped)
                            
                    # 將 ["-14.8", "122"] 組合回 "-14.8, 122"
                    self.all_entries[trigger_key]["val"].value = ", ".join(values_out)

            except Exception as ex:
                print(f"Failed to convert multi-value {trigger_key} value: {ex}")
                # 即使轉換失敗，也要繼續更新標籤

            # --- 4. (修正 Error 2: 解析 current_label) ---
            for key in sync_group:
                if key in self.all_entries:
                    # 更新標籤 (例如 "壓力 P (MPa)" -> "壓力 P (kPa)")
                    try:
                        current_label = self.all_entries[key]["val"].label
                        
                        # 找到最後一個 '(', (例如 "壓力 P (MPa)")
                        base_label = current_label
                        paren_index = current_label.rfind("(")
                        if paren_index != -1:
                            base_label = current_label[:paren_index].strip() # 得到 "壓力 P"
                            
                        # 重組標籤
                        self.all_entries[key]["val"].label = f"{base_label} ({new_unit})"
                    except Exception as ex:
                        print(f"Failed to update label for {key}: {ex}")
                    
                    # 在 control 物件上儲存新單位，供下次變更時使用
                    if self.all_entries[key].get("unit"):
                        setattr(self.all_entries[key]["unit"], "previous_unit", new_unit)

            if self.parent:
                self.page.update()
        
        # --- End of on_change_handler ---
        return on_change_handler

    # ======================================================
    # (修改) 12b. 單位同步設定
    # ======================================================
    def _setup_unit_sync(self):
        """
        (覆寫)
        使用新的 _create_multi_value_unit_sync_handler 
        來處理帶有逗號 (,) 的多筆輸入。
        """
        # 壓力 (P)
        p_sync_group = ["td_P"]
        self.all_entries["td_P"]["unit"].on_change = self._create_unit_sync_handler("P", p_sync_group)
        
        # 焓 (H)
        h_sync_group = ["td_H"] 
        self.all_entries["td_H"]["unit"].on_change = self._create_unit_sync_handler("H", h_sync_group)

        # 熵 (S)
        s_sync_group = ["td_S"]
        self.all_entries["td_S"]["unit"].on_change = self._create_unit_sync_handler("S", s_sync_group)

        # 溫度 (T)
        t_sync_group = ["td_T"]
        self.all_entries["td_T"]["unit"].on_change = self._create_unit_sync_handler("T", t_sync_group)

        # 比容 (V)
        v_sync_group = ["td_V"]
        self.all_entries["td_V"]["unit"].on_change = self._create_unit_sync_handler("V", v_sync_group)
        
        def setup_sync_for_group(unit_type, sync_group):
            """輔助函式：綁定 handler 並設定初始單位"""
            
            # 1. 建立客製化的 handler
            handler = self._create_multi_value_unit_sync_handler(unit_type, sync_group)
            
            initial_unit = None
            for key in sync_group:
                if key in self.all_entries and self.all_entries[key].get("unit"):
                    # 2. 綁定 on_change 事件
                    self.all_entries[key]["unit"].on_change = handler
                    
                    # 3. 獲取初始單位
                    if initial_unit is None:
                         initial_unit = self.all_entries[key]["unit"].value
            
            # 4. 將初始單位儲存為 "previous_unit" 供第一次轉換使用
            if initial_unit is not None:
                for key in sync_group:
                     if key in self.all_entries and self.all_entries[key].get("unit"):
                        setattr(self.all_entries[key]["unit"], "previous_unit", initial_unit)

        # --- 為所有熱力圖輸入框設定同步 ---
        setup_sync_for_group("P", ["td_P"])
        setup_sync_for_group("H", ["td_H"])
        setup_sync_for_group("S", ["td_S"])
        setup_sync_for_group("T", ["td_T"])
        setup_sync_for_group("V", ["td_V"])