"""Domain errors translated into MCP tool errors by the server boundary."""

from typing import Literal


class SourceUnavailableError(RuntimeError):
    def __init__(self, source: Literal["satellite", "weather"], message: str) -> None:
        self.source = source
        super().__init__(message)


def field_not_registered_message(field_id: str) -> str:
    return (
        f'FIELD_NOT_REGISTERED: Field "{field_id}" is not registered (404). '
        "Call list_fields and retry with one of the listed IDs."
    )


def source_unavailable_message(error: SourceUnavailableError) -> str:
    label = "Satellite" if error.source == "satellite" else "Weather"
    code = (
        "SATELLITE_SOURCE_UNAVAILABLE"
        if error.source == "satellite"
        else "WEATHER_SOURCE_UNAVAILABLE"
    )
    return (
        f"{code}: {label} source unavailable (503): {str(error).rstrip('.')}. "
        "Retrying immediately is unlikely to help. Report that this evidence is unavailable "
        "and do not estimate the values."
    )
