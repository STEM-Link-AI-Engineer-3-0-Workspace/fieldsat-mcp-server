"""Tool: find an area to analyse by place name and crop."""

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from fieldsat.domain.area_search import MAX_AREA_SIZE_M, MIN_AREA_SIZE_M
from fieldsat.domain.area_search import search_area as run_area_search
from fieldsat.domain.contracts import AreaSearchResult
from fieldsat.domain.errors import (
    AreaSearchError,
    SourceUnavailableError,
    area_search_message,
    source_unavailable_message,
)
from fieldsat.domain.fields import Crop
from fieldsat.providers.base import LandCoverProvider, PlaceSearchProvider
from fieldsat.tools.common import READ_ONLY, TOOL_TIMEOUT_SECONDS


def register_area_tools(
    mcp: FastMCP,
    place_provider: PlaceSearchProvider,
    land_cover_provider: LandCoverProvider,
) -> None:
    @mcp.tool(
        name="search_area",
        title="Search for an area by place and crop",
        annotations=READ_ONLY,
        timeout=TOOL_TIMEOUT_SECONDS,
    )
    async def search_area(
        place_name: Annotated[
            str,
            Field(
                min_length=1,
                max_length=100,
                description="Town, village or area name, for example Minneriya or Ampara",
            ),
        ],
        crop: Annotated[Crop, Field(description="Crop grown in the area")],
        area_size_m: Annotated[
            int,
            Field(
                ge=MIN_AREA_SIZE_M,
                le=MAX_AREA_SIZE_M,
                description="Side of the square area to analyse, in metres",
            ),
        ] = 1000,
        country_code: Annotated[
            str | None,
            Field(
                pattern=r"^[A-Za-z]{2}$",
                description="ISO 3166-1 alpha-2 country code to search in; null searches worldwide",
            ),
        ] = "LK",
    ) -> AreaSearchResult:
        """Find a square area near a named place whose land cover matches the crop.

        Looks the place up, then checks it and the eight squares around it on the Copernicus
        global 10 m land-cover map, and returns the one with the most matching land cover.
        Pass the returned field_id to get_satellite_analysis and get_weather_context.
        The land-cover map shows cropland, not which crop is grown. Tell the user which
        place was matched and mention other_places if the match may be the wrong one.
        """
        try:
            return await run_area_search(
                place_name, crop, area_size_m, country_code, place_provider, land_cover_provider
            )
        except AreaSearchError as error:
            raise ToolError(area_search_message(error)) from error
        except SourceUnavailableError as error:
            raise ToolError(source_unavailable_message(error)) from error
