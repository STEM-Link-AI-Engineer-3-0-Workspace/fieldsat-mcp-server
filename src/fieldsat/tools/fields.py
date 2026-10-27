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
        """List every field this server can analyse, with its ID, name and crop.

        Call this first. The other tools only accept an ID from this list, so use it to turn
        a place or crop the user mentions (such as "the Minneriya paddy") into a field ID.
        Takes no arguments, makes no network calls and returns the same list every time.
        If no field matches what the user asked about, say the field is not registered.
        """
        return FieldList(
            fields=[FieldSummary(id=field.id, name=field.name, crop=field.crop) for field in fields]
        )
