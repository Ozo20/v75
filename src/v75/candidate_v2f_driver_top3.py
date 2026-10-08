from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

from v75.baseline_safe_v1 import (
    build_safe_projection,
    finish_position,
    score_entry,
)

from v75.form_features_v2 import (
    extract_form_features,
    percentile_scores,
)


MODEL_NAME = (
    "candidate-v2f-driver-top3"
)

BASE_WEIGHT = 0.63
SPEED_WEIGHT = 0.27
DRIVER_TOP3_WEIGHT = 0.10

PRIOR_STRENGTH = 10.0
MIN_OTHER_HORSE_VALID_FINISHES = 3


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


def parse_race_date(
    row: dict[str, Any],
) -> date | None:
    value = row.get(
        "raceDate"
    )

    if not value:
        return None

    try:
        return date.fromisoformat(
            str(value)[:10]
        )
    except ValueError:
        return None


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


def build_driver_corpus(
    snapshots: dict[
        str,
        dict[str, Any],
    ],
    target_day: str,
) -> dict[str, Any]:

    target_date = (
        date.fromisoformat(
            target_day
        )
    )

    deduped = {}

    for source_day in sorted(
        snapshots
    ):
        if source_day > target_day:
            continue

        pre = snapshots[
            source_day
        ]

        for leg in pre["legs"]:
            for entry in leg[
                "entries"
            ]:
                horse_id = str(
                    entry[
                        "horse"
                    ][
                        "registrationNumber"
                    ]
                )

                for row in (
                    entry.get("history")
                    or []
                ):
                    race_date = (
                        parse_race_date(
                            row
                        )
                    )

                    if (
                        race_date is None
                        or race_date
                        >= target_date
                    ):
                        continue

                    driver = (
                        normalize_driver_name(
                            row.get(
                                "driver"
                            )
                        )
                    )

                    form_key = (
                        row.get(
                            "formRowKey"
                        )
                    )

                    if (
                        not driver
                        or not form_key
                    ):
                        continue

                    record = {
                        "horseId":
                            horse_id,
                        "driver":
                            driver,
                        "place":
                            finish_position(
                                row.get(
                                    "placeRaw"
                                )
                            ),
                    }

                    identity = str(
                        form_key
                    )

                    existing = (
                        deduped.get(
                            identity
                        )
                    )

                    if existing is None:
                        deduped[
                            identity
                        ] = record

                    elif existing != record:
                        raise RuntimeError(
                            "Conflicting duplicate "
                            f"formRowKey "
                            f"{identity!r}"
                        )

    global_valid = 0
    global_top3 = 0

    driver_stats = defaultdict(
        lambda: {
            "valid": 0,
            "top3": 0,
        }
    )

    driver_horse_stats = defaultdict(
        lambda: {
            "valid": 0,
            "top3": 0,
        }
    )

    for record in (
        deduped.values()
    ):
        place = record[
            "place"
        ]

        if place <= 0:
            continue

        global_valid += 1

        if place <= 3:
            global_top3 += 1

        driver = record[
            "driver"
        ]

        horse_id = record[
            "horseId"
        ]

        driver_stats[
            driver
        ][
            "valid"
        ] += 1

        driver_horse_stats[
            (
                driver,
                horse_id,
            )
        ][
            "valid"
        ] += 1

        if place <= 3:
            driver_stats[
                driver
            ][
                "top3"
            ] += 1

            driver_horse_stats[
                (
                    driver,
                    horse_id,
                )
            ][
                "top3"
            ] += 1

    if global_valid <= 0:
        raise RuntimeError(
            "No valid historical finishes."
        )

    return {
        "dedupedStarts":
            len(deduped),
        "globalValid":
            global_valid,
        "globalTop3":
            global_top3,
        "globalTop3Rate":
            (
                global_top3
                / global_valid
            ),
        "driverStats":
            driver_stats,
        "driverHorseStats":
            driver_horse_stats,
    }


def driver_top3_strength(
    corpus: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:

    driver = (
        normalize_driver_name(
            (
                entry.get("driver")
                or {}
            ).get("name")
        )
    )

    horse_id = str(
        entry[
            "horse"
        ][
            "registrationNumber"
        ]
    )

    if not driver:
        return {
            "valid":
                0,
            "top3":
                0,
            "top3Rate":
                None,
        }

    total = (
        corpus[
            "driverStats"
        ].get(
            driver,
            {
                "valid": 0,
                "top3": 0,
            },
        )
    )

    own = (
        corpus[
            "driverHorseStats"
        ].get(
            (
                driver,
                horse_id,
            ),
            {
                "valid": 0,
                "top3": 0,
            },
        )
    )

    valid = (
        total["valid"]
        - own["valid"]
    )

    top3 = (
        total["top3"]
        - own["top3"]
    )

    if (
        valid
        < MIN_OTHER_HORSE_VALID_FINISHES
    ):
        return {
            "valid":
                valid,
            "top3":
                top3,
            "top3Rate":
                None,
        }

    rate = (
        top3
        + PRIOR_STRENGTH
        * corpus[
            "globalTop3Rate"
        ]
    ) / (
        valid
        + PRIOR_STRENGTH
    )

    return {
        "valid":
            valid,
        "top3":
            top3,
        "top3Rate":
            rate,
    }


def score_field(
    entries: list[
        dict[str, Any]
    ],
    corpus: dict[str, Any],
) -> list[dict[str, Any]]:

    base_scores = []
    speed_values = []
    driver_rows = []

    for entry in entries:
        safe = (
            build_safe_projection(
                entry
            )
        )

        baseline = (
            score_entry(
                safe
            )
        )

        form = (
            extract_form_features(
                entry.get(
                    "history"
                )
                or []
            )
        )

        strength = (
            driver_top3_strength(
                corpus,
                entry,
            )
        )

        base_scores.append(
            float(
                baseline[
                    "score"
                ]
            )
        )

        speed_values.append(
            form[
                "recentWeightedCleanKmTime"
            ]
        )

        driver_rows.append(
            strength
        )

    base_pct = (
        percentile_high(
            base_scores
        )
    )

    speed_pct = (
        percentile_scores(
            speed_values,
            lower_is_better=True,
        )
    )

    driver_pct = (
        percentile_scores(
            [
                row[
                    "top3Rate"
                ]
                for row
                in driver_rows
            ],
            lower_is_better=False,
        )
    )

    result = []

    for i, entry in enumerate(
        entries
    ):
        score = (
            BASE_WEIGHT
            * base_pct[i]
            + SPEED_WEIGHT
            * speed_pct[i]
            + DRIVER_TOP3_WEIGHT
            * driver_pct[i]
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
                        score,
                        8,
                    ),
                "components": {
                    "basePercentile":
                        round(
                            base_pct[i],
                            8,
                        ),
                    "speedPercentile":
                        round(
                            speed_pct[i],
                            8,
                        ),
                    "driverTop3Percentile":
                        round(
                            driver_pct[i],
                            8,
                        ),
                },
                "driverStrength": {
                    "otherHorseValid":
                        driver_rows[
                            i
                        ][
                            "valid"
                        ],
                    "otherHorseTop3":
                        driver_rows[
                            i
                        ][
                            "top3"
                        ],
                    "shrunkTop3Rate":
                        (
                            None
                            if driver_rows[
                                i
                            ][
                                "top3Rate"
                            ]
                            is None
                            else round(
                                driver_rows[
                                    i
                                ][
                                    "top3Rate"
                                ],
                                8,
                            )
                        ),
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
