"""The tools this server exposes. Each module registers its tools on a FastMCP server."""

from fieldsat.tools.fields import register_field_tools
from fieldsat.tools.satellite import register_satellite_tools
from fieldsat.tools.weather import register_weather_tools

__all__ = ["register_field_tools", "register_satellite_tools", "register_weather_tools"]
