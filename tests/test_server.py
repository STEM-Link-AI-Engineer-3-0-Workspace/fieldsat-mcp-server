"""The MCP surface: names, schemas, resources and prompts the server advertises."""

from fastmcp import Client

from fieldsat.runtime import create_demo_server

mcp = create_demo_server()


async def test_server_advertises_three_tools_one_resource_one_template_one_prompt() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        templates = await client.list_resource_templates()
        prompts = await client.list_prompts()
    assert [tool.name for tool in tools] == [
        "list_fields",
        "get_satellite_analysis",
        "get_weather_context",
    ]
    assert [str(resource.uri) for resource in resources] == ["fields://registry"]
    assert [template.uri_template for template in templates] == ["fields://{field_id}"]
    assert [prompt.name for prompt in prompts] == ["field_health_brief"]


async def test_input_schema_carries_the_validation_rules() -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    days = tools["get_satellite_analysis"].input_schema["properties"]["comparison_days"]
    assert days["minimum"] == 1
    assert days["maximum"] == 90
    assert tools["get_satellite_analysis"].annotations is not None
    assert tools["get_satellite_analysis"].annotations.read_only_hint is True


async def test_resources_and_prompt() -> None:
    async with Client(mcp) as client:
        registry = await client.read_resource("fields://registry")
        profile = await client.read_resource("fields://sl-tea-pedro")
        prompt = await client.get_prompt("field_health_brief", {"field_id": "SL-TEA-PEDRO"})
    assert "SL-PADDY-MINNERIYA" in registry[0].text
    assert '"crop": "tea"' in profile[0].text
    assert "get_satellite_analysis" in prompt.messages[0].content.text
