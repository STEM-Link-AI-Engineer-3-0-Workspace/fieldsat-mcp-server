"""Live Copernicus Data Space Sentinel-2 Statistical API provider."""

import asyncio
import math
import os
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx

from fieldsat.domain.area_search import LAND_COVER_CLASSES
from fieldsat.domain.errors import SourceUnavailableError
from fieldsat.domain.evidence import LandCoverEvidence, SatelliteEvidence, SatellitePeriodEvidence
from fieldsat.domain.fields import RegisteredField
from fieldsat.domain.geometry import PolygonGeometry
from fieldsat.providers.http_retry import Jitter, Sleep, log_provider_event, request_with_retry

COPERNICUS_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
COPERNICUS_STATISTICS_URL = "https://sh.dataspace.copernicus.eu/statistics/v1"
WGS84_URI = "http://www.opengis.net/def/crs/EPSG/0/4326"
# resx/resy are expressed in CRS units. The registry CRS is WGS84, so the
# resolution is in degrees: 0.0001 deg is roughly 11 m at Sri Lankan latitudes,
# close to the native 10 m Sentinel-2 B04/B08 resolution and far below the
# collection's 1500 m-per-pixel limit.
SENTINEL_2_RESOLUTION_DEGREES = 0.0001

SENTINEL_2_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B04", "B08", "SCL", "dataMask"]
    }],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "quality", bands: 1, sampleType: "UINT8" },
      { id: "dataMask", bands: ["ndvi", "quality"] }
    ]
  };
}

function evaluatePixel(samples) {
  const denominator = samples.B08 + samples.B04;
  const unusableScl = [0, 1, 3, 8, 9, 10, 11].includes(samples.SCL);
  const validNdvi = samples.dataMask === 1 && !unusableScl && denominator !== 0;
  return {
    ndvi: [validNdvi ? (samples.B08 - samples.B04) / denominator : 0],
    quality: [unusableScl ? 1 : 0],
    dataMask: [validNdvi ? 1 : 0, samples.dataMask]
  };
}
"""

# Copernicus Global Land Cover Map at 10 m, Annual V1 (CLMS LCM10), served on the same
# Sentinel Hub deployment as Sentinel-2. Collection ID from the CDSE data documentation:
# https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/clms/land-cover-and-land-use-mapping/global-dynamic-land-cover/lcm_global_10m_yearly_v1.html
LAND_COVER_COLLECTION = "byoc-828f6b20-8ffd-48f8-a1da-fefd271456db"
LAND_COVER_SOURCE = "Copernicus Global Land Cover Map 10 m (CLMS LCM10)"
# The 2020 base year. The interval covers the whole year, so one statistics record comes back.
LAND_COVER_YEAR = 2020
LAND_COVER_TIME_RANGE = {"from": "2020-01-01T00:00:00Z", "to": "2021-01-01T00:00:00Z"}
LAND_COVER_INTERVAL = "P366D"
LAND_COVER_CLASS_VALUES: tuple[int, ...] = tuple(LAND_COVER_CLASSES)

# One output band per class: 1 where the pixel has that class. The mean of band Bn over the
# area is then the share of classified pixels in class n. 254 (unclassifiable) and 255
# (no data) are masked out, so they never count towards a class.
LAND_COVER_EVALSCRIPT = f"""//VERSION=3
const CLASSES = {list(LAND_COVER_CLASS_VALUES)};

function setup() {{
  return {{
    input: [{{ bands: ["LCM10", "dataMask"] }}],
    output: [
      {{ id: "land_cover", bands: CLASSES.length, sampleType: "UINT8" }},
      {{ id: "dataMask", bands: 1 }}
    ]
  }};
}}

function evaluatePixel(samples) {{
  const classified = samples.dataMask === 1 && CLASSES.includes(samples.LCM10);
  return {{
    land_cover: CLASSES.map((value) => (samples.LCM10 === value ? 1 : 0)),
    dataMask: [classified ? 1 : 0]
  }};
}}
"""


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


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string.")
    return value


def _number(value: object, label: str, *, optional: bool = False) -> float | None:
    if optional and (value is None or value == "NaN"):
        # The Statistical API encodes statistics for fully masked intervals as
        # the JSON string "NaN" rather than null.
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite.")
    return result


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer.")
    return value


def _timestamp(value: object, label: str) -> datetime:
    raw = _string(value, label)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO-8601 timestamp.") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a UTC offset.")
    return parsed.astimezone(UTC)


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class CopernicusCredentials:
    client_id: str
    client_secret: str

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "CopernicusCredentials":
        values = os.environ if environment is None else environment
        client_id = values.get("COPERNICUS_CLIENT_ID", "").strip()
        client_secret = values.get("COPERNICUS_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise RuntimeError("COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET are required.")
        return cls(client_id=client_id, client_secret=client_secret)


@dataclass(frozen=True, slots=True)
class _BandStats:
    mean: float | None
    standard_deviation: float | None
    sample_count: int
    no_data_count: int

    @property
    def valid_count(self) -> int:
        return self.sample_count - self.no_data_count


@dataclass(frozen=True, slots=True)
class _DailyStats:
    starts_at: datetime
    ndvi: _BandStats
    quality: _BandStats


@dataclass(frozen=True, slots=True)
class _CachedToken:
    value: str
    expires_at: float


class CopernicusSatelliteProvider:
    """Fetch and aggregate daily Sentinel-2 L2A field statistics."""

    def __init__(
        self,
        credentials: CopernicusCredentials,
        *,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        retry_sleep: Sleep = asyncio.sleep,
        retry_jitter: Jitter = random.random,
    ) -> None:
        self._credentials = credentials
        self._client = client
        self._clock = clock
        self._monotonic = monotonic
        self._retry_sleep = retry_sleep
        self._retry_jitter = retry_jitter
        self._token: _CachedToken | None = None
        self._token_lock = asyncio.Lock()

    async def _post_token(self, correlation_id: str) -> httpx.Response:
        data = {
            "grant_type": "client_credentials",
            "client_id": self._credentials.client_id,
            "client_secret": self._credentials.client_secret,
        }

        async def operation() -> httpx.Response:
            if self._client is not None:
                return await self._client.post(COPERNICUS_TOKEN_URL, data=data)
            async with httpx.AsyncClient(timeout=20.0) as client:
                return await client.post(COPERNICUS_TOKEN_URL, data=data)

        return await request_with_retry(
            operation,
            provider="copernicus-oauth",
            correlation_id=correlation_id,
            sleep=self._retry_sleep,
            jitter=self._retry_jitter,
        )

    async def _access_token(self, correlation_id: str) -> str:
        async with self._token_lock:
            now = self._monotonic()
            if self._token is not None and now < self._token.expires_at:
                return self._token.value

            response = await self._post_token(correlation_id)
            response.raise_for_status()
            payload: object = response.json()
            root = _mapping(payload, "OAuth response")
            access_token = _string(root.get("access_token"), "access_token")
            expires_in_value = _number(root.get("expires_in"), "expires_in")
            if expires_in_value is None or expires_in_value <= 0:
                raise ValueError("expires_in must be positive.")
            refresh_margin = min(60.0, expires_in_value / 10)
            self._token = _CachedToken(
                value=access_token,
                expires_at=now + expires_in_value - refresh_margin,
            )
            return access_token

    async def _post_statistics(
        self, access_token: str, payload: Mapping[str, object], correlation_id: str
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        async def operation() -> httpx.Response:
            if self._client is not None:
                return await self._client.post(
                    COPERNICUS_STATISTICS_URL, headers=headers, json=payload
                )
            async with httpx.AsyncClient(timeout=30.0) as client:
                return await client.post(COPERNICUS_STATISTICS_URL, headers=headers, json=payload)

        return await request_with_retry(
            operation,
            provider="copernicus-statistics",
            correlation_id=correlation_id,
            sleep=self._retry_sleep,
            jitter=self._retry_jitter,
        )

    async def get_period_summary(
        self, field: RegisteredField, comparison_days: int
    ) -> SatelliteEvidence:
        if comparison_days < 1:
            raise ValueError("comparison_days must be a positive integer.")
        correlation_id = uuid4().hex
        started_at = self._monotonic()
        now = self._clock()
        if now.tzinfo is None:
            raise SourceUnavailableError("satellite", "The provider clock must be timezone-aware.")
        # Interval boundaries must stay midnight-aligned: the Statistical API
        # assigns each acquisition to the daily interval containing midnight of
        # its acquisition date but mosaics with the exact interval timestamps,
        # so boundaries between 00:00 UTC and the ~05:10 UTC Sentinel-2
        # overpass put every acquisition into the preceding empty interval and
        # all statistics come back as NaN.
        period_end = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        current_start = period_end - timedelta(days=comparison_days)
        combined_start = current_start - timedelta(days=comparison_days)
        request_payload = self._request_payload(field, combined_start, period_end)

        try:
            access_token = await self._access_token(correlation_id)
            response = await self._post_statistics(access_token, request_payload, correlation_id)
            response.raise_for_status()
            payload: object = response.json()
            days = self._parse_response(payload)
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise SourceUnavailableError(
                "satellite", "Copernicus did not return valid Sentinel-2 statistics."
            ) from error

        previous_days = tuple(day for day in days if day.starts_at < current_start)
        current_days = tuple(day for day in days if current_start <= day.starts_at < period_end)
        previous = self._aggregate_period(previous_days, "previous")
        current = self._aggregate_period(current_days, "current")
        if previous.mean_ndvi == 0:
            raise SourceUnavailableError(
                "satellite", "Previous-period NDVI is zero, so relative change is undefined."
            )

        usable_days = tuple(day for day in days if day.ndvi.valid_count > 0)
        source_pixel_count = sum(day.quality.valid_count for day in days)
        clear_pixel_count = sum(day.ndvi.valid_count for day in days)
        if source_pixel_count <= 0:
            raise SourceUnavailableError(
                "satellite", "Copernicus returned no source pixels for the field."
            )
        quality_weighted_sum = sum(
            (day.quality.mean or 0.0) * day.quality.valid_count
            for day in days
            if day.quality.valid_count > 0
        )

        evidence = SatelliteEvidence(
            source="Copernicus Sentinel-2 L2A Statistical API",
            current=current,
            previous=previous,
            valid_observations=len(usable_days),
            average_cloud_coverage_percentage=(100 * quality_weighted_sum / source_pixel_count),
            usable_pixel_percentage=100 * clear_pixel_count / source_pixel_count,
            periods_comparable=True,
        )
        log_provider_event(
            "provider_request_complete",
            provider="copernicus-statistics",
            correlation_id=correlation_id,
            field_id=field.id,
            time_range=f"{_isoformat_utc(combined_start)}/{_isoformat_utc(period_end)}",
            status_class="2xx",
            duration_ms=round((self._monotonic() - started_at) * 1000),
            observation_count=len(usable_days),
        )
        return evidence

    async def get_land_cover(self, geometry: PolygonGeometry) -> LandCoverEvidence:
        """Share of each land-cover class inside a polygon, from the 2020 LCM10 map."""
        correlation_id = uuid4().hex
        started_at = self._monotonic()
        request_payload = self._land_cover_payload(geometry)
        try:
            access_token = await self._access_token(correlation_id)
            response = await self._post_statistics(access_token, request_payload, correlation_id)
            response.raise_for_status()
            evidence = self._parse_land_cover(response.json())
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise SourceUnavailableError(
                "land_cover", "Copernicus did not return valid land-cover statistics."
            ) from error
        log_provider_event(
            "provider_request_complete",
            provider="copernicus-land-cover",
            correlation_id=correlation_id,
            status_class="2xx",
            duration_ms=round((self._monotonic() - started_at) * 1000),
        )
        return evidence

    @staticmethod
    def _request_payload(
        field: RegisteredField, starts_at: datetime, ends_at: datetime
    ) -> Mapping[str, object]:
        coordinates = [
            [[longitude, latitude] for longitude, latitude in ring]
            for ring in field.geometry.coordinates
        ]
        return {
            "input": {
                "bounds": {
                    "geometry": {"type": "Polygon", "coordinates": coordinates},
                    "properties": {"crs": WGS84_URI},
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {"mosaickingOrder": "leastCC"},
                    }
                ],
            },
            "aggregation": {
                "timeRange": {
                    "from": _isoformat_utc(starts_at),
                    "to": _isoformat_utc(ends_at),
                },
                "aggregationInterval": {"of": "P1D"},
                "evalscript": SENTINEL_2_EVALSCRIPT,
                "resx": SENTINEL_2_RESOLUTION_DEGREES,
                "resy": SENTINEL_2_RESOLUTION_DEGREES,
            },
        }

    @staticmethod
    def _land_cover_payload(geometry: PolygonGeometry) -> Mapping[str, object]:
        coordinates = [
            [[longitude, latitude] for longitude, latitude in ring] for ring in geometry.coordinates
        ]
        return {
            "input": {
                "bounds": {
                    "geometry": {"type": "Polygon", "coordinates": coordinates},
                    "properties": {"crs": WGS84_URI},
                },
                "data": [{"type": LAND_COVER_COLLECTION}],
            },
            "aggregation": {
                "timeRange": LAND_COVER_TIME_RANGE,
                "aggregationInterval": {"of": LAND_COVER_INTERVAL},
                "evalscript": LAND_COVER_EVALSCRIPT,
                "resx": SENTINEL_2_RESOLUTION_DEGREES,
                "resy": SENTINEL_2_RESOLUTION_DEGREES,
            },
        }

    @staticmethod
    def _parse_land_cover(payload: object) -> LandCoverEvidence:
        root = _mapping(payload, "statistics response")
        records = _sequence(root.get("data"), "data")
        if not records:
            raise ValueError("The land-cover response has no records.")
        record = _mapping(records[0], "data[0]")
        outputs = _mapping(record.get("outputs"), "data[0].outputs")
        output = _mapping(outputs.get("land_cover"), "data[0].outputs.land_cover")
        bands = _mapping(output.get("bands"), "data[0].outputs.land_cover.bands")
        fractions: dict[int, float] = {}
        sample_count = no_data_count = 0
        for index, value in enumerate(LAND_COVER_CLASS_VALUES):
            label = f"data[0].outputs.land_cover.bands.B{index}"
            stats = _mapping(_mapping(bands.get(f"B{index}"), label).get("stats"), f"{label}.stats")
            sample_count = _integer(stats.get("sampleCount"), f"{label}.stats.sampleCount")
            no_data_count = _integer(stats.get("noDataCount"), f"{label}.stats.noDataCount")
            mean = _number(stats.get("mean"), f"{label}.stats.mean", optional=True)
            if mean is not None and not 0 <= mean <= 1:
                raise ValueError("Land-cover class shares must be between zero and one.")
            fractions[value] = mean or 0.0
        if sample_count <= 0 or no_data_count > sample_count:
            raise ValueError("The land-cover response has no pixels for the area.")
        return LandCoverEvidence(
            source=LAND_COVER_SOURCE,
            map_year=LAND_COVER_YEAR,
            class_fractions=fractions,
            classified_pixel_percentage=100 * (sample_count - no_data_count) / sample_count,
        )

    @classmethod
    def _parse_response(cls, payload: object) -> tuple[_DailyStats, ...]:
        root = _mapping(payload, "statistics response")
        records = _sequence(root.get("data"), "data")
        result: list[_DailyStats] = []
        for index, record_value in enumerate(records):
            record = _mapping(record_value, f"data[{index}]")
            interval = _mapping(record.get("interval"), f"data[{index}].interval")
            outputs = _mapping(record.get("outputs"), f"data[{index}].outputs")
            result.append(
                _DailyStats(
                    starts_at=_timestamp(interval.get("from"), f"data[{index}].interval.from"),
                    ndvi=cls._band_stats(outputs, "ndvi", index),
                    quality=cls._band_stats(outputs, "quality", index),
                )
            )
            quality = result[-1].quality
            if quality.mean is not None and not 0 <= quality.mean <= 1:
                raise ValueError("Quality output mean must be between zero and one.")
        return tuple(result)

    @staticmethod
    def _band_stats(outputs: Mapping[str, object], output_id: str, index: int) -> _BandStats:
        output = _mapping(outputs.get(output_id), f"data[{index}].outputs.{output_id}")
        bands = _mapping(output.get("bands"), f"data[{index}].outputs.{output_id}.bands")
        band = _mapping(bands.get("B0"), f"data[{index}].outputs.{output_id}.bands.B0")
        stats = _mapping(band.get("stats"), f"data[{index}].outputs.{output_id}.bands.B0.stats")
        sample_count = _integer(
            stats.get("sampleCount"),
            f"data[{index}].outputs.{output_id}.bands.B0.stats.sampleCount",
        )
        no_data_count = _integer(
            stats.get("noDataCount"),
            f"data[{index}].outputs.{output_id}.bands.B0.stats.noDataCount",
        )
        if no_data_count > sample_count:
            raise ValueError("noDataCount cannot exceed sampleCount.")
        mean = _number(
            stats.get("mean"),
            f"data[{index}].outputs.{output_id}.bands.B0.stats.mean",
            optional=True,
        )
        standard_deviation = _number(
            stats.get("stDev"),
            f"data[{index}].outputs.{output_id}.bands.B0.stats.stDev",
            optional=True,
        )
        if sample_count > no_data_count and (mean is None or standard_deviation is None):
            raise ValueError("Usable output statistics require mean and stDev.")
        return _BandStats(mean, standard_deviation, sample_count, no_data_count)

    @staticmethod
    def _aggregate_period(days: Sequence[_DailyStats], label: str) -> SatellitePeriodEvidence:
        usable = tuple(day for day in days if day.ndvi.valid_count > 0)
        total_samples = sum(day.ndvi.valid_count for day in usable)
        if total_samples <= 0:
            raise SourceUnavailableError(
                "satellite", f"Copernicus returned no usable NDVI for the {label} period."
            )
        mean = sum((day.ndvi.mean or 0.0) * day.ndvi.valid_count for day in usable) / total_samples
        variance = (
            sum(
                ((day.ndvi.standard_deviation or 0.0) ** 2) * day.ndvi.valid_count for day in usable
            )
            / total_samples
        )
        return SatellitePeriodEvidence(mean_ndvi=mean, ndvi_standard_deviation=math.sqrt(variance))
