"""Single adapter boundary around the excluded psychrometric model."""

from __future__ import annotations

from typing import Any

from Flet_ui.PsychrometricChart import PsychrometricChart_01_ASHF_model as legacy_model


class PsychrometricService:
    """Return numeric SI-oriented psychrometric results for all channels."""

    def calculate_pressure_from_altitude(self, altitude_m: float) -> float:
        """Return atmospheric pressure in pascals for an altitude in metres."""
        return legacy_model.cal_p(altitude_m) * 1000.0

    def calculate_from_tdb_twb(
        self,
        tdb_k: float,
        twb_k: float,
        altitude_m: float,
    ) -> dict[str, Any]:
        """Calculate psychrometric properties from dry/wet-bulb temperatures."""
        tdb_c = tdb_k - 273.15
        twb_c = twb_k - 273.15
        pressure, vapor_pressure, pws_db, pws_wb, w, ws, wss, rh, enthalpy, volume = (
            legacy_model.Calculation_process_m_Tdb_Twb(
                m=altitude_m,
                T_db=tdb_c,
                T_wb=twb_c,
            )
        )
        dew_point_c = legacy_model.cal_Tdp_from_Pw(vapor_pressure)
        return self._build_result(
            altitude_m=altitude_m,
            pressure=pressure,
            tdb_k=tdb_k,
            twb_k=twb_k,
            dew_point_k=dew_point_c + 273.15,
            rh=rh,
            w=w,
            enthalpy=enthalpy * 1000.0,
            volume=volume,
            vapor_pressure=vapor_pressure,
            pws_db=pws_db,
            pws_wb=pws_wb,
            ws=ws,
            wss=wss,
        )

    def calculate_from_tdb_rh(
        self,
        tdb_k: float,
        rh: float,
        altitude_m: float,
    ) -> dict[str, Any]:
        """Calculate psychrometric properties from dry-bulb/RH inputs."""
        tdb_c = tdb_k - 273.15
        twb_c, pressure, vapor_pressure, pws_db, pws_wb, w, ws, wss, _, enthalpy, volume = (
            legacy_model.Calculation_process_m_Tdb_RH(
                m=altitude_m,
                T_db=tdb_c,
                RH=rh,
            )
        )
        dew_point_c = legacy_model.cal_Tdp_from_Pw(vapor_pressure)
        return self._build_result(
            altitude_m=altitude_m,
            pressure=pressure,
            tdb_k=tdb_k,
            twb_k=twb_c + 273.15,
            dew_point_k=dew_point_c + 273.15,
            rh=rh,
            w=w,
            enthalpy=enthalpy * 1000.0,
            volume=volume,
            vapor_pressure=vapor_pressure,
            pws_db=pws_db,
            pws_wb=pws_wb,
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
        """Build the stable neutral result shape shared by both channels."""
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
