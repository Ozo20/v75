from __future__ import annotations

from datetime import datetime
from math import pow
from typing import Any

from v75.baseline_safe_v1 import (
    build_safe_projection,
    finish_position,
)
from v75.form_features_v2 import (
    parse_time_raw,
    percentile_scores,
)


MODEL_NAME = (
    "candidate-v2g-temporal-recency"
)

BASE_WEIGHT = 0.70
SPEED_WEIGHT = 0.30

# Frozen before outcome scoring.
#
# Rationale:
# median historical inter-start gap
# observed in the pre-race corpus = 16 days.
# Use two median gaps as the half-life.
HALF_LIFE_DAYS = 32.0


def percentile_high(
    values: list[float],
) -> list[float]:
    if not values:
        return []

    lo = min(values)
    hi = max(values)

    if lo == hi:
        return [
            1.0
            for _ in values
        ]

    return [
        (value - lo)
        / (hi - lo)
        for value in values
    ]


def ordered_history(
    history: list[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    return sorted(
        history,
        key=lambda row:
            datetime.fromisoformat(
                row["raceDate"]
            ),
        reverse=True,
    )


def temporal_weight(
    *,
    latest: datetime,
    current: datetime,
) -> float:
    age_days = max(
        0.0,
        (
            latest
            - current
        ).total_seconds()
        / 86400.0,
    )

    return pow(
        2.0,
        -age_days
        / HALF_LIFE_DAYS,
    )


def temporal_baseline_score(
    entry: dict[str, Any],
) -> dict[str, Any]:
    safe = build_safe_projection(
        entry
    )

    history = ordered_history(
        safe.get(
            "history"
        )
        or []
    )

    post_raw = (
        safe.get(
            "start",
            {},
        ).get(
            "postPosition"
        )
    )

    try:
        post = int(
            post_raw
        )
    except (
        TypeError,
        ValueError,
    ):
        post = 0

    if not history:
        weights = []
        positions = []
    else:
        latest = (
            datetime.fromisoformat(
                history[0][
                    "raceDate"
                ]
            )
        )

        weights = [
            temporal_weight(
                latest=latest,
                current=
                    datetime.fromisoformat(
                        row[
                            "raceDate"
                        ]
                    ),
            )
            for row
            in history
        ]

        positions = [
            finish_position(
                row.get(
                    "placeRaw"
                )
            )
            for row
            in history
        ]

    weighted_starts = sum(
        weights
    )

    weighted_wins = sum(
        weight
        for position, weight
        in zip(
            positions,
            weights,
        )
        if position == 1
    )

    weighted_places = sum(
        weight
        for position, weight
        in zip(
            positions,
            weights,
        )
        if position in (
            2,
            3,
        )
    )

    weighted_win_rate = (
        weighted_wins
        / weighted_starts
        if weighted_starts
        else 0.0
    )

    recent_form_points = 0.0

    for position, weight in zip(
        positions,
        weights,
    ):
        if position == 1:
            recent_form_points += (
                9.0
                * weight
            )
        elif 1 < position <= 3:
            recent_form_points += (
                4.5
                * weight
            )
        elif 3 < position <= 5:
            recent_form_points += (
                1.8
                * weight
            )

    wins_points = (
        weighted_wins
        * 12.0
    )

    places_points = (
        weighted_places
        * 4.5
    )

    win_rate_points = (
        weighted_win_rate
        * 28.0
    )

    activity_points = (
        min(
            weighted_starts,
            5.0,
        )
        * 0.7
    )

    if 1 <= post <= 4:
        post_points = 2.8
    elif post >= 9:
        post_points = -1.8
    else:
        post_points = 0.0

    components = {
        "temporalWins":
            wins_points,
        "temporalPlaces":
            places_points,
        "temporalWinRate":
            win_rate_points,
        "temporalActivity":
            activity_points,
        "temporalRecentForm":
            recent_form_points,
        "post":
            post_points,
    }

    return {
        "score":
            sum(
                components.values()
            ),
        "weightedStarts":
            weighted_starts,
        "components":
            components,
    }


def temporal_speed(
    history: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    rows = ordered_history(
        history
    )

    if not rows:
        return {
            "value":
                None,
            "cleanTimeCount":
                0,
        }

    latest = datetime.fromisoformat(
        rows[0][
            "raceDate"
        ]
    )

    weighted_sum = 0.0
    weight_sum = 0.0
    clean_count = 0

    for row in rows:
        parsed = parse_time_raw(
            row.get(
                "timeRaw"
            )
        )

        if not parsed[
            "cleanNumeric"
        ]:
            continue

        dt = datetime.fromisoformat(
            row[
                "raceDate"
            ]
        )

        weight = temporal_weight(
            latest=latest,
            current=dt,
        )

        weighted_sum += (
            float(
                parsed["kmTime"]
            )
            * weight
        )

        weight_sum += (
            weight
        )

        clean_count += 1

    return {
        "value":
            (
                weighted_sum
                / weight_sum
                if weight_sum
                else None
            ),
        "cleanTimeCount":
            clean_count,
    }


def score_field(
    entries: list[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    baseline_values = []
    speed_values = []
    features = []

    for entry in entries:
        baseline = (
            temporal_baseline_score(
                entry
            )
        )

        speed = temporal_speed(
            entry.get(
                "history"
            )
            or []
        )

        baseline_values.append(
            float(
                baseline[
                    "score"
                ]
            )
        )

        speed_values.append(
            speed[
                "value"
            ]
        )

        features.append(
            {
                "baseline":
                    baseline,
                "speed":
                    speed,
            }
        )

    baseline_pct = (
        percentile_high(
            baseline_values
        )
    )

    speed_pct = (
        percentile_scores(
            speed_values,
            lower_is_better=True,
        )
    )

    result = []

    for i, entry in enumerate(
        entries
    ):
        combined = (
            BASE_WEIGHT
            * baseline_pct[i]
            + SPEED_WEIGHT
            * speed_pct[i]
        )

        result.append(
            {
                "startNumber":
                    entry[
                        "startNumber"
                    ],
                "horseName":
                    entry[
                        "horse"
                    ][
                        "name"
                    ],
                "score":
                    round(
                        combined,
                        8,
                    ),
                "components": {
                    "temporalBaselinePercentile":
                        round(
                            baseline_pct[i],
                            8,
                        ),
                    "temporalSpeedPercentile":
                        round(
                            speed_pct[i],
                            8,
                        ),
                },
                "features": {
                    "halfLifeDays":
                        HALF_LIFE_DAYS,
                    "weightedStarts":
                        round(
                            features[i][
                                "baseline"
                            ][
                                "weightedStarts"
                            ],
                            8,
                        ),
                    "temporalWeightedCleanKmTime":
                        features[i][
                            "speed"
                        ][
                            "value"
                        ],
                    "cleanTimeCount":
                        features[i][
                            "speed"
                        ][
                            "cleanTimeCount"
                        ],
                },
            }
        )

    result.sort(
        key=lambda row: (
            -row["score"],
            row[
                "startNumber"
            ],
        )
    )

    for rank, row in enumerate(
        result,
        1,
    ):
        row["rank"] = rank

    return result
