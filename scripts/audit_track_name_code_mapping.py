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


def norm(value):
    if value is None:
        return None

    text = str(value).strip().casefold()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text or None


name_to_codes = defaultdict(Counter)
code_to_names = defaultdict(Counter)

history_rows = 0
rows_with_both = 0

current_meetings = []


for date in DATES:
    pre = load(
        Path("data/normalized")
        / date
        / "pre-race.json"
    )

    current_meetings.append(
        {
            "date":
                date,
            "raceDayName":
                pre["raceDayName"],
            "normalizedName":
                norm(
                    pre["raceDayName"]
                ),
            "raceDayKey":
                pre["raceDayKey"],
        }
    )

    for leg in pre["legs"]:
        for entry in leg["entries"]:
            if not entry["start"][
                "eligibleForPrediction"
            ]:
                continue

            for row in (
                entry.get("history")
                or []
            ):
                history_rows += 1

                code = row.get(
                    "trackCode"
                )

                sport_track = row.get(
                    "sportTrack"
                )

                if not code or not sport_track:
                    continue

                rows_with_both += 1

                code = str(
                    code
                ).strip()

                name = norm(
                    sport_track
                )

                if not name:
                    continue

                name_to_codes[
                    name
                ][
                    code
                ] += 1

                code_to_names[
                    code
                ][
                    name
                ] += 1


print(
    "=== TRACK NAME ↔ CODE AUDIT ==="
)

print(
    f"Historical rows:              "
    f"{history_rows}"
)

print(
    f"Rows with code + sportTrack:  "
    f"{rows_with_both}/{history_rows} "
    f"({100*rows_with_both/history_rows:.1f}%)"
)

print()

print(
    "=== CURRENT DEVELOPMENT TRACKS ==="
)

resolved = {}
unresolved = []


for meeting in current_meetings:
    current_name = meeting[
        "normalizedName"
    ]

    exact = (
        name_to_codes.get(
            current_name
        )
    )

    print()
    print(
        f"{meeting['date']} "
        f"{meeting['raceDayName']} "
        f"| {meeting['raceDayKey']}"
    )

    if exact:
        print(
            "  EXACT sportTrack match:"
        )

        for code, count in (
            exact.most_common()
        ):
            print(
                f"    {code:<8} "
                f"{count} historical rows"
            )

        if len(exact) == 1:
            resolved[
                meeting["date"]
            ] = next(
                iter(exact)
            )

        continue

    # If exact name fails, show close
    # candidates by substring only.
    candidates = []

    for history_name, codes in (
        name_to_codes.items()
    ):
        if (
            current_name in history_name
            or history_name in current_name
        ):
            candidates.append(
                (
                    history_name,
                    codes,
                )
            )

    if candidates:
        print(
            "  No exact match. "
            "Substring candidates:"
        )

        for history_name, codes in (
            candidates
        ):
            print(
                f"    {history_name}: "
                f"{dict(codes)}"
            )
    else:
        print(
            "  No exact/substr match."
        )

    unresolved.append(
        meeting["date"]
    )


print()
print(
    "=== UNIQUE HISTORICAL SPORTTRACK -> CODE MAP ==="
)

unique_name_map = {}

for name in sorted(
    name_to_codes
):
    codes = (
        name_to_codes[
            name
        ]
    )

    if len(codes) == 1:
        code = next(
            iter(codes)
        )

        unique_name_map[
            name
        ] = code

        print(
            f"{name:<35} -> "
            f"{code:<6} "
            f"({codes[code]} rows)"
        )


print()
print(
    "=== AMBIGUOUS SPORTTRACK NAMES ==="
)

ambiguous_names = {
    name: dict(codes)
    for name, codes
    in name_to_codes.items()
    if len(codes) > 1
}

if not ambiguous_names:
    print(
        "None."
    )
else:
    for name, codes in sorted(
        ambiguous_names.items()
    ):
        print(
            f"{name}: {codes}"
        )


print()
print(
    "=== AMBIGUOUS TRACK CODES ==="
)

ambiguous_codes = {
    code: dict(names)
    for code, names
    in code_to_names.items()
    if len(names) > 1
}

if not ambiguous_codes:
    print(
        "None."
    )
else:
    for code, names in sorted(
        ambiguous_codes.items()
    ):
        print(
            f"{code}: {names}"
        )


print()
print(
    "=== RESOLUTION SUMMARY ==="
)

for meeting in current_meetings:
    date = meeting["date"]

    print(
        f"{date} "
        f"{meeting['raceDayName']:<14} "
        f"-> "
        f"{resolved.get(date, 'UNRESOLVED')}"
    )


report = {
    "schemaVersion":
        "1.0",
    "scope":
        "development-only-read-only",
    "historyRows":
        history_rows,
    "rowsWithTrackCodeAndSportTrack":
        rows_with_both,
    "resolvedCurrentTrackCodes":
        resolved,
    "unresolvedDates":
        unresolved,
    "uniqueSportTrackToCode":
        unique_name_map,
    "ambiguousSportTrackNames":
        ambiguous_names,
    "ambiguousTrackCodes":
        ambiguous_codes,
    "guardrails": {
        "mappingDerivedFromHistoricalPreRaceRows":
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
    "track-name-code-mapping-audit.json"
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
