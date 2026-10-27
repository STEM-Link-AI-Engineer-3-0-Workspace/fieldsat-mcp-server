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
    "Read-only satellite and weather evidence for registered agricultural fields in Sri Lanka.\n"
    "Workflow:\n"
    "1. Call list_fields to get field IDs. Do not guess an ID; map a place or crop the user "
    "mentions to a listed field.\n"
    "2. Call get_satellite_analysis for vegetation change and get_weather_context for "
    "rainfall. They are independent and can run in parallel.\n"
    "3. Check data_quality before you use the satellite numbers. If it is poor, say the reading "
    "is unreliable.\n"
    "The tools return measurements, not diagnoses. Do not name a cause such as pests, disease "
    "or drought from these values alone.\n"
    "Errors start with a code. FIELD_NOT_REGISTERED: call list_fields and retry with a listed "
    "ID. SATELLITE_SOURCE_UNAVAILABLE or WEATHER_SOURCE_UNAVAILABLE: report that the source is "
    "unavailable. Do not invent values."
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
        # Unexpected exceptions reach the client as a generic message, not a stack trace.
        # ToolError messages are always sent in full.
        mask_error_details=True,
    )
    register_field_tools(mcp, fields)
    register_satellite_tools(mcp, satellite_provider, find_field)
    register_weather_tools(mcp, weather_provider, find_field)
    register_resources(mcp, fields, find_field)
    register_prompts(mcp)
    return mcp
