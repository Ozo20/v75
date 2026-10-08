from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from v75.baseline_safe_v1 import (
    build_safe_projection,
    score_entry as score_safe_v1,
)

from v75.form_features_v2 import (
    extract_form_features,
    percentile_scores,
)


MODEL_NAME = (
    "candidate-v2c-driver-continuity"
)

BASE_WEIGHT = 0.63
SPEED_WEIGHT = 0.27
DRIVER_CONTINUITY_WEIGHT = 0.10


def normalize_driver_name(
    value: Any,
) -> str | None:
    if value is None:
        return None

    text = re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    )

    return (
        text.casefold()
        if text
        else None
    )


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


def driver_continuity_features(
    entry: dict[str, Any],
) -> dict[str, Any]:

    current_driver = (
        normalize_driver_name(
            (
                entry.get("driver")
                or {}
            ).get("name")
        )
    )

    history = sorted(
        entry.get("history")
        or [],
        key=lambda row: (
            datetime.fromisoformat(
                row["raceDate"]
            )
        ),
        reverse=True,
    )

    if (
        not current_driver
        or not history
    ):
        return {
            "sameDriverLatest":
                False,
            "pairCount":
                0,
            "historyCount":
                len(history),
            "pairShare":
                0.0,
            "continuityRaw":
                0.0,
        }

    matches = [
        normalize_driver_name(
            row.get("driver")
        )
        == current_driver
        for row in history
    ]

    pair_count = sum(
        matches
    )

    pair_share = (
        pair_count
        / len(history)
    )

    same_driver_latest = (
        matches[0]
    )

    continuity_raw = (
        0.50
        * float(
            same_driver_latest
        )
        + 0.50
        * pair_share
    )

    return {
        "sameDriverLatest":
            same_driver_latest,
        "pairCount":
            pair_count,
        "historyCount":
            len(history),
        "pairShare":
            pair_share,
        "continuityRaw":
            continuity_raw,
    }


def score_field(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    base_scores = []
    speed_values = []
    driver_features = []

    for entry in entries:
        safe = build_safe_projection(
            entry
        )

        baseline = score_safe_v1(
            safe
        )

        form = extract_form_features(
            entry.get("history")
            or []
        )

        continuity = (
            driver_continuity_features(
                entry
            )
        )

        base_scores.append(
            float(
                baseline["score"]
            )
        )

        speed_values.append(
            form[
                "recentWeightedCleanKmTime"
            ]
        )

        driver_features.append(
            continuity
        )

    base_pct = percentile_high(
        base_scores
    )

    speed_pct = percentile_scores(
        speed_values,
        lower_is_better=True,
    )

    continuity_pct = (
        percentile_high(
            [
                row[
                    "continuityRaw"
                ]
                for row
                in driver_features
            ]
        )
    )

    result = []

    for i, entry in enumerate(
        entries
    ):
        combined = (
            BASE_WEIGHT
            * base_pct[i]
            + SPEED_WEIGHT
            * speed_pct[i]
            + DRIVER_CONTINUITY_WEIGHT
            * continuity_pct[i]
        )

        driver = (
            driver_features[i]
        )

        result.append(
            {
                "startNumber":
                    entry["startNumber"],
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
                    "safeBaselinePercentile":
                        round(
                            base_pct[i],
                            8,
                        ),
                    "speedPercentile":
                        round(
                            speed_pct[i],
                            8,
                        ),
                    "driverContinuityPercentile":
                        round(
                            continuity_pct[i],
                            8,
                        ),
                },
                "features": {
                    "sameDriverLatest":
                        driver[
                            "sameDriverLatest"
                        ],
                    "pairCount":
                        driver[
                            "pairCount"
                        ],
                    "historyCount":
                        driver[
                            "historyCount"
                        ],
                    "pairShare":
                        round(
                            driver[
                                "pairShare"
                            ],
                            8,
                        ),
                    "continuityRaw":
                        round(
                            driver[
                                "continuityRaw"
                            ],
                            8,
                        ),
                },
            }
        )

    result.sort(
        key=lambda row: (
            -row["score"],
            row["startNumber"],
        )
    )

    for rank, row in enumerate(
        result,
        1,
    ):
        row["rank"] = rank

    return result
