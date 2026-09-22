# flet_app_re.py (主程式 - 負責依賴注入)

import flet as ft 

# 從 "ui_components.unit" 套件導入所有工具類
from .ui_components.unit.UnitConverter import UnitConverter
from .ui_components.unit.ThermoStateCalculator import ThermoStateCalculator
from .ui_components.unit.PropertyFormatter import PropertyFormatter
from .ui_components.unit.HVACAnalyzer import HVACAnalyzer
from .ui_components.unit.PsychrometricCalculator import PsychrometricCalculator

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
    
    # --- 在這裡建立 "服務"，而不是在 Tab 內部 ---
    hvac_analyzer = HVACAnalyzer()
    psy_calculator = PsychrometricCalculator()

    # 3. 建立兩個分頁的 UI 元件實例 (注入依賴)
    prop_tab_content = PropertyTab(
        unit_converter=unit_converter,
        state_calculator=state_calculator,
        formatter=formatter,
        page=page
    )

    # --- 將 "服務" 注入到 AnalysisTab ---
    analysis_tab_content = AnalysisTab(
        unit_converter=unit_converter, 
        page=page,
        analyzer=hvac_analyzer,         # <-- 注入 HVAC 分析器
        psy_calculator=psy_calculator,  # <-- 注入 濕空氣 分析器
        state_calculator=state_calculator,
    )

    # 4. 建立分頁控制器 (Tabs)
    main_tabs = ft.Tabs(
        selected_index=0, 
        animation_duration=300, 
        tabs=[
            ft.Tab(
                text="熱力性質查詢", 
                icon=ft.Icons.BOOK_ONLINE, 
                content=prop_tab_content
            ),
            ft.Tab(
                text="冷凍空調分析", 
                icon=ft.Icons.AC_UNIT, 
                content=analysis_tab_content
            ),
        ],
        expand=1, 
    )

    # 5. 將分頁控制器加入頁面
    page.add(main_tabs)
    page.update()


if __name__ == "__main__":
    ft.app(target=main)