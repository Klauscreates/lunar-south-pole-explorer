"""Grid-resolved continuous availability interval extraction."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from science.config import utc_iso


def build_window_summary(
    samples: Sequence[Dict[str, Any]], end_time: datetime
) -> Dict[str, Any]:
    timestamps = [
        datetime.fromisoformat(sample["timestamp"].replace("Z", "+00:00"))
        for sample in samples
    ]
    sun_visible = [sample["sun"]["visibility_fraction"] > 0.0 for sample in samples]
    earth_visible = [
        sample["earth"]["visibility_fraction"] > 0.0 for sample in samples
    ]

    sunlight = _condition_summary(timestamps, sun_visible, end_time)
    shadow = _condition_summary(
        timestamps, [not value for value in sun_visible], end_time
    )
    dte = _condition_summary(timestamps, earth_visible, end_time)
    dte_blackout = _condition_summary(
        timestamps, [not value for value in earth_visible], end_time
    )

    combined_conditions = {
        "SUN_VISIBLE_EARTH_VISIBLE": [
            sun and earth for sun, earth in zip(sun_visible, earth_visible)
        ],
        "SUN_VISIBLE_EARTH_BLOCKED": [
            sun and not earth for sun, earth in zip(sun_visible, earth_visible)
        ],
        "SUN_BLOCKED_EARTH_VISIBLE": [
            not sun and earth for sun, earth in zip(sun_visible, earth_visible)
        ],
        "SUN_BLOCKED_EARTH_BLOCKED": [
            not sun and not earth for sun, earth in zip(sun_visible, earth_visible)
        ],
    }
    combined = {
        name: _condition_summary(timestamps, condition, end_time)
        for name, condition in combined_conditions.items()
    }
    return {
        "method": (
            "left-closed sample-grid intervals; each state applies from its "
            "timestamp to the next timestamp, so transition timing precision "
            "is bounded by the configured step"
        ),
        "solar": {
            "sunlight": sunlight,
            "shadow": shadow,
            "illumination_percentage": sunlight["percentage"],
            "longest_continuous_sunlight_seconds": sunlight[
                "longest_duration_seconds"
            ],
            "longest_continuous_darkness_seconds": shadow[
                "longest_duration_seconds"
            ],
        },
        "earth": {
            "dte_visible": dte,
            "dte_blackout": dte_blackout,
            "earth_visible_percentage": dte["percentage"],
            "longest_dte_window_seconds": dte["longest_duration_seconds"],
            "longest_dte_blackout_seconds": dte_blackout[
                "longest_duration_seconds"
            ],
        },
        "combined": combined,
    }


def _condition_summary(
    timestamps: Sequence[datetime],
    condition: Sequence[bool],
    end_time: datetime,
) -> Dict[str, Any]:
    intervals = extract_boolean_windows(timestamps, condition, end_time)
    total_seconds = sum(interval["duration_seconds"] for interval in intervals)
    total_span = (end_time - timestamps[0]).total_seconds() if timestamps else 0.0
    longest = max(
        (interval["duration_seconds"] for interval in intervals), default=0.0
    )
    return {
        "intervals": intervals,
        "interval_count": len(intervals),
        "total_duration_seconds": round(total_seconds, 3),
        "total_duration_hours": round(total_seconds / 3600.0, 6),
        "percentage": round(
            (100.0 * total_seconds / total_span) if total_span > 0 else 0.0,
            6,
        ),
        "longest_duration_seconds": round(longest, 3),
        "longest_duration_hours": round(longest / 3600.0, 6),
    }


def extract_boolean_windows(
    timestamps: Sequence[datetime],
    condition: Sequence[bool],
    end_time: datetime,
) -> List[Dict[str, Any]]:
    if len(timestamps) != len(condition):
        raise ValueError("timestamps and condition lengths differ")
    if not timestamps:
        return []
    boundaries = list(timestamps[1:]) + [end_time]
    intervals: List[Dict[str, Any]] = []
    run_start: Optional[datetime] = None
    run_end: Optional[datetime] = None
    for timestamp, boundary, active in zip(timestamps, boundaries, condition):
        if active and run_start is None:
            run_start = timestamp
        if active:
            run_end = boundary
        if run_start is not None and (not active or boundary >= end_time):
            if active and boundary < end_time:
                continue
            if run_end is not None and run_end > run_start:
                duration = (run_end - run_start).total_seconds()
                intervals.append(
                    {
                        "start_utc": utc_iso(run_start),
                        "end_utc": utc_iso(run_end),
                        "duration_seconds": round(duration, 3),
                        "duration_hours": round(duration / 3600.0, 6),
                    }
                )
            run_start = None
            run_end = None
    return intervals
