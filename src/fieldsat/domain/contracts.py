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
    provider_notes: str | None = None


class WeatherContext(StrictContract):
    rainfall_last_7_days_mm: float
    rainy_days_last_7_days: int
    rainfall_last_48_hours_mm: float | None = None
    rainfall_forecast_next_48_hours_mm: float
    average_humidity_last_7_days: float | None = None
    heavy_rain_recent: bool | None = None
    heavy_rain_expected: bool
