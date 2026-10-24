"""Async provider contracts implemented by live services and test doubles."""

from typing import Protocol

from fieldsat.domain.evidence import LandCoverEvidence, Place, SatelliteEvidence, WeatherEvidence
from fieldsat.domain.fields import RegisteredField
from fieldsat.domain.geometry import PolygonGeometry


class SatelliteEvidenceProvider(Protocol):
    async def get_period_summary(
        self, field: RegisteredField, comparison_days: int
    ) -> SatelliteEvidence: ...


class WeatherEvidenceProvider(Protocol):
    async def get_daily_context(
        self, field: RegisteredField, historical_days: int, forecast_days: int
    ) -> WeatherEvidence: ...


class PlaceSearchProvider(Protocol):
    async def search_places(
        self, name: str, country_code: str | None, count: int
    ) -> tuple[Place, ...]: ...


class LandCoverProvider(Protocol):
    async def get_land_cover(self, geometry: PolygonGeometry) -> LandCoverEvidence: ...
