"""Tool: Sentinel-2 vegetation evidence for one registered field."""

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from fieldsat.domain.contracts import SatelliteContext
from fieldsat.domain.errors import (
    SourceUnavailableError,
    field_not_registered_message,
    source_unavailable_message,
)
from fieldsat.domain.fields import FieldLookup
from fieldsat.domain.satellite import get_satellite_analysis as build_satellite_analysis
from fieldsat.providers.base import SatelliteEvidenceProvider
from fieldsat.tools.common import READ_ONLY, TOOL_TIMEOUT_SECONDS, FieldId


def register_satellite_tools(
    mcp: FastMCP, provider: SatelliteEvidenceProvider, find_field: FieldLookup
) -> None:
    @mcp.tool(
        name="get_satellite_analysis",
        title="Get satellite analysis",
        annotations=READ_ONLY,
        timeout=TOOL_TIMEOUT_SECONDS,
    )
    async def get_satellite_analysis(
        field_id: FieldId,
        comparison_days: Annotated[
            int,
            Field(
                ge=1,
                le=90,
                description=(
                    "Days in each comparison period. The current period is the last N days and "
                    "the previous period is the N days before it. Use 14 unless the user asks "
                    "for a different window. Short windows often have too few cloud-free images."
                ),
            ),
        ],
    ) -> SatelliteContext:
        """Sentinel-2 vegetation change (NDVI) and data quality for one registered field.

        Requires a field_id from list_fields. Compares mean NDVI over the last
        `comparison_days` with the same number of days before that.

        Returns:
        - trend: change in mean NDVI. stable is within ±5%, moderate is 5-15%, significant
          is more than 15%.
        - field_uniformity: uniform, moderately_variable or uneven, from how much NDVI
          varies across the field.
        - data_quality: good, moderate or poor, from the number of cloud-free observations,
          cloud cover and usable pixels. If it is poor, the trend is unreliable. Say so first,
          or try a longer comparison_days.

        These are measurements, not a diagnosis. A decline does not show a cause.
        Pair this with get_weather_context for rainfall.
        """
        field = find_field(field_id)
        if field is None:
            # ToolError: the message goes back to the model, which can correct itself.
            raise ToolError(field_not_registered_message(field_id))
        try:
            return await build_satellite_analysis(field, comparison_days, provider)
        except SourceUnavailableError as error:
            raise ToolError(source_unavailable_message(error)) from error
