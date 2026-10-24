"""Live Open-Meteo weather evidence provider."""

import asyncio
import random
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from fieldsat.domain.errors import SourceUnavailableError
from fieldsat.domain.evidence import WeatherEvidence, WeatherHour
from fieldsat.domain.fields import AUTO_TIME_ZONE, RegisteredField
from fieldsat.domain.geometry import centroid
from fieldsat.providers.http_retry import Jitter, Sleep, log_provider_event, request_with_retry

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object.")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array.")
    return value


def _number(value: object, label: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be numeric.")
    return float(value)


def _time_zone(name: object, label: str) -> ZoneInfo:
    if not isinstance(name, str) or not name:
        raise ValueError(f"{label} must be a time zone name.")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"{label} is not a known time zone.") from error


def _local_timestamp(value: object, time_zone: ZoneInfo, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 string.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO-8601 string.") from error
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=time_zone)
    return parsed.astimezone(time_zone)


class OpenMeteoWeatherProvider:
    """Fetch hourly rainfall and humidity for a field centroid from Open-Meteo."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] = _utc_now,
        retry_sleep: Sleep = asyncio.sleep,
        retry_jitter: Jitter = random.random,
    ) -> None:
        self._client = client
        self._clock = clock
        self._retry_sleep = retry_sleep
        self._retry_jitter = retry_jitter

    async def _get(
        self,
        params: Mapping[str, str | int | float | bool | None],
        correlation_id: str,
    ) -> httpx.Response:
        async def operation() -> httpx.Response:
            if self._client is not None:
                return await self._client.get(OPEN_METEO_FORECAST_URL, params=params)
            async with httpx.AsyncClient(timeout=20.0) as client:
                return await client.get(OPEN_METEO_FORECAST_URL, params=params)

        return await request_with_retry(
            operation,
            provider="open-meteo",
            correlation_id=correlation_id,
            sleep=self._retry_sleep,
            jitter=self._retry_jitter,
        )

    async def get_daily_context(
        self, field: RegisteredField, historical_days: int, forecast_days: int
    ) -> WeatherEvidence:
        correlation_id = uuid4().hex
        started_at = time.monotonic()
        longitude, latitude = centroid(field.geometry)
        requested_history = max(7, historical_days)
        # Open-Meteo counts forecast days from its own current date, which can be a day behind
        # the field's local date (00:00-05:30 in Colombo). One extra day keeps 48 hours covered.
        requested_forecast = max(3, forecast_days) + 1
        params: dict[str, str | int | float | bool | None] = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "precipitation,relative_humidity_2m",
            "past_days": requested_history,
            "forecast_days": requested_forecast,
            "precipitation_unit": "mm",
            "timezone": field.time_zone,
        }

        try:
            response = await self._get(params, correlation_id)
            response.raise_for_status()
            payload: object = response.json()
            # With "auto", Open-Meteo picks the time zone from the coordinates and names it.
            time_zone = _time_zone(
                _mapping(payload, "response").get("timezone")
                if field.time_zone == AUTO_TIME_ZONE
                else field.time_zone,
                "timezone",
            )
            hours = self._parse_hours(payload, time_zone)
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise SourceUnavailableError(
                "weather", "Open-Meteo did not return valid hourly weather data."
            ) from error

        now = self._clock()
        if now.tzinfo is None:
            raise SourceUnavailableError("weather", "The provider clock must be timezone-aware.")
        as_of = now.astimezone(time_zone).replace(minute=0, second=0, microsecond=0)
        by_timestamp = {hour.timestamp: hour for hour in hours}
        if len(by_timestamp) != len(hours):
            raise SourceUnavailableError("weather", "Open-Meteo returned duplicate hourly records.")

        history_start = (as_of - timedelta(days=6)).replace(hour=0)
        required_history = self._hourly_range(history_start, as_of)
        required_forecast = self._hourly_range(
            as_of + timedelta(hours=1), as_of + timedelta(hours=48)
        )
        missing_history = required_history.difference(by_timestamp)
        missing_forecast = required_forecast.difference(by_timestamp)
        if missing_history or missing_forecast:
            raise SourceUnavailableError(
                "weather", "Open-Meteo returned an incomplete seven-day or 48-hour window."
            )

        history = tuple(by_timestamp[timestamp] for timestamp in sorted(required_history))
        forecast = tuple(by_timestamp[timestamp] for timestamp in sorted(required_forecast))
        evidence = WeatherEvidence(
            source="Open-Meteo",
            as_of=as_of,
            history=history,
            forecast=forecast,
        )
        log_provider_event(
            "provider_request_complete",
            provider="open-meteo",
            correlation_id=correlation_id,
            field_id=field.id,
            time_range=f"{history[0].timestamp.isoformat()}/{forecast[-1].timestamp.isoformat()}",
            status_class="2xx",
            duration_ms=round((time.monotonic() - started_at) * 1000),
            observation_count=len(history) + len(forecast),
        )
        return evidence

    @staticmethod
    def _hourly_range(start: datetime, end: datetime) -> set[datetime]:
        count = int((end - start).total_seconds() // 3600)
        return {start + timedelta(hours=offset) for offset in range(count + 1)}

    @staticmethod
    def _parse_hours(payload: object, time_zone: ZoneInfo) -> tuple[WeatherHour, ...]:
        root = _mapping(payload, "response")
        hourly = _mapping(root.get("hourly"), "hourly")
        timestamps = _sequence(hourly.get("time"), "hourly.time")
        rainfall = _sequence(hourly.get("precipitation"), "hourly.precipitation")
        humidity = _sequence(hourly.get("relative_humidity_2m"), "hourly.relative_humidity_2m")
        if not (len(timestamps) == len(rainfall) == len(humidity)):
            raise ValueError("Open-Meteo hourly arrays must have equal lengths.")

        result: list[WeatherHour] = []
        for index, (timestamp_value, rainfall_value, humidity_value) in enumerate(
            zip(timestamps, rainfall, humidity, strict=True)
        ):
            timestamp = _local_timestamp(timestamp_value, time_zone, f"hourly.time[{index}]")
            rain = _number(rainfall_value, f"hourly.precipitation[{index}]")
            relative_humidity = _number(
                humidity_value, f"hourly.relative_humidity_2m[{index}]", optional=True
            )
            if rain is None:
                raise ValueError("Hourly precipitation cannot be null.")
            if rain < 0:
                raise ValueError("Hourly precipitation cannot be negative.")
            if relative_humidity is not None and not 0 <= relative_humidity <= 100:
                raise ValueError("Hourly relative humidity must be between 0 and 100.")
            result.append(WeatherHour(timestamp, rain, relative_humidity))
        return tuple(result)
