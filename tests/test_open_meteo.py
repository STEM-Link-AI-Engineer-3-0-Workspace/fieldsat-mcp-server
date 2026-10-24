"""Live Open-Meteo provider contract tests with mocked HTTP responses."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from fieldsat.domain.errors import SourceUnavailableError
from fieldsat.domain.evidence import Place
from fieldsat.domain.fields import RegisteredField, find_registered_field
from fieldsat.domain.weather import get_weather_context
from fieldsat.providers.open_meteo import (
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_GEOCODING_URL,
    OpenMeteoPlaceSearchProvider,
    OpenMeteoWeatherProvider,
)

NOW = datetime(2026, 7, 14, 4, 30, tzinfo=UTC)
LOCAL_NOW = NOW.astimezone(ZoneInfo("Asia/Colombo")).replace(minute=0)


def registered_field() -> RegisteredField:
    result = find_registered_field("SL-PADDY-MINNERIYA")
    if result is None:
        raise AssertionError("Missing production field.")
    return result


def weather_payload(
    *,
    start: datetime = LOCAL_NOW - timedelta(days=7),
    end: datetime = LOCAL_NOW + timedelta(days=3),
    rainfall_for: Callable[[datetime], float] = lambda _timestamp: 1.0,
) -> dict[str, Any]:
    count = int((end - start).total_seconds() // 3600)
    timestamps = [start + timedelta(hours=offset) for offset in range(count + 1)]
    return {
        "hourly": {
            "time": [
                timestamp.replace(tzinfo=None).isoformat(timespec="minutes")
                for timestamp in timestamps
            ],
            "precipitation": [rainfall_for(timestamp) for timestamp in timestamps],
            "relative_humidity_2m": [82.0 for _timestamp in timestamps],
        }
    }


@pytest.mark.asyncio
async def test_fetches_fixed_open_meteo_windows_and_aggregates_weather() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json=weather_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoWeatherProvider(client=client, clock=lambda: NOW)
        result = await get_weather_context(registered_field(), 1, 1, provider)

    assert result.rainfall_last_48_hours_mm == 48.0
    assert result.rainfall_forecast_next_48_hours_mm == 48.0
    assert result.rainy_days_last_7_days == 7
    assert result.average_humidity_last_7_days == 82.0
    assert captured_request is not None
    assert str(captured_request.url).startswith(OPEN_METEO_FORECAST_URL)
    assert captured_request.url.params["hourly"] == "precipitation,relative_humidity_2m"
    assert captured_request.url.params["past_days"] == "7"
    assert captured_request.url.params["forecast_days"] == "4"
    assert captured_request.url.params["timezone"] == "Asia/Colombo"
    assert float(captured_request.url.params["latitude"]) == pytest.approx(8.035)
    assert float(captured_request.url.params["longitude"]) == pytest.approx(80.930)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"reason": "unavailable"}),
        httpx.Response(200, json={"hourly": {"time": [], "precipitation": []}}),
        httpx.Response(
            200,
            json={
                "hourly": {
                    "time": ["2026-07-14T09:00"],
                    "precipitation": [None],
                    "relative_humidity_2m": [80],
                }
            },
        ),
    ],
)
async def test_rejects_http_and_schema_failures(response: httpx.Response) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: response)
    ) as client:
        provider = OpenMeteoWeatherProvider(client=client, clock=lambda: NOW)
        with pytest.raises(SourceUnavailableError, match="valid hourly weather data"):
            await provider.get_daily_context(registered_field(), 7, 3)


@pytest.mark.asyncio
async def test_rejects_incomplete_required_window() -> None:
    payload = weather_payload(start=LOCAL_NOW - timedelta(hours=47))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    ) as client:
        provider = OpenMeteoWeatherProvider(client=client, clock=lambda: NOW)
        with pytest.raises(SourceUnavailableError, match="incomplete seven-day"):
            await provider.get_daily_context(registered_field(), 7, 3)


@pytest.mark.asyncio
async def test_allows_missing_optional_humidity() -> None:
    payload = weather_payload()
    payload["hourly"]["relative_humidity_2m"] = [None for _timestamp in payload["hourly"]["time"]]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    ) as client:
        provider = OpenMeteoWeatherProvider(client=client, clock=lambda: NOW)
        result = await get_weather_context(registered_field(), 7, 3, provider)

    assert result.average_humidity_last_7_days is None


@pytest.mark.asyncio
async def test_auto_time_zone_uses_the_zone_open_meteo_names() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={**weather_payload(), "timezone": "Asia/Colombo"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoWeatherProvider(client=client, clock=lambda: NOW)
        field = replace(registered_field(), time_zone="auto")
        result = await get_weather_context(field, 1, 1, provider)

    assert captured_request is not None
    assert captured_request.url.params["timezone"] == "auto"
    assert result.rainfall_forecast_next_48_hours_mm == 48.0


@pytest.mark.asyncio
async def test_auto_time_zone_without_a_zone_in_the_response_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=weather_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoWeatherProvider(client=client, clock=lambda: NOW)
        with pytest.raises(SourceUnavailableError):
            await provider.get_daily_context(replace(registered_field(), time_zone="auto"), 7, 3)


@pytest.mark.asyncio
async def test_place_search_parses_geocoder_results() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "Minneriya",
                        "latitude": 8.04652,
                        "longitude": 80.90251,
                        "timezone": "Asia/Colombo",
                        "country": "Sri Lanka",
                        "admin1": "North Central Province",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        places = await OpenMeteoPlaceSearchProvider(client=client).search_places(
            "Minneriya", "lk", 5
        )

    assert places == (
        Place(
            "Minneriya", 8.04652, 80.90251, "Asia/Colombo", "North Central Province", "Sri Lanka"
        ),
    )
    assert captured_request is not None
    assert str(captured_request.url).startswith(OPEN_METEO_GEOCODING_URL)
    assert captured_request.url.params["countryCode"] == "LK"
    assert captured_request.url.params["count"] == "5"


@pytest.mark.asyncio
async def test_place_search_without_results_is_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"generationtime_ms": 0.1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoPlaceSearchProvider(client=client)
        assert await provider.search_places("zzzqqq", None, 5) == ()


@pytest.mark.asyncio
async def test_place_search_errors_are_reported_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoPlaceSearchProvider(client=client)
        with pytest.raises(SourceUnavailableError) as error:
            await provider.search_places("Minneriya", None, 5)
    assert error.value.source == "place_search"
