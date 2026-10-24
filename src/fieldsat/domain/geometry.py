"""Polygon geometry helpers: closed rings, centroid, and self-intersection checks."""

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

type Coordinate = tuple[float, float]
type LinearRing = tuple[Coordinate, ...]


@dataclass(frozen=True, slots=True)
class PolygonGeometry:
    type: Literal["Polygon"]
    coordinates: tuple[LinearRing, ...]


def polygon(*coordinates: Coordinate) -> PolygonGeometry:
    return PolygonGeometry(type="Polygon", coordinates=(coordinates,))


def _twice_signed_area(ring: LinearRing) -> float:
    return sum(
        longitude_a * latitude_b - longitude_b * latitude_a
        for (longitude_a, latitude_a), (longitude_b, latitude_b) in pairwise(ring)
    )


def centroid(geometry: PolygonGeometry) -> Coordinate:
    """Return the centroid of the polygon's exterior ring in longitude/latitude order."""
    ring = geometry.coordinates[0]
    if len(ring) < 4:
        raise ValueError("A polygon exterior ring requires at least four coordinates.")

    twice_area = _twice_signed_area(ring)
    longitude_sum = 0.0
    latitude_sum = 0.0
    for (longitude_a, latitude_a), (longitude_b, latitude_b) in pairwise(ring):
        cross_product = longitude_a * latitude_b - longitude_b * latitude_a
        longitude_sum += (longitude_a + longitude_b) * cross_product
        latitude_sum += (latitude_a + latitude_b) * cross_product

    if abs(twice_area) < 1e-12:
        raise ValueError("A polygon must enclose a non-zero area.")

    return longitude_sum / (3 * twice_area), latitude_sum / (3 * twice_area)


def _orientation(a: Coordinate, b: Coordinate, c: Coordinate) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Coordinate, b: Coordinate, point: Coordinate) -> bool:
    return (
        min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= point[1] <= max(a[1], b[1])
        and abs(_orientation(a, b, point)) < 1e-12
    )


def _segments_intersect(
    first_a: Coordinate,
    first_b: Coordinate,
    second_a: Coordinate,
    second_b: Coordinate,
) -> bool:
    first_orientation_a = _orientation(first_a, first_b, second_a)
    first_orientation_b = _orientation(first_a, first_b, second_b)
    second_orientation_a = _orientation(second_a, second_b, first_a)
    second_orientation_b = _orientation(second_a, second_b, first_b)
    if (
        first_orientation_a * first_orientation_b < 0
        and second_orientation_a * second_orientation_b < 0
    ):
        return True
    return any(
        (
            abs(first_orientation_a) < 1e-12 and _on_segment(first_a, first_b, second_a),
            abs(first_orientation_b) < 1e-12 and _on_segment(first_a, first_b, second_b),
            abs(second_orientation_a) < 1e-12 and _on_segment(second_a, second_b, first_a),
            abs(second_orientation_b) < 1e-12 and _on_segment(second_a, second_b, first_b),
        )
    )


def validate_ring(ring: LinearRing) -> None:
    if len(ring) < 4:
        raise ValueError("A polygon ring requires at least four coordinates.")
    if ring[0] != ring[-1]:
        raise ValueError("A polygon ring must be closed.")
    for longitude, latitude in ring:
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            raise ValueError("Polygon coordinates must be finite.")
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError("Polygon coordinates must be valid WGS84 longitude/latitude.")
    if abs(_twice_signed_area(ring)) < 1e-12:
        raise ValueError("A polygon ring must enclose a non-zero area.")

    edges = tuple(pairwise(ring))
    final_index = len(edges) - 1
    for first_index, (first_a, first_b) in enumerate(edges):
        for second_index, (second_a, second_b) in enumerate(
            edges[first_index + 1 :], first_index + 1
        ):
            adjacent = second_index == first_index + 1 or (
                first_index == 0 and second_index == final_index
            )
            if not adjacent and _segments_intersect(first_a, first_b, second_a, second_b):
                raise ValueError("A polygon ring must not self-intersect.")


def point_in_ring(point: Coordinate, ring: LinearRing) -> bool:
    longitude, latitude = point
    inside = False
    for (longitude_a, latitude_a), (longitude_b, latitude_b) in pairwise(ring):
        if _on_segment((longitude_a, latitude_a), (longitude_b, latitude_b), point):
            return True
        crosses = (latitude_a > latitude) != (latitude_b > latitude)
        if crosses:
            crossing_longitude = (longitude_b - longitude_a) * (latitude - latitude_a) / (
                latitude_b - latitude_a
            ) + longitude_a
            if longitude < crossing_longitude:
                inside = not inside
    return inside


METRES_PER_DEGREE_LATITUDE = 111_320.0


def square_around(longitude: float, latitude: float, size_m: float) -> PolygonGeometry:
    """A square of side `size_m` metres centred on a point, as a counter-clockwise polygon."""
    if size_m <= 0:
        raise ValueError("size_m must be positive.")
    half_latitude = size_m / 2 / METRES_PER_DEGREE_LATITUDE
    half_longitude = size_m / 2 / (METRES_PER_DEGREE_LATITUDE * math.cos(math.radians(latitude)))
    west, east = longitude - half_longitude, longitude + half_longitude
    south, north = latitude - half_latitude, latitude + half_latitude
    return polygon((west, south), (east, south), (east, north), (west, north), (west, south))
