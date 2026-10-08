from __future__ import annotations

from typing import Any

from v75.baseline_safe_v1 import (
    build_safe_projection,
    score_entry as score_safe_v1,
)

from v75.form_features_v2 import (
    extract_form_features,
    percentile_scores,
)


MODEL_NAME = "candidate-v2a-speed"

BASE_WEIGHT = 0.70
SPEED_WEIGHT = 0.30


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


def score_field(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    base_scores = []
    speed_values = []
    feature_rows = []

    for entry in entries:
        safe = build_safe_projection(
            entry
        )

        baseline = score_safe_v1(
            safe
        )

        form = extract_form_features(
            entry.get("history") or []
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

        feature_rows.append(
            form
        )

    base_pct = percentile_high(
        base_scores
    )

    speed_pct = percentile_scores(
        speed_values,
        lower_is_better=True,
    )

    result = []

    for i, entry in enumerate(entries):
        combined = (
            BASE_WEIGHT
            * base_pct[i]
            + SPEED_WEIGHT
            * speed_pct[i]
        )

        result.append(
            {
                "startNumber":
                    entry["startNumber"],
                "horseName":
                    entry["horse"]["name"],
                "score":
                    round(combined, 8),
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
                },
                "features": {
                    "recentWeightedCleanKmTime":
                        feature_rows[i][
                            "recentWeightedCleanKmTime"
                        ],
                    "cleanTimeCount":
                        feature_rows[i][
                            "cleanTimeCount"
                        ],
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
