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
                description="Length of each current and previous comparison period in days",
            ),
        ],
    ) -> SatelliteContext:
        """Sentinel-2 vegetation change (NDVI) and data quality for one registered field.

        Compares the last `comparison_days` with the period before it and returns NDVI change,
        spatial variability, observation count, cloud coverage and a data-quality grade.
        The measurements do not diagnose a cause.
        """
        field = find_field(field_id)
        if field is None:
            # ToolError: the message goes back to the model, which can correct itself.
            raise ToolError(field_not_registered_message(field_id))
        try:
            return await build_satellite_analysis(field, comparison_days, provider)
        except SourceUnavailableError as error:
            raise ToolError(source_unavailable_message(error)) from error
