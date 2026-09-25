"""不依賴 UI 的濕空氣線圖曲線資料。

曲線點位全部由 `PsychrometricService` 計算（飽和線、等相對濕度線、等焓線），
本模組只負責取樣與裁切；呈現（Matplotlib／Flet）由通道轉接器負責。
座標：x 為乾球溫度（°C），y 為濕度比（kg/kg 乾空氣）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from domain.psychrometrics.service import PsychrometricService

DEFAULT_RH_LEVELS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
DEFAULT_ENTHALPY_LEVELS_KJ = tuple(float(level) for level in range(0, 130, 10))


@dataclass(frozen=True)
class ChartCurve:
    """一條以乾球溫度（°C）與濕度比（kg/kg）描述的曲線。"""

    label: str
    dry_bulb_c: tuple[float, ...]
    humidity_ratio: tuple[float, ...]


@dataclass(frozen=True)
class PsychrometricChartData:
    """一張濕空氣線圖所需的全部曲線與座標範圍。"""

    altitude_m: float
    pressure_pa: float
    dry_bulb_range_c: tuple[float, float]
    humidity_ratio_max: float
    saturation: ChartCurve
    relative_humidity_lines: tuple[ChartCurve, ...]
    enthalpy_lines: tuple[ChartCurve, ...]


@dataclass(frozen=True)
class ChartMarker:
    """線圖上的一個標註點（乾球溫度 °C、濕度比 kg/kg）。"""

    label: str
    dry_bulb_c: float
    humidity_ratio: float

    @classmethod
    def from_state(cls, label: str, state: Mapping[str, Any]) -> "ChartMarker":
        """由濕空氣服務回傳的狀態建立標註點。

參數：
    label: 標註文字。
    state: 含 Tdb（K）與 W（kg/kg）的狀態。

回傳：
    ChartMarker。"""
        return cls(label, float(state["Tdb"]) - 273.15, float(state["W"]))


@dataclass(frozen=True)
class ChartGuide:
    """由狀態點延伸出的輔助線（例如到露點或濕球溫度）；終點標籤取自 end.label。"""

    start: ChartMarker
    end: ChartMarker


def _linspace(start: float, stop: float, count: int) -> list[float]:
    """回傳含端點的等距取樣值。

參數：
    start: 起點。
    stop: 終點。
    count: 點數（至少 2）。

回傳：
    取樣值清單。"""
    step = (stop - start) / (count - 1)
    return [start + step * index for index in range(count)]


def _rh_curve(
    service: PsychrometricService,
    rh: float,
    temperatures_c: Sequence[float],
    altitude_m: float,
    humidity_ratio_max: float,
    label: str,
) -> ChartCurve:
    """取樣一條等相對濕度線，超出 y 軸上限的點不納入。

參數：
    service: 濕空氣服務。
    rh: RH 分率。
    temperatures_c: 乾球溫度取樣（°C）。
    altitude_m: 海拔（m）。
    humidity_ratio_max: y 軸上限（kg/kg）。
    label: 曲線標籤。

回傳：
    ChartCurve。"""
    xs: list[float] = []
    ys: list[float] = []
    for tdb_c in temperatures_c:
        try:
            w = service.humidity_ratio_from_rh(tdb_c + 273.15, rh, altitude_m)
        except ValueError:
            break
        if w > humidity_ratio_max:
            if xs:
                xs.append(tdb_c)
                ys.append(humidity_ratio_max)
            break
        xs.append(tdb_c)
        ys.append(w)
    return ChartCurve(label, tuple(xs), tuple(ys))


def _enthalpy_curve(
    service: PsychrometricService,
    enthalpy_kj: float,
    dry_bulb_range_c: tuple[float, float],
    altitude_m: float,
    humidity_ratio_max: float,
    samples: int,
) -> ChartCurve:
    """取樣一條等焓線：由濕度比 0 開始，直到碰到飽和線或座標邊界。

參數：
    service: 濕空氣服務。
    enthalpy_kj: 比焓（kJ/kg 乾空氣）。
    dry_bulb_range_c: x 軸範圍（°C）。
    altitude_m: 海拔（m）。
    humidity_ratio_max: y 軸上限（kg/kg）。
    samples: 取樣點數。

回傳：
    ChartCurve；完全落在座標外時點位為空。"""
    low_c, high_c = dry_bulb_range_c
    xs: list[float] = []
    ys: list[float] = []
    for w in _linspace(0.0, humidity_ratio_max, samples):
        try:
            tdb_k = service.dry_bulb_from_enthalpy(enthalpy_kj * 1000.0, w)
        except ValueError:
            break
        tdb_c = tdb_k - 273.15
        if tdb_c < low_c:
            break
        if tdb_c > high_c:
            continue
        saturation_w = service.humidity_ratio_from_rh(tdb_k, 1.0, altitude_m)
        if w > saturation_w:
            break
        xs.append(tdb_c)
        ys.append(w)
    return ChartCurve(f"{enthalpy_kj:g} kJ/kg", tuple(xs), tuple(ys))


def build_psychrometric_chart_data(
    service: PsychrometricService,
    altitude_m: float = 0.0,
    *,
    dry_bulb_range_c: tuple[float, float] = (-10.0, 50.0),
    humidity_ratio_max: float = 0.030,
    rh_levels: Sequence[float] = DEFAULT_RH_LEVELS,
    enthalpy_levels_kj: Sequence[float] = DEFAULT_ENTHALPY_LEVELS_KJ,
    samples: int = 61,
) -> PsychrometricChartData:
    """建立指定海拔的濕空氣線圖曲線資料。

參數：
    service: 濕空氣服務。
    altitude_m: 海拔（m），決定大氣壓力。
    dry_bulb_range_c: x 軸乾球溫度範圍（°C）。
    humidity_ratio_max: y 軸濕度比上限（kg/kg）。
    rh_levels: 要繪製的等相對濕度線（分率，不含飽和線）。
    enthalpy_levels_kj: 要繪製的等焓線（kJ/kg）。
    samples: 每條曲線的取樣點數。

回傳：
    PsychrometricChartData。

引發：
    ValueError：座標範圍或取樣點數不合理時。"""
    low_c, high_c = dry_bulb_range_c
    if high_c <= low_c:
        raise ValueError("乾球溫度範圍的上限必須大於下限。")
    if humidity_ratio_max <= 0:
        raise ValueError("濕度比上限必須大於 0。")
    if samples < 2:
        raise ValueError("取樣點數至少為 2。")
    temperatures = _linspace(low_c, high_c, samples)
    saturation = _rh_curve(service, 1.0, temperatures, altitude_m, humidity_ratio_max, "100%")
    rh_lines = tuple(
        _rh_curve(service, rh, temperatures, altitude_m, humidity_ratio_max, f"{rh * 100:.0f}%")
        for rh in rh_levels
    )
    enthalpy_lines = tuple(
        curve
        for curve in (
            _enthalpy_curve(service, level, dry_bulb_range_c, altitude_m, humidity_ratio_max, samples)
            for level in enthalpy_levels_kj
        )
        if len(curve.dry_bulb_c) >= 2
    )
    return PsychrometricChartData(
        altitude_m=altitude_m,
        pressure_pa=service.calculate_pressure_from_altitude(altitude_m),
        dry_bulb_range_c=(low_c, high_c),
        humidity_ratio_max=humidity_ratio_max,
        saturation=saturation,
        relative_humidity_lines=rh_lines,
        enthalpy_lines=enthalpy_lines,
    )
