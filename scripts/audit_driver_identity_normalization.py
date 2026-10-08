from __future__ import annotations

import json
import re
import unicodedata
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
    "2026-08-29",
    "2026-09-05",
    "2026-09-12",
    "2026-09-19",
]


SCANDINAVIAN_TRANSLATION = str.maketrans(
    {
        "ø": "o",
        "Ø": "O",
        "æ": "ae",
        "Æ": "Ae",
        "å": "a",
        "Å": "A",
    }
)


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def basic_name(
    value: Any,
) -> str | None:
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


def canonical_name(
    value: Any,
) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    text = text.translate(
        SCANDINAVIAN_TRANSLATION
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(
            char
        )
    )

    # Treat punctuation as separators.
    text = re.sub(
        r"[^0-9A-Za-z]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return (
        text.casefold()
        if text
        else None
    )


def driver_token(
    form_row_key: Any,
) -> str | None:
    if not form_row_key:
        return None

    parts = str(
        form_row_key
    ).split("#")

    if len(parts) < 2:
        return None

    token = parts[-1].strip()

    return token or None


raw_name_counts = Counter()

basic_to_raw = defaultdict(
    Counter
)

canonical_to_raw = defaultdict(
    Counter
)

canonical_to_tokens = defaultdict(
    Counter
)

token_to_canonical = defaultdict(
    Counter
)

token_to_raw = defaultdict(
    Counter
)

history_rows = 0
rows_with_driver = 0
rows_with_token = 0

form_key_observations = defaultdict(
    list
)

current_driver_names = Counter()


for snapshot_day in DATES:
    pre = load(
        Path("data/normalized")
        / snapshot_day
        / "pre-race.json"
    )

    for leg in pre["legs"]:
        for entry in leg["entries"]:
            if entry["start"][
                "eligibleForPrediction"
            ]:
                current_name = (
                    (
                        entry.get("driver")
                        or {}
                    ).get("name")
                )

                if current_name:
                    current_driver_names[
                        str(current_name)
                    ] += 1

            horse_id = str(
                entry["horse"][
                    "registrationNumber"
                ]
            )

            horse_name = (
                entry["horse"]["name"]
            )

            for row in (
                entry.get("history")
                or []
            ):
                history_rows += 1

                raw = row.get(
                    "driver"
                )

                if not raw:
                    continue

                rows_with_driver += 1

                raw_text = str(
                    raw
                ).strip()

                basic = basic_name(
                    raw_text
                )

                canonical = canonical_name(
                    raw_text
                )

                token = driver_token(
                    row.get(
                        "formRowKey"
                    )
                )

                raw_name_counts[
                    raw_text
                ] += 1

                if basic:
                    basic_to_raw[
                        basic
                    ][
                        raw_text
                    ] += 1

                if canonical:
                    canonical_to_raw[
                        canonical
                    ][
                        raw_text
                    ] += 1

                if token:
                    rows_with_token += 1

                    canonical_to_tokens[
                        canonical
                    ][
                        token
                    ] += 1

                    token_to_canonical[
                        token
                    ][
                        canonical
                    ] += 1

                    token_to_raw[
                        token
                    ][
                        raw_text
                    ] += 1

                form_key = row.get(
                    "formRowKey"
                )

                if form_key:
                    form_key_observations[
                        str(form_key)
                    ].append(
                        {
                            "snapshotDay":
                                snapshot_day,
                            "horseId":
                                horse_id,
                            "horseName":
                                horse_name,
                            "driverRaw":
                                raw_text,
                            "driverBasic":
                                basic,
                            "driverCanonical":
                                canonical,
                            "driverToken":
                                token,
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


ambiguous_canonical_names = {
    name: dict(tokens)
    for name, tokens
    in canonical_to_tokens.items()
    if len(tokens) > 1
}

ambiguous_tokens = {
    token: dict(names)
    for token, names
    in token_to_canonical.items()
    if len(names) > 1
}


def semantic_without_name(
    row: dict[str, Any],
):
    return (
        row["horseId"],
        row["raceDate"],
        row["trackCode"],
        row["raceNumber"],
        row["startNumber"],
        str(row["placeRaw"]),
    )


duplicate_keys = 0
conflicts_before = 0
conflicts_after = 0

resolved_examples = []
remaining_conflicts = []


for form_key, rows in (
    form_key_observations.items()
):
    if len(rows) <= 1:
        continue

    duplicate_keys += 1

    before = {
        (
            semantic_without_name(
                row
            ),
            row[
                "driverBasic"
            ],
        )
        for row in rows
    }

    after = {
        (
            semantic_without_name(
                row
            ),
            row[
                "driverCanonical"
            ],
        )
        for row in rows
    }

    if len(before) > 1:
        conflicts_before += 1

    if len(after) > 1:
        conflicts_after += 1

        remaining_conflicts.append(
            {
                "formRowKey":
                    form_key,
                "observations":
                    rows,
            }
        )

    elif (
        len(before) > 1
        and len(after) == 1
    ):
        resolved_examples.append(
            {
                "formRowKey":
                    form_key,
                "rawDrivers":
                    sorted(
                        {
                            row[
                                "driverRaw"
                            ]
                            for row in rows
                        }
                    ),
                "canonicalDriver":
                    rows[0][
                        "driverCanonical"
                    ],
                "driverToken":
                    rows[0][
                        "driverToken"
                    ],
            }
        )


current_canonical = Counter()

for raw, count in (
    current_driver_names.items()
):
    canonical = canonical_name(
        raw
    )

    if canonical:
        current_canonical[
            canonical
        ] += count


current_unique_token = 0
current_no_token = 0
current_ambiguous_token = 0

current_resolution_examples = []


for canonical, count in (
    current_canonical.items()
):
    tokens = (
        canonical_to_tokens.get(
            canonical,
            {}
        )
    )

    if len(tokens) == 1:
        current_unique_token += count

    elif len(tokens) == 0:
        current_no_token += count

    else:
        current_ambiguous_token += count

        if (
            len(
                current_resolution_examples
            )
            < 20
        ):
            current_resolution_examples.append(
                {
                    "canonical":
                        canonical,
                    "currentCount":
                        count,
                    "tokens":
                        dict(tokens),
                }
            )


total_current = sum(
    current_driver_names.values()
)


print(
    "=== DRIVER IDENTITY NORMALIZATION AUDIT ==="
)

print(
    f"Snapshots:                    "
    f"{len(DATES)}"
)

print(
    f"Historical rows:              "
    f"{history_rows}"
)

print(
    f"Rows with driver:             "
    f"{rows_with_driver}"
)

print(
    f"Rows with formRow driver token:"
    f" {rows_with_token}"
)

print()

print(
    "=== CANONICAL NAME ↔ FORMROW DRIVER TOKEN ==="
)

print(
    f"Canonical driver identities:  "
    f"{len(canonical_to_tokens)}"
)

print(
    f"Distinct driver tokens:       "
    f"{len(token_to_canonical)}"
)

print(
    f"Canonical names -> >1 token:  "
    f"{len(ambiguous_canonical_names)}"
)

print(
    f"Tokens -> >1 canonical name:  "
    f"{len(ambiguous_tokens)}"
)

print()

print(
    "=== FORMROWKEY DUPLICATE RECONCILIATION ==="
)

print(
    f"Duplicate keys:               "
    f"{duplicate_keys}"
)

print(
    f"Conflicts with old basic name:"
    f" {conflicts_before}"
)

print(
    f"Conflicts after canonical name:"
    f" {conflicts_after}"
)

print(
    f"Resolved by canonicalization: "
    f"{conflicts_before - conflicts_after}"
)

print()

print(
    "=== CURRENT DRIVER RESOLUTION ==="
)

print(
    f"Current eligible entries:     "
    f"{total_current}"
)

print(
    f"Unique historical token:      "
    f"{current_unique_token}/"
    f"{total_current} "
    f"({100*current_unique_token/total_current:.1f}%)"
)

print(
    f"No historical token:          "
    f"{current_no_token}/"
    f"{total_current} "
    f"({100*current_no_token/total_current:.1f}%)"
)

print(
    f"Ambiguous historical token:   "
    f"{current_ambiguous_token}/"
    f"{total_current} "
    f"({100*current_ambiguous_token/total_current:.1f}%)"
)

print()

print(
    "=== RESOLVED COLLISION EXAMPLES ==="
)

for row in resolved_examples:
    print(
        json.dumps(
            row,
            ensure_ascii=False,
        )
    )


if ambiguous_canonical_names:
    print()
    print(
        "=== AMBIGUOUS CANONICAL NAMES ==="
    )

    for name, tokens in sorted(
        ambiguous_canonical_names.items()
    ):
        print(
            json.dumps(
                {
                    "canonical":
                        name,
                    "tokens":
                        tokens,
                    "rawNames":
                        dict(
                            canonical_to_raw[
                                name
                            ]
                        ),
                },
                ensure_ascii=False,
            )
        )


if ambiguous_tokens:
    print()
    print(
        "=== TOKENS WITH MULTIPLE CANONICAL NAMES ==="
    )

    for token, names in sorted(
        ambiguous_tokens.items()
    ):
        print(
            json.dumps(
                {
                    "token":
                        token,
                    "canonicalNames":
                        names,
                    "rawNames":
                        dict(
                            token_to_raw[
                                token
                            ]
                        ),
                },
                ensure_ascii=False,
            )
        )


if remaining_conflicts:
    print()
    print(
        "=== REMAINING FORMROWKEY CONFLICTS ==="
    )

    for row in remaining_conflicts:
        print(
            json.dumps(
                row,
                ensure_ascii=False,
            )
        )


safe = (
    conflicts_after == 0
    and len(
        ambiguous_canonical_names
    ) == 0
)


print()
print(
    "=== CONCLUSION ==="
)

print(
    "All duplicate formRowKeys reconcile "
    "after canonicalization:",
    conflicts_after == 0,
)

print(
    "Canonical driver identity maps to "
    "one form-row token only:",
    len(
        ambiguous_canonical_names
    ) == 0,
)

print(
    "Canonical driver normalization "
    "supported:",
    safe,
)


report = {
    "schemaVersion":
        "1.0",
    "scope":
        "pre-race-driver-identity-inspection",
    "dates":
        DATES,
    "historyRows":
        history_rows,
    "rowsWithDriver":
        rows_with_driver,
    "rowsWithDriverToken":
        rows_with_token,
    "canonicalDriverCount":
        len(
            canonical_to_tokens
        ),
    "driverTokenCount":
        len(
            token_to_canonical
        ),
    "ambiguousCanonicalNames":
        ambiguous_canonical_names,
    "ambiguousTokens":
        ambiguous_tokens,
    "duplicateFormRowKeys":
        duplicate_keys,
    "conflictsBeforeCanonicalization":
        conflicts_before,
    "conflictsAfterCanonicalization":
        conflicts_after,
    "resolvedExamples":
        resolved_examples,
    "currentDriverResolution": {
        "entries":
            total_current,
        "uniqueHistoricalToken":
            current_unique_token,
        "noHistoricalToken":
            current_no_token,
        "ambiguousHistoricalToken":
            current_ambiguous_token,
    },
    "canonicalNormalizationSupported":
        safe,
    "guardrails": {
        "outcomesRead":
            False,
        "marketRead":
            False,
        "frozenCandidateModified":
            False,
        "validationOutcomesConsumed":
            False,
    },
}

output = Path(
    "data/experiments/"
    "driver-identity-normalization-audit.json"
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
