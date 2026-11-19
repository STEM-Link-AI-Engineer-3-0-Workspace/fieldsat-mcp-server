"""Satellite aggregation and STEM Link demonstration classifications."""

from typing import Literal

from fieldsat.domain.contracts import SatelliteContext
from fieldsat.domain.evidence import SatelliteEvidence
from fieldsat.domain.fields import RegisteredField
from fieldsat.providers.base import SatelliteEvidenceProvider

type NdviTrend = Literal[
    "significant_decline",
    "moderate_decline",
    "stable",
    "moderate_increase",
    "significant_increase",
]
type FieldUniformity = Literal["uniform", "moderately_variable", "uneven"]
type DataQuality = Literal["good", "moderate", "poor"]


def calculate_ndvi_change_percentage(current_mean_ndvi: float, previous_mean_ndvi: float) -> float:
    if previous_mean_ndvi == 0:
        raise ValueError("Previous mean NDVI must be non-zero.")
    return ((current_mean_ndvi - previous_mean_ndvi) / previous_mean_ndvi) * 100


def classify_trend(change_percentage: float) -> NdviTrend:
    if change_percentage < -15:
        return "significant_decline"
    if change_percentage < -5:
        return "moderate_decline"
    if change_percentage <= 5:
        return "stable"
    if change_percentage <= 15:
        return "moderate_increase"
    return "significant_increase"


def classify_field_uniformity(mean_ndvi: float, standard_deviation: float) -> FieldUniformity:
    if mean_ndvi == 0:
        return "uneven"
    coefficient_of_variation = abs(standard_deviation / mean_ndvi)
    if coefficient_of_variation <= 0.1:
        return "uniform"
    if coefficient_of_variation <= 0.2:
        return "moderately_variable"
    return "uneven"


def classify_data_quality(evidence: SatelliteEvidence) -> DataQuality:
    if (
        evidence.valid_observations < 2
        or evidence.average_cloud_coverage_percentage > 60
        or evidence.usable_pixel_percentage < 40
        or not evidence.periods_comparable
    ):
        return "poor"
    if (
        evidence.valid_observations >= 4
        and evidence.average_cloud_coverage_percentage <= 20
        and evidence.usable_pixel_percentage >= 80
    ):
        return "good"
    return "moderate"


async def get_satellite_analysis(
    field: RegisteredField,
    comparison_days: int,
    provider: SatelliteEvidenceProvider,
) -> SatelliteContext:
    if comparison_days < 1:
        raise ValueError("comparison_days must be a positive integer.")

    evidence = await provider.get_period_summary(field, comparison_days)
    raw_change = calculate_ndvi_change_percentage(
        evidence.current.mean_ndvi, evidence.previous.mean_ndvi
    )
    return SatelliteContext(
        field_id=field.id,
        current_mean_ndvi=evidence.current.mean_ndvi,
        previous_mean_ndvi=evidence.previous.mean_ndvi,
        ndvi_change_percentage=round(raw_change, 1),
        trend=classify_trend(raw_change),
        ndvi_standard_deviation=evidence.current.ndvi_standard_deviation,
        field_uniformity=classify_field_uniformity(
            evidence.current.mean_ndvi, evidence.current.ndvi_standard_deviation
        ),
        valid_observations=evidence.valid_observations,
        average_cloud_coverage_percentage=evidence.average_cloud_coverage_percentage,
        data_quality=classify_data_quality(evidence),
        provider_notes=evidence.provider_notes,
    )
