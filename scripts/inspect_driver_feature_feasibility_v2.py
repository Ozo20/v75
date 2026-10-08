from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path


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


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def normalize_name(value):
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


entries = 0
history_rows = 0

horse_id_present = 0
driver_id_present = 0
driver_name_present = 0
history_driver_present = 0

driver_ids = Counter()
driver_names = Counter()
history_driver_names = Counter()

id_to_names = defaultdict(set)
name_to_ids = defaultdict(set)

pair_repeats = Counter()

same_driver_latest = 0
same_driver_any = 0
same_driver_2plus = 0
same_driver_3plus = 0

# Pass 1:
# establish stable current driver
# name -> ID crosswalk.
all_entries = []

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

            horse_id = (
                entry.get("horse", {})
                .get("registrationNumber")
            )

            driver = (
                entry.get("driver")
                or {}
            )

            driver_id = driver.get("id")
            driver_name = driver.get("name")

            normalized_driver = (
                normalize_name(
                    driver_name
                )
            )

            if horse_id:
                horse_id_present += 1

            if driver_id:
                driver_id_present += 1
                driver_ids[
                    str(driver_id)
                ] += 1

            if normalized_driver:
                driver_name_present += 1
                driver_names[
                    normalized_driver
                ] += 1

            if (
                driver_id
                and normalized_driver
            ):
                id_to_names[
                    str(driver_id)
                ].add(
                    normalized_driver
                )

                name_to_ids[
                    normalized_driver
                ].add(
                    str(driver_id)
                )

            all_entries.append(
                (
                    date,
                    entry,
                    normalized_driver,
                )
            )


ambiguous_ids = {
    key: values
    for key, values
    in id_to_names.items()
    if len(values) > 1
}

ambiguous_names = {
    key: values
    for key, values
    in name_to_ids.items()
    if len(values) > 1
}

unique_name_to_id = {
    name: next(iter(ids))
    for name, ids
    in name_to_ids.items()
    if len(ids) == 1
}


# Pass 2:
# inspect historical names and true
# horse × CURRENT driver continuity.
mapped_history_rows = 0

unmapped_history_names = Counter()

for (
    date,
    entry,
    current_driver_name,
) in all_entries:

    history = (
        entry.get("history")
        or []
    )

    historical_names = []

    for row in history:
        history_rows += 1

        name = normalize_name(
            row.get("driver")
        )

        if name:
            history_driver_present += 1

            history_driver_names[
                name
            ] += 1

            historical_names.append(
                name
            )

            if name in (
                unique_name_to_id
            ):
                mapped_history_rows += 1
            else:
                unmapped_history_names[
                    name
                ] += 1

    if not current_driver_name:
        continue

    repeat_count = sum(
        historical_name
        == current_driver_name
        for historical_name
        in historical_names
    )

    pair_repeats[
        repeat_count
    ] += 1

    if repeat_count >= 1:
        same_driver_any += 1

    if repeat_count >= 2:
        same_driver_2plus += 1

    if repeat_count >= 3:
        same_driver_3plus += 1

    if (
        historical_names
        and historical_names[0]
        == current_driver_name
    ):
        same_driver_latest += 1


print(
    "=== DRIVER FEATURE FEASIBILITY V2 ==="
)

print(
    f"Development entries:           "
    f"{entries}"
)

print(
    f"Historical form rows:          "
    f"{history_rows}"
)

print()

print(
    "=== CURRENT IDENTITY ==="
)

print(
    f"Horse registration number:     "
    f"{horse_id_present}/{entries} "
    f"({100*horse_id_present/entries:.1f}%)"
)

print(
    f"Driver ID:                     "
    f"{driver_id_present}/{entries} "
    f"({100*driver_id_present/entries:.1f}%)"
)

print(
    f"Driver name:                   "
    f"{driver_name_present}/{entries} "
    f"({100*driver_name_present/entries:.1f}%)"
)

print(
    f"Unique driver IDs:             "
    f"{len(driver_ids)}"
)

print(
    f"Unique driver names:           "
    f"{len(driver_names)}"
)

print()

print(
    "=== IDENTITY CONSISTENCY ==="
)

print(
    f"IDs mapping to >1 name:        "
    f"{len(ambiguous_ids)}"
)

print(
    f"Names mapping to >1 ID:        "
    f"{len(ambiguous_names)}"
)

print(
    f"Unique name -> ID mappings:    "
    f"{len(unique_name_to_id)}"
)

if ambiguous_ids:
    print(
        "Sample ambiguous IDs:"
    )

    for key, values in list(
        ambiguous_ids.items()
    )[:10]:
        print(
            f"  {key}: "
            f"{sorted(values)}"
        )

if ambiguous_names:
    print(
        "Sample ambiguous names:"
    )

    for key, values in list(
        ambiguous_names.items()
    )[:10]:
        print(
            f"  {key}: "
            f"{sorted(values)}"
        )

print()

print(
    "=== HISTORICAL DRIVER COVERAGE ==="
)

print(
    f"Rows with driver name:         "
    f"{history_driver_present}/{history_rows} "
    f"({100*history_driver_present/history_rows:.1f}%)"
)

print(
    f"Unique historical names:       "
    f"{len(history_driver_names)}"
)

print(
    f"Rows mappable to stable ID:    "
    f"{mapped_history_rows}/{history_rows} "
    f"({100*mapped_history_rows/history_rows:.1f}%)"
)

print(
    f"Unmapped historical names:     "
    f"{len(unmapped_history_names)}"
)

print()

print(
    "=== TRUE HORSE × CURRENT DRIVER COVERAGE ==="
)

print(
    f"Current driver drove last start: "
    f"{same_driver_latest}/{entries} "
    f"({100*same_driver_latest/entries:.1f}%)"
)

print(
    f"At least 1 prior start together: "
    f"{same_driver_any}/{entries} "
    f"({100*same_driver_any/entries:.1f}%)"
)

print(
    f"At least 2 prior starts together:"
    f" {same_driver_2plus}/{entries} "
    f"({100*same_driver_2plus/entries:.1f}%)"
)

print(
    f"At least 3 prior starts together:"
    f" {same_driver_3plus}/{entries} "
    f"({100*same_driver_3plus/entries:.1f}%)"
)

print()

print(
    "=== PAIR REPEAT DISTRIBUTION ==="
)

for repeats in sorted(
    pair_repeats
):
    count = pair_repeats[
        repeats
    ]

    print(
        f"{repeats} prior starts: "
        f"{count:>4} "
        f"({100*count/entries:5.1f}%)"
    )

print()

print(
    "=== MOST COMMON UNMAPPED HISTORY DRIVERS ==="
)

for name, count in (
    unmapped_history_names
    .most_common(20)
):
    print(
        f"{count:>4}  {name}"
    )


report = {
    "schemaVersion":
        "2.0",
    "scope":
        "development-only-read-only",
    "dates":
        DATES,
    "entries":
        entries,
    "historyRows":
        history_rows,
    "currentIdentity": {
        "horseRegistrationCoverage":
            horse_id_present / entries,
        "driverIdCoverage":
            driver_id_present / entries,
        "driverNameCoverage":
            driver_name_present / entries,
        "uniqueDriverIds":
            len(driver_ids),
        "uniqueDriverNames":
            len(driver_names),
    },
    "identityConsistency": {
        "idsWithMultipleNames":
            len(ambiguous_ids),
        "namesWithMultipleIds":
            len(ambiguous_names),
        "uniqueNameToIdMappings":
            len(unique_name_to_id),
    },
    "historicalIdentity": {
        "driverNameCoverage":
            history_driver_present
            / history_rows,
        "rowsMappedToStableCurrentId":
            mapped_history_rows,
        "mappedCoverage":
            mapped_history_rows
            / history_rows,
        "uniqueHistoricalNames":
            len(history_driver_names),
    },
    "horseDriverContinuity": {
        "sameDriverLatest":
            same_driver_latest,
        "sameDriverLatestRate":
            same_driver_latest / entries,
        "atLeast1":
            same_driver_any,
        "atLeast1Rate":
            same_driver_any / entries,
        "atLeast2":
            same_driver_2plus,
        "atLeast2Rate":
            same_driver_2plus / entries,
        "atLeast3":
            same_driver_3plus,
        "atLeast3Rate":
            same_driver_3plus / entries,
        "repeatDistribution":
            dict(pair_repeats),
    },
    "guardrails": {
        "outcomesRead":
            False,
        "marketRead":
            False,
        "modelChanged":
            False,
    },
}


output = Path(
    "data/experiments/"
    "driver-feature-feasibility-v2.json"
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
