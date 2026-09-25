from collections.abc import Callable
import flet as ft
import flet_charts as fch
import matplotlib.pyplot as plt
from .base_analysis_module import BaseAnalysisModule
from ...ui.theme import (
    TOKENS,
    card_shadow,
    primary_button_style,
    style_dropdown,
    style_text_field,
)
from ..unit.thermo_draw.coolprop_utils import generate_thermo_diagram, safe_props, check_coolprop_fluid 
from chart.state_point_parser import StatePointParser
import traceback # 用於印出詳細錯誤

class ThermoDiagramModule(BaseAnalysisModule):
    """
    熱力圖繪製模組
    """

    def __init__(self, unit_converter, page, analyzer, state_calculator):
        super().__init__(unit_converter, page, analyzer=analyzer, state_calculator=state_calculator)
        self.state_point_parser = StatePointParser()
        self._build_thermo_diagram_ui()
        self._setup_unit_sync() # (修改) 現在會呼叫我們覆寫的 _setup_unit_sync

    # ======================================================
    # 模組登錄：讓 analysis_tab 自動載入
    # ======================================================
    def get_analysis_definitions(self):
        """提供熱力圖分析的註冊資料與專屬結果呈現設定。

回傳：
    以分析名稱為鍵的模組註冊定義。
    """
        return {
            "熱力圖繪製": {
                "analysis_id": "thermodynamics.diagram",
                "show_execute_button": False,
                "show_result_panel": False,
                "ui": self.thermo_diagram_ui_container,
                "calc_func": self.calculate_thermo_diagram
            }
        }

    # ======================================================
    # 1️⃣ UI 建構區 (與前版相同)
    # ======================================================
    def set_diagram_type(self, diagram: str) -> None:
        """切換圖表種類並清除舊圖，避免顯示與目前路由不符的內容。

參數：
    diagram: 要顯示的圖表種類，限 P-h、T-s、P-v 或 T-v。

回傳：
    無。

引發：
    ValueError: 指定的圖表種類不在目前支援選項中。
        """
        supported_diagrams = {"P-h", "T-s", "P-v", "T-v"}
        if diagram not in supported_diagrams:
            raise ValueError(f"不支援的圖表種類：{diagram}")

        self.diagram_dd.value = diagram
        figure = self.chart.figure
        figure.clear()
        axes = figure.add_subplot(111)
        axes.text(0.5, 0.5, "尚未繪製", ha="center", va="center", color="gray")
        self.chart.figure = figure
        self.result_text.value = "請輸入參數並點擊繪圖。"
        self.result_text.color = ft.Colors.GREY_600
        self.fluid_check_result.value = ""
        self.plot_btn.disabled = False

        try:
            chart_page = self.chart.page
        except RuntimeError:
            chart_page = None
        if chart_page:
            self.chart.send_message({"type": "refresh"})
        if self.parent:
            self.page.update()

    def _build_thermo_diagram_ui(self):
        """建立熱力圖輸入與繪圖區

回傳：
    無。"""
        #單位處理
        temp_unit = self.unit_converter.default_units["T"]
        # Heatmap defaults use MPa because the example values are 0.16 and 0.70 MPa.
        press_unit = "MPa"
        enthalpy_unit = self.unit_converter.default_units["H"]
        entropy_unit = self.unit_converter.default_units["S"]
        volume_unit = self.unit_converter.default_units["V"] 


        # --- 冷媒 TextField + 驗證按鈕 ---
        self.fluid_tf = style_text_field(ft.TextField(
            value="R134a",
            hint_text="例如 R134a, Water, Air",
            prefix_icon=ft.Icons.PROPANE_TANK_OUTLINED,
            expand=True,
            height=TOKENS.input_height,
        ))
        self.check_fluid_btn = ft.IconButton(
            icon=ft.Icons.FACT_CHECK_OUTLINED,
            on_click=self._on_check_fluid,
            tooltip="檢查冷媒名稱是否存在於 CoolProp",
            icon_color=TOKENS.primary,
            style=ft.ButtonStyle(
                bgcolor=TOKENS.primary_soft,
                shape=ft.RoundedRectangleBorder(radius=TOKENS.radius_sm),
            ),
        )
        self.fluid_check_result = ft.Text(value="", size=TOKENS.caption, color="grey")

        self.diagram_dd = style_dropdown(ft.Dropdown(
            options=[ft.dropdown.Option(x) for x in ["P-h", "T-s", "P-v", "T-v"]],
            value="P-h",
            expand=True,
            on_select=lambda event: self.set_diagram_type(event.control.value),
        ))

        # --- 參考狀態選項 ---
        self.ref_state_dd = style_dropdown(ft.Dropdown(
            options=[
                ft.dropdown.Option("Auto", "自動 (冷媒:ASHRAE, 水:Default)"),
                ft.dropdown.Option("ASHRAE", "ASHRAE (冷媒常用)"),
                ft.dropdown.Option("NBP", "NBP (常壓沸點為 0)"),
                ft.dropdown.Option("IIR", "IIR (0°C 飽和液體為基準)"),
            ],
            value="Auto",
            expand=True,
        ))

        # --- 壓力軸單位選項 ---
        self.pressure_unit_dd = style_dropdown(ft.Dropdown(
            options=[
                ft.dropdown.Option("MPa"),
                ft.dropdown.Option("kPa"),
            ],
            value="MPa",
            expand=True,
        ))

        # --- 輸入組合選項 ---
        self.input_pair_dd = style_dropdown(ft.Dropdown(
            options=[
                ft.dropdown.Option("Compressor", "壓縮機分析 (T1,P1 ; T2,P2)"),
                ft.dropdown.Option("T-P", "溫度 (T) - 壓力 (P)"),
                ft.dropdown.Option("P-h", "壓力 (P) - 焓 (h)"),
                ft.dropdown.Option("T-s", "溫度 (T) - 熵 (s)"),
                ft.dropdown.Option("P-s", "壓力 (P) - 熵 (s)"),
                ft.dropdown.Option("P-v", "壓力 (P) - 比容 (v)"),
            ],
            value="Compressor",
            expand=True,
            on_select=self._on_input_mode_change
        ))

        # --- 建立所有輸入欄 ---
        # 欄名包含單位，單位切換時由同步處理器解析並更新括號內的單位。
        self.create_input_row("td_T", f"溫度 T ({temp_unit})", "10, 50", "T", temp_unit)
        self.create_input_row("td_P", f"壓力 P ({press_unit})", "0.16, 0.7", "P", press_unit)
        self.create_input_row("td_H", f"焓 H ({enthalpy_unit})", "", "H", enthalpy_unit)
        self.create_input_row("td_S", f"熵 S ({entropy_unit})", "", "S", entropy_unit)
        self.create_input_row("td_V", f"比容 V ({volume_unit})", "", "V", volume_unit)
        for key in ("td_T", "td_P", "td_H", "td_S", "td_V"):
            self.all_entries[key]["val"].hint_text = "以逗號分隔多筆，例如 10, 50"
            self.all_entries[key]["val"].keyboard_type = ft.KeyboardType.TEXT

        self.all_entries["td_H"]["ui_row"].visible = False
        self.all_entries["td_S"]["ui_row"].visible = False
        self.all_entries["td_V"]["ui_row"].visible = False

        # --- 結果輸出與按鈕 ---
        self.result_text = ft.Text("請輸入參數並點擊繪圖。", selectable=True, size=TOKENS.caption + 1)

        # --- 初始空圖 ---
        fig, ax = plt.subplots(figsize=(8, 5.5))
        ax.text(0.5, 0.5, "尚未繪製", ha="center", va="center", color="gray")
        self.chart = fch.MatplotlibChart(figure=fig, expand=True)
        self.chart_container = ft.Container(
            content=self.chart,
            expand=True,
            height=560,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        # --- 版面配置：左側設定、右側結果圖表 ---
        self.info_text = ft.Text(
            "格式：T1,T2 與 P1,P2，各輸入兩筆；範例：10, 50 與 0.16, 0.70 MPa。",
            size=TOKENS.caption,
            color=TOKENS.text_secondary,
        )
        self.plot_btn = ft.Button(
            "繪製熱力圖",
            icon=ft.Icons.AUTO_GRAPH,
            on_click=self._on_plot_click,
            tooltip="依目前設定繪製熱力圖",
            style=primary_button_style(),
            expand=True,
        )
        self.connect_points_cb = ft.Checkbox(label="以線段連接狀態點", value=True,
                                             active_color=TOKENS.primary)

        def field(label: str, control: ft.Control) -> ft.Column:
            """以框外欄名包裝設定控制項，與其他工作區表單一致。

參數：
    label: 欄位名稱。
    control: 要包裝的 Flet 控制項。

回傳：
    欄名與控制項組成的直欄。"""
            return ft.Column(
                [ft.Text(label, size=TOKENS.body, weight=ft.FontWeight.W_500,
                         color=TOKENS.text_primary), control],
                spacing=6,
                expand=True,
            )

        def section(title: str, icon: ft.IconData, controls: list[ft.Control]) -> ft.Column:
            """建立設定面板中的分區標題與內容。

參數：
    title: 分區標題。
    icon: 分區圖示。
    controls: 分區內的控制項。

回傳：
    分區直欄。"""
            return ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, size=16, color=TOKENS.text_muted),
                            ft.Text(title, size=TOKENS.caption, weight=ft.FontWeight.W_600,
                                    color=TOKENS.text_muted),
                        ],
                        spacing=6,
                    ),
                    *controls,
                ],
                spacing=TOKENS.spacing_sm + 2,
            )

        self.result_status_box = ft.Container(
            content=ft.Row(
                [ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=TOKENS.text_muted),
                 ft.Container(content=self.result_text, expand=True)],
                spacing=TOKENS.spacing_sm,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            bgcolor=TOKENS.surface_variant,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
        )

        settings_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(ft.Icons.TUNE, size=18, color=TOKENS.primary),
                                width=34, height=34, alignment=ft.Alignment.CENTER,
                                bgcolor=TOKENS.primary_soft,
                                border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
                            ),
                            ft.Text("繪圖設定", size=TOKENS.section_title, weight=ft.FontWeight.W_600,
                                    color=TOKENS.text_primary),
                        ],
                        spacing=TOKENS.spacing_sm + 4,
                    ),
                    section("工作流體", ft.Icons.PROPANE_TANK_OUTLINED, [
                        ft.Row([self.fluid_tf, self.check_fluid_btn], spacing=TOKENS.spacing_sm,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        self.fluid_check_result,
                    ]),
                    ft.Divider(height=1, color=TOKENS.border),
                    section("圖表", ft.Icons.INSERT_CHART_OUTLINED, [
                        ft.Row([field("圖表類型", self.diagram_dd),
                                field("壓力軸單位", self.pressure_unit_dd)],
                               spacing=TOKENS.spacing_sm + 2),
                        field("參考狀態 (Reference State)", self.ref_state_dd),
                    ]),
                    ft.Divider(height=1, color=TOKENS.border),
                    section("狀態點", ft.Icons.SCATTER_PLOT_OUTLINED, [
                        field("輸入模式", self.input_pair_dd),
                        self.all_entries["td_T"]["ui_row"],
                        self.all_entries["td_P"]["ui_row"],
                        self.all_entries["td_H"]["ui_row"],
                        self.all_entries["td_S"]["ui_row"],
                        self.all_entries["td_V"]["ui_row"],
                        ft.Container(
                            content=ft.Row(
                                [ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=14, color=TOKENS.warning),
                                 ft.Container(content=self.info_text, expand=True)],
                                spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                            ),
                            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                            bgcolor=TOKENS.warning_soft,
                            border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
                        ),
                        self.connect_points_cb,
                    ]),
                    ft.Row([self.plot_btn]),
                    self.result_status_box,
                ],
                spacing=TOKENS.spacing_md,
            ),
            padding=TOKENS.spacing_lg,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
            shadow=card_shadow(),
            col={"xs": 12, "md": 5},
        )
        chart_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(ft.Icons.SHOW_CHART, size=18, color=TOKENS.warning),
                                width=34, height=34, alignment=ft.Alignment.CENTER,
                                bgcolor=TOKENS.warning_soft,
                                border_radius=ft.BorderRadius.all(TOKENS.radius_sm),
                            ),
                            ft.Column(
                                [
                                    ft.Text("熱力圖", size=TOKENS.section_title,
                                            weight=ft.FontWeight.W_600, color=TOKENS.text_primary),
                                    ft.Text("繪圖完成後，飽和曲線、等值線與狀態點會顯示在這裡。",
                                            size=TOKENS.caption, color=TOKENS.text_muted),
                                ],
                                spacing=2,
                                tight=True,
                                expand=True,
                            ),
                        ],
                        spacing=TOKENS.spacing_sm + 4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.chart_container,
                ],
                spacing=TOKENS.spacing_md,
                expand=True,
            ),
            padding=TOKENS.spacing_lg,
            bgcolor=TOKENS.surface,
            border=ft.Border.all(1, TOKENS.border),
            border_radius=ft.BorderRadius.all(TOKENS.radius_md),
            shadow=card_shadow(),
            col={"xs": 12, "md": 7},
        )
        layout = ft.ResponsiveRow(
            controls=[settings_card, chart_card],
            spacing=TOKENS.spacing_md,
            run_spacing=TOKENS.spacing_md,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        self.thermo_diagram_ui_container = ft.Container(layout, expand=True)

    # ======================================================
    # 1a. 冷媒驗證事件 (無變更)
    # ======================================================
    def _on_check_fluid(self, e):
        """使用者按下 [驗證] 按鈕時

參數：
    e (未指定型別): 函數輸入值。

回傳：
    無。"""
        fluid_name = self.fluid_tf.value.strip()
        if not fluid_name:
            self.fluid_check_result.value = "請輸入冷媒名稱"
            self.fluid_check_result.color = "red"
            if self.parent:
                self.page.update()
            return

        is_valid, msg = check_coolprop_fluid(fluid_name)
        
        if is_valid:
            self.fluid_check_result.value = f"'{fluid_name}' 驗證成功"
            self.fluid_check_result.color = "green"
        else:
            self.fluid_check_result.value = f"'{fluid_name}' 無效: {msg}"
            self.fluid_check_result.color = "red"
        
        if self.parent:
            self.page.update()

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
            
        
        if self.parent:
            self.page.update()

    # ======================================================
    # 2️⃣ 繪圖邏輯：事件觸發
    # ======================================================
    def perform_plot(self, event=None) -> None:
        """執行完整的繪圖流程：更新狀態文字、呼叫計算、處理例外並回復按鈕狀態。

        供 UI 按鈕（``_on_plot_click``）與 dedicated view（見
        ``ThermoDiagramView.perform_calculation``，供 AppShell 的
        Ctrl+Enter 捷徑使用）共用的 *public* 執行入口，兩者最終都走這
        同一條路徑，確保 plot button 與 Ctrl+Enter 行為一致。

        參數：
            event: Flet 事件；此處不需讀取事件內容。

        回傳：
            無。
        """
        self.result_text.value = "繪製中..."
        self.result_text.color = "blue"
        self.plot_btn.disabled = True
        if self.parent:
            self.page.update()

        try:
            result_str = self.calculate_thermo_diagram(use_imperial=False)
            self.result_text.value = result_str
            self.result_text.color = "green" if "成功" in result_str else "red"

        except Exception as ex:
            print(f"Error in perform_plot: {ex}")
            traceback.print_exc()
            self.result_text.value = f"計算時發生未預期的錯誤: {ex}"
            self.result_text.color = "red"

        finally:
            self.plot_btn.disabled = False
            if self.parent:
                self.page.update()

    def _on_plot_click(self, e):
        """使用者按下 [繪圖] 按鈕時的既有事件簽章；轉交給 public perform_plot()。

參數：
    e (未指定型別): 函數輸入值。

回傳：
    無。"""
        self.perform_plot(e)

    # ======================================================
    # 3️⃣ 核心邏輯：計算並繪製圖形 (無變更)
    # ======================================================
    def calculate_thermo_diagram(self, use_imperial: bool) -> str:
        """呼叫 coolprop_utils.generate_thermo_diagram() 執行繪圖

參數：
    use_imperial (bool): 函數輸入值。

回傳：
    str：函數計算或處理後的結果。"""
        try:
            # --- 繪圖前驗證冷媒 ---
            fluid = self.fluid_tf.value.strip()
            if not fluid:
                raise ValueError("冷媒名稱不可為空")

            is_valid, msg = check_coolprop_fluid(fluid)
            if not is_valid:
                self.fluid_check_result.value = f"'{fluid}' 無效: {msg}"
                self.fluid_check_result.color = "red"
                if self.parent:
                    self.page.update()
                raise ValueError(f"冷媒 '{fluid}' 無效: {msg}")
            else:
                self.fluid_check_result.value = f"'{fluid}' 驗證成功"
                self.fluid_check_result.color = "green"
                if self.parent:
                    self.page.update()
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
                points = self.state_point_parser.parse(
                    pressures=P_val_str,
                    temperatures=T_val_str,
                    pressure_unit=P_unit,
                    temperature_unit=T_unit,
                )
                if len(points) != 2:
                    raise ValueError("壓縮機分析模式需要 T1, T2 (共 2 筆溫度) 和 P1, P2 (共 2 筆壓力)。")
                T1_K, T2_K = points[0].temperature_k, points[1].temperature_k
                P1_Pa, P2_Pa = points[0].pressure_pa, points[1].pressure_pa

                s1_J_kgK = safe_props("S", "T", T1_K, "P", P1_Pa, fluid, ref_state)
                if s1_J_kgK is None or s1_J_kgK != s1_J_kgK:
                    raise ValueError(f"無法計算 s1 (T1={T_val_str}, P1={P_val_str})")
                
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
                unit_converter=self.unit_converter,
                figure=self.chart.figure,
            )

            # Reuse the attached figure so Flet Charts keeps its live WebSocket manager.
            self.chart.figure = fig
            try:
                chart_page = self.chart.page
            except RuntimeError:
                chart_page = None
            if chart_page:
                # Ask the existing Flet Charts manager to render the refreshed figure.
                self.chart.send_message({"type": "refresh"})
            point_count = len(state_points_si)
            if point_count == 0:
                 return f"成功繪製 {fluid} 的 {diagram} 圖 (無狀態點)。"
            if input_mode == "Compressor":
                return "成功繪製壓縮機分析 (3 個點)。"
            else:
                return f"成功繪製 {fluid} 的 {diagram} 圖 ({point_count} 個點)。"

        except Exception as ex:
            print(f"Error in calculate_thermo_diagram: {ex}")
            traceback.print_exc() 
            return f"熱力圖繪製失敗: {ex}"
        

    # ======================================================
    # (修正) 12a. 多數值單位同步處理器
    # ======================================================
    def _create_multi_value_unit_sync_handler(
        self, unit_type: str, sync_group: list[str]
    ) -> Callable[[ft.ControlEvent], None]:
        """建立可轉換多筆輸入並同步更新框外單位標籤的事件處理器。

        參數：
            unit_type: 單位轉換器使用的性質代碼。
            sync_group: 需要共用所選單位及更新標籤的輸入鍵。

        回傳：
            接收 Flet 控制項事件並更新輸入值、單位與標籤的回呼函式。
        """
        def on_change_handler(e: ft.ControlEvent) -> None:
            """換算所選欄位的數值，並同步群組單位與框外標籤。

            參數：
                e: 含有觸發單位選單之控制項的 Flet 事件。

            回傳：
                無。
            """
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
                        current_label = self.all_entries[key]["label_control"].value
                        
                        # 找到最後一個 '(', (例如 "壓力 P (MPa)")
                        base_label = current_label
                        paren_index = current_label.rfind("(")
                        if paren_index != -1:
                            base_label = current_label[:paren_index].strip() # 得到 "壓力 P"
                            
                        # 重組標籤
                        self.all_entries[key]["label_control"].value = f"{base_label} ({new_unit})"
                    except Exception as ex:
                        print(f"Failed to update label for {key}: {ex}")
                    
                    # 在 control 物件上儲存新單位，供下次變更時使用
                    if self.all_entries[key].get("unit"):
                        setattr(self.all_entries[key]["unit"], "previous_unit", new_unit)

            if self.parent:
                self.page.update()
        
        # --- on_change_handler 結束 ---
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
        self.all_entries["td_P"]["unit"].on_select = self._create_unit_sync_handler("P", p_sync_group)
        
        # 焓 (H)
        h_sync_group = ["td_H"] 
        self.all_entries["td_H"]["unit"].on_select = self._create_unit_sync_handler("H", h_sync_group)

        # 熵 (S)
        s_sync_group = ["td_S"]
        self.all_entries["td_S"]["unit"].on_select = self._create_unit_sync_handler("S", s_sync_group)

        # 溫度 (T)
        t_sync_group = ["td_T"]
        self.all_entries["td_T"]["unit"].on_select = self._create_unit_sync_handler("T", t_sync_group)

        # 比容 (V)
        v_sync_group = ["td_V"]
        self.all_entries["td_V"]["unit"].on_select = self._create_unit_sync_handler("V", v_sync_group)
        
        def setup_sync_for_group(unit_type, sync_group):
            """輔助函式：綁定 handler 並設定初始單位

參數：
    unit_type (未指定型別): 函數輸入值。
    sync_group (未指定型別): 函數輸入值。

回傳：
    無。"""
            
            # 1. 建立客製化的 handler
            handler = self._create_multi_value_unit_sync_handler(unit_type, sync_group)
            
            initial_unit = None
            for key in sync_group:
                if key in self.all_entries and self.all_entries[key].get("unit"):
                    # 2. 綁定 on_select 事件
                    self.all_entries[key]["unit"].on_select = handler
                    
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