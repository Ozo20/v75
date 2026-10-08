from __future__ import annotations

import json
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


TOKENS = (
    "distance",
    "startmethod",
    "start_method",
    "starttype",
    "start_type",
    "autostart",
    "auto",
    "volt",
    "method",
)


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def walk_scalars(
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

            yield from walk_scalars(
                child,
                path,
            )

    elif isinstance(value, list):
        # Avoid exploding every history row
        # into indexed paths.
        return

    else:
        yield prefix, value


def relevant(path: str) -> bool:
    lower = path.casefold()

    return any(
        token in lower
        for token in TOKENS
    )


current_paths = Counter()
current_values = defaultdict(
    Counter
)

history_paths = Counter()
history_values = defaultdict(
    Counter
)

entries = 0
history_rows = 0

sample_current_entries = []
sample_history_rows = []


for day in DATES:
    pre = load(
        Path("data/normalized")
        / day
        / "pre-race.json"
    )

    for leg in pre["legs"]:
        # Inspect leg-level race context.
        for path, value in walk_scalars(
            leg
        ):
            if not relevant(path):
                continue

            # Ignore nested entry/history paths here.
            if path.startswith("entries"):
                continue

            current_paths[
                f"leg.{path}"
            ] += 1

            if (
                value is not None
                and str(value).strip()
            ):
                current_values[
                    f"leg.{path}"
                ][
                    str(value)
                ] += 1

        for entry in leg["entries"]:
            if not entry["start"][
                "eligibleForPrediction"
            ]:
                continue

            entries += 1

            current_found = {}

            for path, value in walk_scalars(
                {
                    key: value
                    for key, value
                    in entry.items()
                    if key != "history"
                }
            ):
                if not relevant(path):
                    continue

                current_paths[
                    f"entry.{path}"
                ] += 1

                if (
                    value is not None
                    and str(value).strip()
                ):
                    current_values[
                        f"entry.{path}"
                    ][
                        str(value)
                    ] += 1

                    current_found[
                        path
                    ] = value

            if (
                current_found
                and len(
                    sample_current_entries
                ) < 20
            ):
                sample_current_entries.append(
                    {
                        "date":
                            day,
                        "raceDayName":
                            pre[
                                "raceDayName"
                            ],
                        "leg":
                            leg["leg"],
                        "horse":
                            entry[
                                "horse"
                            ][
                                "name"
                            ],
                        "fields":
                            current_found,
                    }
                )

            for row in (
                entry.get("history")
                or []
            ):
                history_rows += 1

                found = {}

                for path, value in walk_scalars(
                    row
                ):
                    if not relevant(path):
                        continue

                    history_paths[
                        f"history.{path}"
                    ] += 1

                    if (
                        value is not None
                        and str(value).strip()
                    ):
                        history_values[
                            f"history.{path}"
                        ][
                            str(value)
                        ] += 1

                        found[
                            path
                        ] = value

                if (
                    found
                    and len(
                        sample_history_rows
                    ) < 20
                ):
                    sample_history_rows.append(
                        {
                            "date":
                                day,
                            "horse":
                                entry[
                                    "horse"
                                ][
                                    "name"
                                ],
                            "raceDate":
                                row.get(
                                    "raceDate"
                                ),
                            "fields":
                                found,
                        }
                    )


print(
    "=== DISTANCE / START-METHOD SCHEMA AUDIT ==="
)

print(
    f"Development entries: "
    f"{entries}"
)

print(
    f"Historical rows:     "
    f"{history_rows}"
)

print()

print(
    "=== CURRENT / TARGET-RACE CANDIDATE PATHS ==="
)

if not current_paths:
    print("None found.")
else:
    for path, count in (
        current_paths.most_common()
    ):
        print(
            f"{count:>5} {path}"
        )

        values = (
            current_values[
                path
            ].most_common(
                20
            )
        )

        if values:
            print(
                "      values:",
                values,
            )

print()

print(
    "=== HISTORICAL CANDIDATE PATHS ==="
)

if not history_paths:
    print("None found.")
else:
    for path, count in (
        history_paths.most_common()
    ):
        print(
            f"{count:>5} {path}"
        )

        values = (
            history_values[
                path
            ].most_common(
                20
            )
        )

        if values:
            print(
                "      values:",
                values,
            )

print()

print(
    "=== SAMPLE CURRENT ENTRIES ==="
)

for row in sample_current_entries:
    print(
        json.dumps(
            row,
            ensure_ascii=False,
        )
    )

print()

print(
    "=== SAMPLE HISTORICAL ROWS ==="
)

for row in sample_history_rows:
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
        "development-only-read-only",
    "entries":
        entries,
    "historicalRows":
        history_rows,
    "currentPaths": {
        path: {
            "count":
                count,
            "topValues":
                current_values[
                    path
                ].most_common(
                    50
                ),
        }
        for path, count
        in current_paths.items()
    },
    "historyPaths": {
        path: {
            "count":
                count,
            "topValues":
                history_values[
                    path
                ].most_common(
                    50
                ),
        }
        for path, count
        in history_paths.items()
    },
    "sampleCurrentEntries":
        sample_current_entries,
    "sampleHistoryRows":
        sample_history_rows,
    "guardrails": {
        "developmentOnly":
            True,
        "outcomesRead":
            False,
        "marketRead":
            False,
        "validationUsed":
            False,
        "modelsModified":
            False,
    },
}

output = Path(
    "data/experiments/"
    "distance-start-method-schema-audit.json"
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
