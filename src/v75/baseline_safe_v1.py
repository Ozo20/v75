from __future__ import annotations

from datetime import datetime
from typing import Any


MODEL_NAME = "baseline-safe-v1"


def finish_position(value: Any) -> int:
    if value is None:
        return 0

    if isinstance(value, int):
        return max(value, 0)

    if isinstance(value, float):
        return max(int(value), 0)

    text = str(value).strip()

    if text.isdigit():
        return max(int(text), 0)

    return 0


def build_safe_projection(
    entry: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the ONLY object the scoring model is allowed to see.

    Deliberately excluded:
      - horseAnnualStatistics
      - career aggregates
      - total earnings
      - win/triple/gallop percentages
      - records
      - outcomes
      - market ranks
    """

    history = []

    for row in entry.get("history") or []:
        history.append(
            {
                "raceDate":
                    row.get("raceDate"),
                "placeRaw":
                    row.get("placeRaw"),
            }
        )

    return {
        "startNumber":
            entry["startNumber"],
        "start": {
            "postPosition":
                entry.get(
                    "start",
                    {},
                ).get(
                    "postPosition"
                ),
            "eligibleForPrediction":
                entry.get(
                    "start",
                    {},
                ).get(
                    "eligibleForPrediction",
                    False,
                ),
        },
        "history": history,
    }


def extract_features(
    safe_entry: dict[str, Any],
) -> dict[str, Any]:
    history = list(
        safe_entry.get(
            "history"
        )
        or []
    )

    history.sort(
        key=lambda row: (
            datetime.fromisoformat(
                row["raceDate"]
            )
        ),
        reverse=True,
    )

    positions = [
        finish_position(
            row.get("placeRaw")
        )
        for row in history
    ]

    observed_starts = len(
        positions
    )

    observed_wins = sum(
        1
        for position in positions
        if position == 1
    )

    observed_seconds = sum(
        1
        for position in positions
        if position == 2
    )

    observed_thirds = sum(
        1
        for position in positions
        if position == 3
    )

    observed_places = (
        observed_seconds
        + observed_thirds
    )

    observed_top3 = (
        observed_wins
        + observed_places
    )

    win_rate = (
        observed_wins
        / observed_starts
        if observed_starts
        else 0.0
    )

    top3_rate = (
        observed_top3
        / observed_starts
        if observed_starts
        else 0.0
    )

    post_raw = (
        safe_entry.get(
            "start",
            {},
        ).get("postPosition")
    )

    try:
        post = int(post_raw)
    except (TypeError, ValueError):
        post = 0

    return {
        "observedStarts":
            observed_starts,
        "observedWins":
            observed_wins,
        "observedSeconds":
            observed_seconds,
        "observedThirds":
            observed_thirds,
        "observedPlaces":
            observed_places,
        "observedTop3":
            observed_top3,
        "observedWinRate":
            win_rate,
        "observedTop3Rate":
            top3_rate,
        "lastPositions":
            positions[:4],
        "postPosition":
            post,
    }


def score_entry(
    safe_entry: dict[str, Any],
) -> dict[str, Any]:
    """
    Mechanical leakage-safe adaptation of the old baseline.

    We are NOT tuning weights against outcomes.

    Old unsafe annual components are replaced by statistics
    calculated only from historical form rows.

    Earnings are removed entirely.
    """

    f = extract_features(
        safe_entry
    )

    wins_points = (
        f["observedWins"]
        * 12.0
    )

    places_points = (
        f["observedPlaces"]
        * 4.5
    )

    win_rate_points = (
        f["observedWinRate"]
        * 28.0
    )

    activity_points = (
        min(
            f["observedStarts"],
            5,
        )
        * 0.7
    )

    recent_form_points = 0.0

    for i, position in enumerate(
        f["lastPositions"]
    ):
        weight = (
            1.0 / (i + 1)
        )

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
        "observedWins":
            wins_points,
        "observedPlaces":
            places_points,
        "observedWinRate":
            win_rate_points,
        "observedActivity":
            activity_points,
        "recentForm":
            recent_form_points,
        "post":
            post_points,
    }

    total = sum(
        components.values()
    )

    return {
        "score":
            round(total, 4),
        "features":
            f,
        "components": {
            key: round(
                value,
                4,
            )
            for key, value
            in components.items()
        },
    }
