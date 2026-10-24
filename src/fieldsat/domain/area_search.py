"""Find an area by place name and crop: geocode the place, then pick the nearby square whose
Copernicus land cover best matches the crop.

A searched area gets an ID that encodes its crop, centre and size, for example
AREA_PADDY_8.04652_80.90251_1000M. The ID is enough to rebuild the area, so the satellite and
weather tools accept it without the server having to remember the search.
"""

import asyncio
import math
import re

from fieldsat.domain.contracts import AreaSearchResult, LandCoverShare
from fieldsat.domain.errors import AreaSearchError
from fieldsat.domain.evidence import LandCoverEvidence, Place
from fieldsat.domain.fields import (
    AUTO_TIME_ZONE,
    CROPS,
    Crop,
    FieldLookup,
    RegisteredField,
    normalize_field_id,
)
from fieldsat.domain.geometry import METRES_PER_DEGREE_LATITUDE, square_around
from fieldsat.providers.base import LandCoverProvider, PlaceSearchProvider

# Class values of the Copernicus Global Land Cover Map at 10 m (CLMS LCM10), from the
# classification:classes block of the collection's STAC record.
LAND_COVER_CLASSES: dict[int, str] = {
    10: "tree_cover",
    20: "shrubland",
    30: "grassland",
    40: "cropland",
    50: "herbaceous_wetland",
    60: "mangroves",
    70: "moss_lichen",
    80: "bare_sparse_vegetation",
    90: "built_up",
    100: "permanent_water_bodies",
    110: "snow_ice",
}

# The map has no crop types. Flooded paddy is often mapped as herbaceous wetland, so paddy
# accepts both. The map has no plantation class either: tea can appear as tree cover,
# shrubland or cropland, so for tea the search only steers away from towns, water and bare land.
CROP_LAND_COVER: dict[Crop, tuple[int, ...]] = {
    "paddy": (40, 50),
    "tea": (10, 20, 40),
}

MIN_AREA_SIZE_M = 200
MAX_AREA_SIZE_M = 5000
# A candidate square is only chosen when at least this share of it matches the crop.
MIN_MATCHING_FRACTION = 0.4
# Below this share of classified pixels, a candidate's land cover is not trusted.
MIN_CLASSIFIED_PERCENTAGE = 50.0
# Candidate squares: the one centred on the place, then the eight around it.
GRID_OFFSETS: tuple[tuple[int, int], ...] = (
    (0, 0),
    *((row, column) for row in (-1, 0, 1) for column in (-1, 0, 1) if (row, column) != (0, 0)),
)
MAX_PLACES = 5

_AREA_ID = re.compile(
    r"AREA_(?P<crop>[A-Z]+)_(?P<latitude>-?\d{1,2}\.\d+)_(?P<longitude>-?\d{1,3}\.\d+)_(?P<size>\d+)M"
)


def area_field_id(crop: Crop, latitude: float, longitude: float, size_m: int) -> str:
    return f"AREA_{crop.upper()}_{latitude:.5f}_{longitude:.5f}_{size_m}M"


def area_field(crop: Crop, latitude: float, longitude: float, size_m: int) -> RegisteredField:
    return RegisteredField(
        id=area_field_id(crop, latitude, longitude, size_m),
        name=f"Searched {crop} area at {latitude:.5f}, {longitude:.5f}",
        crop=crop,
        time_zone=AUTO_TIME_ZONE,
        geometry=square_around(longitude, latitude, size_m),
    )


def find_searched_area(field_id: str) -> RegisteredField | None:
    """Rebuild a searched area from its ID, or None if the ID is not a valid area ID."""
    match = _AREA_ID.fullmatch(normalize_field_id(field_id))
    if match is None:
        return None
    crop = match["crop"].lower()
    latitude, longitude = float(match["latitude"]), float(match["longitude"])
    size_m = int(match["size"])
    if (
        crop not in CROPS
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
        or not MIN_AREA_SIZE_M <= size_m <= MAX_AREA_SIZE_M
    ):
        return None
    return area_field(crop, latitude, longitude, size_m)


def with_searched_areas(find_field: FieldLookup) -> FieldLookup:
    """Registered fields first, then searched-area IDs."""

    def find(field_id: str) -> RegisteredField | None:
        return find_field(field_id) or find_searched_area(field_id)

    return find


def _place_label(place: Place) -> str:
    return ", ".join(part for part in (place.name, place.region, place.country) if part)


def _candidate_centre(place: Place, size_m: int, row: int, column: int) -> tuple[float, float]:
    latitude = place.latitude + row * size_m / METRES_PER_DEGREE_LATITUDE
    longitude = place.longitude + column * size_m / (
        METRES_PER_DEGREE_LATITUDE * math.cos(math.radians(place.latitude))
    )
    return round(latitude, 5), round(longitude, 5)


def _matching_fraction(evidence: LandCoverEvidence, crop: Crop) -> float:
    if evidence.classified_pixel_percentage < MIN_CLASSIFIED_PERCENTAGE:
        return 0.0
    return sum(evidence.class_fractions.get(value, 0.0) for value in CROP_LAND_COVER[crop])


async def search_area(
    place_name: str,
    crop: Crop,
    size_m: int,
    country_code: str | None,
    place_provider: PlaceSearchProvider,
    land_cover_provider: LandCoverProvider,
) -> AreaSearchResult:
    if not place_name.strip():
        raise ValueError("place_name must not be empty.")
    if not MIN_AREA_SIZE_M <= size_m <= MAX_AREA_SIZE_M:
        raise ValueError(f"size_m must be between {MIN_AREA_SIZE_M} and {MAX_AREA_SIZE_M}.")

    places = await place_provider.search_places(place_name.strip(), country_code, MAX_PLACES)
    if not places:
        where = f" in {country_code.upper()}" if country_code else ""
        raise AreaSearchError(
            "PLACE_NOT_FOUND", f'No place called "{place_name}" was found{where}.'
        )
    place = places[0]

    centres = [_candidate_centre(place, size_m, row, column) for row, column in GRID_OFFSETS]
    land_covers = await asyncio.gather(
        *(
            land_cover_provider.get_land_cover(square_around(longitude, latitude, size_m))
            for latitude, longitude in centres
        )
    )
    # max() keeps the first of equal scores, so ties go to the square centred on the place.
    best_index = max(
        range(len(centres)), key=lambda index: _matching_fraction(land_covers[index], crop)
    )
    best_fraction = _matching_fraction(land_covers[best_index], crop)
    if best_fraction < MIN_MATCHING_FRACTION:
        classes = ", ".join(LAND_COVER_CLASSES[value] for value in CROP_LAND_COVER[crop])
        raise AreaSearchError(
            "NO_MATCHING_LAND_COVER",
            f"No {size_m} m square around {_place_label(place)} is at least "
            f"{MIN_MATCHING_FRACTION:.0%} {classes} on the Copernicus land-cover map "
            f"(best: {best_fraction:.0%}). Try a nearby place or a different area size.",
        )

    latitude, longitude = centres[best_index]
    evidence = land_covers[best_index]
    shares = sorted(
        (
            LandCoverShare(land_cover=LAND_COVER_CLASSES[value], percentage=round(100 * share, 1))
            for value, share in evidence.class_fractions.items()
            if value in LAND_COVER_CLASSES and share > 0
        ),
        key=lambda share: share.percentage,
        reverse=True,
    )
    return AreaSearchResult(
        field_id=area_field_id(crop, latitude, longitude, size_m),
        place=_place_label(place),
        crop=crop,
        latitude=latitude,
        longitude=longitude,
        area_size_m=size_m,
        area_hectares=round(size_m * size_m / 10_000, 2),
        matching_land_cover_percentage=round(100 * best_fraction, 1),
        matching_land_cover_classes=[LAND_COVER_CLASSES[value] for value in CROP_LAND_COVER[crop]],
        land_cover=shares,
        land_cover_source=f"{evidence.source} ({evidence.map_year})",
        candidates_checked=len(centres),
        other_places=[_place_label(other) for other in places[1:]],
    )
