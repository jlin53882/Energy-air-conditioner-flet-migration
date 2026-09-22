# PsychrometricCalculator.py
# 職責：封裝 PsychrometricChart 函式庫，專門用於濕空氣計算。
# 
# *** 新版本 ***
# 返回包含 *所有* 變數的 SI 基礎單位 (K, Pa, J/kg...) 的 *數值字典*，
# 以便 Flet UI (analysis_tab) 進行後續的單位轉換和詳細格式化。

# 導入底層模型
from Flet_ui.PsychrometricChart import PsychrometricChart_01_ASHF_model as psy

class PsychrometricCalculator:

    def calculate_pressure_from_altitude(self, altitude_m):
        """
        計算海拔高度對應的大氣壓力。
        :param altitude_m: 海拔高度 (SI: m)
        :return: 大氣壓力 (SI: Pa)
        """
        # psy.cal_p 返回 kPa
        P_Pa = psy.cal_p(altitude_m)
        return P_Pa * 1000.0 # 轉換為 Pa

    def calculate_from_tdb_twb(self, tdb_k, twb_k, altitude_m):
        """
        從乾球、濕球和高度計算濕空氣性質。
        :param tdb_k: 乾球溫度 (SI: K)
        :param twb_k: 濕球溫度 (SI: K)
        :param altitude_m: 海拔高度 (SI: m)
        :return: 包含 *所有* SI 基礎單位 *數值* 的字典
        """
        # 1. 將 SI 單位 (K) 轉換為模型需要的單位 (°C)
        tdb_c = tdb_k - 273.15
        twb_c = twb_k - 273.15

        # 2. 呼叫底層模型 (模型接受 m, °C, °C)
        # 返回：(P_Pa, Pw_Pa, Pws_db, Pws_wd, W, Ws, Wss, RH, h_kj, v)
        P_Pa, Pw_Pa, Pws_db, Pws_wd, W, Ws, Wss, RH, h_kj, v = psy.Calculation_process_m_Tdb_Twb(
            m=altitude_m, T_db=tdb_c, T_wb=twb_c
        )
        
        # 3. 額外計算露點溫度
        tdp_c = psy.cal_Tdp_from_Pw(Pw_Pa)

        # 4. 將模型的輸出 (kPa, °C, kJ/kg...) 轉換為 SI 基礎單位 (Pa, K, J/kg...)
        return {
            # --- 主要性質 ---
            'Altitude': altitude_m,       # m
            'P': P_Pa ,                   # Pa
            'Tdb': tdb_k,                 # K
            'Twb': twb_k,                 # K
            'Tdp': tdp_c + 273.15,        # K
            'RH': RH,                     # % (RH 是比例，非單位)
            'W': W,                       # kg/kg (模型已是 SI)
            'H': h_kj * 1000.0,           # J/kg
            'V': v,                       # m³/kg (模型已是 SI)
            # --- 中間過程壓力值 ---
            'Pw': Pw_Pa ,                  # Pa
            'Pws_db': Pws_db ,     # Pa
            'Pws_wd': Pws_wd ,     # Pa
            # --- 中間過程濕度比 ---
            'Ws': Ws,                     # kg/kg
            'Wss': Wss,                   # kg/kg
        }

    def calculate_from_tdb_rh(self, tdb_k, rh, altitude_m):
        """
        從乾球、相對濕度和高度計算濕空氣性質。
        :param tdb_k: 乾球溫度 (SI: K)
        :param rh: 相對濕度 (SI: %)
        :param altitude_m: 海拔高度 (SI: m)
        :return: 包含 *所有* SI 基礎單位 *數值* 的字典
        """
        # 1. 將 SI 單位 (K) 轉換為模型需要的單位 (°C)
        tdb_c = tdb_k - 273.15
        
        # 2. 呼叫底層模型 (模型接受 m, °C, %)
        # 返回：(twb_c, P_Pa, Pw_Pa, Pws_db, Pws_wd, W, Ws, Wss, _, h_kj, v)
        twb_c, P_Pa, Pw_Pa, Pws_db, Pws_wd, W, Ws, Wss, _, h_kj, v = psy.Calculation_process_m_Tdb_RH(
            m=altitude_m, T_db=tdb_c, RH=rh
        )

        # 3. 額外計算露點溫度
        tdp_c = psy.cal_Tdp_from_Pw(Pw_Pa)

        # 4. 將模型的輸出 (kPa, °C, kJ/kg...) 轉換為 SI 基礎單位 (Pa, K, J/kg...)
        return {
            # --- 主要性質 ---
            'Altitude': altitude_m,           # m
            'P': P_Pa ,                   # Pa
            'Tdb': tdb_k,                 # K
            'Twb': twb_c + 273.15,        # K
            'Tdp': tdp_c + 273.15,        # K
            'RH': rh,                     # %
            'W': W,                       # kg/kg
            'H': h_kj * 1000.0,           # J/kg
            'V': v,                       # m³/kg
            # --- 中間過程壓力值 ---
            'Pw': Pw_Pa,                   # Pa
            'Pws_db': Pws_db ,     # Pa
            'Pws_wd': Pws_wd ,     # Pa
            # --- 中間過程濕度比 ---
            'Ws': Ws,                     # kg/kg
            'Wss': Wss,                   # kg/kg
        }