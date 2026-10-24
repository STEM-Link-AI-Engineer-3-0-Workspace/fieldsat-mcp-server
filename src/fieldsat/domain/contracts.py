"""Frozen AgriVibe evidence contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictContract(BaseModel):
    """Base model that forbids fields outside the frozen application contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SatelliteContext(StrictContract):
    field_id: str
    current_mean_ndvi: float
    previous_mean_ndvi: float
    ndvi_change_percentage: float
    trend: Literal[
        "significant_decline",
        "moderate_decline",
        "stable",
        "moderate_increase",
        "significant_increase",
    ]
    ndvi_standard_deviation: float
    field_uniformity: Literal["uniform", "moderately_variable", "uneven"]
    valid_observations: int
    average_cloud_coverage_percentage: float
    data_quality: Literal["good", "moderate", "poor"]


class WeatherContext(StrictContract):
    rainfall_last_7_days_mm: float
    rainy_days_last_7_days: int
    rainfall_last_48_hours_mm: float | None = None
    rainfall_forecast_next_48_hours_mm: float
    average_humidity_last_7_days: float | None = None
    heavy_rain_recent: bool | None = None
    heavy_rain_expected: bool


class LandCoverShare(StrictContract):
    land_cover: str
    percentage: float


class AreaSearchResult(StrictContract):
    field_id: str
    place: str
    crop: Literal["paddy", "tea"]
    latitude: float
    longitude: float
    area_size_m: int
    area_hectares: float
    matching_land_cover_percentage: float
    matching_land_cover_classes: list[str]
    land_cover: list[LandCoverShare]
    land_cover_source: str
    candidates_checked: int
    other_places: list[str]
