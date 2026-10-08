from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
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
]


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def normalize_name(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.casefold()


def scalar_paths(
    value: Any,
    prefix: str = "",
):
    if isinstance(value, dict):
        for key, child in value.items():
            path = (
                f"{prefix}.{key}"
                if prefix
                else key
            )

            if isinstance(
                child,
                (dict, list),
            ):
                yield from scalar_paths(
                    child,
                    path,
                )
            else:
                yield (
                    path,
                    key,
                    child,
                )

    elif isinstance(value, list):
        for child in value:
            yield from scalar_paths(
                child,
                prefix + "[]",
            )


def find_first_by_key(
    value: Any,
    keys: tuple[str, ...],
):
    priorities = {
        key.casefold(): i
        for i, key
        in enumerate(keys)
    }

    candidates = []

    for path, key, child in scalar_paths(
        value
    ):
        lower = key.casefold()

        if lower not in priorities:
            continue

        if child is None:
            continue

        if isinstance(
            child,
            str,
        ) and not child.strip():
            continue

        candidates.append(
            (
                priorities[lower],
                path,
                child,
            )
        )

    if not candidates:
        return None, None

    candidates.sort(
        key=lambda row: (
            row[0],
            row[1],
        )
    )

    _, path, child = candidates[0]

    return child, path


current_paths = Counter()
history_paths = Counter()

current_examples = defaultdict(list)
history_examples = defaultdict(list)

entries = 0
history_rows = 0

horse_ids_present = 0

current_driver_id_present = 0
current_driver_name_present = 0

history_driver_id_present = 0
history_driver_name_present = 0

current_driver_ids = Counter()
current_driver_names = Counter()

history_driver_ids = Counter()
history_driver_names = Counter()

# Current-ID -> observed current names.
id_to_current_names = defaultdict(
    Counter
)

# Current normalized name -> observed IDs.
current_name_to_ids = defaultdict(
    Counter
)

# Horse -> all historical normalized driver names.
horse_history_driver_names = defaultdict(
    list
)

# Current horse-driver name pairs.
current_pair_seen_in_history = 0
current_pair_has_2_history_rows = 0
current_pair_has_3_history_rows = 0

history_rows_with_driver_and_horse = 0


for date in DATES:
    pre = load(
        Path("data/normalized")
        / date
        / "pre-race.json"
    )

    for leg in pre["legs"]:
        for entry in leg["entries"]:
            if not entry["start"][
                "eligibleForPrediction"
            ]:
                continue

            entries += 1

            for path, key, value in scalar_paths(
                entry
            ):
                if "driver" in key.casefold():
                    current_paths[path] += 1

                    if (
                        len(
                            current_examples[path]
                        )
                        < 5
                        and value
                        not in current_examples[path]
                    ):
                        current_examples[
                            path
                        ].append(
                            value
                        )

            horse_id, horse_path = (
                find_first_by_key(
                    entry,
                    (
                        "horseRegistrationNumber",
                    ),
                )
            )

            if horse_id is not None:
                horse_ids_present += 1

            driver_id, driver_id_path = (
                find_first_by_key(
                    entry,
                    (
                        "driverId",
                    ),
                )
            )

            driver_name, driver_name_path = (
                find_first_by_key(
                    entry,
                    (
                        "driverFullName",
                        "driverName",
                        "driver",
                    ),
                )
            )

            if driver_id is not None:
                current_driver_id_present += 1
                current_driver_ids[
                    str(driver_id)
                ] += 1

            normalized_current_name = (
                normalize_name(
                    driver_name
                )
            )

            if normalized_current_name:
                current_driver_name_present += 1
                current_driver_names[
                    normalized_current_name
                ] += 1

            if (
                driver_id is not None
                and normalized_current_name
            ):
                id_to_current_names[
                    str(driver_id)
                ][
                    normalized_current_name
                ] += 1

                current_name_to_ids[
                    normalized_current_name
                ][
                    str(driver_id)
                ] += 1

            historical_names = []

            for row in (
                entry.get("history")
                or []
            ):
                history_rows += 1

                for (
                    path,
                    key,
                    value,
                ) in scalar_paths(row):
                    if (
                        "driver"
                        in key.casefold()
                    ):
                        history_paths[
                            path
                        ] += 1

                        if (
                            len(
                                history_examples[
                                    path
                                ]
                            )
                            < 5
                            and value
                            not in history_examples[
                                path
                            ]
                        ):
                            history_examples[
                                path
                            ].append(
                                value
                            )

                hist_driver_id, _ = (
                    find_first_by_key(
                        row,
                        (
                            "driverId",
                        ),
                    )
                )

                hist_driver_name, _ = (
                    find_first_by_key(
                        row,
                        (
                            "driverFullName",
                            "driverName",
                            "driver",
                        ),
                    )
                )

                if hist_driver_id is not None:
                    history_driver_id_present += 1
                    history_driver_ids[
                        str(
                            hist_driver_id
                        )
                    ] += 1

                normalized_hist_name = (
                    normalize_name(
                        hist_driver_name
                    )
                )

                if normalized_hist_name:
                    history_driver_name_present += 1
                    history_driver_names[
                        normalized_hist_name
                    ] += 1

                    historical_names.append(
                        normalized_hist_name
                    )

                    if horse_id is not None:
                        history_rows_with_driver_and_horse += 1

                        horse_history_driver_names[
                            str(horse_id)
                        ].append(
                            normalized_hist_name
                        )

            if normalized_current_name:
                repeats = sum(
                    name
                    == normalized_current_name
                    for name
                    in historical_names
                )

                if repeats >= 1:
                    current_pair_seen_in_history += 1

                if repeats >= 2:
                    current_pair_has_2_history_rows += 1

                if repeats >= 3:
                    current_pair_has_3_history_rows += 1


print(
    "=== DRIVER FEATURE FEASIBILITY ==="
)

print(
    f"Development entries:         "
    f"{entries}"
)

print(
    f"Historical form rows:        "
    f"{history_rows}"
)

print()

print(
    "=== CURRENT STARTER IDENTITY ==="
)

print(
    f"Horse registration ID:       "
    f"{horse_ids_present}/{entries} "
    f"({100 * horse_ids_present / entries:.1f}%)"
)

print(
    f"Current driver ID:           "
    f"{current_driver_id_present}/{entries} "
    f"({100 * current_driver_id_present / entries:.1f}%)"
)

print(
    f"Current driver name:         "
    f"{current_driver_name_present}/{entries} "
    f"({100 * current_driver_name_present / entries:.1f}%)"
)

print(
    f"Unique current driver IDs:   "
    f"{len(current_driver_ids)}"
)

print(
    f"Unique current driver names: "
    f"{len(current_driver_names)}"
)

print()

print(
    "=== HISTORICAL DRIVER IDENTITY ==="
)

print(
    f"History rows with driver ID: "
    f"{history_driver_id_present}/{history_rows} "
    f"({100 * history_driver_id_present / history_rows:.1f}%)"
)

print(
    f"History rows with name:      "
    f"{history_driver_name_present}/{history_rows} "
    f"({100 * history_driver_name_present / history_rows:.1f}%)"
)

print(
    f"Unique history driver IDs:   "
    f"{len(history_driver_ids)}"
)

print(
    f"Unique history names:        "
    f"{len(history_driver_names)}"
)

print()

print(
    "=== DRIVER-LIKE PATHS: CURRENT ENTRY ==="
)

for path, count in (
    current_paths.most_common()
):
    print(
        f"{path:<55} "
        f"{count:>5} "
        f"examples="
        f"{current_examples[path]}"
    )

print()

print(
    "=== DRIVER-LIKE PATHS: HISTORY ROW ==="
)

for path, count in (
    history_paths.most_common()
):
    print(
        f"{path:<55} "
        f"{count:>5} "
        f"examples="
        f"{history_examples[path]}"
    )

print()

print(
    "=== CURRENT DRIVER ID/NAME CONSISTENCY ==="
)

ambiguous_ids = {
    driver_id: names
    for driver_id, names
    in id_to_current_names.items()
    if len(names) > 1
}

ambiguous_names = {
    name: ids
    for name, ids
    in current_name_to_ids.items()
    if len(ids) > 1
}

print(
    f"IDs mapping to >1 current name: "
    f"{len(ambiguous_ids)}"
)

print(
    f"Names mapping to >1 current ID: "
    f"{len(ambiguous_names)}"
)

if ambiguous_ids:
    print(
        "Sample ambiguous IDs:"
    )

    for driver_id, names in list(
        ambiguous_ids.items()
    )[:10]:
        print(
            f"  {driver_id}: "
            f"{dict(names)}"
        )

if ambiguous_names:
    print(
        "Sample ambiguous names:"
    )

    for name, ids in list(
        ambiguous_names.items()
    )[:10]:
        print(
            f"  {name}: "
            f"{dict(ids)}"
        )

print()

print(
    "=== HORSE × CURRENT DRIVER REPEAT COVERAGE ==="
)

print(
    "NOTE: this section matches normalized "
    "driver names only; it is diagnostic, "
    "not yet the production identity contract."
)

print(
    f"At least 1 prior row together: "
    f"{current_pair_seen_in_history}/{entries} "
    f"({100 * current_pair_seen_in_history / entries:.1f}%)"
)

print(
    f"At least 2 prior rows together: "
    f"{current_pair_has_2_history_rows}/{entries} "
    f"({100 * current_pair_has_2_history_rows / entries:.1f}%)"
)

print(
    f"At least 3 prior rows together: "
    f"{current_pair_has_3_history_rows}/{entries} "
    f"({100 * current_pair_has_3_history_rows / entries:.1f}%)"
)

print()

print(
    "=== MOST COMMON CURRENT DRIVERS ==="
)

for name, count in (
    current_driver_names.most_common(20)
):
    print(
        f"{count:>4}  {name}"
    )

print()

print(
    "=== MOST COMMON HISTORICAL DRIVERS ==="
)

for name, count in (
    history_driver_names.most_common(20)
):
    print(
        f"{count:>4}  {name}"
    )

report = {
    "schemaVersion":
        "1.0",
    "scope":
        "development-only-read-only",
    "dates":
        DATES,
    "entries":
        entries,
    "historyRows":
        history_rows,
    "current": {
        "horseRegistrationIdCoverage":
            horse_ids_present / entries,
        "driverIdCoverage":
            current_driver_id_present / entries,
        "driverNameCoverage":
            current_driver_name_present / entries,
        "uniqueDriverIds":
            len(current_driver_ids),
        "uniqueDriverNames":
            len(current_driver_names),
    },
    "history": {
        "driverIdCoverage":
            (
                history_driver_id_present
                / history_rows
            ),
        "driverNameCoverage":
            (
                history_driver_name_present
                / history_rows
            ),
        "uniqueDriverIds":
            len(history_driver_ids),
        "uniqueDriverNames":
            len(history_driver_names),
    },
    "pairDiagnostic": {
        "identityBasis":
            "normalized-driver-name",
        "atLeast1PriorRow":
            current_pair_seen_in_history,
        "atLeast2PriorRows":
            current_pair_has_2_history_rows,
        "atLeast3PriorRows":
            current_pair_has_3_history_rows,
        "coverageAtLeast1":
            (
                current_pair_seen_in_history
                / entries
            ),
    },
    "identityConsistency": {
        "currentIdsWithMultipleNames":
            len(ambiguous_ids),
        "currentNamesWithMultipleIds":
            len(ambiguous_names),
    },
    "guardrails": {
        "outcomesRead":
            False,
        "marketRead":
            False,
        "validationUsed":
            False,
        "holdoutUsed":
            False,
    },
}

output = Path(
    "data/experiments/"
    "driver-feature-feasibility.json"
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
