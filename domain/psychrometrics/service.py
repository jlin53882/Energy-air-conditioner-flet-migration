"""圍繞排除的 psychrometric model 建立單一 adapter 邊界。"""

from __future__ import annotations

from typing import Any, Protocol


class PsychrometricModel(Protocol):
    """由注入的舊版 psychrometric adapter 實作的 Protocol。"""

    def cal_p(self, altitude_m: float) -> float: ...

    def Calculation_process_m_Tdb_Twb(self, **kwargs: Any) -> tuple[Any, ...]: ...

    def Calculation_process_m_Tdb_RH(self, **kwargs: Any) -> tuple[Any, ...]: ...

    def cal_Tdp_from_Pw(self, vapor_pressure: float) -> float: ...


class PsychrometricService:
    """回傳注入 model 邊界的 SI 導向數值結果。"""

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
        return self._build_result(
            altitude_m=altitude_m,
            pressure=pressure_kpa * 1000.0,
            tdb_k=tdb_k,
            twb_k=twb_k,
            dew_point_k=dew_point_c + 273.15,
            rh=rh,
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
        rh_fraction = rh if 0.0 <= rh <= 1.0 else rh / 100.0
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
            rh=rh_fraction if rh <= 1.0 else rh,
            w=w,
            enthalpy=enthalpy * 1000.0,
            volume=volume,
            vapor_pressure=vapor_pressure_kpa * 1000.0,
            pws_db=pws_db_kpa * 1000.0,
            pws_wb=pws_wb_kpa * 1000.0,
            ws=ws,
            wss=wss,
        )

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
