# PsychrometricCalculator.py
# 職責：封裝 shared psychrometric domain service，提供 Flet 相容介面。

from domain.psychrometrics.service import PsychrometricService
from infrastructure.psychrometrics import LegacyPsychrometricModelAdapter


class PsychrometricCalculator:
    """面向 Flet 的共用 psychrometric service adapter。"""

    def __init__(self, service: PsychrometricService | None = None) -> None:
        """以可注入的 psychrometric service 初始化 adapter。

參數：
    service (PsychrometricService | None): 函數輸入值。

回傳：
    無。"""
        self._service = service or PsychrometricService(LegacyPsychrometricModelAdapter())

    def calculate_pressure_from_altitude(self, altitude_m):
        """回傳以 pascal 為單位的大氣壓力。

參數：
    altitude_m (未指定型別): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
        return self._service.calculate_pressure_from_altitude(altitude_m)

    def calculate_from_tdb_twb(self, tdb_k, twb_k, altitude_m):
        """回傳乾球／濕球輸入的共用數值結果。

參數：
    tdb_k (未指定型別): 函數輸入值。
    twb_k (未指定型別): 函數輸入值。
    altitude_m (未指定型別): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
        return self._service.calculate_from_tdb_twb(tdb_k, twb_k, altitude_m)

    def calculate_from_tdb_rh(self, tdb_k, rh, altitude_m):
        """回傳乾球／RH 輸入的共用數值結果。

參數：
    tdb_k (未指定型別): 函數輸入值。
    rh (未指定型別): 函數輸入值。
    altitude_m (未指定型別): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
        return self._service.calculate_from_tdb_rh(tdb_k, rh, altitude_m)
