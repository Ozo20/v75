from __future__ import annotations

import json
from collections import Counter
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


def scalar_paths(
    value: Any,
    prefix: str = "",
):
    rows = []

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
                rows.extend(
                    scalar_paths(
                        child,
                        path,
                    )
                )
            else:
                rows.append(
                    (
                        path,
                        child,
                    )
                )

    elif isinstance(value, list):
        for child in value:
            rows.extend(
                scalar_paths(
                    child,
                    prefix,
                )
            )

    return rows


def nonempty(value: Any) -> bool:
    return (
        value is not None
        and value != ""
        and value != []
        and value != {}
    )


entries = 0
history_rows = 0

current_equipment_present = 0

current_paths = Counter()
current_values = {}

history_paths = Counter()
history_values = {}

current_shape_examples = []
history_shape_examples = []


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

            equipment = entry.get(
                "equipment"
            )

            if nonempty(
                equipment
            ):
                current_equipment_present += 1

            if (
                len(
                    current_shape_examples
                )
                < 10
            ):
                current_shape_examples.append(
                    {
                        "date": date,
                        "horse":
                            entry["horse"]["name"],
                        "equipment":
                            equipment,
                    }
                )

            for path, value in (
                scalar_paths(
                    equipment,
                    "equipment",
                )
                if equipment is not None
                else []
            ):
                if nonempty(value):
                    current_paths[
                        path
                    ] += 1

                    current_values.setdefault(
                        path,
                        Counter(),
                    )[
                        str(value)
                    ] += 1

            for row in (
                entry.get("history")
                or []
            ):
                history_rows += 1

                if (
                    len(
                        history_shape_examples
                    )
                    < 15
                ):
                    history_shape_examples.append(
                        {
                            "date": date,
                            "horse":
                                entry["horse"]["name"],
                            "history":
                                row,
                        }
                    )

                for path, value in (
                    scalar_paths(
                        row,
                        "history",
                    )
                ):
                    lower = path.casefold()

                    if not any(
                        token in lower
                        for token in (
                            "shoe",
                            "sko",
                            "cart",
                            "sulky",
                            "wagon",
                            "equipment",
                            "bike",
                            "gear",
                        )
                    ):
                        continue

                    if not nonempty(
                        value
                    ):
                        continue

                    history_paths[
                        path
                    ] += 1

                    history_values.setdefault(
                        path,
                        Counter(),
                    )[
                        str(value)
                    ] += 1


print(
    "=== EQUIPMENT FEATURE FEASIBILITY ==="
)

print(
    f"Development entries:          "
    f"{entries}"
)

print(
    f"Historical form rows:         "
    f"{history_rows}"
)

print()

print(
    "=== CURRENT EQUIPMENT COVERAGE ==="
)

print(
    f"Entries with equipment object:"
    f" {current_equipment_present}/"
    f"{entries} "
    f"({100*current_equipment_present/entries:.1f}%)"
)

print()

print(
    "=== CURRENT EQUIPMENT SCALAR PATHS ==="
)

if not current_paths:
    print(
        "No populated scalar equipment paths."
    )
else:
    for path, count in (
        current_paths.most_common()
    ):
        print(
            f"{count:>4}/{entries} "
            f"{path}"
        )

        values = (
            current_values[
                path
            ].most_common(
                20
            )
        )

        print(
            "      values:",
            values,
        )


print()
print(
    "=== HISTORICAL EQUIPMENT-LIKE PATHS ==="
)

if not history_paths:
    print(
        "No equipment-like historical "
        "scalar paths found."
    )
else:
    for path, count in (
        history_paths.most_common()
    ):
        print(
            f"{count:>5}/{history_rows} "
            f"{path}"
        )

        values = (
            history_values[
                path
            ].most_common(
                20
            )
        )

        print(
            "       values:",
            values,
        )


print()
print(
    "=== SAMPLE CURRENT EQUIPMENT OBJECTS ==="
)

for row in current_shape_examples:
    print(
        json.dumps(
            row,
            ensure_ascii=False,
        )
    )


print()
print(
    "=== SAMPLE HISTORY ROW KEYS ==="
)

seen_key_shapes = set()

shown = 0

for sample in history_shape_examples:
    row = sample["history"]

    keys = tuple(
        sorted(
            row.keys()
        )
    )

    if keys in seen_key_shapes:
        continue

    seen_key_shapes.add(
        keys
    )

    print(
        json.dumps(
            {
                "date":
                    sample["date"],
                "horse":
                    sample["horse"],
                "keys":
                    list(keys),
                "equipmentLike": {
                    key: value
                    for key, value
                    in row.items()
                    if any(
                        token
                        in key.casefold()
                        for token
                        in (
                            "shoe",
                            "sko",
                            "cart",
                            "sulky",
                            "wagon",
                            "equipment",
                            "bike",
                            "gear",
                        )
                    )
                },
            },
            ensure_ascii=False,
        )
    )

    shown += 1

    if shown >= 10:
        break


report = {
    "schemaVersion":
        "1.0",
    "scope":
        "development-only-read-only",
    "entries":
        entries,
    "historyRows":
        history_rows,
    "currentEquipmentPresent":
        current_equipment_present,
    "currentEquipmentPaths":
        dict(current_paths),
    "historicalEquipmentPaths":
        dict(history_paths),
    "currentValueCounts": {
        path:
            dict(values)
        for path, values
        in current_values.items()
    },
    "historicalValueCounts": {
        path:
            dict(values)
        for path, values
        in history_values.items()
    },
    "guardrails": {
        "outcomesRead":
            False,
        "marketRead":
            False,
        "validationUsed":
            False,
        "modelChanged":
            False,
    },
}

output = Path(
    "data/experiments/"
    "equipment-feature-feasibility.json"
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
