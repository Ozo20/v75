from __future__ import annotations

import json
import re
from collections import defaultdict
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

TARGET_KEY = (
    "ÅR_DNT#2026-07-11T00:00:00#6#12#Dju MA"
)


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def norm_name(value: Any) -> str | None:
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


observations = defaultdict(list)

total_history_rows = 0
rows_with_form_key = 0


for snapshot_day in DATES:
    pre = load(
        Path("data/normalized")
        / snapshot_day
        / "pre-race.json"
    )

    for leg in pre["legs"]:
        for entry in leg["entries"]:
            horse = entry["horse"]

            horse_id = str(
                horse[
                    "registrationNumber"
                ]
            )

            horse_name = horse[
                "name"
            ]

            for row in (
                entry.get("history")
                or []
            ):
                total_history_rows += 1

                form_key = row.get(
                    "formRowKey"
                )

                if not form_key:
                    continue

                rows_with_form_key += 1

                observations[
                    str(form_key)
                ].append(
                    {
                        "snapshotDay":
                            snapshot_day,
                        "horseId":
                            horse_id,
                        "horseName":
                            horse_name,
                        "driver":
                            norm_name(
                                row.get(
                                    "driver"
                                )
                            ),
                        "driverRaw":
                            row.get(
                                "driver"
                            ),
                        "raceDate":
                            row.get(
                                "raceDate"
                            ),
                        "trackCode":
                            row.get(
                                "trackCode"
                            ),
                        "raceNumber":
                            row.get(
                                "raceNumber"
                            ),
                        "startNumber":
                            row.get(
                                "startNumber"
                            ),
                        "placeRaw":
                            row.get(
                                "placeRaw"
                            ),
                    }
                )


def semantic_signature(
    row: dict[str, Any],
):
    return (
        row["horseId"],
        row["driver"],
        row["raceDate"],
        row["trackCode"],
        row["raceNumber"],
        row["startNumber"],
        str(row["placeRaw"]),
    )


def same_horse_signature(
    row: dict[str, Any],
):
    return (
        row["driver"],
        row["raceDate"],
        row["trackCode"],
        row["raceNumber"],
        row["startNumber"],
        str(row["placeRaw"]),
    )


duplicate_keys = 0
conflicting_keys = 0
cross_horse_collisions = 0
same_horse_conflicting_keys = 0

conflict_rows = []


for form_key, rows in (
    observations.items()
):
    if len(rows) <= 1:
        continue

    duplicate_keys += 1

    semantic = {
        semantic_signature(
            row
        )
        for row in rows
    }

    if len(semantic) <= 1:
        continue

    conflicting_keys += 1

    horse_ids = {
        row["horseId"]
        for row in rows
    }

    cross_horse = (
        len(horse_ids) > 1
    )

    if cross_horse:
        cross_horse_collisions += 1

    same_horse_conflict = False

    by_horse = defaultdict(list)

    for row in rows:
        by_horse[
            row["horseId"]
        ].append(
            row
        )

    for horse_id, horse_rows in (
        by_horse.items()
    ):
        signatures = {
            same_horse_signature(
                row
            )
            for row in horse_rows
        }

        if len(signatures) > 1:
            same_horse_conflict = True
            break

    if same_horse_conflict:
        same_horse_conflicting_keys += 1

    conflict_rows.append(
        {
            "formRowKey":
                form_key,
            "crossHorseCollision":
                cross_horse,
            "sameHorseConflict":
                same_horse_conflict,
            "horseIds":
                sorted(horse_ids),
            "observations":
                rows,
        }
    )


print(
    "=== FORMROWKEY COLLISION AUDIT ==="
)

print(
    f"Snapshots:                    "
    f"{len(DATES)}"
)

print(
    f"Historical rows:              "
    f"{total_history_rows}"
)

print(
    f"Rows with formRowKey:         "
    f"{rows_with_form_key}"
)

print(
    f"Keys seen >1 time:            "
    f"{duplicate_keys}"
)

print(
    f"Conflicting formRowKeys:      "
    f"{conflicting_keys}"
)

print(
    f"Cross-horse collisions:       "
    f"{cross_horse_collisions}"
)

print(
    f"Same-horse conflicting keys:  "
    f"{same_horse_conflicting_keys}"
)

print()

print(
    "=== TARGET FAILURE KEY ==="
)

target_rows = observations.get(
    TARGET_KEY,
    [],
)

print(
    f"formRowKey: {TARGET_KEY}"
)

print(
    f"observations: {len(target_rows)}"
)

for row in target_rows:
    print(
        json.dumps(
            row,
            ensure_ascii=False,
        )
    )


print()
print(
    "=== ALL CONFLICTING KEYS ==="
)

if not conflict_rows:
    print("None.")
else:
    for conflict in conflict_rows:
        print()
        print(
            "KEY:",
            conflict[
                "formRowKey"
            ],
        )

        print(
            "crossHorseCollision:",
            conflict[
                "crossHorseCollision"
            ],
        )

        print(
            "sameHorseConflict:",
            conflict[
                "sameHorseConflict"
            ],
        )

        print(
            "horseIds:",
            conflict[
                "horseIds"
            ],
        )

        unique_rows = {}

        for row in conflict[
            "observations"
        ]:
            signature = (
                semantic_signature(
                    row
                )
            )

            unique_rows.setdefault(
                signature,
                row,
            )

        for row in (
            unique_rows.values()
        ):
            print(
                " ",
                json.dumps(
                    row,
                    ensure_ascii=False,
                ),
            )


safe_composite_identity = (
    conflicting_keys > 0
    and cross_horse_collisions
    == conflicting_keys
    and same_horse_conflicting_keys
    == 0
)

print()
print(
    "=== IDENTITY CONCLUSION ==="
)

print(
    "All conflicts cross-horse only:",
    (
        conflicting_keys > 0
        and cross_horse_collisions
        == conflicting_keys
    ),
)

print(
    "Any same-horse semantic conflict:",
    (
        same_horse_conflicting_keys
        > 0
    ),
)

print(
    "Composite (horseId, formRowKey) "
    "supported by audit:",
    safe_composite_identity,
)


report = {
    "schemaVersion":
        "1.0",
    "scope":
        "pre-race-identity-inspection",
    "dates":
        DATES,
    "historicalRows":
        total_history_rows,
    "rowsWithFormRowKey":
        rows_with_form_key,
    "duplicateKeys":
        duplicate_keys,
    "conflictingKeys":
        conflicting_keys,
    "crossHorseCollisions":
        cross_horse_collisions,
    "sameHorseConflictingKeys":
        same_horse_conflicting_keys,
    "targetFailureKey":
        TARGET_KEY,
    "targetFailureObservations":
        target_rows,
    "compositeHorseIdFormRowKeySupported":
        safe_composite_identity,
    "conflicts":
        conflict_rows,
    "guardrails": {
        "outcomesRead":
            False,
        "marketRead":
            False,
        "candidateModified":
            False,
        "validationOutcomesConsumed":
            False,
    },
}

output = Path(
    "data/experiments/"
    "formrowkey-collision-audit.json"
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
