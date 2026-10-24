"""Domain errors translated into MCP tool errors by the server boundary."""

from typing import Literal

type Source = Literal["satellite", "weather", "place_search", "land_cover"]

_SOURCE_LABELS: dict[Source, tuple[str, str]] = {
    "satellite": ("SATELLITE_SOURCE_UNAVAILABLE", "Satellite"),
    "weather": ("WEATHER_SOURCE_UNAVAILABLE", "Weather"),
    "place_search": ("PLACE_SEARCH_UNAVAILABLE", "Place search"),
    "land_cover": ("LAND_COVER_SOURCE_UNAVAILABLE", "Land cover"),
}


class SourceUnavailableError(RuntimeError):
    def __init__(self, source: Source, message: str) -> None:
        self.source = source
        super().__init__(message)


class AreaSearchError(ValueError):
    """The search ran but found nothing usable: an unknown place or no matching land cover."""

    def __init__(self, code: Literal["PLACE_NOT_FOUND", "NO_MATCHING_LAND_COVER"], message: str):
        self.code = code
        super().__init__(message)


def field_not_registered_message(field_id: str) -> str:
    return (
        f'FIELD_NOT_REGISTERED: Field "{field_id}" is not registered (404). Check the field ID, '
        "or call search_area to find an area by place name and crop."
    )


def source_unavailable_message(error: SourceUnavailableError) -> str:
    code, label = _SOURCE_LABELS[error.source]
    return f"{code}: {label} source unavailable (503): {error}"


def area_search_message(error: AreaSearchError) -> str:
    return f"{error.code}: {error}"
