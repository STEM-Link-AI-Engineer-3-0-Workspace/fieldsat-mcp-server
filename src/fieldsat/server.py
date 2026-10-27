"""Build the MCP server: one FastMCP object with our tools, resources and prompts."""

from fastmcp import FastMCP

from fieldsat import __version__
from fieldsat.domain.fields import (
    REGISTERED_FIELDS,
    FieldLookup,
    RegisteredField,
    find_registered_field,
)
from fieldsat.prompts import register_prompts
from fieldsat.providers.base import SatelliteEvidenceProvider, WeatherEvidenceProvider
from fieldsat.resources import register_resources
from fieldsat.tools import register_field_tools, register_satellite_tools, register_weather_tools

INSTRUCTIONS = (
    "Read-only field-level satellite and weather evidence for Sri Lankan agricultural fields. "
    "Call list_fields to find a field ID. Measurements describe the field; they do not "
    "diagnose a cause."
)


def create_server(
    satellite_provider: SatelliteEvidenceProvider,
    weather_provider: WeatherEvidenceProvider,
    fields: tuple[RegisteredField, ...] = REGISTERED_FIELDS,
    find_field: FieldLookup = find_registered_field,
) -> FastMCP:
    mcp = FastMCP(
        name="STEM Link Satellite MCP",
        instructions=INSTRUCTIONS,
        version=__version__,
    )
    register_field_tools(mcp, fields)
    register_satellite_tools(mcp, satellite_provider, find_field)
    register_weather_tools(mcp, weather_provider, find_field)
    register_resources(mcp, fields, find_field)
    register_prompts(mcp)
    return mcp
