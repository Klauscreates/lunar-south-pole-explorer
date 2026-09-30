"""Terrain acquisition and sampling."""

from science.terrain.lola import (
    PreparedTerrain,
    prepare_lola_crop,
    sample_pgda_psr_classification,
)

__all__ = [
    "PreparedTerrain",
    "prepare_lola_crop",
    "sample_pgda_psr_classification",
]
