"""Tool: list the fields this server knows about."""

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from fieldsat.domain.fields import Crop, RegisteredField


class FieldSummary(BaseModel):
    id: str
    name: str
    crop: Crop


class FieldList(BaseModel):
    fields: list[FieldSummary]


def register_field_tools(mcp: FastMCP, fields: tuple[RegisteredField, ...]) -> None:
    @mcp.tool(
        name="list_fields",
        title="List registered fields",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def list_fields() -> FieldList:
        """List every agricultural field this server can analyse, with its ID, name and crop.

        Call this first when the user names a place (such as Minneriya) instead of a field ID.
        """
        return FieldList(
            fields=[FieldSummary(id=field.id, name=field.name, crop=field.crop) for field in fields]
        )
