"""The tools this server exposes. Each module registers its tools on a FastMCP server."""

from .fields import register_field_tools
from .satellite import register_satellite_tools
from .weather import register_weather_tools

__all__ = ["register_field_tools", "register_satellite_tools", "register_weather_tools"]
