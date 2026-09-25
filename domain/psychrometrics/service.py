"""圍繞排除的 psychrometric model 建立單一 adapter 邊界。"""

from __future__ import annotations

from typing import Any, Protocol


class PsychrometricModel(Protocol):
    """由注入的舊版 psychrometric adapter 實作的 Protocol。"""

    def cal_p(self, altitude_m: float) -> float: ...

    def Calculation_process_m_Tdb_Twb(self, **kwargs: Any) -> tuple[Any, ...]: ...

    def Calculation_process_m_Tdb_RH(self, **kwargs: Any) -> tuple[Any, ...]: ...

    def cal_Tdp_from_Pw(self, vapor_pressure: float) -> float: ...

    def cal_Pws(self, dry_bulb_c: float) -> float: ...

    def cal_Ws(self, total_pressure_kpa: float, vapor_pressure_kpa: float) -> float: ...

    def cal_Pw(self, total_pressure_kpa: float, humidity_ratio: float) -> float: ...

    def cal_h(self, dry_bulb_c: float, humidity_ratio: float) -> float: ...


class PsychrometricService:
    """回傳注入 model 邊界的 SI 導向數值結果。

所有濕空氣關係式（飽和壓力、濕度比、焓）都由注入的 model 提供；本服務只做
單位正規化、驗證與反解，不另行實作第二套濕空氣公式。
"""

    # 反解乾球溫度時的搜尋範圍（°C）與收斂容許誤差。
    _DRY_BULB_SEARCH_RANGE_C = (-100.0, 200.0)
    _DRY_BULB_TOLERANCE_C = 1e-7

    def __init__(self, model: PsychrometricModel) -> None:
        """以舊版 model 的中立 adapter 初始化。

參數：
    model (PsychrometricModel): 函數輸入值。

回傳：
    無。"""
        self._model = model

    def calculate_pressure_from_altitude(self, altitude_m: float) -> float:
        """回傳以公尺海拔高度計算、以 pascal 為單位的大氣壓力。

參數：
    altitude_m (float): 函數輸入值。

回傳：
    float：函數計算或處理後的結果。"""
        return self._model.cal_p(altitude_m) * 1000.0

    def calculate_from_tdb_twb(
        self,
        tdb_k: float,
        twb_k: float,
        altitude_m: float,
    ) -> dict[str, Any]:
        """由乾球／濕球溫度計算 psychrometric properties。

參數：
    tdb_k (float): 函數輸入值。
    twb_k (float): 函數輸入值。
    altitude_m (float): 函數輸入值。

回傳：
    dict[str, Any]：函數計算或處理後的結果。"""
        tdb_c = tdb_k - 273.15
        twb_c = twb_k - 273.15
        pressure_kpa, vapor_pressure_kpa, pws_db_kpa, pws_wb_kpa, w, ws, wss, rh, enthalpy, volume = (
            self._model.Calculation_process_m_Tdb_Twb(
                m=altitude_m,
                T_db=tdb_c,
                T_wb=twb_c,
            )
        )
        dew_point_c = self._model.cal_Tdp_from_Pw(vapor_pressure_kpa)
        if not 0.0 <= rh <= 100.0:
            raise ValueError("Legacy model RH must be between 0.0 and 100.0 percent")
        rh_fraction = rh / 100.0
        return self._build_result(
            altitude_m=altitude_m,
            pressure=pressure_kpa * 1000.0,
            tdb_k=tdb_k,
            twb_k=twb_k,
            dew_point_k=dew_point_c + 273.15,
            rh=rh_fraction,
            w=w,
            enthalpy=enthalpy * 1000.0,
            volume=volume,
            vapor_pressure=vapor_pressure_kpa * 1000.0,
            pws_db=pws_db_kpa * 1000.0,
            pws_wb=pws_wb_kpa * 1000.0,
            ws=ws,
            wss=wss,
        )

    def calculate_from_tdb_rh(
        self,
        tdb_k: float,
        rh: float,
        altitude_m: float,
    ) -> dict[str, Any]:
        """由乾球／RH 輸入計算 psychrometric properties。

參數：
    tdb_k (float): 函數輸入值。
    rh (float): 函數輸入值。
    altitude_m (float): 函數輸入值。

回傳：
    dict[str, Any]：函數計算或處理後的結果。"""
        tdb_c = tdb_k - 273.15
        rh_fraction = self._normalize_rh_fraction(rh)
        twb_c, pressure_kpa, vapor_pressure_kpa, pws_db_kpa, pws_wb_kpa, w, ws, wss, _, enthalpy, volume = (
            self._model.Calculation_process_m_Tdb_RH(
                m=altitude_m,
                T_db=tdb_c,
                RH=rh_fraction * 100.0,
            )
        )
        dew_point_c = self._model.cal_Tdp_from_Pw(vapor_pressure_kpa)
        return self._build_result(
            altitude_m=altitude_m,
            pressure=pressure_kpa * 1000.0,
            tdb_k=tdb_k,
            twb_k=twb_c + 273.15,
            dew_point_k=dew_point_c + 273.15,
            rh=rh_fraction,
            w=w,
            enthalpy=enthalpy * 1000.0,
            volume=volume,
            vapor_pressure=vapor_pressure_kpa * 1000.0,
            pws_db=pws_db_kpa * 1000.0,
            pws_wb=pws_wb_kpa * 1000.0,
            ws=ws,
            wss=wss,
        )

    def humidity_ratio_from_rh(self, tdb_k: float, rh: float, altitude_m: float) -> float:
        """以乾球溫度與 RH 計算濕度比，不執行完整狀態計算。

供圖表取樣等需要大量點位的呼叫端使用；結果與完整狀態計算使用相同的 model 公式。

參數：
    tdb_k: 乾球溫度（K）。
    rh: 相對濕度分率（0–1）。
    altitude_m: 海拔高度（m）。

回傳：
    濕度比（kg 水／kg 乾空氣）。

引發：
    ValueError：RH 超出範圍，或水蒸氣分壓不小於大氣壓力時。"""
        rh_fraction = self._normalize_rh_fraction(rh)
        pressure_kpa = self._model.cal_p(altitude_m)
        vapor_pressure_kpa = rh_fraction * self._model.cal_Pws(tdb_k - 273.15)
        if vapor_pressure_kpa >= pressure_kpa:
            raise ValueError("水蒸氣分壓不可大於或等於大氣壓力，請確認溫度與海拔。")
        return self._model.cal_Ws(pressure_kpa, vapor_pressure_kpa)

    def relative_humidity_from_w(self, tdb_k: float, w: float, altitude_m: float) -> float:
        """以乾球溫度與濕度比計算 RH 分率；結果可能大於 1，代表過飽和。

參數：
    tdb_k: 乾球溫度（K）。
    w: 濕度比（kg/kg）。
    altitude_m: 海拔高度（m）。

回傳：
    RH 分率；未截斷，由呼叫端判斷是否過飽和。

引發：
    ValueError：濕度比為負值時。"""
        if w < 0:
            raise ValueError("濕度比不可為負值。")
        pressure_kpa = self._model.cal_p(altitude_m)
        vapor_pressure_kpa = self._model.cal_Pw(pressure_kpa, w)
        return vapor_pressure_kpa / self._model.cal_Pws(tdb_k - 273.15)

    def calculate_from_tdb_w(self, tdb_k: float, w: float, altitude_m: float) -> dict[str, Any]:
        """由乾球溫度與濕度比計算完整濕空氣狀態。

參數：
    tdb_k: 乾球溫度（K）。
    w: 濕度比（kg/kg）。
    altitude_m: 海拔高度（m）。

回傳：
    與其他計算路徑相同結構的中立結果。

引發：
    ValueError：濕度比為負值，或狀態超過飽和（會產生凝結或霧化）時。"""
        rh = self.relative_humidity_from_w(tdb_k, w, altitude_m)
        if rh > 1.0 + 1e-6:
            raise ValueError(
                f"此狀態超過飽和（RH {rh * 100:.1f}%），會產生凝結或霧化，超出濕空氣模型適用範圍。"
            )
        return self.calculate_from_tdb_rh(tdb_k, min(rh, 1.0), altitude_m)

    def enthalpy_at(self, tdb_k: float, w: float) -> float:
        """回傳指定乾球溫度與濕度比的濕空氣比焓（J/kg 乾空氣）。

參數：
    tdb_k: 乾球溫度（K）。
    w: 濕度比（kg/kg）。

回傳：
    比焓（J/kg 乾空氣）。"""
        return self._model.cal_h(tdb_k - 273.15, w) * 1000.0

    def dry_bulb_from_enthalpy(self, h_j_kg: float, w: float) -> float:
        """以比焓與濕度比反解乾球溫度（K），使用 model 的焓公式二分搜尋。

參數：
    h_j_kg: 比焓（J/kg 乾空氣）。
    w: 濕度比（kg/kg）。

回傳：
    乾球溫度（K）。

引發：
    ValueError：濕度比為負值，或比焓超出可反解範圍時。"""
        if w < 0:
            raise ValueError("濕度比不可為負值。")
        target_kj = h_j_kg / 1000.0
        low, high = self._DRY_BULB_SEARCH_RANGE_C
        if not self._model.cal_h(low, w) <= target_kj <= self._model.cal_h(high, w):
            raise ValueError("比焓超出可反解的乾球溫度範圍（-100–200 °C）。")
        while high - low > self._DRY_BULB_TOLERANCE_C:
            middle = (low + high) / 2.0
            if self._model.cal_h(middle, w) < target_kj:
                low = middle
            else:
                high = middle
        return (low + high) / 2.0 + 273.15

    @staticmethod
    def _normalize_rh_fraction(rh: float) -> float:
        """驗證 domain RH fraction，維持單一 canonical input semantics。

參數：
    rh (float): 0.0 至 1.0 的 domain RH fraction。

回傳：
    float：原樣回傳的 RH fraction。

引發：
    ValueError：RH 不在 0.0 至 1.0 的 domain 範圍。"""
        if not 0.0 <= rh <= 1.0:
            raise ValueError("RH must be a fraction between 0.0 and 1.0")
        return rh

    @staticmethod
    def _build_result(
        *,
        altitude_m: float,
        pressure: float,
        tdb_k: float,
        twb_k: float,
        dew_point_k: float,
        rh: float,
        w: float,
        enthalpy: float,
        volume: float,
        vapor_pressure: float,
        pws_db: float,
        pws_wb: float,
        ws: float,
        wss: float,
    ) -> dict[str, Any]:
        """建立兩個 channel 共用的穩定中立結果結構。

參數：
    altitude_m (float): 函數輸入值。
    pressure (float): 函數輸入值。
    tdb_k (float): 函數輸入值。
    twb_k (float): 函數輸入值。
    dew_point_k (float): 函數輸入值。
    rh (float): 函數輸入值。
    w (float): 函數輸入值。
    enthalpy (float): 函數輸入值。
    volume (float): 函數輸入值。
    vapor_pressure (float): 函數輸入值。
    pws_db (float): 函數輸入值。
    pws_wb (float): 函數輸入值。
    ws (float): 函數輸入值。
    wss (float): 函數輸入值。

回傳：
    dict[str, Any]：函數計算或處理後的結果。"""
        return {
            "Altitude": altitude_m,
            "P": pressure,
            "Tdb": tdb_k,
            "Twb": twb_k,
            "Tdp": dew_point_k,
            "RH": rh,
            "W": w,
            "H": enthalpy,
            "V": volume,
            "Pw": vapor_pressure,
            "Pws_db": pws_db,
            "Pws_wd": pws_wb,
            "Ws": ws,
            "Wss": wss,
        }
