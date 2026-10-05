"""Curvature-aware terrain horizon computation."""

from science.horizon.engine import (
    HorizonProfile,
    combine_horizon_profiles,
    compute_horizon_profile,
)
from science.horizon.mask import build_one_degree_horizon_mask

__all__ = [
    "HorizonProfile",
    "combine_horizon_profiles",
    "compute_horizon_profile",
    "build_one_degree_horizon_mask",
]
