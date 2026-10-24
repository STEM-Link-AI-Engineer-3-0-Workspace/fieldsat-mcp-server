"""The field registry: which agricultural zones the server knows about."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fieldsat.domain.geometry import (
    PolygonGeometry,
    centroid,
    point_in_ring,
    polygon,
    validate_ring,
)

type Crop = Literal["paddy", "tea"]

CROPS: tuple[Crop, ...] = get_args(Crop.__value__)

# "auto" lets the weather provider take the time zone from the field's location.
AUTO_TIME_ZONE = "auto"


@dataclass(frozen=True, slots=True)
class RegisteredField:
    id: str
    name: str
    crop: Crop
    time_zone: str
    geometry: PolygonGeometry


type FieldLookup = Callable[[str], RegisteredField | None]


def validate_time_zone(time_zone: str) -> None:
    if time_zone == AUTO_TIME_ZONE:
        return
    try:
        ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f'"{time_zone}" is not an IANA time zone such as Asia/Colombo.') from error


def validate_field_registry(fields: tuple[RegisteredField, ...]) -> None:
    seen_ids: set[str] = set()
    for field in fields:
        if not field.id or field.id != normalize_field_id(field.id):
            raise ValueError("Registered field IDs must be non-empty and normalized.")
        if field.id in seen_ids:
            raise ValueError(f'Duplicate registered field ID "{field.id}".')
        seen_ids.add(field.id)
        if not field.name.strip():
            raise ValueError("Registered field names must be non-empty.")
        if field.crop not in CROPS:
            raise ValueError(f"Registered fields must use a supported crop: {', '.join(CROPS)}.")
        validate_time_zone(field.time_zone)
        if field.geometry.type != "Polygon" or not field.geometry.coordinates:
            raise ValueError("Registered field geometry must be a Polygon.")
        for ring in field.geometry.coordinates:
            validate_ring(ring)
        if not point_in_ring(centroid(field.geometry), field.geometry.coordinates[0]):
            raise ValueError("The field centroid must fall inside the exterior polygon ring.")


REGISTERED_FIELDS: tuple[RegisteredField, ...] = (
    RegisteredField(
        id="SL-PADDY-MINNERIYA",
        name="Minneriya Paddy Fields",
        crop="paddy",
        time_zone="Asia/Colombo",
        geometry=polygon(
            (80.910, 8.050),
            (80.950, 8.050),
            (80.950, 8.020),
            (80.910, 8.020),
            (80.910, 8.050),
        ),
    ),
    RegisteredField(
        id="SL-PADDY-SAMMANTHURAI",
        name="Sammanthurai Plains / Gal Oya Scheme",
        crop="paddy",
        time_zone="Asia/Colombo",
        geometry=polygon(
            (81.780, 7.400),
            (81.840, 7.400),
            (81.840, 7.340),
            (81.780, 7.340),
            (81.780, 7.400),
        ),
    ),
    RegisteredField(
        id="SL-PADDY-KALA-WEWA",
        name="Mahaweli System H / Kala Wewa Basin",
        crop="paddy",
        time_zone="Asia/Colombo",
        geometry=polygon(
            (80.450, 8.040),
            (80.500, 8.040),
            (80.500, 7.990),
            (80.450, 7.990),
            (80.450, 8.040),
        ),
    ),
    RegisteredField(
        id="SL-TEA-PEDRO",
        name="Pedro Tea Estate",
        crop="tea",
        time_zone="Asia/Colombo",
        geometry=polygon(
            (80.785, 6.975),
            (80.810, 6.975),
            (80.810, 6.955),
            (80.785, 6.955),
            (80.785, 6.975),
        ),
    ),
)


def normalize_field_id(field_id: str) -> str:
    return field_id.strip().upper()


def field_lookup(fields: tuple[RegisteredField, ...]) -> FieldLookup:
    """Look fields up by ID in a fixed tuple."""
    by_id = {field.id: field for field in fields}

    def find(field_id: str) -> RegisteredField | None:
        return by_id.get(normalize_field_id(field_id))

    return find


def find_registered_field(field_id: str) -> RegisteredField | None:
    normalized = normalize_field_id(field_id)
    return next((field for field in REGISTERED_FIELDS if field.id == normalized), None)


def parse_field_registry(document: object) -> tuple[RegisteredField, ...]:
    """Read fields from a GeoJSON FeatureCollection of Polygon features.

    Each feature needs properties `id`, `name` and `crop`; `time_zone` defaults to "auto".
    """
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise ValueError("The field file must be a GeoJSON FeatureCollection.")
    features = document.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("The field file must contain at least one feature.")

    fields: list[RegisteredField] = []
    for index, feature in enumerate(features):
        label = f"features[{index}]"
        if not isinstance(feature, dict):
            raise ValueError(f"{label} must be a GeoJSON Feature.")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict):
            raise ValueError(f"{label}.properties must be an object.")
        if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
            raise ValueError(f"{label}.geometry must be a GeoJSON Polygon.")
        field_id, name, crop = (properties.get(key) for key in ("id", "name", "crop"))
        time_zone = properties.get("time_zone", AUTO_TIME_ZONE)
        if not isinstance(field_id, str) or not isinstance(name, str):
            raise ValueError(f"{label}.properties.id and .name must be strings.")
        if crop not in CROPS:
            raise ValueError(f"{label}.properties.crop must be one of: {', '.join(CROPS)}.")
        if not isinstance(time_zone, str):
            raise ValueError(f"{label}.properties.time_zone must be a string.")
        fields.append(
            RegisteredField(
                id=normalize_field_id(field_id),
                name=name,
                crop=crop,
                time_zone=time_zone,
                geometry=_parse_polygon(geometry.get("coordinates"), label),
            )
        )
    result = tuple(fields)
    validate_field_registry(result)
    return result


def _parse_polygon(coordinates: object, label: str) -> PolygonGeometry:
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError(f"{label}.geometry.coordinates must be a list of rings.")
    rings: list[tuple[tuple[float, float], ...]] = []
    for ring in coordinates:
        if not isinstance(ring, list):
            raise ValueError(f"{label}.geometry.coordinates must be a list of rings.")
        points: list[tuple[float, float]] = []
        for point in ring:
            if (
                not isinstance(point, list)
                or len(point) < 2
                or not all(
                    isinstance(value, int | float) and not isinstance(value, bool)
                    for value in point[:2]
                )
            ):
                raise ValueError(f"{label} coordinates must be [longitude, latitude] pairs.")
            points.append((float(point[0]), float(point[1])))
        rings.append(tuple(points))
    return PolygonGeometry(type="Polygon", coordinates=tuple(rings))


def load_field_registry(path: str | Path) -> tuple[RegisteredField, ...]:
    """Load a field registry from a GeoJSON file, for example fields.example.geojson."""
    with Path(path).open(encoding="utf-8") as file:
        return parse_field_registry(json.load(file))


validate_field_registry(REGISTERED_FIELDS)
