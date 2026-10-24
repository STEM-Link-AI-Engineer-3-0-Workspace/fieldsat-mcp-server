"""Copernicus Sentinel-2 provider tests with mocked OAuth and statistics HTTP."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from fieldsat.domain.errors import SourceUnavailableError
from fieldsat.domain.fields import RegisteredField, find_registered_field
from fieldsat.providers.copernicus import (
    COPERNICUS_STATISTICS_URL,
    COPERNICUS_TOKEN_URL,
    LAND_COVER_COLLECTION,
    LAND_COVER_EVALSCRIPT,
    SENTINEL_2_EVALSCRIPT,
    SENTINEL_2_RESOLUTION_DEGREES,
    CopernicusCredentials,
    CopernicusSatelliteProvider,
)

NOW = datetime(2026, 7, 14, 12, tzinfo=UTC)


def registered_field() -> RegisteredField:
    result = find_registered_field("SL-PADDY-MINNERIYA")
    if result is None:
        raise AssertionError("Missing production field.")
    return result


def band_stats(
    *, mean: float | None, stdev: float | None, valid: int, total: int = 100
) -> dict[str, Any]:
    return {
        "bands": {
            "B0": {
                "stats": {
                    "mean": mean,
                    "stDev": stdev,
                    "sampleCount": total,
                    "noDataCount": total - valid,
                }
            }
        }
    }


def statistics_payload(*, empty_period: str | None = None) -> dict[str, Any]:
    starts_at = NOW - timedelta(days=28)
    records: list[dict[str, Any]] = []
    for offset in range(28):
        previous = offset < 14
        empty = empty_period == ("previous" if previous else "current")
        valid = 0 if empty else (80 if previous else (30 if offset == 14 else 90))
        records.append(
            {
                "interval": {
                    "from": (starts_at + timedelta(days=offset)).isoformat().replace("+00:00", "Z"),
                    "to": (starts_at + timedelta(days=offset + 1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                },
                "outputs": {
                    "ndvi": band_stats(
                        mean=None if empty else (0.6 if previous else 0.5),
                        stdev=(
                            None if empty else (0.1 if previous else (0.4 if offset == 14 else 0.2))
                        ),
                        valid=valid,
                    ),
                    "quality": band_stats(
                        mean=0.2 if previous else 0.1,
                        stdev=0.0,
                        valid=100,
                    ),
                },
            }
        )
    return {"data": records, "status": "OK"}


@pytest.mark.asyncio
async def test_fetches_and_aggregates_adjacent_sentinel_periods() -> None:
    token_calls = 0
    statistics_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if str(request.url) == COPERNICUS_TOKEN_URL:
            token_calls += 1
            form = parse_qs(request.content.decode())
            assert form == {
                "grant_type": ["client_credentials"],
                "client_id": ["client-id"],
                "client_secret": ["client-secret"],
            }
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 600})
        assert str(request.url) == COPERNICUS_STATISTICS_URL
        statistics_requests.append(request)
        assert request.headers["Authorization"] == "Bearer access-token"
        return httpx.Response(200, json=statistics_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = CopernicusSatelliteProvider(
            CopernicusCredentials("client-id", "client-secret"),
            client=client,
            clock=lambda: NOW,
            monotonic=lambda: 100.0,
        )
        result = await provider.get_period_summary(registered_field(), 14)
        await provider.get_period_summary(registered_field(), 14)

    assert result.current.mean_ndvi == pytest.approx(0.5)
    assert result.current.ndvi_standard_deviation == pytest.approx(
        ((0.4**2 * 30 + 0.2**2 * 13 * 90) / 1200) ** 0.5
    )
    assert result.previous.mean_ndvi == pytest.approx(0.6)
    assert result.previous.ndvi_standard_deviation == pytest.approx(0.1)
    assert result.valid_observations == 28
    assert result.average_cloud_coverage_percentage == pytest.approx(15.0)
    assert result.usable_pixel_percentage == pytest.approx(100 * 2320 / 2800)
    assert result.periods_comparable is True
    assert token_calls == 1
    assert len(statistics_requests) == 2

    request_payload = json.loads(statistics_requests[0].content)
    assert request_payload["input"]["data"] == [
        {"type": "sentinel-2-l2a", "dataFilter": {"mosaickingOrder": "leastCC"}}
    ]
    assert request_payload["input"]["bounds"]["geometry"]["type"] == "Polygon"
    assert request_payload["aggregation"]["timeRange"] == {
        "from": "2026-06-16T00:00:00Z",
        "to": "2026-07-14T00:00:00Z",
    }
    assert request_payload["aggregation"]["aggregationInterval"] == {"of": "P1D"}
    assert request_payload["aggregation"]["resx"] == SENTINEL_2_RESOLUTION_DEGREES
    assert request_payload["aggregation"]["resy"] == SENTINEL_2_RESOLUTION_DEGREES
    assert request_payload["aggregation"]["evalscript"] == SENTINEL_2_EVALSCRIPT
    assert 'bands: ["ndvi", "quality"]' in SENTINEL_2_EVALSCRIPT
    assert "[0, 1, 3, 8, 9, 10, 11]" in SENTINEL_2_EVALSCRIPT
    assert "samples.SCL === 6" not in SENTINEL_2_EVALSCRIPT


@pytest.mark.asyncio
async def test_aggregation_intervals_are_midnight_aligned_for_morning_clocks() -> None:
    """Interval boundaries between 00:00 UTC and the ~05:10 UTC Sentinel-2
    overpass make the Statistical API bin every acquisition into the preceding
    empty interval, so the payload must always be midnight-aligned."""
    statistics_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == COPERNICUS_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "token", "expires_in": 600})
        statistics_requests.append(request)
        return httpx.Response(200, json=statistics_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = CopernicusSatelliteProvider(
            CopernicusCredentials("id", "secret"),
            client=client,
            clock=lambda: datetime(2026, 7, 17, 3, 53, 19, tzinfo=UTC),
        )
        await provider.get_period_summary(registered_field(), 14)

    request_payload = json.loads(statistics_requests[0].content)
    assert request_payload["aggregation"]["timeRange"] == {
        "from": "2026-06-19T00:00:00Z",
        "to": "2026-07-17T00:00:00Z",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_period", ["previous", "current"])
async def test_fails_when_either_period_has_no_usable_ndvi(empty_period: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == COPERNICUS_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "token", "expires_in": 600})
        return httpx.Response(200, json=statistics_payload(empty_period=empty_period))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = CopernicusSatelliteProvider(
            CopernicusCredentials("id", "secret"), client=client, clock=lambda: NOW
        )
        with pytest.raises(SourceUnavailableError, match=f"{empty_period} period"):
            await provider.get_period_summary(registered_field(), 14)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "statistics_response",
    [
        httpx.Response(401, json={"error": "unauthorized"}),
        httpx.Response(503, json={"error": "unavailable"}),
        httpx.Response(200, json={"data": [{"interval": {}}]}),
    ],
)
async def test_normalizes_statistics_http_and_schema_failures(
    statistics_response: httpx.Response,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == COPERNICUS_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "token", "expires_in": 600})
        return statistics_response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = CopernicusSatelliteProvider(
            CopernicusCredentials("id", "secret"), client=client, clock=lambda: NOW
        )
        with pytest.raises(SourceUnavailableError, match="valid Sentinel-2 statistics"):
            await provider.get_period_summary(registered_field(), 14)


@pytest.mark.asyncio
async def test_normalizes_oauth_failures_without_exposing_credentials() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(401, json={"error": "invalid_client"})
        )
    ) as client:
        provider = CopernicusSatelliteProvider(
            CopernicusCredentials("sensitive-id", "sensitive-secret"),
            client=client,
            clock=lambda: NOW,
        )
        with pytest.raises(SourceUnavailableError) as error:
            await provider.get_period_summary(registered_field(), 14)

    assert "sensitive-id" not in str(error.value)
    assert "sensitive-secret" not in str(error.value)


def test_copernicus_credentials_require_only_the_two_provider_secrets() -> None:
    assert CopernicusCredentials.from_environment(
        {
            "COPERNICUS_CLIENT_ID": " client ",
            "COPERNICUS_CLIENT_SECRET": " secret ",
            "UNRELATED_SETTING": "ignored",
        }
    ) == CopernicusCredentials("client", "secret")
    with pytest.raises(RuntimeError, match="COPERNICUS_CLIENT_ID"):
        CopernicusCredentials.from_environment({})


@pytest.mark.asyncio
async def test_parses_nan_string_statistics_for_fully_masked_days() -> None:
    """The live Statistical API encodes fully masked stats as the string "NaN"."""
    payload = statistics_payload()
    masked_day = payload["data"][20]
    masked_stats = masked_day["outputs"]["ndvi"]["bands"]["B0"]["stats"]
    masked_stats.update({"mean": "NaN", "stDev": "NaN", "noDataCount": 100})

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == COPERNICUS_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "token", "expires_in": 600})
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = CopernicusSatelliteProvider(
            CopernicusCredentials("id", "secret"), client=client, clock=lambda: NOW
        )
        result = await provider.get_period_summary(registered_field(), 14)

    assert result.valid_observations == 27
    assert result.periods_comparable is True


def land_cover_payload(shares: dict[int, float], *, valid: int = 90) -> dict[str, Any]:
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110]
    return {
        "data": [
            {
                "interval": {"from": "2020-01-01T00:00:00Z", "to": "2021-01-01T00:00:00Z"},
                "outputs": {
                    "land_cover": {
                        "bands": {
                            f"B{index}": {
                                "stats": {
                                    "mean": shares.get(value, 0.0),
                                    "stDev": 0.0,
                                    "sampleCount": 100,
                                    "noDataCount": 100 - valid,
                                }
                            }
                            for index, value in enumerate(values)
                        }
                    }
                },
            }
        ],
        "status": "OK",
    }


@pytest.mark.asyncio
async def test_land_cover_requests_the_lcm10_collection_and_reads_class_shares() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == COPERNICUS_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 600})
        requests.append(request)
        return httpx.Response(200, json=land_cover_payload({40: 0.7, 90: 0.3}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = CopernicusSatelliteProvider(
            CopernicusCredentials("client-id", "client-secret"), client=client
        )
        result = await provider.get_land_cover(registered_field().geometry)

    assert result.class_fractions[40] == pytest.approx(0.7)
    assert result.class_fractions[90] == pytest.approx(0.3)
    assert result.class_fractions[10] == 0.0
    assert result.classified_pixel_percentage == pytest.approx(90.0)
    assert result.map_year == 2020
    request_payload = json.loads(requests[0].content)
    assert request_payload["input"]["data"] == [{"type": LAND_COVER_COLLECTION}]
    assert request_payload["aggregation"]["timeRange"] == {
        "from": "2020-01-01T00:00:00Z",
        "to": "2021-01-01T00:00:00Z",
    }
    assert request_payload["aggregation"]["evalscript"] == LAND_COVER_EVALSCRIPT
    assert 'bands: ["LCM10", "dataMask"]' in LAND_COVER_EVALSCRIPT


@pytest.mark.asyncio
async def test_land_cover_failures_are_reported_as_land_cover_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == COPERNICUS_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 600})
        return httpx.Response(200, json={"data": [], "status": "OK"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = CopernicusSatelliteProvider(
            CopernicusCredentials("client-id", "client-secret"), client=client
        )
        with pytest.raises(SourceUnavailableError) as error:
            await provider.get_land_cover(registered_field().geometry)
    assert error.value.source == "land_cover"
