from __future__ import annotations

import re
from datetime import datetime
from statistics import median
from typing import Any


TIME_RE = re.compile(
    r"^\s*(\d+)[,.](\d+)"
)


def parse_time_raw(
    value: Any,
) -> dict[str, Any]:
    raw = (
        ""
        if value is None
        else str(value).strip()
    )

    lower = raw.lower()

    match = TIME_RE.match(
        lower
    )

    km_time = None

    if match:
        km_time = float(
            f"{match.group(1)}."
            f"{match.group(2)}"
        )

    broken = lower.startswith(
        "br"
    )

    disqualified = (
        lower.startswith("d")
        and not broken
    )

    gallop = (
        "g" in lower
    )

    numeric = (
        km_time is not None
    )

    clean_numeric = (
        numeric
        and not gallop
        and not disqualified
        and not broken
    )

    if clean_numeric:
        status = "CLEAN_NUMERIC"
    elif numeric and gallop:
        status = "NUMERIC_GALLOP"
    elif disqualified:
        status = "DISQUALIFIED"
    elif broken:
        status = "BROKEN"
    elif numeric:
        status = "NUMERIC_OTHER"
    elif raw:
        status = "OTHER"
    else:
        status = "EMPTY"

    return {
        "raw": raw,
        "kmTime": km_time,
        "gallop": gallop,
        "disqualified":
            disqualified,
        "broken": broken,
        "cleanNumeric":
            clean_numeric,
        "status": status,
    }


def extract_form_features(
    history: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    rows = sorted(
        history,
        key=lambda row: (
            datetime.fromisoformat(
                row["raceDate"]
            )
        ),
        reverse=True,
    )

    parsed = [
        {
            "raceDate":
                row["raceDate"],
            **parse_time_raw(
                row.get(
                    "timeRaw"
                )
            ),
        }
        for row in rows
    ]

    clean = [
        row["kmTime"]
        for row in parsed
        if row[
            "cleanNumeric"
        ]
    ]

    issue_count = sum(
        1
        for row in parsed
        if (
            row["gallop"]
            or row[
                "disqualified"
            ]
            or row["broken"]
        )
    )

    disqualification_count = sum(
        1
        for row in parsed
        if row[
            "disqualified"
        ]
    )

    broken_count = sum(
        1
        for row in parsed
        if row["broken"]
    )

    gallop_count = sum(
        1
        for row in parsed
        if row["gallop"]
    )

    weighted_time_sum = 0.0
    weighted_time_weight = 0.0

    weighted_issue_sum = 0.0
    weighted_issue_weight = 0.0

    for i, row in enumerate(
        parsed
    ):
        weight = (
            1.0 / (i + 1)
        )

        if row[
            "cleanNumeric"
        ]:
            weighted_time_sum += (
                row["kmTime"]
                * weight
            )

            weighted_time_weight += (
                weight
            )

        issue = (
            row["gallop"]
            or row[
                "disqualified"
            ]
            or row["broken"]
        )

        weighted_issue_sum += (
            float(issue)
            * weight
        )

        weighted_issue_weight += (
            weight
        )

    recent_weighted_time = (
        weighted_time_sum
        / weighted_time_weight
        if weighted_time_weight
        else None
    )

    recent_issue_rate = (
        weighted_issue_sum
        / weighted_issue_weight
        if weighted_issue_weight
        else 0.0
    )

    issue_rate = (
        issue_count
        / len(parsed)
        if parsed
        else 0.0
    )

    return {
        "historyCount":
            len(parsed),
        "cleanTimeCount":
            len(clean),
        "bestCleanKmTime":
            min(clean)
            if clean
            else None,
        "medianCleanKmTime":
            median(clean)
            if clean
            else None,
        "recentWeightedCleanKmTime":
            recent_weighted_time,
        "issueCount":
            issue_count,
        "issueRate":
            issue_rate,
        "recentIssueRate":
            recent_issue_rate,
        "gallopCount":
            gallop_count,
        "disqualificationCount":
            disqualification_count,
        "brokenCount":
            broken_count,
    }


def percentile_scores(
    values: list[
        float | None
    ],
    *,
    lower_is_better: bool,
) -> list[float]:
    """
    Field-relative score in [0, 1].

    Best observed value -> 1.
    Worst observed value -> 0.

    Missing values -> neutral 0.5.
    """

    valid = [
        value
        for value in values
        if value is not None
    ]

    if not valid:
        return [
            0.5
            for _ in values
        ]

    lo = min(valid)
    hi = max(valid)

    if hi == lo:
        return [
            (
                0.5
                if value is None
                else 1.0
            )
            for value in values
        ]

    scores = []

    for value in values:
        if value is None:
            scores.append(
                0.5
            )
            continue

        scaled = (
            (value - lo)
            / (hi - lo)
        )

        if lower_is_better:
            scaled = (
                1.0 - scaled
            )

        scores.append(
            scaled
        )

    return scores
