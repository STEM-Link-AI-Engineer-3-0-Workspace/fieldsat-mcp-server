"""Deterministic providers and fields for tests and for the offline demo mode.

The demo mode (`--demo`) serves these numbers instead of calling Copernicus and
Open-Meteo, so the server runs without credentials or network. It also adds four
verification fields that misbehave on purpose, for the resilience block.
"""

import asyncio
from datetime import datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fieldsat.domain.area_search import LAND_COVER_CLASSES
from fieldsat.domain.errors import SourceUnavailableError
from fieldsat.domain.evidence import (
    LandCoverEvidence,
    Place,
    SatelliteEvidence,
    SatellitePeriodEvidence,
    WeatherEvidence,
    WeatherHour,
)
from fieldsat.domain.fields import REGISTERED_FIELDS, RegisteredField, normalize_field_id
from fieldsat.domain.geometry import PolygonGeometry, centroid, polygon

type FixtureProfile = Literal[
    "canonical",
    "poor_quality",
    "satellite_unavailable",
    "weather_unavailable",
    "slow",
]

# Seconds the "slow" verification field waits before answering.
SLOW_FIELD_DELAY_SECONDS = 20.0

_PROFILE_BY_FIELD_ID: dict[str, FixtureProfile] = {
    "SL-PADDY-MINNERIYA": "canonical",
    "SL-PADDY-POOR": "poor_quality",
    "SL-PADDY-SAT-FAIL": "satellite_unavailable",
    "SL-PADDY-WEATHER-FAIL": "weather_unavailable",
    "SL-PADDY-SLOW": "slow",
}

_PRODUCTION_IDS = {field.id for field in REGISTERED_FIELDS}

TEST_REGISTERED_FIELDS: tuple[RegisteredField, ...] = (
    RegisteredField(
        id="SL-PADDY-MINNERIYA",
        name="Minneriya Paddy Fields",
        crop="paddy",
        time_zone="Asia/Colombo",
        geometry=polygon(
            (80.910, 8.050),
            (80.950, 8.050),
            (80.950, 8.020),
            (80.910, 8.020),
            (80.910, 8.050),
        ),
    ),
    RegisteredField(
        id="SL-PADDY-POOR",
        name="Poor-quality verification field",
        crop="paddy",
        time_zone="Asia/Colombo",
        geometry=polygon(
            (80.4050, 7.4862),
            (80.4060, 7.4862),
            (80.4060, 7.4872),
            (80.4050, 7.4872),
            (80.4050, 7.4862),
        ),
    ),
    RegisteredField(
        id="SL-PADDY-SAT-FAIL",
        name="Satellite-failure verification field",
        crop="paddy",
        time_zone="Asia/Colombo",
        geometry=polygon(
            (80.4070, 7.4862),
            (80.4080, 7.4862),
            (80.4080, 7.4872),
            (80.4070, 7.4872),
            (80.4070, 7.4862),
        ),
    ),
    RegisteredField(
        id="SL-PADDY-WEATHER-FAIL",
        name="Weather-failure verification field",
        crop="paddy",
        time_zone="Asia/Colombo",
        geometry=polygon(
            (80.4090, 7.4862),
            (80.4100, 7.4862),
            (80.4100, 7.4872),
            (80.4090, 7.4872),
            (80.4090, 7.4862),
        ),
    ),
    RegisteredField(
        id="SL-PADDY-SLOW",
        name="Slow-provider verification field",
        crop="paddy",
        time_zone="Asia/Colombo",
        geometry=polygon(
            (80.4110, 7.4862),
            (80.4120, 7.4862),
            (80.4120, 7.4872),
            (80.4110, 7.4872),
            (80.4110, 7.4862),
        ),
    ),
)


def demo_fields(fields: tuple[RegisteredField, ...]) -> tuple[RegisteredField, ...]:
    """The given fields plus the verification fields whose IDs they do not already use."""
    ids = {field.id for field in fields}
    return (
        *fields,
        *(field for field in TEST_REGISTERED_FIELDS if field.id not in _PRODUCTION_IDS | ids),
    )


# Demo mode knows the four real zones plus the verification fields.
DEMO_FIELDS: tuple[RegisteredField, ...] = demo_fields(REGISTERED_FIELDS)


def find_test_field(field_id: str) -> RegisteredField | None:
    normalized = normalize_field_id(field_id)
    return next((field for field in TEST_REGISTERED_FIELDS if field.id == normalized), None)


def find_demo_field(field_id: str) -> RegisteredField | None:
    normalized = normalize_field_id(field_id)
    return next((field for field in DEMO_FIELDS if field.id == normalized), None)


CANONICAL_SATELLITE = SatelliteEvidence(
    source="sentinel-2-l2a-fixture",
    current=SatellitePeriodEvidence(mean_ndvi=0.56, ndvi_standard_deviation=0.17),
    previous=SatellitePeriodEvidence(mean_ndvi=0.66, ndvi_standard_deviation=0.14),
    valid_observations=4,
    average_cloud_coverage_percentage=11,
    usable_pixel_percentage=92,
    periods_comparable=True,
)

POOR_QUALITY_SATELLITE = SatelliteEvidence(
    source="sentinel-2-l2a-fixture",
    current=SatellitePeriodEvidence(mean_ndvi=0.52, ndvi_standard_deviation=0.08),
    previous=SatellitePeriodEvidence(mean_ndvi=0.61, ndvi_standard_deviation=0.07),
    valid_observations=1,
    average_cloud_coverage_percentage=74,
    usable_pixel_percentage=31,
    periods_comparable=False,
)

# Other production zones get their own plausible demo numbers.
_DEMO_SATELLITE_BY_FIELD_ID: dict[str, SatelliteEvidence] = {
    "SL-PADDY-SAMMANTHURAI": SatelliteEvidence(
        source="sentinel-2-l2a-fixture",
        current=SatellitePeriodEvidence(mean_ndvi=0.71, ndvi_standard_deviation=0.06),
        previous=SatellitePeriodEvidence(mean_ndvi=0.69, ndvi_standard_deviation=0.06),
        valid_observations=5,
        average_cloud_coverage_percentage=8,
        usable_pixel_percentage=95,
        periods_comparable=True,
    ),
    "SL-PADDY-KALA-WEWA": SatelliteEvidence(
        source="sentinel-2-l2a-fixture",
        current=SatellitePeriodEvidence(mean_ndvi=0.48, ndvi_standard_deviation=0.08),
        previous=SatellitePeriodEvidence(mean_ndvi=0.53, ndvi_standard_deviation=0.07),
        valid_observations=3,
        average_cloud_coverage_percentage=28,
        usable_pixel_percentage=72,
        periods_comparable=True,
    ),
    "SL-TEA-PEDRO": SatelliteEvidence(
        source="sentinel-2-l2a-fixture",
        current=SatellitePeriodEvidence(mean_ndvi=0.78, ndvi_standard_deviation=0.05),
        previous=SatellitePeriodEvidence(mean_ndvi=0.70, ndvi_standard_deviation=0.05),
        valid_observations=2,
        average_cloud_coverage_percentage=45,
        usable_pixel_percentage=55,
        periods_comparable=True,
    ),
}

_AS_OF = datetime(2026, 7, 14, 10, tzinfo=ZoneInfo("Asia/Colombo"))
_DAILY_RAINFALL = (16.0, 22.0, 0.0, 18.0, 24.0, 32.0, 0.0)


def _weather_history() -> tuple[WeatherHour, ...]:
    start_date = _AS_OF.date() - timedelta(days=6)
    hours: list[WeatherHour] = []
    cursor = datetime.combine(start_date, time(), tzinfo=_AS_OF.tzinfo)
    while cursor <= _AS_OF:
        day_offset = (_AS_OF.date() - cursor.date()).days
        rainfall = _DAILY_RAINFALL[day_offset] if cursor.hour == 9 else 0.0
        hours.append(WeatherHour(cursor, rainfall, 88.0))
        cursor += timedelta(hours=1)
    return tuple(hours)


def _weather_forecast() -> tuple[WeatherHour, ...]:
    return tuple(
        WeatherHour(
            timestamp=_AS_OF + timedelta(hours=offset),
            rainfall_mm=22.0 if offset == 1 else 24.0 if offset == 25 else 0.0,
            relative_humidity_percentage=89.0,
        )
        for offset in range(1, 49)
    )


CANONICAL_WEATHER = WeatherEvidence(
    source="deterministic-weather-fixture",
    as_of=_AS_OF,
    history=_weather_history(),
    forecast=_weather_forecast(),
)


class FixtureSatelliteProvider:
    async def get_period_summary(
        self, field: RegisteredField, comparison_days: int
    ) -> SatelliteEvidence:
        del comparison_days
        profile = _PROFILE_BY_FIELD_ID.get(field.id, "canonical")
        if profile == "satellite_unavailable":
            raise SourceUnavailableError(
                "satellite", "the verification fixture simulates a provider timeout"
            )
        if profile == "slow":
            await asyncio.sleep(SLOW_FIELD_DELAY_SECONDS)
        if profile == "poor_quality":
            return POOR_QUALITY_SATELLITE
        return _DEMO_SATELLITE_BY_FIELD_ID.get(field.id, CANONICAL_SATELLITE)


class FixtureWeatherProvider:
    async def get_daily_context(
        self, field: RegisteredField, historical_days: int, forecast_days: int
    ) -> WeatherEvidence:
        del historical_days, forecast_days
        if _PROFILE_BY_FIELD_ID.get(field.id) == "weather_unavailable":
            raise SourceUnavailableError(
                "weather", "the verification fixture simulates a provider timeout"
            )
        return CANONICAL_WEATHER


def _land_cover(**percentages: float) -> LandCoverEvidence:
    values = {name: value for value, name in LAND_COVER_CLASSES.items()}
    return LandCoverEvidence(
        source="land-cover-fixture",
        map_year=2020,
        class_fractions={values[name]: share / 100 for name, share in percentages.items()},
        classified_pixel_percentage=99.0,
    )


# The demo gazetteer: each place comes with the land cover every square around it reports.
# Colombo is mostly built-up, so searching it for paddy shows NO_MATCHING_LAND_COVER.
_DEMO_PLACES: tuple[tuple[Place, LandCoverEvidence], ...] = (
    (
        Place(
            "Minneriya", 8.04652, 80.90251, "Asia/Colombo", "North Central Province", "Sri Lanka"
        ),
        _land_cover(cropland=68, herbaceous_wetland=9, tree_cover=15, built_up=5, grassland=3),
    ),
    (
        Place("Ampara", 7.29754, 81.68202, "Asia/Colombo", "Eastern Province", "Sri Lanka"),
        _land_cover(cropland=74, tree_cover=10, built_up=9, permanent_water_bodies=7),
    ),
    (
        Place("Nuwara Eliya", 6.97078, 80.78286, "Asia/Colombo", "Central Province", "Sri Lanka"),
        _land_cover(tree_cover=48, shrubland=21, cropland=12, built_up=14, grassland=5),
    ),
    (
        Place("Colombo", 6.93548, 79.84868, "Asia/Colombo", "Western Province", "Sri Lanka"),
        _land_cover(built_up=82, tree_cover=10, permanent_water_bodies=8),
    ),
)


class FixturePlaceSearchProvider:
    async def search_places(
        self, name: str, country_code: str | None, count: int
    ) -> tuple[Place, ...]:
        query = name.casefold()
        matches = tuple(
            place
            for place, _land_cover in _DEMO_PLACES
            if query in place.name.casefold() and country_code in (None, "", "LK", "lk")
        )
        return matches[:count]


class FixtureLandCoverProvider:
    async def get_land_cover(self, geometry: PolygonGeometry) -> LandCoverEvidence:
        longitude, latitude = centroid(geometry)
        _place, land_cover = min(
            _DEMO_PLACES,
            key=lambda entry: (
                (entry[0].latitude - latitude) ** 2 + (entry[0].longitude - longitude) ** 2
            ),
        )
        return land_cover


FIXTURE_SATELLITE_PROVIDER = FixtureSatelliteProvider()
FIXTURE_WEATHER_PROVIDER = FixtureWeatherProvider()
FIXTURE_PLACE_SEARCH_PROVIDER = FixturePlaceSearchProvider()
FIXTURE_LAND_COVER_PROVIDER = FixtureLandCoverProvider()
