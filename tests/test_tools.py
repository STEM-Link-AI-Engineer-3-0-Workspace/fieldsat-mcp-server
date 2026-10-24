"""Tool behaviour through a real MCP client connected in memory to the demo server."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from fieldsat.runtime import create_demo_server

mcp = create_demo_server()
ROOT = Path(__file__).resolve().parents[1]

SATELLITE_KEYS = [
    "field_id",
    "current_mean_ndvi",
    "previous_mean_ndvi",
    "ndvi_change_percentage",
    "trend",
    "ndvi_standard_deviation",
    "field_uniformity",
    "valid_observations",
    "average_cloud_coverage_percentage",
    "data_quality",
]

WEATHER_KEYS = [
    "rainfall_last_7_days_mm",
    "rainy_days_last_7_days",
    "rainfall_last_48_hours_mm",
    "rainfall_forecast_next_48_hours_mm",
    "average_humidity_last_7_days",
    "heavy_rain_recent",
    "heavy_rain_expected",
]


async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
    assert isinstance(result.structured_content, dict)
    return result.structured_content


async def test_strict_output_schemas() -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    satellite_schema = tools["get_satellite_analysis"].output_schema
    weather_schema = tools["get_weather_context"].output_schema
    assert satellite_schema is not None
    assert weather_schema is not None
    assert list(satellite_schema["properties"]) == SATELLITE_KEYS
    assert list(weather_schema["properties"]) == WEATHER_KEYS
    assert satellite_schema["additionalProperties"] is False


async def test_handlers_return_canonical_evidence() -> None:
    satellite = await call(
        "get_satellite_analysis", {"field_id": "SL-PADDY-MINNERIYA", "comparison_days": 14}
    )
    weather = await call("get_weather_context", {"field_id": "SL-PADDY-MINNERIYA"})
    assert satellite["ndvi_change_percentage"] == -15.2
    assert satellite["data_quality"] == "good"
    assert weather["rainfall_last_7_days_mm"] == 112
    assert weather["rainfall_forecast_next_48_hours_mm"] == 46
    assert weather["heavy_rain_expected"] is True


async def test_field_ids_are_normalized() -> None:
    satellite = await call(
        "get_satellite_analysis", {"field_id": " sl-paddy-minneriya ", "comparison_days": 14}
    )
    assert satellite["field_id"] == "SL-PADDY-MINNERIYA"


async def test_list_fields_includes_real_zones() -> None:
    listed = await call("list_fields", {})
    ids = [field["id"] for field in listed["fields"]]
    assert ids[:4] == [
        "SL-PADDY-MINNERIYA",
        "SL-PADDY-SAMMANTHURAI",
        "SL-PADDY-KALA-WEWA",
        "SL-TEA-PEDRO",
    ]


async def test_unknown_field_error_remains_distinguishable() -> None:
    with pytest.raises(ToolError, match=r"FIELD_NOT_REGISTERED.*not registered \(404\)"):
        await call("get_satellite_analysis", {"field_id": "SL-PADDY-404", "comparison_days": 14})


async def test_out_of_range_arguments_are_rejected_before_the_handler_runs() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_satellite_analysis",
            {"field_id": "SL-PADDY-MINNERIYA", "comparison_days": 500},
            raise_on_error=False,
        )
    assert result.is_error is True


async def test_poor_quality_is_a_successful_primary_path() -> None:
    payload = await call(
        "get_satellite_analysis", {"field_id": "SL-PADDY-POOR", "comparison_days": 14}
    )
    assert payload["valid_observations"] == 1
    assert payload["data_quality"] == "poor"


async def test_satellite_failure_does_not_remove_weather() -> None:
    with pytest.raises(ToolError, match="SATELLITE_SOURCE_UNAVAILABLE"):
        await call(
            "get_satellite_analysis", {"field_id": "SL-PADDY-SAT-FAIL", "comparison_days": 14}
        )
    weather = await call("get_weather_context", {"field_id": "SL-PADDY-SAT-FAIL"})
    assert weather["heavy_rain_expected"] is True


async def test_weather_failure_does_not_remove_satellite() -> None:
    with pytest.raises(ToolError, match="WEATHER_SOURCE_UNAVAILABLE"):
        await call("get_weather_context", {"field_id": "SL-PADDY-WEATHER-FAIL"})
    satellite = await call(
        "get_satellite_analysis", {"field_id": "SL-PADDY-WEATHER-FAIL", "comparison_days": 14}
    )
    assert satellite["ndvi_change_percentage"] == -15.2


async def test_search_area_returns_an_id_the_other_tools_accept() -> None:
    area = await call("search_area", {"place_name": "minneriya", "crop": "paddy"})
    assert area["field_id"].startswith("AREA_PADDY_8.04652_80.90251_1000M")
    assert area["matching_land_cover_percentage"] == 77.0
    assert area["candidates_checked"] == 9

    satellite = await call(
        "get_satellite_analysis", {"field_id": area["field_id"], "comparison_days": 14}
    )
    weather = await call("get_weather_context", {"field_id": area["field_id"]})
    assert satellite["field_id"] == area["field_id"]
    assert weather["heavy_rain_expected"] is True


async def test_search_area_reports_places_it_cannot_use() -> None:
    with pytest.raises(ToolError, match="NO_MATCHING_LAND_COVER"):
        await call("search_area", {"place_name": "Colombo", "crop": "paddy"})
    with pytest.raises(ToolError, match="PLACE_NOT_FOUND"):
        await call("search_area", {"place_name": "Atlantis", "crop": "tea"})


async def test_demo_fields_can_come_from_a_field_file(tmp_path: Path) -> None:
    document = json.loads((ROOT / "fields.example.geojson").read_text())
    document["features"] = document["features"][:1]
    document["features"][0]["properties"].update(id="my-farm", name="My farm")
    fields_file = tmp_path / "fields.geojson"
    fields_file.write_text(json.dumps(document))

    async with Client(create_demo_server(fields_file=fields_file)) as client:
        listed = await client.call_tool("list_fields", {})
    assert isinstance(listed.structured_content, dict)
    ids = [field["id"] for field in listed.structured_content["fields"]]
    assert ids[0] == "MY-FARM"
    assert "SL-PADDY-MINNERIYA" not in ids
    assert "SL-PADDY-SAT-FAIL" in ids
