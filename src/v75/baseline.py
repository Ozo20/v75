from __future__ import annotations

from typing import Any

from .features import (
    extract_baseline_features,
)


MODEL_NAME = "baseline-v1"


def score_entry(
    entry: dict[str, Any],
) -> dict[str, Any]:
    """
    Preserve the original prototype scoring philosophy.

    This is intentionally simple and transparent.
    It is a benchmark, not yet an optimized model.
    """

    f = extract_baseline_features(entry)

    wins_points = (
        f["winsCurrentYear"] * 12.0
    )

    places_points = (
        f["placesCurrentYear"] * 4.5
    )

    if f["startsCurrentYear"] > 0:
        win_rate_points = (
            f["winRateCurrentYear"]
            * 28.0
        )

        activity_points = (
            min(
                f["startsCurrentYear"],
                14,
            )
            * 0.7
        )
    else:
        win_rate_points = 0.0
        activity_points = 0.0

    earnings_points = min(
        f["earningsCurrentYear"]
        / 12_000.0,
        28.0,
    )

    recent_form_points = 0.0

    for i, position in enumerate(
        f["lastPositions"]
    ):
        weight = 1.0 / (i + 1)

        if position == 1:
            recent_form_points += (
                9.0 * weight
            )
        elif 1 < position <= 3:
            recent_form_points += (
                4.5 * weight
            )
        elif 3 < position <= 5:
            recent_form_points += (
                1.8 * weight
            )

    post = f["postPosition"]

    if 1 <= post <= 4:
        post_points = 2.8
    elif post >= 9:
        post_points = -1.8
    else:
        post_points = 0.0

    components = {
        "wins": wins_points,
        "places": places_points,
        "winRate": win_rate_points,
        "activity": activity_points,
        "earnings": earnings_points,
        "recentForm": recent_form_points,
        "post": post_points,
    }

    total = sum(
        components.values()
    )

    return {
        "score": round(total, 4),
        "features": f,
        "components": {
            key: round(value, 4)
            for key, value
            in components.items()
        },
    }
