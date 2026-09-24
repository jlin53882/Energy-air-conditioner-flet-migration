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


ROUTES = (
    WorkspaceRoute("home", "首頁", "工作區", "HOME_OUTLINED"),
    WorkspaceRoute("thermo_properties", "狀態查詢", "熱力學", "SCIENCE_OUTLINED"),
    WorkspaceRoute("compressor", "壓縮機", "冷凍系統", "COMPRESS_OUTLINED"),
    WorkspaceRoute("evaporator", "蒸發器", "冷凍系統", "AC_UNIT"),
    WorkspaceRoute("condenser", "冷凝器", "冷凍系統", "DEVICE_THERMOSTAT_OUTLINED"),
    WorkspaceRoute("psychrometrics", "濕空氣性質", "空氣處理", "AIR_OUTLINED"),
    WorkspaceRoute("ph_chart", "P-h 圖", "圖表", "SHOW_CHART_OUTLINED"),
    WorkspaceRoute("ts_chart", "T-s 圖", "圖表", "SHOW_CHART"),
)

ROUTE_BY_KEY = {route.key: route for route in ROUTES}
DEFAULT_ROUTE = "thermo_properties"
