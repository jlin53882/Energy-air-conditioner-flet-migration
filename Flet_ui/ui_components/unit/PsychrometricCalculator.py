# PsychrometricCalculator.py
# 職責：封裝 shared psychrometric domain service，提供 Flet 相容介面。

from domain.psychrometrics.service import PsychrometricService
from infrastructure.psychrometrics import LegacyPsychrometricModelAdapter


class PsychrometricCalculator:
    """Flet-facing adapter for the shared psychrometric service."""

    def __init__(self, service: PsychrometricService | None = None) -> None:
        """Initialize the adapter with an injectable psychrometric service."""
        self._service = service or PsychrometricService(LegacyPsychrometricModelAdapter())

    def calculate_pressure_from_altitude(self, altitude_m):
        """Return atmospheric pressure in pascals."""
        return self._service.calculate_pressure_from_altitude(altitude_m)

    def calculate_from_tdb_twb(self, tdb_k, twb_k, altitude_m):
        """Return the shared numeric result for dry/wet-bulb inputs."""
        return self._service.calculate_from_tdb_twb(tdb_k, twb_k, altitude_m)

    def calculate_from_tdb_rh(self, tdb_k, rh, altitude_m):
        """Return the shared numeric result for dry-bulb/RH inputs."""
        return self._service.calculate_from_tdb_rh(tdb_k, rh, altitude_m)
