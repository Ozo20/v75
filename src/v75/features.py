from __future__ import annotations

from datetime import datetime
from typing import Any


def as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(
    value: Any,
    default: float = 0.0,
) -> float:
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def finish_position(value: Any) -> int:
    """
    Convert a raw placing to an integer.

    Non-numeric results deliberately become 0 rather than
    disappearing, so a recent gallop/disqualification still
    consumes one of the recent-form slots.
    """
    if isinstance(value, int):
        return max(value, 0)

    if isinstance(value, float):
        return max(int(value), 0)

    if isinstance(value, str):
        text = value.strip()

        if text.isdigit():
            return max(int(text), 0)

    return 0


def extract_baseline_features(
    entry: dict[str, Any],
) -> dict[str, Any]:
    stats = (
        entry.get("annualStatistics", {})
        .get("currentYear")
        or {}
    )

    starts = as_int(stats.get("starts"))
    wins = as_int(stats.get("wins"))
    seconds = as_int(stats.get("seconds"))
    thirds = as_int(stats.get("thirds"))
    places = seconds + thirds

    earnings = as_float(
        stats.get("earnings")
    )

    win_rate = (
        wins / starts
        if starts > 0
        else 0.0
    )

    history = list(
        entry.get("history") or []
    )

    history.sort(
        key=lambda row: datetime.fromisoformat(
            row["raceDate"]
        ),
        reverse=True,
    )

    last_positions = [
        finish_position(
            row.get("placeRaw")
        )
        for row in history[:4]
    ]

    post_position = as_int(
        entry.get("start", {}).get(
            "postPosition"
        )
    )

    return {
        "startsCurrentYear": starts,
        "winsCurrentYear": wins,
        "secondsCurrentYear": seconds,
        "thirdsCurrentYear": thirds,
        "placesCurrentYear": places,
        "earningsCurrentYear": earnings,
        "winRateCurrentYear": win_rate,
        "lastPositions": last_positions,
        "postPosition": post_position,
    }
