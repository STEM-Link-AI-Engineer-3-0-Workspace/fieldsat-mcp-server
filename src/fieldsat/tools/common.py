"""Pieces shared by every tool: the field ID argument and the read-only hints."""

from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field

# Hints for the client and the model. They describe the tool; they enforce nothing.
READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

FieldId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        description="Registered STEM Link field identifier, for example SL-PADDY-MINNERIYA",
    ),
]
