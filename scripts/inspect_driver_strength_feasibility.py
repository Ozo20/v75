from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from v75.baseline_safe_v1 import (
    finish_position,
)


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
]


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def norm_name(
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


def row_date(
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


def row_identity(
    horse_id: str,
    row: dict[str, Any],
):
    form_key = row.get(
        "formRowKey"
    )

    if form_key:
        return (
            "formRowKey",
            str(form_key),
        )

    # Conservative fallback used only
    # if formRowKey is missing.
    return (
        "fallback",
        horse_id,
        row.get("raceDate"),
        row.get("trackCode"),
        row.get("raceNumber"),
        row.get("startNumber"),
    )


snapshots = {
    day: load(
        Path("data/normalized")
        / day
        / "pre-race.json"
    )
    for day in DATES
}


all_current_entries = 0

coverage = Counter()
corpus_stats = []

missing_form_key = 0
duplicate_rows = 0
conflicting_duplicates = 0
future_rows_rejected = 0

duplicate_conflict_examples = []


for target_day in DATES:
    target_date = date.fromisoformat(
        target_day
    )

    # Build only from snapshots that would
    # already exist by the target meeting.
    allowed_snapshot_days = [
        day
        for day in DATES
        if day <= target_day
    ]

    deduped = {}

    for source_day in (
        allowed_snapshot_days
    ):
        pre = snapshots[
            source_day
        ]

        for leg in pre["legs"]:
            for entry in leg["entries"]:
                horse_id = str(
                    entry["horse"][
                        "registrationNumber"
                    ]
                )

                for row in (
                    entry.get("history")
                    or []
                ):
                    race_date = (
                        row_date(row)
                    )

                    if race_date is None:
                        continue

                    if race_date >= target_date:
                        future_rows_rejected += 1
                        continue

                    driver = norm_name(
                        row.get("driver")
                    )

                    if not driver:
                        continue

                    identity = row_identity(
                        horse_id,
                        row,
                    )

                    if (
                        identity[0]
                        == "fallback"
                    ):
                        missing_form_key += 1

                    record = {
                        "horseId":
                            horse_id,
                        "driver":
                            driver,
                        "raceDate":
                            race_date.isoformat(),
                        "placeRaw":
                            row.get(
                                "placeRaw"
                            ),
                        "trackCode":
                            row.get(
                                "trackCode"
                            ),
                    }

                    existing = (
                        deduped.get(
                            identity
                        )
                    )

                    if existing is None:
                        deduped[
                            identity
                        ] = record
                        continue

                    duplicate_rows += 1

                    comparable_existing = {
                        "horseId":
                            existing[
                                "horseId"
                            ],
                        "driver":
                            existing[
                                "driver"
                            ],
                        "raceDate":
                            existing[
                                "raceDate"
                            ],
                        "placeRaw":
                            existing[
                                "placeRaw"
                            ],
                        "trackCode":
                            existing[
                                "trackCode"
                            ],
                    }

                    if (
                        comparable_existing
                        != record
                    ):
                        conflicting_duplicates += 1

                        if (
                            len(
                                duplicate_conflict_examples
                            )
                            < 20
                        ):
                            duplicate_conflict_examples.append(
                                {
                                    "identity":
                                        repr(
                                            identity
                                        ),
                                    "existing":
                                        comparable_existing,
                                    "new":
                                        record,
                                }
                            )

    driver_rows = defaultdict(
        list
    )

    for record in (
        deduped.values()
    ):
        driver_rows[
            record["driver"]
        ].append(
            record
        )

    target_pre = snapshots[
        target_day
    ]

    meeting_entries = 0

    meeting_thresholds = Counter()

    for leg in target_pre[
        "legs"
    ]:
        for entry in leg[
            "entries"
        ]:
            if not entry["start"][
                "eligibleForPrediction"
            ]:
                continue

            meeting_entries += 1
            all_current_entries += 1

            current_driver = norm_name(
                (
                    entry.get("driver")
                    or {}
                ).get("name")
            )

            horse_id = str(
                entry["horse"][
                    "registrationNumber"
                ]
            )

            rows = (
                driver_rows.get(
                    current_driver,
                    []
                )
                if current_driver
                else []
            )

            other_horse_rows = [
                row
                for row in rows
                if row[
                    "horseId"
                ] != horse_id
            ]

            starts = len(rows)
            other_starts = len(
                other_horse_rows
            )

            valid_finishes = [
                finish_position(
                    row.get(
                        "placeRaw"
                    )
                )
                for row in (
                    other_horse_rows
                )
            ]

            valid_finishes = [
                value
                for value
                in valid_finishes
                if value > 0
            ]

            for threshold in (
                1,
                3,
                5,
                10,
                20,
                30,
            ):
                if starts >= threshold:
                    coverage[
                        f"allStartsAtLeast{threshold}"
                    ] += 1

                    meeting_thresholds[
                        f"allStartsAtLeast{threshold}"
                    ] += 1

                if (
                    other_starts
                    >= threshold
                ):
                    coverage[
                        f"otherHorseStartsAtLeast{threshold}"
                    ] += 1

                    meeting_thresholds[
                        f"otherHorseStartsAtLeast{threshold}"
                    ] += 1

                if (
                    len(
                        valid_finishes
                    )
                    >= threshold
                ):
                    coverage[
                        f"otherHorseValidFinishAtLeast{threshold}"
                    ] += 1

                    meeting_thresholds[
                        f"otherHorseValidFinishAtLeast{threshold}"
                    ] += 1

    corpus_stats.append(
        {
            "date":
                target_day,
            "raceDayName":
                target_pre[
                    "raceDayName"
                ],
            "sourceSnapshots":
                len(
                    allowed_snapshot_days
                ),
            "dedupedHistoricalStarts":
                len(deduped),
            "uniqueHistoricalDrivers":
                len(driver_rows),
            "currentEntries":
                meeting_entries,
            "coverage":
                dict(
                    meeting_thresholds
                ),
        }
    )


print(
    "=== POINT-IN-TIME DRIVER STRENGTH FEASIBILITY ==="
)

print(
    f"Development meetings:       "
    f"{len(DATES)}"
)

print(
    f"Current entries:            "
    f"{all_current_entries}"
)

print()

print(
    "=== CORPUS INTEGRITY ==="
)

print(
    f"Rows without formRowKey:    "
    f"{missing_form_key}"
)

print(
    f"Duplicate observations:     "
    f"{duplicate_rows}"
)

print(
    f"Conflicting duplicates:     "
    f"{conflicting_duplicates}"
)

print(
    f"Rows rejected >= target:    "
    f"{future_rows_rejected}"
)

print()

print(
    "=== CURRENT DRIVER COVERAGE ==="
)

for threshold in (
    1,
    3,
    5,
    10,
    20,
    30,
):
    all_count = coverage[
        f"allStartsAtLeast{threshold}"
    ]

    other_count = coverage[
        f"otherHorseStartsAtLeast{threshold}"
    ]

    finish_count = coverage[
        f"otherHorseValidFinishAtLeast{threshold}"
    ]

    print(
        f">= {threshold:>2} prior starts "
        f"| any horse "
        f"{all_count:>4}/"
        f"{all_current_entries} "
        f"({100*all_count/all_current_entries:5.1f}%) "
        f"| other horses "
        f"{other_count:>4}/"
        f"{all_current_entries} "
        f"({100*other_count/all_current_entries:5.1f}%) "
        f"| valid finishes "
        f"{finish_count:>4}/"
        f"{all_current_entries} "
        f"({100*finish_count/all_current_entries:5.1f}%)"
    )

print()

print(
    "=== POINT-IN-TIME CORPUS GROWTH ==="
)

for row in corpus_stats:
    coverage_row = row[
        "coverage"
    ]

    count5 = coverage_row.get(
        "otherHorseValidFinishAtLeast5",
        0,
    )

    count10 = coverage_row.get(
        "otherHorseValidFinishAtLeast10",
        0,
    )

    total = row[
        "currentEntries"
    ]

    print(
        f"{row['date']} "
        f"{row['raceDayName']:<14} "
        f"snapshots="
        f"{row['sourceSnapshots']:>2} "
        f"dedupStarts="
        f"{row['dedupedHistoricalStarts']:>4} "
        f"drivers="
        f"{row['uniqueHistoricalDrivers']:>3} "
        f"| >=5 valid "
        f"{count5:>3}/{total:<3} "
        f"({100*count5/total:5.1f}%) "
        f"| >=10 valid "
        f"{count10:>3}/{total:<3} "
        f"({100*count10/total:5.1f}%)"
    )

if duplicate_conflict_examples:
    print()
    print(
        "=== SAMPLE DUPLICATE CONFLICTS ==="
    )

    for row in (
        duplicate_conflict_examples
    ):
        print(
            json.dumps(
                row,
                ensure_ascii=False,
            )
        )


report = {
    "schemaVersion":
        "1.0",
    "scope":
        "development-only-point-in-time",
    "dates":
        DATES,
    "currentEntries":
        all_current_entries,
    "coverage":
        dict(coverage),
    "corpusStats":
        corpus_stats,
    "integrity": {
        "missingFormRowKey":
            missing_form_key,
        "duplicateObservations":
            duplicate_rows,
        "conflictingDuplicates":
            conflicting_duplicates,
        "rowsRejectedAtOrAfterTargetDate":
            future_rows_rejected,
    },
    "design": {
        "sourceSnapshots":
            "development snapshots dated <= target date only",
        "rowFilter":
            "history raceDate strictly < target date",
        "deduplication":
            "formRowKey; conservative fallback if absent",
        "driverIdentity":
            "normalized driver name",
        "otherHorseCoverageMeasured":
            True,
        "futureSnapshotsUsed":
            False,
        "futureOutcomesUsed":
            False,
    },
    "guardrails": {
        "developmentOnly":
            True,
        "validationUsed":
            False,
        "oldHoldoutUsed":
            False,
        "robustnessSetUsed":
            False,
        "freshSystemSetUsed":
            False,
        "marketUsed":
            False,
        "targetOutcomesRead":
            False,
        "championModified":
            False,
    },
}

output = Path(
    "data/experiments/"
    "driver-strength-feasibility.json"
)

output.write_text(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

print()
print(
    f"Report: {output}"
)
