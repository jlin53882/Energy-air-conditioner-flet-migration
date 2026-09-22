# flet_app_re.py (主程式 - 負責依賴注入)

import flet as ft 

# 從 "ui_components.unit" 套件導入所有工具類
from .ui_components.unit.UnitConverter import UnitConverter
from .ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from .ui_components.unit.PropertyFormatter import PropertyFormatter
from .ui_components.unit.HVACAnalyzer import HVACAnalyzer
from .ui_components.unit.PsychrometricCalculator import PsychrometricCalculator
from application.property_queries import PropertyQueryService

# 從 "ui_components" 套件導入 UI 類
from .ui_components.property_tab import PropertyTab #熱力學分析
from .ui_components.analysis_tab import AnalysisTab #冷凍空調原理 分析

# 定義主函數
def main(page: ft.Page):
    # 1. 頁面基本設定
    page.title = "熱力學性質與分析工具 (Flet 版)"
    page.window_width = 640
    page.window_height = 840
    page.theme_mode = ft.ThemeMode.LIGHT

    # 2. 建立依賴鏈 (Dependency Chain)
    unit_converter = UnitConverter()
    state_calculator = ThermoStateCalculator(unit_converter)
    formatter = PropertyFormatter(unit_converter)
    property_query_service = PropertyQueryService(state_calculator.state_service)
    
    # --- 在這裡建立 "服務"，而不是在 Tab 內部 ---
    hvac_analyzer = HVACAnalyzer()
    psy_calculator = PsychrometricCalculator()

    # 3. 建立兩個分頁的 UI 元件實例 (注入依賴)
    prop_tab_content = PropertyTab(
        unit_converter=unit_converter,
        state_calculator=state_calculator,
        formatter=formatter,
        page=page,
        query_service=property_query_service
    )

    # --- 將 "服務" 注入到 AnalysisTab ---
    analysis_tab_content = AnalysisTab(
        unit_converter=unit_converter, 
        page=page,
        analyzer=hvac_analyzer,         # <-- 注入 HVAC 分析器
        psy_calculator=psy_calculator,  # <-- 注入 濕空氣 分析器
        state_calculator=state_calculator,
    )

    # 4. 建立 Flet 1.0 分頁控制器。
    tab_bar = ft.TabBar(
        tabs=[
            ft.Tab(label="熱力性質查詢", icon=ft.Icons.BOOK_ONLINE),
            ft.Tab(label="冷凍空調分析", icon=ft.Icons.AC_UNIT),
        ],
    )
    tab_view = ft.TabBarView(
        controls=[
            ft.Container(content=prop_tab_content, expand=True),
            ft.Container(content=analysis_tab_content, expand=True),
        ],
        expand=True,
    )
    main_tabs = ft.Tabs(
        content=ft.Column(
            controls=[tab_bar, tab_view],
            expand=True,
        ),
        length=2,
        selected_index=0,
        animation_duration=300,
        expand=1,
    )

    # 5. 將分頁控制器加入頁面
    page.add(main_tabs)
    page.update()


if __name__ == "__main__":
    ft.run(main)