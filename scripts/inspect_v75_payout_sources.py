from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


DATES = [
    "2026-01-06",
    "2026-01-10",
    "2026-01-17",
    "2026-01-24",
    "2026-01-31",
    "2026-02-07",
    "2026-02-14",
    "2026-02-21",
    "2026-02-28",
    "2026-03-07",
    "2026-03-21",
]


TOKENS = (
    "payout",
    "payOut",
    "prize",
    "dividend",
    "correct",
    "winning",
    "stake",
    "investment",
    "turnover",
    "pool",
    "unit",
    "price",
    "eventual",
    "value",
)


def normalize_path(path: str) -> str:
    return re.sub(
        r"\[\d+\]",
        "[]",
        path,
    )


def compact(value: Any) -> str:
    if isinstance(
        value,
        (dict, list),
    ):
        if isinstance(value, dict):
            return (
                "{"
                + ", ".join(
                    list(value.keys())[:8]
                )
                + (
                    ", ..."
                    if len(value) > 8
                    else ""
                )
                + "}"
            )

        return (
            f"[{len(value)} items]"
        )

    text = repr(value)

    if len(text) > 100:
        text = (
            text[:97]
            + "..."
        )

    return text


def walk(
    value: Any,
    path: str,
):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (
                f"{path}.{key}"
                if path
                else key
            )

            yield (
                child_path,
                key,
                child,
            )

            yield from walk(
                child,
                child_path,
            )

    elif isinstance(value, list):
        for i, child in enumerate(value):
            child_path = (
                f"{path}[{i}]"
            )

            yield from walk(
                child,
                child_path,
            )


records = defaultdict(
    lambda: {
        "dates": set(),
        "files": set(),
        "examples": [],
    }
)


print(
    "=== RAW FILE INVENTORY ==="
)

for date in DATES:
    root = (
        Path("data/raw")
        / date
    )

    if not root.exists():
        print(
            f"WARNING: missing {root}"
        )
        continue

    files = sorted(
        path
        for path
        in root.rglob("*.json")
        if path.is_file()
    )

    print()
    print(
        f"{date}: "
        f"{len(files)} JSON files"
    )

    for path in files:
        print(
            f"  {path.relative_to(root)}"
        )

        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except Exception as exc:
            print(
                f"    WARNING: "
                f"could not parse: {exc}"
            )
            continue

        for (
            raw_path,
            key,
            value,
        ) in walk(
            data,
            "",
        ):
            lower_key = (
                key.lower()
            )

            if not any(
                token.lower()
                in lower_key
                for token
                in TOKENS
            ):
                continue

            normalized = (
                normalize_path(
                    raw_path
                )
            )

            record_key = (
                str(
                    path.relative_to(
                        root
                    )
                ),
                normalized,
            )

            record = records[
                record_key
            ]

            record[
                "dates"
            ].add(date)

            record[
                "files"
            ].add(
                str(
                    path.relative_to(
                        root
                    )
                )
            )

            example = (
                f"{date}: "
                f"{compact(value)}"
            )

            if (
                example
                not in record[
                    "examples"
                ]
                and len(
                    record[
                        "examples"
                    ]
                ) < 4
            ):
                record[
                    "examples"
                ].append(
                    example
                )


print()
print(
    "=== PAYOUT / STAKE / POOL "
    "CANDIDATE PATHS ==="
)

if not records:
    print(
        "No candidate fields found."
    )

for (
    filename,
    path,
), record in sorted(
    records.items()
):
    print()
    print(
        f"FILE: {filename}"
    )

    print(
        f"PATH: {path}"
    )

    print(
        f"DATES: "
        f"{len(record['dates'])}/"
        f"{len(DATES)}"
    )

    for example in (
        record["examples"]
    ):
        print(
            f"  {example}"
        )


print()
print(
    "=== LIKELY PAYOUT-SOURCE FILES ==="
)

candidate_names = set()

for (
    filename,
    path,
), record in records.items():
    lower = (
        filename
        + " "
        + path
    ).lower()

    if any(
        token in lower
        for token in (
            "payout",
            "prize",
            "dividend",
            "correct",
            "stake",
            "investment",
            "pool",
        )
    ):
        candidate_names.add(
            filename
        )

for filename in sorted(
    candidate_names
):
    print(filename)

if not candidate_names:
    print(
        "No obvious payout source "
        "already stored."
    )
