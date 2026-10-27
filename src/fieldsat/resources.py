"""Resources: read-only data the client application attaches, rather than the model calling."""

import json

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError
from pydantic import BaseModel

from fieldsat.domain.errors import field_not_registered_message
from fieldsat.domain.fields import Crop, FieldLookup, RegisteredField


class FieldProfile(BaseModel):
    id: str
    name: str
    crop: Crop
    time_zone: str


def _profile(field: RegisteredField) -> FieldProfile:
    return FieldProfile(id=field.id, name=field.name, crop=field.crop, time_zone=field.time_zone)


def register_resources(
    mcp: FastMCP, fields: tuple[RegisteredField, ...], find_field: FieldLookup
) -> None:
    @mcp.resource(
        "fields://registry",
        name="field_registry",
        title="Field registry",
        mime_type="application/json",
    )
    def field_registry() -> str:
        """Every registered field as JSON. Geometry stays on the server."""
        profiles = [_profile(field).model_dump() for field in fields]
        return json.dumps(profiles, indent=2)

    @mcp.resource(
        "fields://{field_id}",
        name="field_profile",
        title="Field profile",
        mime_type="application/json",
    )
    def field_profile(field_id: str) -> str:
        """One registered field as JSON, looked up by its ID."""
        field = find_field(field_id)
        if field is None:
            raise ResourceError(field_not_registered_message(field_id))
        return _profile(field).model_dump_json(indent=2)
