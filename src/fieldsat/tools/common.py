"""Pieces shared by every tool: the field ID argument and the read-only hints."""

from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field

# Upper bound for one tool call. Copernicus usually answers in a few seconds;
# anything slower than this is reported to the client as a failed call.
TOOL_TIMEOUT_SECONDS = 30.0

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
