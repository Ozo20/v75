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


def norm(value: Any) -> str | None:
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


def collect_horse_rows(
    value: Any,
) -> list[dict[str, Any]]:
    rows = []

    if isinstance(value, dict):
        if (
            "horseRegistrationNumber"
            in value
        ):
            rows.append(value)

        for child in value.values():
            rows.extend(
                collect_horse_rows(
                    child
                )
            )

    elif isinstance(value, list):
        for child in value:
            rows.extend(
                collect_horse_rows(
                    child
                )
            )

    return rows


totals = Counter()

examples = defaultdict(list)

raw_program_id_to_names = defaultdict(
    set
)

raw_starts_id_to_names = defaultdict(
    set
)

normalized_id_to_names = defaultdict(
    set
)


for date in DATES:
    normalized = load(
        Path("data/normalized")
        / date
        / "pre-race.json"
    )

    raw_starts = load(
        Path("data/raw")
        / date
        / "starts.json"
    )

    starts_rows = (
        collect_horse_rows(
            raw_starts
        )
    )

    starts_by_horse = defaultdict(
        list
    )

    for row in starts_rows:
        horse_id = row.get(
            "horseRegistrationNumber"
        )

        if horse_id:
            starts_by_horse[
                str(horse_id)
            ].append(row)

        driver_id = row.get(
            "driverLicenseNumber"
        )

        driver_name = norm(
            row.get("driverName")
        )

        if (
            driver_id is not None
            and driver_name
        ):
            raw_starts_id_to_names[
                str(driver_id)
            ].add(
                driver_name
            )

    for leg in normalized["legs"]:
        leg_number = int(
            leg["leg"]
        )

        program = load(
            Path("data/raw")
            / date
            / "program"
            / f"v75-{leg_number}.json"
        )

        program_rows = (
            collect_horse_rows(
                program
            )
        )

        program_by_horse = defaultdict(
            list
        )

        for row in program_rows:
            horse_id = row.get(
                "horseRegistrationNumber"
            )

            if horse_id:
                program_by_horse[
                    str(horse_id)
                ].append(row)

            driver_id = row.get(
                "driverId"
            )

            driver_name = norm(
                row.get("driver")
            )

            if (
                driver_id is not None
                and driver_name
            ):
                raw_program_id_to_names[
                    str(driver_id)
                ].add(
                    driver_name
                )

        for entry in leg["entries"]:
            if not entry["start"][
                "eligibleForPrediction"
            ]:
                continue

            totals["entries"] += 1

            horse_id = str(
                entry["horse"][
                    "registrationNumber"
                ]
            )

            horse_name = (
                entry["horse"]["name"]
            )

            normalized_driver_id = str(
                entry["driver"]["id"]
            )

            normalized_driver_name = norm(
                entry["driver"]["name"]
            )

            normalized_id_to_names[
                normalized_driver_id
            ].add(
                normalized_driver_name
            )

            program_matches = (
                program_by_horse.get(
                    horse_id,
                    []
                )
            )

            starts_matches = (
                starts_by_horse.get(
                    horse_id,
                    []
                )
            )

            if len(
                program_matches
            ) != 1:
                totals[
                    "programMatchProblem"
                ] += 1

                if len(
                    examples[
                        "programMatchProblem"
                    ]
                ) < 15:
                    examples[
                        "programMatchProblem"
                    ].append(
                        {
                            "date": date,
                            "leg": leg_number,
                            "horse": horse_name,
                            "horseId": horse_id,
                            "matches":
                                len(
                                    program_matches
                                ),
                        }
                    )

                continue

            program_row = (
                program_matches[0]
            )

            program_driver_id = str(
                program_row.get(
                    "driverId"
                )
            )

            program_driver_name = norm(
                program_row.get(
                    "driver"
                )
            )

            if (
                normalized_driver_id
                == program_driver_id
            ):
                totals[
                    "normalizedProgramIdMatch"
                ] += 1
            else:
                totals[
                    "normalizedProgramIdMismatch"
                ] += 1

            if (
                normalized_driver_name
                == program_driver_name
            ):
                totals[
                    "normalizedProgramNameMatch"
                ] += 1
            else:
                totals[
                    "normalizedProgramNameMismatch"
                ] += 1

            if (
                normalized_driver_id
                != program_driver_id
                or normalized_driver_name
                != program_driver_name
            ):
                if len(
                    examples[
                        "normalizedProgramMismatch"
                    ]
                ) < 25:
                    examples[
                        "normalizedProgramMismatch"
                    ].append(
                        {
                            "date": date,
                            "leg": leg_number,
                            "startNumber":
                                entry[
                                    "startNumber"
                                ],
                            "horse":
                                horse_name,
                            "horseId":
                                horse_id,
                            "normalized": {
                                "id":
                                    normalized_driver_id,
                                "name":
                                    normalized_driver_name,
                            },
                            "program": {
                                "id":
                                    program_driver_id,
                                "name":
                                    program_driver_name,
                            },
                        }
                    )

            # starts.json may contain the
            # horse only once on the day.
            if len(
                starts_matches
            ) == 1:
                totals[
                    "uniqueStartsMatch"
                ] += 1

                starts_row = (
                    starts_matches[0]
                )

                starts_driver_id = str(
                    starts_row.get(
                        "driverLicenseNumber"
                    )
                )

                starts_driver_name = norm(
                    starts_row.get(
                        "driverName"
                    )
                )

                if (
                    program_driver_id
                    == starts_driver_id
                ):
                    totals[
                        "programStartsIdMatch"
                    ] += 1
                else:
                    totals[
                        "programStartsIdMismatch"
                    ] += 1

                if (
                    program_driver_name
                    == starts_driver_name
                ):
                    totals[
                        "programStartsNameMatch"
                    ] += 1
                else:
                    totals[
                        "programStartsNameMismatch"
                    ] += 1

                if (
                    program_driver_id
                    != starts_driver_id
                    or program_driver_name
                    != starts_driver_name
                ):
                    if len(
                        examples[
                            "programStartsMismatch"
                        ]
                    ) < 25:
                        examples[
                            "programStartsMismatch"
                        ].append(
                            {
                                "date":
                                    date,
                                "leg":
                                    leg_number,
                                "horse":
                                    horse_name,
                                "horseId":
                                    horse_id,
                                "program": {
                                    "id":
                                        program_driver_id,
                                    "name":
                                        program_driver_name,
                                },
                                "starts": {
                                    "id":
                                        starts_driver_id,
                                    "name":
                                        starts_driver_name,
                                },
                            }
                        )
            else:
                totals[
                    "startsMatchProblem"
                ] += 1


def ambiguous(
    mapping,
):
    return {
        key: sorted(values)
        for key, values
        in mapping.items()
        if len(values) > 1
    }


normalized_ambiguous = ambiguous(
    normalized_id_to_names
)

program_ambiguous = ambiguous(
    raw_program_id_to_names
)

starts_ambiguous = ambiguous(
    raw_starts_id_to_names
)


print(
    "=== DRIVER IDENTITY "
    "CROSS-SOURCE AUDIT ==="
)

print(
    f"Eligible normalized entries: "
    f"{totals['entries']}"
)

print()

print(
    "=== NORMALIZED ↔ RAW PROGRAM ==="
)

print(
    f"ID match:       "
    f"{totals['normalizedProgramIdMatch']}"
)

print(
    f"ID mismatch:    "
    f"{totals['normalizedProgramIdMismatch']}"
)

print(
    f"Name match:     "
    f"{totals['normalizedProgramNameMatch']}"
)

print(
    f"Name mismatch:  "
    f"{totals['normalizedProgramNameMismatch']}"
)

print(
    f"Match problems: "
    f"{totals['programMatchProblem']}"
)

print()

print(
    "=== RAW PROGRAM ↔ RAW STARTS ==="
)

print(
    f"Unique horse matches: "
    f"{totals['uniqueStartsMatch']}"
)

print(
    f"ID match:             "
    f"{totals['programStartsIdMatch']}"
)

print(
    f"ID mismatch:          "
    f"{totals['programStartsIdMismatch']}"
)

print(
    f"Name match:           "
    f"{totals['programStartsNameMatch']}"
)

print(
    f"Name mismatch:        "
    f"{totals['programStartsNameMismatch']}"
)

print(
    f"Starts match problems:"
    f" {totals['startsMatchProblem']}"
)

print()

print(
    "=== AMBIGUOUS ID -> NAME "
    "BY SOURCE ==="
)

print(
    f"Normalized:  "
    f"{len(normalized_ambiguous)}"
)

print(
    f"Raw program: "
    f"{len(program_ambiguous)}"
)

print(
    f"Raw starts:  "
    f"{len(starts_ambiguous)}"
)

print()

if normalized_ambiguous:
    print(
        "--- NORMALIZED AMBIGUOUS ---"
    )

    for key, values in sorted(
        normalized_ambiguous.items()
    ):
        print(
            f"{key}: {values}"
        )

    print()

if program_ambiguous:
    print(
        "--- RAW PROGRAM AMBIGUOUS ---"
    )

    for key, values in sorted(
        program_ambiguous.items()
    ):
        print(
            f"{key}: {values}"
        )

    print()

if starts_ambiguous:
    print(
        "--- RAW STARTS AMBIGUOUS ---"
    )

    for key, values in sorted(
        starts_ambiguous.items()
    ):
        print(
            f"{key}: {values}"
        )

    print()

for category in (
    "normalizedProgramMismatch",
    "programStartsMismatch",
    "programMatchProblem",
):
    rows = examples[
        category
    ]

    if not rows:
        continue

    print(
        f"=== SAMPLE {category} ==="
    )

    for row in rows:
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
    "totals":
        dict(totals),
    "ambiguousIdToName": {
        "normalized":
            normalized_ambiguous,
        "rawProgram":
            program_ambiguous,
        "rawStarts":
            starts_ambiguous,
    },
    "examples":
        dict(examples),
    "guardrails": {
        "matchedByHorseRegistrationNumber":
            True,
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
    "driver-identity-cross-source-audit.json"
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
