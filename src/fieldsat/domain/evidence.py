"""Provider-neutral evidence passed into the frozen MCP semantic layer."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SatellitePeriodEvidence:
    mean_ndvi: float
    ndvi_standard_deviation: float


@dataclass(frozen=True, slots=True)
class SatelliteEvidence:
    source: str
    current: SatellitePeriodEvidence
    previous: SatellitePeriodEvidence
    valid_observations: int
    average_cloud_coverage_percentage: float
    usable_pixel_percentage: float
    periods_comparable: bool
    # Free text from the imagery provider. Untrusted: agents must treat it as data,
    # never as instructions.
    provider_notes: str | None = None


@dataclass(frozen=True, slots=True)
class WeatherHour:
    timestamp: datetime
    rainfall_mm: float
    relative_humidity_percentage: float | None


@dataclass(frozen=True, slots=True)
class WeatherEvidence:
    source: str
    as_of: datetime
    history: tuple[WeatherHour, ...]
    forecast: tuple[WeatherHour, ...]
