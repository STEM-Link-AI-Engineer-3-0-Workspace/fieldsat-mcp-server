"""Satellite formula and fixture tests."""

import pytest

from fieldsat.domain.evidence import SatelliteEvidence, SatellitePeriodEvidence
from fieldsat.domain.fields import RegisteredField, find_registered_field
from fieldsat.domain.satellite import (
    calculate_ndvi_change_percentage,
    classify_data_quality,
    classify_field_uniformity,
    classify_trend,
    get_satellite_analysis,
)
from fieldsat.providers.fixtures import FIXTURE_SATELLITE_PROVIDER


def field(field_id: str) -> RegisteredField:
    result = find_registered_field(field_id)
    if result is None:
        raise AssertionError(f"Missing test field {field_id}")
    return result


@pytest.mark.asyncio
async def test_canonical_webinar_evidence() -> None:
    result = await get_satellite_analysis(
        field("SL-PADDY-MINNERIYA"), 14, FIXTURE_SATELLITE_PROVIDER
    )
    assert result.model_dump() == {
        "field_id": "SL-PADDY-MINNERIYA",
        "current_mean_ndvi": 0.56,
        "previous_mean_ndvi": 0.66,
        "ndvi_change_percentage": -15.2,
        "trend": "significant_decline",
        "ndvi_standard_deviation": 0.17,
        "field_uniformity": "uneven",
        "valid_observations": 4,
        "average_cloud_coverage_percentage": 11.0,
        "data_quality": "good",
        "provider_notes": None,
    }


def test_change_formula_and_documented_trend_boundaries() -> None:
    assert calculate_ndvi_change_percentage(0.56, 0.66) == pytest.approx(-15.1515, abs=0.0001)
    assert classify_trend(-15.1) == "significant_decline"
    assert classify_trend(-15) == "moderate_decline"
    assert classify_trend(-5) == "stable"
    assert classify_trend(5) == "stable"
    assert classify_trend(15) == "moderate_increase"
    assert classify_trend(15.1) == "significant_increase"


def test_uniformity_uses_coefficient_of_variation() -> None:
    assert classify_field_uniformity(0.5, 0.05) == "uniform"
    assert classify_field_uniformity(0.5, 0.075) == "moderately_variable"
    assert classify_field_uniformity(0.5, 0.11) == "uneven"


@pytest.mark.asyncio
async def test_insufficient_observations_are_poor_quality() -> None:
    from fieldsat.providers.fixtures import find_test_field

    poor_field = find_test_field("SL-PADDY-POOR")
    assert poor_field is not None
    result = await get_satellite_analysis(poor_field, 14, FIXTURE_SATELLITE_PROVIDER)
    assert result.valid_observations == 1
    assert result.data_quality == "poor"


def test_moderate_quality_between_explicit_gates() -> None:
    evidence = SatelliteEvidence(
        source="sentinel-2-l2a-fixture",
        current=SatellitePeriodEvidence(0.5, 0.05),
        previous=SatellitePeriodEvidence(0.5, 0.05),
        valid_observations=3,
        average_cloud_coverage_percentage=25,
        usable_pixel_percentage=70,
        periods_comparable=True,
    )
    assert classify_data_quality(evidence) == "moderate"
