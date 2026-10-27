"""Tool: recent and forecast rainfall for one registered field."""

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from fieldsat.domain.contracts import WeatherContext
from fieldsat.domain.errors import (
    SourceUnavailableError,
    field_not_registered_message,
    source_unavailable_message,
)
from fieldsat.domain.fields import FieldLookup
from fieldsat.domain.weather import get_weather_context as build_weather_context
from fieldsat.providers.base import WeatherEvidenceProvider
from fieldsat.tools.common import READ_ONLY, FieldId


def register_weather_tools(
    mcp: FastMCP, provider: WeatherEvidenceProvider, find_field: FieldLookup
) -> None:
    @mcp.tool(
        name="get_weather_context",
        title="Get weather context",
        annotations=READ_ONLY,
    )
    async def get_weather_context(
        field_id: FieldId,
        historical_days: Annotated[
            int,
            Field(
                ge=1,
                le=30,
                description=(
                    "Requested historical provider window; output always covers the last 7 days"
                ),
            ),
        ] = 7,
        forecast_days: Annotated[
            int,
            Field(
                ge=1,
                le=7,
                description=(
                    "Requested forecast provider window; output always covers the next 48 hours"
                ),
            ),
        ] = 2,
    ) -> WeatherContext:
        """Recent rainfall and humidity, and the 48-hour rain forecast, for one registered field.

        Values are provider estimates, not on-field gauge readings. Use them for weather context
        and the timing of field work, not for diagnosis.
        """
        field = find_field(field_id)
        if field is None:
            raise ToolError(field_not_registered_message(field_id))
        try:
            return await build_weather_context(field, historical_days, forecast_days, provider)
        except SourceUnavailableError as error:
            raise ToolError(source_unavailable_message(error)) from error
