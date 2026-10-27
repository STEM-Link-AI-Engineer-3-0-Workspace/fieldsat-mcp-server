"""Prompts: reusable instructions a user picks from the client's menu."""

from typing import Literal

from fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    @mcp.prompt(name="field_health_brief", title="Field health brief")
    def field_health_brief(
        field_id: str,
        audience: Literal["farmer", "extension_officer"] = "extension_officer",
    ) -> str:
        """Brief on one field's vegetation and rainfall, written for a farmer or an officer."""
        reader = "a farmer" if audience == "farmer" else "an agricultural extension officer"
        return (
            f"Write a short field health brief on field {field_id} for {reader}.\n"
            "1. Call get_satellite_analysis with comparison_days=14.\n"
            "2. Call get_weather_context.\n"
            "3. In at most six lines, report the NDVI trend, how uniform the field is, "
            "recent and forecast rain, and the data quality.\n"
            "Report measurements only. Do not diagnose a cause such as pests or disease. "
            "If data quality is poor, say the reading is unreliable before anything else."
        )
