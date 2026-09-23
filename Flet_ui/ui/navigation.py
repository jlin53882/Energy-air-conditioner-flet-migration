"""Stable route definitions for implemented HVAC workspace views."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceRoute:
    """Describe one reachable workspace view using a stable internal key."""

    key: str
    label: str
    section: str
    icon: str
    analysis_category: str | None = None


ROUTES = (
    WorkspaceRoute("home", "首頁", "工作區", "HOME_OUTLINED"),
    WorkspaceRoute("thermo_properties", "狀態查詢", "熱力學", "SCIENCE_OUTLINED"),
    WorkspaceRoute("compressor", "壓縮機", "冷凍系統", "COMPRESS_OUTLINED", "compressor"),
    WorkspaceRoute("evaporator", "蒸發器", "冷凍系統", "AC_UNIT", "evaporator"),
    WorkspaceRoute("condenser", "冷凝器", "冷凍系統", "DEVICE_THERMOSTAT_OUTLINED", "condenser"),
    WorkspaceRoute("psychrometrics", "濕空氣性質", "空氣處理", "AIR_OUTLINED", "psychrometrics"),
    WorkspaceRoute("ph_chart", "P-h 圖", "圖表", "SHOW_CHART_OUTLINED", "charts"),
    WorkspaceRoute("ts_chart", "T-s 圖", "圖表", "SHOW_CHART", "charts"),
)

ROUTE_BY_KEY = {route.key: route for route in ROUTES}
DEFAULT_ROUTE = "thermo_properties"
