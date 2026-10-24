"""Choose where evidence comes from: live providers (needs credentials) or demo fixtures.

Both modes serve the built-in fields unless a GeoJSON field file is given, either as an
argument or through FIELDSAT_FIELDS_FILE. See fields.example.geojson for the format.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from fastmcp import FastMCP

from fieldsat.domain.fields import (
    REGISTERED_FIELDS,
    RegisteredField,
    field_lookup,
    load_field_registry,
)
from fieldsat.providers.copernicus import CopernicusCredentials, CopernicusSatelliteProvider
from fieldsat.providers.fixtures import (
    FIXTURE_LAND_COVER_PROVIDER,
    FIXTURE_PLACE_SEARCH_PROVIDER,
    FIXTURE_SATELLITE_PROVIDER,
    FIXTURE_WEATHER_PROVIDER,
    demo_fields,
)
from fieldsat.providers.open_meteo import OpenMeteoPlaceSearchProvider, OpenMeteoWeatherProvider
from fieldsat.server import create_server

FIELDS_FILE_VARIABLE = "FIELDSAT_FIELDS_FILE"


def load_fields(
    fields_file: str | Path | None = None, environment: Mapping[str, str] | None = None
) -> tuple[RegisteredField, ...]:
    """The field file's fields if one is given, otherwise the built-in registry."""
    values = os.environ if environment is None else environment
    path = fields_file or values.get(FIELDS_FILE_VARIABLE, "").strip()
    return load_field_registry(path) if path else REGISTERED_FIELDS


def create_live_server(
    environment: Mapping[str, str] | None = None, fields_file: str | Path | None = None
) -> FastMCP:
    """Copernicus Sentinel-2 and Open-Meteo. Refuses to start without Copernicus credentials."""
    credentials = CopernicusCredentials.from_environment(environment)
    fields = load_fields(fields_file, environment)
    # One Copernicus provider serves Sentinel-2 and land cover, so they share one token.
    copernicus = CopernicusSatelliteProvider(credentials)
    return create_server(
        copernicus,
        OpenMeteoWeatherProvider(),
        OpenMeteoPlaceSearchProvider(),
        copernicus,
        fields=fields,
        find_field=field_lookup(fields),
    )


def create_demo_server(
    environment: Mapping[str, str] | None = None, fields_file: str | Path | None = None
) -> FastMCP:
    """Fixed numbers, no network, plus verification fields that fail on purpose."""
    fields = demo_fields(load_fields(fields_file, environment))
    return create_server(
        FIXTURE_SATELLITE_PROVIDER,
        FIXTURE_WEATHER_PROVIDER,
        FIXTURE_PLACE_SEARCH_PROVIDER,
        FIXTURE_LAND_COVER_PROVIDER,
        fields=fields,
        find_field=field_lookup(fields),
    )
