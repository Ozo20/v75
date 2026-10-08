from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DATE = "2026-06-13"


TOKENS = (
    "driver",
    "horse",
    "registration",
    "startnumber",
    "start_number",
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
    *,
    skip_history: bool = False,
):
    if isinstance(value, dict):
        for key, child in value.items():

            if (
                skip_history
                and key == "history"
            ):
                continue

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
                    skip_history=skip_history,
                )
            else:
                yield (
                    child_path,
                    key,
                    child,
                )

    elif isinstance(value, list):
        for i, child in enumerate(value):
            child_path = (
                f"{path}[{i}]"
            )

            yield from walk(
                child,
                child_path,
                skip_history=skip_history,
            )


def relevant(
    key: str,
    path: str,
):
    text = (
        key + " " + path
    ).casefold()

    return any(
        token in text
        for token in TOKENS
    )


def print_relevant(
    title: str,
    value: Any,
    *,
    skip_history: bool = False,
    max_rows: int = 200,
):
    print()
    print(
        f"=== {title} ==="
    )

    count = 0

    for path, key, scalar in walk(
        value,
        skip_history=skip_history,
    ):
        if not relevant(
            key,
            path,
        ):
            continue

        text = repr(scalar)

        if len(text) > 120:
            text = (
                text[:117]
                + "..."
            )

        print(
            f"{path:<70} "
            f"{text}"
        )

        count += 1

        if count >= max_rows:
            print(
                "... output truncated ..."
            )
            break

    if count == 0:
        print(
            "No matching scalar paths."
        )


pre = load(
    Path(
        "data/normalized"
    )
    / DATE
    / "pre-race.json"
)


eligible_entries = []

for leg in pre["legs"]:
    for entry in leg["entries"]:
        if entry["start"][
            "eligibleForPrediction"
        ]:
            eligible_entries.append(
                (
                    leg["leg"],
                    entry,
                )
            )


print(
    "=== NORMALIZED TOP-LEVEL ==="
)

print(
    f"Date: {DATE}"
)

print(
    f"Eligible entries: "
    f"{len(eligible_entries)}"
)

print(
    f"Top-level keys: "
    f"{list(pre.keys())}"
)

print()

for index, (
    leg_number,
    entry,
) in enumerate(
    eligible_entries[:3],
    1,
):
    print(
        f"=== NORMALIZED ENTRY {index} "
        f"(LEG {leg_number}) KEYS ==="
    )

    print(
        list(entry.keys())
    )

    print_relevant(
        f"NORMALIZED ENTRY {index} "
        f"CURRENT-ONLY PATHS",
        entry,
        skip_history=True,
    )

    history = (
        entry.get("history")
        or []
    )

    if history:
        print_relevant(
            f"NORMALIZED ENTRY {index} "
            f"FIRST HISTORY ROW",
            history[0],
            skip_history=False,
        )


raw_root = (
    Path("data/raw")
    / DATE
)


for filename in (
    "starts.json",
    "program/v75-1.json",
):
    path = (
        raw_root
        / filename
    )

    data = load(path)

    print()
    print(
        f"=== RAW FILE: "
        f"{filename} ==="
    )

    print(
        f"Root type: "
        f"{type(data).__name__}"
    )

    if isinstance(
        data,
        dict,
    ):
        print(
            f"Root keys: "
            f"{list(data.keys())}"
        )

    print_relevant(
        f"RAW {filename} "
        f"RELEVANT PATHS",
        data,
        skip_history=True,
        max_rows=250,
    )


print()
print(
    "=== NORMALIZER SOURCE SEARCH HINTS ==="
)

normalizer = Path(
    "src/rikstoto_normalizer.py"
).read_text(
    encoding="utf-8"
)

for token in (
    "driverId",
    "driver",
    "horseRegistrationNumber",
):
    count = normalizer.count(
        token
    )

    print(
        f"{token}: "
        f"{count} occurrence(s) "
        f"in normalizer source"
    )
