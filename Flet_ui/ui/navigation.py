"""定義目前已實作工作區畫面的穩定路由。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceRoute:
    """描述一個可到達的工作區畫面及其穩定內部路由鍵。

    PR #4（Analysis Workspace Migration）之後，route 直接映射至各自的
    dedicated view，不再需要 ``analysis_category`` 這個中介欄位轉交給共用
    的 ``AnalysisTab.set_category``；因此不保留該欄位。
    """

    key: str
    label: str
    section: str
    icon: str
    description: str = ""


ROUTES = (
    WorkspaceRoute(
        "home", "首頁", "工作區", "SPACE_DASHBOARD_OUTLINED",
        description="總覽所有已實作的熱力學與冷凍空調工具。",
    ),
    WorkspaceRoute(
        "thermo_properties", "狀態查詢", "熱力學", "SCIENCE_OUTLINED",
        description="以兩個獨立性質查詢冷媒或水的熱力狀態，並可計算廣延性質。",
    ),
    WorkspaceRoute(
        "compressor", "壓縮機", "冷凍系統", "COMPRESS_OUTLINED",
        description="壓縮比、壓縮功、等熵／容積效率、可逆功與 Exergy 分析。",
    ),
    WorkspaceRoute(
        "evaporator", "蒸發器", "冷凍系統", "AC_UNIT",
        description="以進出口焓值與質量流率計算蒸發器熱交換率。",
    ),
    WorkspaceRoute(
        "condenser", "冷凝器", "冷凍系統", "DEVICE_THERMOSTAT_OUTLINED",
        description="冷凝器放熱率，以及能量、熵與 Exergy 平衡分析。",
    ),
    WorkspaceRoute(
        "refrigeration_cycle", "冷凍循環", "冷凍系統", "LOOP",
        description="蒸氣壓縮循環 COP、流量與 P-h 圖。",
    ),
    WorkspaceRoute(
        "saturation", "飽和性質", "冷凍系統", "WATER_DROP_OUTLINED",
        description="已知壓力或溫度查詢冷媒泡點、露點與溫度滑移；已知壓力時另提供蒸發潛熱。",
    ),
    WorkspaceRoute(
        "superheat_subcooling", "過熱／過冷", "冷凍系統", "THERMOSTAT_OUTLINED",
        description="以現場量測壓力（錶壓或絕對）與管溫判讀過熱度或過冷度。",
    ),
    WorkspaceRoute(
        "psychrometrics", "濕空氣性質", "空氣處理", "AIR_OUTLINED",
        description="依海拔與乾濕球溫度或相對濕度計算濕空氣完整性質。",
    ),
    WorkspaceRoute(
        "air_processes", "空氣處理程序", "空氣處理", "HVAC_OUTLINED",
        description="氣流混合、顯熱加熱／冷卻、冷卻除濕與送風量，並標示在濕空氣線圖上。",
    ),
    WorkspaceRoute(
        "ph_chart", "P-h 圖", "圖表", "SHOW_CHART_OUTLINED",
        description="繪製壓力－焓圖並標示狀態點或壓縮過程。",
    ),
    WorkspaceRoute(
        "ts_chart", "T-s 圖", "圖表", "STACKED_LINE_CHART",
        description="繪製溫度－熵圖並標示狀態點或壓縮過程。",
    ),
    WorkspaceRoute(
        "psychrometric_chart", "濕空氣線圖", "圖表", "BUBBLE_CHART_OUTLINED",
        description="依海拔繪製濕空氣線圖，標示多個狀態點並列出完整性質。",
    ),
    WorkspaceRoute(
        "unit_converter", "單位換算", "工具", "SWAP_HORIZ",
        description="壓力、溫度、溫差、冷凍能力（RT、kcal/h）、風量等常用單位即時換算。",
    ),
)

ROUTE_BY_KEY = {route.key: route for route in ROUTES}
DEFAULT_ROUTE = "thermo_properties"
