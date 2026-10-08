from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any


DATES = [
    "2026-06-13",
    "2026-06-16",
    "2026-06-20",
    "2026-06-27",
    "2026-07-04",
    "2026-07-11",
    "2026-07-18",
    "2026-07-25",
    "2026-08-01",
    "2026-08-08",
    "2026-08-15",
    "2026-08-22",
    "2026-08-29",
    "2026-09-05",
    "2026-09-12",
    "2026-09-19",
]


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def as_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def row_date(row: dict[str, Any]) -> date:
    return date.fromisoformat(
        str(row["raceDate"])[:10]
    )


def placing(row: dict[str, Any]) -> int | None:
    raw = row.get("placeRaw")

    if raw is None:
        return None

    text = str(raw).strip()

    if text.isdigit():
        return int(text)

    return None


records_by_horse: dict[
    str,
    list[dict[str, Any]],
] = defaultdict(list)


for date_text in DATES:
    base = (
        Path("data/normalized")
        / date_text
    )

    pre = load(
        base / "pre-race.json"
    )

    outcomes = load(
        base / "outcomes.json"
    )

    outcome_by_leg = {
        row["leg"]: row
        for row in outcomes["legs"]
    }

    for leg in pre["legs"]:
        outcome = outcome_by_leg[
            leg["leg"]
        ]

        winner = int(
            outcome["winnerStartNumber"]
        )

        for entry in leg["entries"]:
            horse = entry["horse"]

            registration = horse.get(
                "registrationNumber"
            )

            if not registration:
                continue

            current_year = (
                entry.get(
                    "annualStatistics",
                    {},
                ).get("currentYear")
                or {}
            )

            records_by_horse[
                registration
            ].append(
                {
                    "date":
                        date.fromisoformat(
                            date_text
                        ),
                    "dateText":
                        date_text,
                    "raceDayName":
                        pre["raceDayName"],
                    "leg":
                        leg["leg"],
                    "raceNumber":
                        leg[
                            "raceNumber"
                        ],
                    "startNumber":
                        entry[
                            "startNumber"
                        ],
                    "name":
                        horse["name"],
                    "eligible":
                        entry["start"][
                            "eligibleForPrediction"
                        ],
                    "won":
                        (
                            entry[
                                "startNumber"
                            ]
                            == winner
                        ),
                    "starts":
                        as_int(
                            current_year.get(
                                "starts"
                            )
                        ),
                    "wins":
                        as_int(
                            current_year.get(
                                "wins"
                            )
                        ),
                    "earnings":
                        current_year.get(
                            "earnings"
                        ),
                    "history":
                        entry.get(
                            "history"
                        )
                        or [],
                }
            )


repeated_horses = {
    reg: sorted(
        records,
        key=lambda row: row["date"],
    )
    for reg, records
    in records_by_horse.items()
    if len(records) >= 2
}


exact_checks = 0
exact_matches = 0

possible_previous_target_included = 0
other_mismatches = 0

incomplete_history = 0
missing_previous_race_in_history = 0
missing_statistics = 0

examples_exact: list[str] = []
examples_included: list[str] = []
examples_mismatch: list[str] = []


for registration, records in (
    repeated_horses.items()
):
    for prev, curr in zip(
        records,
        records[1:],
    ):
        # A scratched horse did not produce
        # an additional race start.
        if not prev["eligible"]:
            continue

        if (
            prev["starts"] is None
            or curr["starts"] is None
            or prev["wins"] is None
            or curr["wins"] is None
        ):
            missing_statistics += 1
            continue

        history = curr["history"]

        if not history:
            incomplete_history += 1
            continue

        dates = [
            row_date(row)
            for row in history
        ]

        oldest = min(dates)

        # The later snapshot contains only
        # the five latest starts. We can make
        # an exact comparison only when those
        # five reach back to the previous
        # V75 appearance.
        if oldest > prev["date"]:
            incomplete_history += 1
            continue

        interval_rows = [
            row
            for row in history
            if (
                prev["date"]
                <= row_date(row)
                < curr["date"]
            )
        ]

        previous_day_rows = [
            row
            for row in interval_rows
            if row_date(row)
            == prev["date"]
        ]

        if not previous_day_rows:
            missing_previous_race_in_history += 1
            continue

        expected_start_delta = len(
            interval_rows
        )

        expected_win_delta = sum(
            1
            for row in interval_rows
            if placing(row) == 1
        )

        actual_start_delta = (
            curr["starts"]
            - prev["starts"]
        )

        actual_win_delta = (
            curr["wins"]
            - prev["wins"]
        )

        exact_checks += 1

        exact = (
            actual_start_delta
            == expected_start_delta
            and actual_win_delta
            == expected_win_delta
        )

        if exact:
            exact_matches += 1

            if len(examples_exact) < 8:
                examples_exact.append(
                    f"{prev['name']}: "
                    f"{prev['dateText']} -> "
                    f"{curr['dateText']} | "
                    f"starts "
                    f"{prev['starts']} -> "
                    f"{curr['starts']} "
                    f"(+{actual_start_delta}, "
                    f"history +"
                    f"{expected_start_delta}) | "
                    f"wins "
                    f"{prev['wins']} -> "
                    f"{curr['wins']} "
                    f"(+{actual_win_delta}, "
                    f"history +"
                    f"{expected_win_delta})"
                )

            continue

        # This is the characteristic pattern
        # we would expect if the previous
        # snapshot had ALREADY counted its
        # own target race.
        expected_if_prev_target_included_starts = (
            expected_start_delta - 1
        )

        expected_if_prev_target_included_wins = (
            expected_win_delta
            - (1 if prev["won"] else 0)
        )

        looks_like_previous_target_included = (
            actual_start_delta
            == expected_if_prev_target_included_starts
            and actual_win_delta
            == expected_if_prev_target_included_wins
        )

        description = (
            f"{prev['name']}: "
            f"{prev['dateText']} -> "
            f"{curr['dateText']} | "
            f"starts actual +"
            f"{actual_start_delta}, "
            f"history +"
            f"{expected_start_delta} | "
            f"wins actual +"
            f"{actual_win_delta}, "
            f"history +"
            f"{expected_win_delta} | "
            f"previous race won="
            f"{prev['won']}"
        )

        if looks_like_previous_target_included:
            possible_previous_target_included += 1

            if len(examples_included) < 15:
                examples_included.append(
                    description
                )
        else:
            other_mismatches += 1

            if len(examples_mismatch) < 15:
                examples_mismatch.append(
                    description
                )


print(
    f"Unique horses:                 "
    f"{len(records_by_horse)}"
)

print(
    f"Horses appearing >=2 times:   "
    f"{len(repeated_horses)}"
)

print(
    f"Exact point-in-time checks:    "
    f"{exact_checks}"
)

print(
    f"Exact matches:                 "
    f"{exact_matches}"
)

print(
    f"Prev-target-included pattern:  "
    f"{possible_previous_target_included}"
)

print(
    f"Other mismatches:              "
    f"{other_mismatches}"
)

print(
    f"Skipped: history too short:    "
    f"{incomplete_history}"
)

print(
    f"Skipped: prior race not found: "
    f"{missing_previous_race_in_history}"
)

print(
    f"Skipped: missing annual stats: "
    f"{missing_statistics}"
)


if examples_exact:
    print()
    print(
        "=== EXAMPLE EXACT MATCHES ==="
    )

    for item in examples_exact:
        print(item)


if examples_included:
    print()
    print(
        "=== POSSIBLE TARGET-RACE "
        "LEAKAGE PATTERN ==="
    )

    for item in examples_included:
        print(item)


if examples_mismatch:
    print()
    print(
        "=== OTHER MISMATCHES ==="
    )

    for item in examples_mismatch:
        print(item)


print()
print("=== VERDICT ===")

if exact_checks == 0:
    print(
        "INCONCLUSIVE: no exact "
        "cross-meeting checks available."
    )

elif (
    possible_previous_target_included == 0
    and other_mismatches == 0
):
    print(
        "PASS: all checkable annual-stat "
        "transitions match the later "
        "pre-race form history exactly."
    )

    print(
        "This is strong evidence that "
        "currentYear statistics are "
        "point-in-time rather than "
        "recomputed with later results."
    )

else:
    print(
        "WARNING: annual statistics do "
        "not consistently match the "
        "point-in-time history."
    )

    print(
        "Do NOT use currentYear fields "
        "for model development until "
        "the mismatches are understood."
    )
