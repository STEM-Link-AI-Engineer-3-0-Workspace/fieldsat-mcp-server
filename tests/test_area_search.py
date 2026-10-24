"""Area search: geocode a place, pick the square whose land cover matches the crop."""

import pytest

from fieldsat.domain.area_search import (
    area_field_id,
    find_searched_area,
    search_area,
    with_searched_areas,
)
from fieldsat.domain.errors import AreaSearchError
from fieldsat.domain.evidence import LandCoverEvidence, Place
from fieldsat.domain.fields import REGISTERED_FIELDS, field_lookup, find_registered_field
from fieldsat.domain.geometry import PolygonGeometry, centroid, square_around

MINNERIYA = Place("Minneriya", 8.04652, 80.90251, "Asia/Colombo", "North Central", "Sri Lanka")


class FakePlaces:
    def __init__(self, *places: Place) -> None:
        self.places = places
        self.calls: list[tuple[str, str | None, int]] = []

    async def search_places(
        self, name: str, country_code: str | None, count: int
    ) -> tuple[Place, ...]:
        self.calls.append((name, country_code, count))
        return self.places


class NorthEastCropland:
    """Cropland only in the square north-east of the place; forest everywhere else."""

    def __init__(self) -> None:
        self.geometries: list[PolygonGeometry] = []

    async def get_land_cover(self, geometry: PolygonGeometry) -> LandCoverEvidence:
        self.geometries.append(geometry)
        longitude, latitude = centroid(geometry)
        north_east = (
            latitude > MINNERIYA.latitude + 0.001 and longitude > MINNERIYA.longitude + 0.001
        )
        fractions = {40: 0.8, 10: 0.2} if north_east else {10: 0.9, 40: 0.1}
        return LandCoverEvidence("land-cover-fake", 2020, fractions, 99.0)


async def test_picks_the_neighbouring_square_with_the_most_cropland() -> None:
    places = FakePlaces(MINNERIYA, Place("Minneriya Tank", 8.0, 80.8, "Asia/Colombo", None, None))
    land_cover = NorthEastCropland()

    result = await search_area("Minneriya", "paddy", 1000, "LK", places, land_cover)

    assert places.calls == [("Minneriya", "LK", 5)]
    assert len(land_cover.geometries) == result.candidates_checked == 9
    assert result.latitude > MINNERIYA.latitude
    assert result.longitude > MINNERIYA.longitude
    assert result.matching_land_cover_percentage == 80.0
    assert result.matching_land_cover_classes == ["cropland", "herbaceous_wetland"]
    assert [share.land_cover for share in result.land_cover] == ["cropland", "tree_cover"]
    assert result.area_hectares == 100.0
    assert result.place == "Minneriya, North Central, Sri Lanka"
    assert result.other_places == ["Minneriya Tank"]
    assert result.field_id == area_field_id("paddy", result.latitude, result.longitude, 1000)


async def test_rejects_a_place_without_matching_land_cover() -> None:
    class Town:
        async def get_land_cover(self, geometry: PolygonGeometry) -> LandCoverEvidence:
            return LandCoverEvidence("land-cover-fake", 2020, {90: 0.9, 40: 0.1}, 99.0)

    with pytest.raises(AreaSearchError) as error:
        await search_area("Minneriya", "paddy", 1000, "LK", FakePlaces(MINNERIYA), Town())
    assert error.value.code == "NO_MATCHING_LAND_COVER"


async def test_ignores_squares_that_are_mostly_unclassified() -> None:
    class Cloudy:
        async def get_land_cover(self, geometry: PolygonGeometry) -> LandCoverEvidence:
            return LandCoverEvidence("land-cover-fake", 2020, {40: 1.0}, 10.0)

    with pytest.raises(AreaSearchError, match="best: 0%"):
        await search_area("Minneriya", "paddy", 1000, "LK", FakePlaces(MINNERIYA), Cloudy())


async def test_unknown_place() -> None:
    with pytest.raises(AreaSearchError) as error:
        await search_area("Nowhere", "tea", 1000, "LK", FakePlaces(), NorthEastCropland())
    assert error.value.code == "PLACE_NOT_FOUND"


async def test_rejects_area_sizes_outside_the_limits() -> None:
    with pytest.raises(ValueError, match="size_m"):
        await search_area(
            "Minneriya", "tea", 50_000, None, FakePlaces(MINNERIYA), NorthEastCropland()
        )


def test_area_ids_rebuild_the_searched_square() -> None:
    field = find_searched_area(" area_paddy_8.04652_80.90251_1000m ")
    assert field is not None
    assert field.id == "AREA_PADDY_8.04652_80.90251_1000M"
    assert field.crop == "paddy"
    assert field.time_zone == "auto"
    assert centroid(field.geometry) == pytest.approx((80.90251, 8.04652))
    assert field.geometry == square_around(80.90251, 8.04652, 1000)


@pytest.mark.parametrize(
    "field_id",
    [
        "AREA_RICE_8.04652_80.90251_1000M",
        "AREA_PADDY_8.04652_80.90251_99999M",
        "AREA_PADDY_95.00000_80.90251_1000M",
        "SL-PADDY-MINNERIYA",
    ],
)
def test_invalid_area_ids_are_not_found(field_id: str) -> None:
    assert find_searched_area(field_id) is None


def test_lookup_tries_registered_fields_then_area_ids() -> None:
    find = with_searched_areas(field_lookup(REGISTERED_FIELDS))
    assert find("sl-paddy-minneriya") == find_registered_field("SL-PADDY-MINNERIYA")
    assert find("AREA_TEA_6.97000_80.78000_500M") is not None
    assert find("SL-PADDY-UNKNOWN") is None


def test_square_around_has_the_requested_size() -> None:
    ring = square_around(80.9, 8.0, 1000).coordinates[0]
    assert ring[0] == ring[-1]
    width_degrees = ring[1][0] - ring[0][0]
    height_degrees = ring[2][1] - ring[1][1]
    assert height_degrees * 111_320 == pytest.approx(1000)
    assert width_degrees * 111_320 * 0.99027 == pytest.approx(1000, rel=1e-3)
