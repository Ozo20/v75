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
    "bane",
    "arena",
    "venue",
    "sporttrack",
    "racetrack",
)


FILES = (
    "race-info.json",
    "starts.json",
    "program/v75-1.json",
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
            yield from walk(
                child,
                f"{path}[{i}]",
            )


def compact(value: Any) -> str:
    text = repr(value)

    if len(text) > 120:
        text = text[:117] + "..."

    return text


summary = defaultdict(
    lambda: defaultdict(set)
)


print(
    "=== CURRENT TRACK CODE SOURCE INSPECTION ==="
)


for date in DATES:
    normalized_path = (
        Path("data/normalized")
        / date
        / "pre-race.json"
    )

    normalized = load(
        normalized_path
    )

    print()
    print(
        "============================================================"
    )
    print(
        f"{date} | "
        f"{normalized['raceDayName']} | "
        f"{normalized['raceDayKey']}"
    )
    print(
        "============================================================"
    )

    for filename in FILES:
        path = (
            Path("data/raw")
            / date
            / filename
        )

        print()
        print(
            f"--- {filename} ---"
        )

        if not path.exists():
            print(
                "MISSING"
            )
            continue

        data = load(path)

        matches = 0

        for (
            field_path,
            key,
            value,
        ) in walk(data):

            text = (
                key
                + " "
                + field_path
            ).casefold()

            if not any(
                token in text
                for token in TOKENS
            ):
                continue

            if isinstance(
                value,
                (dict, list),
            ):
                continue

            matches += 1

            print(
                f"{field_path:<75} "
                f"{compact(value)}"
            )

            summary[
                filename
            ][
                field_path
            ].add(
                str(value)
            )

        if matches == 0:
            print(
                "No matching scalar fields."
            )


print()
print(
    "=== NORMALIZER TRACK REFERENCES ==="
)

normalizer_path = Path(
    "src/rikstoto_normalizer.py"
)

text = normalizer_path.read_text(
    encoding="utf-8"
)

for lineno, line in enumerate(
    text.splitlines(),
    1,
):
    lower = line.casefold()

    if any(
        token in lower
        for token in TOKENS
    ):
        print(
            f"{lineno:>5}: {line}"
        )


print()
print(
    "=== DISTINCT CANDIDATE PATHS ==="
)

for filename in FILES:
    print()
    print(
        f"--- {filename} ---"
    )

    paths = summary.get(
        filename,
        {},
    )

    if not paths:
        print(
            "No candidate paths."
        )
        continue

    for field_path in sorted(
        paths
    ):
        values = sorted(
            paths[
                field_path
            ]
        )

        sample = values[:20]

        print(
            f"{field_path}"
        )
        print(
            f"  values={sample}"
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
        "modelChanged":
            False,
    },
}

output = Path(
    "data/experiments/"
    "current-track-code-source-inspection.json"
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
