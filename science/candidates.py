"""NASA-published lunar south-pole reference points for comparative analysis.

These coordinates are centers of original LOLA DEM polygons in NASA's 2025
Lunar Surface Data Book, Table A2.1-1. They are *not* certified landing spots.
Connecting Ridge belonged to the 2022 thirteen-region Artemis list and was
not retained in the 2024 nine-region cohort. The other three are in that
cohort, which NASA now presents for the Artemis campaign rather than as
Artemis III touchdown commitments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


NASA_COORDINATE_SOURCE = (
    "https://ntrs.nasa.gov/api/citations/20250002845/downloads/"
    "M2M-30044%20Lunar%20Surface%20Data%20Book%20Baseline_Final.pdf?attachment=true"
)
NASA_NINE_REGION_SOURCE = (
    "https://www.nasa.gov/news-release/"
    "nasa-provides-update-on-artemis-iii-moon-landing-regions/"
)
NASA_THIRTEEN_REGION_SOURCE = (
    "https://www.nasa.gov/news-release/"
    "nasa-identifies-candidate-regions-for-landing-next-americans-on-moon/"
)


@dataclass(frozen=True)
class EvaluatedSite:
    id: str
    name: str
    latitude_deg: float
    longitude_deg_east: float
    kind: str
    region_status: Optional[str]
    coordinate_source_url: Optional[str]


EVALUATED_SITES: Tuple[EvaluatedSite, ...] = (
    EvaluatedSite(
        "test-site-a", "Test Site A", -89.9, 0.0,
        "validation", None, None,
    ),
    EvaluatedSite(
        "connecting-ridge", "Connecting Ridge", -89.4632, -137.49,
        "candidate", "historical_2022_cohort", NASA_COORDINATE_SOURCE,
    ),
    EvaluatedSite(
        "haworth", "Haworth", -86.7639, -22.777,
        "candidate", "current_2024_cohort", NASA_COORDINATE_SOURCE,
    ),
    EvaluatedSite(
        "malapert-massif", "Malapert Massif", -85.9948, -0.23578,
        "candidate", "current_2024_cohort", NASA_COORDINATE_SOURCE,
    ),
    EvaluatedSite(
        "nobile-rim-1", "Nobile Rim 1", -85.4381, 37.36667,
        "candidate", "current_2024_cohort", NASA_COORDINATE_SOURCE,
    ),
)
