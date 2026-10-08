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


def clean(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    return text or None


def normalize_shoes(
    value: Any,
) -> str | None:
    value = clean(value)

    if value in {
        "Both",
        "None",
        "Fore",
        "Hind",
    }:
        return value

    return value


def normalize_sulky(
    value: Any,
) -> str | None:
    value = clean(value)

    if value == "Sulky":
        return "StandardSulky"

    if value in {
        "StandardSulky",
        "AmericanSulky",
        "NoSulky",
    }:
        return value

    return value


entries = 0
entries_with_history = 0

shoe_previous_present = 0
shoe_latest_present = 0
shoe_comparable = 0
shoe_match = 0
shoe_mismatch = 0

sulky_previous_present = 0
sulky_latest_present = 0
sulky_comparable = 0
sulky_match = 0
sulky_mismatch = 0

previous_sulky_counts = Counter()
latest_sulky_counts = Counter()

previous_shoe_counts = Counter()
latest_shoe_counts = Counter()

shoe_transitions = Counter()
sulky_transitions = Counter()

no_sulky_cases = Counter()

shoe_mismatch_examples = []
sulky_mismatch_examples = []


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

            history = sorted(
                entry.get("history")
                or [],
                key=lambda row: (
                    row.get("raceDate")
                    or ""
                ),
                reverse=True,
            )

            if not history:
                continue

            entries_with_history += 1

            latest = history[0]

            equipment = (
                entry.get("equipment")
                or {}
            )

            current_shoes = (
                normalize_shoes(
                    equipment.get(
                        "shoes"
                    )
                )
            )

            previous_shoes = (
                normalize_shoes(
                    equipment.get(
                        "previousStartShoes"
                    )
                )
            )

            latest_shoes = (
                normalize_shoes(
                    latest.get(
                        "shoes"
                    )
                )
            )

            current_sulky = (
                normalize_sulky(
                    equipment.get(
                        "sulky"
                    )
                )
            )

            previous_sulky = (
                normalize_sulky(
                    equipment.get(
                        "previousStartSulky"
                    )
                )
            )

            latest_sulky = (
                normalize_sulky(
                    latest.get(
                        "sulky"
                    )
                )
            )

            latest_monte = bool(
                latest.get("monte")
            )

            if previous_shoes:
                shoe_previous_present += 1
                previous_shoe_counts[
                    previous_shoes
                ] += 1

            if latest_shoes:
                shoe_latest_present += 1
                latest_shoe_counts[
                    latest_shoes
                ] += 1

            if (
                previous_shoes
                and latest_shoes
            ):
                shoe_comparable += 1

                if (
                    previous_shoes
                    == latest_shoes
                ):
                    shoe_match += 1
                else:
                    shoe_mismatch += 1

                    if (
                        len(
                            shoe_mismatch_examples
                        )
                        < 25
                    ):
                        shoe_mismatch_examples.append(
                            {
                                "date":
                                    date,
                                "horse":
                                    entry[
                                        "horse"
                                    ][
                                        "name"
                                    ],
                                "previousStartShoes":
                                    previous_shoes,
                                "latestHistoryShoes":
                                    latest_shoes,
                                "latestRaceDate":
                                    latest.get(
                                        "raceDate"
                                    ),
                            }
                        )

            if (
                current_shoes
                and previous_shoes
            ):
                shoe_transitions[
                    (
                        previous_shoes,
                        current_shoes,
                    )
                ] += 1

            if previous_sulky:
                sulky_previous_present += 1
                previous_sulky_counts[
                    previous_sulky
                ] += 1

            if latest_sulky:
                sulky_latest_present += 1
                latest_sulky_counts[
                    latest_sulky
                ] += 1

            if (
                previous_sulky
                and latest_sulky
            ):
                sulky_comparable += 1

                if (
                    previous_sulky
                    == latest_sulky
                ):
                    sulky_match += 1
                else:
                    sulky_mismatch += 1

                    if (
                        len(
                            sulky_mismatch_examples
                        )
                        < 25
                    ):
                        sulky_mismatch_examples.append(
                            {
                                "date":
                                    date,
                                "horse":
                                    entry[
                                        "horse"
                                    ][
                                        "name"
                                    ],
                                "previousStartSulky":
                                    previous_sulky,
                                "latestHistorySulky":
                                    latest_sulky,
                                "latestMonte":
                                    latest_monte,
                                "latestRaceDate":
                                    latest.get(
                                        "raceDate"
                                    ),
                            }
                        )

            if (
                current_sulky
                and previous_sulky
            ):
                sulky_transitions[
                    (
                        previous_sulky,
                        current_sulky,
                    )
                ] += 1

            if previous_sulky == "NoSulky":
                no_sulky_cases[
                    "total"
                ] += 1

                if latest_monte:
                    no_sulky_cases[
                        "latestMonteTrue"
                    ] += 1

                if latest_sulky is None:
                    no_sulky_cases[
                        "latestSulkyMissing"
                    ] += 1

                if latest_sulky:
                    no_sulky_cases[
                        f"latestSulky={latest_sulky}"
                    ] += 1


print(
    "=== EQUIPMENT SEMANTICS AUDIT ==="
)

print(
    f"Development entries:       "
    f"{entries}"
)

print(
    f"Entries with history:      "
    f"{entries_with_history}"
)

print()

print(
    "=== SHOES: SNAPSHOT PREVIOUS "
    "VS LATEST HISTORY ==="
)

print(
    f"previousStartShoes present:"
    f" {shoe_previous_present}/"
    f"{entries_with_history}"
)

print(
    f"latest history shoes:      "
    f"{shoe_latest_present}/"
    f"{entries_with_history}"
)

print(
    f"comparable:                "
    f"{shoe_comparable}"
)

print(
    f"match:                     "
    f"{shoe_match}"
)

print(
    f"mismatch:                  "
    f"{shoe_mismatch}"
)

if shoe_comparable:
    print(
        f"match rate:                "
        f"{100*shoe_match/shoe_comparable:.1f}%"
    )

print()

print(
    "Previous shoe values:",
    dict(previous_shoe_counts),
)

print(
    "Latest history values:",
    dict(latest_shoe_counts),
)

print()

print(
    "=== SULKY: SNAPSHOT PREVIOUS "
    "VS LATEST HISTORY ==="
)

print(
    f"previousStartSulky present:"
    f" {sulky_previous_present}/"
    f"{entries_with_history}"
)

print(
    f"latest history sulky:      "
    f"{sulky_latest_present}/"
    f"{entries_with_history}"
)

print(
    f"comparable:                "
    f"{sulky_comparable}"
)

print(
    f"match:                     "
    f"{sulky_match}"
)

print(
    f"mismatch:                  "
    f"{sulky_mismatch}"
)

if sulky_comparable:
    print(
        f"match rate:                "
        f"{100*sulky_match/sulky_comparable:.1f}%"
    )

print()

print(
    "Previous sulky values:",
    dict(previous_sulky_counts),
)

print(
    "Latest history values:",
    dict(latest_sulky_counts),
)

print()

print(
    "=== PREVIOUS NoSulky DIAGNOSTIC ==="
)

for key, count in (
    no_sulky_cases.most_common()
):
    print(
        f"{key:<30} {count}"
    )

print()

print(
    "=== MOST COMMON SHOE TRANSITIONS ==="
)

for (
    previous,
    current,
), count in (
    shoe_transitions.most_common(
        20
    )
):
    changed = (
        "CHANGE"
        if previous != current
        else "same"
    )

    print(
        f"{count:>4} "
        f"{previous:<5} -> "
        f"{current:<5} "
        f"{changed}"
    )

print()

print(
    "=== MOST COMMON SULKY TRANSITIONS ==="
)

for (
    previous,
    current,
), count in (
    sulky_transitions.most_common(
        20
    )
):
    changed = (
        "CHANGE"
        if previous != current
        else "same"
    )

    print(
        f"{count:>4} "
        f"{previous:<14} -> "
        f"{current:<14} "
        f"{changed}"
    )

print()

if shoe_mismatch_examples:
    print(
        "=== SAMPLE SHOE MISMATCHES ==="
    )

    for row in shoe_mismatch_examples:
        print(
            json.dumps(
                row,
                ensure_ascii=False,
            )
        )

    print()

if sulky_mismatch_examples:
    print(
        "=== SAMPLE SULKY MISMATCHES ==="
    )

    for row in sulky_mismatch_examples:
        print(
            json.dumps(
                row,
                ensure_ascii=False,
            )
        )

    print()


report = {
    "schemaVersion":
        "1.0",
    "scope":
        "development-only-read-only",
    "entries":
        entries,
    "entriesWithHistory":
        entries_with_history,
    "shoes": {
        "previousPresent":
            shoe_previous_present,
        "latestHistoryPresent":
            shoe_latest_present,
        "comparable":
            shoe_comparable,
        "match":
            shoe_match,
        "mismatch":
            shoe_mismatch,
        "transitions": {
            f"{previous}->{current}":
                count
            for (
                previous,
                current,
            ), count in (
                shoe_transitions.items()
            )
        },
    },
    "sulky": {
        "previousPresent":
            sulky_previous_present,
        "latestHistoryPresent":
            sulky_latest_present,
        "comparable":
            sulky_comparable,
        "match":
            sulky_match,
        "mismatch":
            sulky_mismatch,
        "noSulkyDiagnostic":
            dict(
                no_sulky_cases
            ),
        "transitions": {
            f"{previous}->{current}":
                count
            for (
                previous,
                current,
            ), count in (
                sulky_transitions.items()
            )
        },
    },
    "guardrails": {
        "developmentOnly":
            True,
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
    "equipment-semantics-audit.json"
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

print(
    f"Report: {output}"
)
