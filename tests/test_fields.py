"""Field registry tests."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from fieldsat.domain.fields import (
    REGISTERED_FIELDS,
    find_registered_field,
    normalize_field_id,
    parse_field_registry,
    validate_field_registry,
)
from fieldsat.domain.geometry import PolygonGeometry, centroid, polygon
from fieldsat.runtime import load_fields

ROOT = Path(__file__).resolve().parents[1]


def test_production_registry_contains_the_demo_field_and_four_agricultural_zones() -> None:
    assert [(field.id, field.crop) for field in REGISTERED_FIELDS] == [
        ("SL-PADDY-MINNERIYA", "paddy"),
        ("SL-PADDY-SAMMANTHURAI", "paddy"),
        ("SL-PADDY-KALA-WEWA", "paddy"),
        ("SL-TEA-PEDRO", "tea"),
    ]


def test_field_lookup_normalizes_without_changing_record() -> None:
    assert normalize_field_id(" sl-paddy-minneriya ") == "SL-PADDY-MINNERIYA"
    assert (
        find_registered_field(" sl-paddy-minneriya ").id  # type: ignore[union-attr]
        == "SL-PADDY-MINNERIYA"
    )
    assert find_registered_field("SL-PADDY-UNKNOWN") is None


def test_every_geometry_has_a_closed_polygon_ring() -> None:
    for field in REGISTERED_FIELDS:
        ring = field.geometry.coordinates[0]
        assert len(ring) >= 4
        assert ring[0] == ring[-1]


def test_registered_geometries_have_expected_centroids() -> None:
    expected_centroids = {
        "SL-PADDY-MINNERIYA": (80.930, 8.035),
        "SL-PADDY-SAMMANTHURAI": (81.810, 7.370),
        "SL-PADDY-KALA-WEWA": (80.475, 8.015),
        "SL-TEA-PEDRO": (80.7975, 6.965),
    }
    for field in REGISTERED_FIELDS:
        assert centroid(field.geometry) == pytest.approx(expected_centroids[field.id])
    validate_field_registry(REGISTERED_FIELDS)


@pytest.mark.parametrize(
    ("geometry", "message"),
    [
        (polygon((80.0, 7.0), (81.0, 7.0), (81.0, 8.0), (80.0, 8.0)), "closed"),
        (
            polygon((181.0, 7.0), (182.0, 7.0), (182.0, 8.0), (181.0, 7.0)),
            "WGS84",
        ),
        (
            polygon((80.0, 7.0), (81.0, 8.0), (80.0, 8.0), (81.0, 7.0), (80.0, 7.0)),
            "non-zero area",
        ),
        (
            PolygonGeometry(
                type="Polygon",
                coordinates=(
                    (
                        (80.0, 7.0),
                        (82.0, 7.0),
                        (81.0, 8.0),
                        (82.0, 9.0),
                        (80.0, 9.0),
                        (81.0, 8.0),
                        (80.0, 7.0),
                    ),
                ),
            ),
            "self-intersect",
        ),
    ],
)
def test_rejects_invalid_live_geometry(geometry: PolygonGeometry, message: str) -> None:
    field = replace(REGISTERED_FIELDS[0], geometry=geometry)
    with pytest.raises(ValueError, match=message):
        validate_field_registry((field,))


def test_rejects_duplicate_or_non_normalized_field_ids() -> None:
    field = REGISTERED_FIELDS[0]
    with pytest.raises(ValueError, match="normalized"):
        validate_field_registry((replace(field, id="sl-paddy-04"),))
    with pytest.raises(ValueError, match="Duplicate"):
        validate_field_registry((field, replace(field)))


def test_example_field_file_matches_the_built_in_registry() -> None:
    assert load_fields(ROOT / "fields.example.geojson", {}) == REGISTERED_FIELDS
    assert load_fields(None, {}) == REGISTERED_FIELDS
    assert load_fields(None, {"FIELDSAT_FIELDS_FILE": str(ROOT / "fields.example.geojson")}) == (
        REGISTERED_FIELDS
    )


def field_document(**properties: object) -> dict[str, object]:
    with (ROOT / "fields.example.geojson").open() as file:
        document: dict[str, object] = json.load(file)
    features = document["features"]
    assert isinstance(features, list)
    features[0]["properties"].update(properties)
    return document


def test_field_file_ids_are_normalized_and_time_zone_is_any_iana_zone() -> None:
    fields = parse_field_registry(field_document(id="my-farm", time_zone="Asia/Kolkata"))
    assert fields[0].id == "MY-FARM"
    assert fields[0].time_zone == "Asia/Kolkata"


@pytest.mark.parametrize(
    ("properties", "message"),
    [
        ({"crop": "rice"}, "crop"),
        ({"time_zone": "Mars/Olympus"}, "IANA"),
        ({"id": 7}, "strings"),
        ({"id": "SL-TEA-PEDRO"}, "Duplicate"),
    ],
)
def test_field_file_rejects_bad_properties(properties: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_field_registry(field_document(**properties))


def test_field_file_must_be_a_feature_collection() -> None:
    with pytest.raises(ValueError, match="FeatureCollection"):
        parse_field_registry({"type": "Feature"})
