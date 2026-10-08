from __future__ import annotations

import json
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
]


TOKENS = (
    "track",
    "sport",
    "organization",
    "organisation",
    "venue",
    "arena",
    "course",
    "code",
    "key",
    "name",
)


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def walk(
    value: Any,
    path: str = "",
):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (
                f"{path}.{key}"
                if path
                else key
            )

            if isinstance(
                child,
                (dict, list),
            ):
                yield from walk(
                    child,
                    child_path,
                )
            else:
                yield (
                    child_path,
                    key,
                    child,
                )

    elif isinstance(value, list):
        for index, child in enumerate(
            value
        ):
            yield from walk(
                child,
                f"{path}[{index}]",
            )


def interesting(
    path: str,
    key: str,
):
    text = (
        path + " " + key
    ).casefold()

    return any(
        token in text
        for token in TOKENS
    )


def compact(value: Any):
    text = repr(value)

    if len(text) > 140:
        text = (
            text[:137]
            + "..."
        )

    return text


def contains_value(
    value: Any,
    needle: str,
) -> bool:
    if isinstance(value, dict):
        return any(
            contains_value(
                child,
                needle,
            )
            for child
            in value.values()
        )

    if isinstance(value, list):
        return any(
            contains_value(
                child,
                needle,
            )
            for child
            in value
        )

    return (
        str(value) == needle
    )


def find_matching_objects(
    value: Any,
    needle: str,
):
    matches = []

    if isinstance(value, dict):
        if contains_value(
            value,
            needle,
        ):
            # Prefer relatively small objects
            # containing the target directly.
            direct = any(
                str(child) == needle
                for child
                in value.values()
                if not isinstance(
                    child,
                    (dict, list),
                )
            )

            if direct:
                matches.append(
                    value
                )

        for child in value.values():
            matches.extend(
                find_matching_objects(
                    child,
                    needle,
                )
            )

    elif isinstance(value, list):
        for child in value:
            matches.extend(
                find_matching_objects(
                    child,
                    needle,
                )
            )

    return matches


print(
    "=== CURRENT TRACK MAPPING SOURCE AUDIT ==="
)

discovery_path = Path(
    "data/discovery/"
    "v75-days-2026.json"
)

discovery = (
    load(discovery_path)
    if discovery_path.exists()
    else None
)

summary = defaultdict(
    lambda: defaultdict(set)
)


for date in DATES:
    normalized = load(
        Path("data/normalized")
        / date
        / "pre-race.json"
    )

    race_day_key = (
        normalized["raceDayKey"]
    )

    race_day_name = (
        normalized["raceDayName"]
    )

    prefix = (
        race_day_key.split(
            "_NR_",
            1,
        )[0]
    )

    print()
    print(
        "============================================================"
    )
    print(
        f"{date} | "
        f"{race_day_name} | "
        f"{race_day_key} | "
        f"prefix={prefix}"
    )
    print(
        "============================================================"
    )

    sources = [
        (
            "raw/manifest.json",
            Path("data/raw")
            / date
            / "manifest.json",
        ),
        (
            "raw/v75-pool.json",
            Path("data/raw")
            / date
            / "v75-pool.json",
        ),
        (
            "raw/race-info.json",
            Path("data/raw")
            / date
            / "race-info.json",
        ),
        (
            "raw/program/v75-1.json",
            Path("data/raw")
            / date
            / "program"
            / "v75-1.json",
        ),
    ]

    for label, path in sources:
        print()
        print(
            f"--- {label} ---"
        )

        if not path.exists():
            print("MISSING")
            continue

        data = load(path)

        rows = []

        for (
            field_path,
            key,
            value,
        ) in walk(data):
            if not interesting(
                field_path,
                key,
            ):
                continue

            rows.append(
                (
                    field_path,
                    value,
                )
            )

            summary[
                label
            ][
                field_path
            ].add(
                str(value)
            )

        # Avoid drowning in repeated
        # race-info arrays.
        seen = set()
        shown = 0

        for (
            field_path,
            value,
        ) in rows:
            normalized_path = (
                field_path
            )

            signature = (
                normalized_path,
                str(value),
            )

            if signature in seen:
                continue

            seen.add(
                signature
            )

            print(
                f"{normalized_path:<75} "
                f"{compact(value)}"
            )

            shown += 1

            if shown >= 80:
                print(
                    "... truncated ..."
                )
                break

        if shown == 0:
            print(
                "No candidate scalar fields."
            )

    print()
    print(
        "--- discovery match ---"
    )

    if discovery is None:
        print(
            "Discovery file missing."
        )
    else:
        matches = (
            find_matching_objects(
                discovery,
                race_day_key,
            )
        )

        print(
            f"Objects containing exact "
            f"raceDayKey: {len(matches)}"
        )

        for index, obj in enumerate(
            matches[:5],
            1,
        ):
            print(
                f"  MATCH {index}:"
            )

            for (
                field_path,
                key,
                value,
            ) in walk(obj):
                if interesting(
                    field_path,
                    key,
                ):
                    print(
                        f"    "
                        f"{field_path:<55} "
                        f"{compact(value)}"
                    )


print()
print(
    "=== DISTINCT CANDIDATE PATH SUMMARY ==="
)

for source in sorted(
    summary
):
    print()
    print(
        f"--- {source} ---"
    )

    for path in sorted(
        summary[source]
    ):
        values = sorted(
            summary[source][path]
        )

        if len(values) > 20:
            sample = (
                values[:20]
                + [
                    f"... "
                    f"({len(values)} distinct)"
                ]
            )
        else:
            sample = values

        print(
            f"{path}"
        )
        print(
            f"  {sample}"
        )


report = {
    "schemaVersion":
        "1.0",
    "scope":
        "development-only-read-only",
    "dates":
        DATES,
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
    "current-track-mapping-source-audit.json"
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
