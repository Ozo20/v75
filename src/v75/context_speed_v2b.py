from __future__ import annotations

from datetime import datetime
from typing import Any

from v75.form_features_v2 import (
    parse_time_raw,
)


def infer_current_method(
    value: Any,
) -> str:
    text = str(
        value or ""
    ).upper()

    if "AUTO" in text:
        return "AUTO"

    if "VOLT" in text:
        return "NON_AUTO"

    return "UNKNOWN"


def infer_historical_method(
    time_raw: Any,
) -> str:
    parsed = parse_time_raw(
        time_raw
    )

    if not parsed[
        "cleanNumeric"
    ]:
        return "UNKNOWN"

    text = str(
        time_raw or ""
    ).lower()

    if "a" in text:
        return "AUTO"

    return "NON_AUTO"


def context_weighted_speed(
    history: list[
        dict[str, Any]
    ],
    *,
    current_distance: int,
    current_start_method: Any,
) -> dict[str, Any]:
    """
    Select the most relevant clean historical
    speed context without using outcomes or
    aggregate statistics.

    Priority:
      1 same method + within 200m
      2 same method
      3 within 200m
      4 any clean time

    Within the selected tier, retain the
    original recency weighting 1/(i+1).
    """

    current_method = (
        infer_current_method(
            current_start_method
        )
    )

    ordered = sorted(
        history,
        key=lambda row: (
            datetime.fromisoformat(
                row["raceDate"]
            )
        ),
        reverse=True,
    )

    clean_rows = []

    for recency_index, row in enumerate(
        ordered
    ):
        parsed = parse_time_raw(
            row.get("timeRaw")
        )

        if not parsed[
            "cleanNumeric"
        ]:
            continue

        try:
            distance = int(
                row.get("distance")
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        hist_method = (
            infer_historical_method(
                row.get("timeRaw")
            )
        )

        delta = abs(
            distance
            - current_distance
        )

        same_method = (
            current_method
            != "UNKNOWN"
            and hist_method
            == current_method
        )

        clean_rows.append(
            {
                "kmTime":
                    float(
                        parsed[
                            "kmTime"
                        ]
                    ),
                "distance":
                    distance,
                "distanceDelta":
                    delta,
                "historicalMethod":
                    hist_method,
                "sameMethod":
                    same_method,
                "within200m":
                    delta <= 200,
                "recencyIndex":
                    recency_index,
            }
        )

    if not clean_rows:
        return {
            "contextKmTime":
                None,
            "tier":
                "NO_CLEAN_TIME",
            "rowsUsed":
                0,
            "cleanRowsAvailable":
                0,
            "currentMethod":
                current_method,
        }

    tier1 = [
        row
        for row in clean_rows
        if (
            row["sameMethod"]
            and row["within200m"]
        )
    ]

    tier2 = [
        row
        for row in clean_rows
        if row["sameMethod"]
    ]

    tier3 = [
        row
        for row in clean_rows
        if row["within200m"]
    ]

    if tier1:
        selected = tier1
        tier = (
            "SAME_METHOD_WITHIN_200M"
        )
    elif tier2:
        selected = tier2
        tier = "SAME_METHOD"
    elif tier3:
        selected = tier3
        tier = "WITHIN_200M"
    else:
        selected = clean_rows
        tier = "ANY_CLEAN"

    weighted_sum = 0.0
    weight_sum = 0.0

    for row in selected:
        weight = (
            1.0
            / (
                row[
                    "recencyIndex"
                ]
                + 1
            )
        )

        weighted_sum += (
            row["kmTime"]
            * weight
        )

        weight_sum += weight

    context_time = (
        weighted_sum
        / weight_sum
    )

    return {
        "contextKmTime":
            context_time,
        "tier":
            tier,
        "rowsUsed":
            len(selected),
        "cleanRowsAvailable":
            len(clean_rows),
        "currentMethod":
            current_method,
        "meanDistanceDelta":
            sum(
                row[
                    "distanceDelta"
                ]
                for row in selected
            )
            / len(selected),
    }
