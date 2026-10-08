from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from v75.track_identity import (
    history_track_code_for_race_day_key,
    race_day_prefix,
)


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


entries = 0
history_rows = 0
history_track_present = 0

same_track_latest = 0
same_track_1 = 0
same_track_2 = 0
same_track_3 = 0

same_track_history_rows = 0

repeat_distribution = Counter()
history_tracks = Counter()

meeting_rows = []


for date in DATES:
    pre = load(
        Path("data/normalized")
        / date
        / "pre-race.json"
    )

    race_day_key = (
        pre["raceDayKey"]
    )

    prefix = race_day_prefix(
        race_day_key
    )

    current_track = (
        history_track_code_for_race_day_key(
            race_day_key
        )
    )

    meeting_entries = 0
    meeting_same_1 = 0
    meeting_same_2 = 0
    meeting_same_3 = 0
    meeting_latest = 0

    for leg in pre["legs"]:
        for entry in leg["entries"]:
            if not entry["start"][
                "eligibleForPrediction"
            ]:
                continue

            entries += 1
            meeting_entries += 1

            history = sorted(
                entry.get("history")
                or [],
                key=lambda row: (
                    row.get("raceDate")
                    or ""
                ),
                reverse=True,
            )

            codes = []

            for row in history:
                history_rows += 1

                code = row.get(
                    "trackCode"
                )

                if not code:
                    continue

                history_track_present += 1

                code = str(
                    code
                ).strip()

                codes.append(
                    code
                )

                history_tracks[
                    code
                ] += 1

            repeats = sum(
                code == current_track
                for code in codes
            )

            same_track_history_rows += (
                repeats
            )

            repeat_distribution[
                repeats
            ] += 1

            if (
                codes
                and codes[0]
                == current_track
            ):
                same_track_latest += 1
                meeting_latest += 1

            if repeats >= 1:
                same_track_1 += 1
                meeting_same_1 += 1

            if repeats >= 2:
                same_track_2 += 1
                meeting_same_2 += 1

            if repeats >= 3:
                same_track_3 += 1
                meeting_same_3 += 1

    meeting_rows.append(
        {
            "date":
                date,
            "raceDayName":
                pre["raceDayName"],
            "raceDayKey":
                race_day_key,
            "raceDayPrefix":
                prefix,
            "historyTrackCode":
                current_track,
            "entries":
                meeting_entries,
            "sameTrackLatest":
                meeting_latest,
            "atLeast1":
                meeting_same_1,
            "atLeast2":
                meeting_same_2,
            "atLeast3":
                meeting_same_3,
        }
    )


print(
    "=== TRACK FEATURE FEASIBILITY V2 ==="
)

print(
    f"Development meetings:       "
    f"{len(DATES)}"
)

print(
    f"Development entries:        "
    f"{entries}"
)

print(
    f"Historical form rows:       "
    f"{history_rows}"
)

print()

print(
    "=== VERIFIED CURRENT TRACK MAPPING ==="
)

for row in meeting_rows:
    print(
        f"{row['date']} "
        f"{row['raceDayName']:<14} "
        f"{row['raceDayPrefix']:>2} "
        f"-> "
        f"{row['historyTrackCode']}"
    )

print()

print(
    "=== HISTORICAL TRACK COVERAGE ==="
)

print(
    f"Rows with trackCode:        "
    f"{history_track_present}/"
    f"{history_rows} "
    f"({100*history_track_present/history_rows:.1f}%)"
)

print(
    f"Same-track history rows:    "
    f"{same_track_history_rows}"
)

print(
    f"Unique historical tracks:   "
    f"{len(history_tracks)}"
)

print()

print(
    "=== HORSE × CURRENT TRACK COVERAGE ==="
)

print(
    f"Last start same track:      "
    f"{same_track_latest}/{entries} "
    f"({100*same_track_latest/entries:.1f}%)"
)

print(
    f"At least 1 prior same track:"
    f" {same_track_1}/{entries} "
    f"({100*same_track_1/entries:.1f}%)"
)

print(
    f"At least 2 prior same track:"
    f" {same_track_2}/{entries} "
    f"({100*same_track_2/entries:.1f}%)"
)

print(
    f"At least 3 prior same track:"
    f" {same_track_3}/{entries} "
    f"({100*same_track_3/entries:.1f}%)"
)

print()

print(
    "=== SAME-TRACK REPEAT DISTRIBUTION ==="
)

for repeats in sorted(
    repeat_distribution
):
    count = repeat_distribution[
        repeats
    ]

    print(
        f"{repeats} prior starts: "
        f"{count:>4} "
        f"({100*count/entries:5.1f}%)"
    )

print()

print(
    "=== PER MEETING COVERAGE ==="
)

for row in meeting_rows:
    total = row["entries"]

    print(
        f"{row['date']} "
        f"{row['raceDayName']:<14} "
        f"{row['historyTrackCode']:>2} "
        f"| latest="
        f"{row['sameTrackLatest']:>2}/{total:<3} "
        f"| 1+="
        f"{row['atLeast1']:>2}/{total:<3} "
        f"({100*row['atLeast1']/total:5.1f}%) "
        f"| 2+="
        f"{row['atLeast2']:>2} "
        f"| 3+="
        f"{row['atLeast3']:>2}"
    )


report = {
    "schemaVersion":
        "2.0",
    "scope":
        "development-only-read-only",
    "dates":
        DATES,
    "entries":
        entries,
    "historyRows":
        history_rows,
    "historyTrackCoverage":
        history_track_present
        / history_rows,
    "sameTrackHistoryRows":
        same_track_history_rows,
    "horseTrackCoverage": {
        "sameTrackLatest":
            same_track_latest,
        "sameTrackLatestRate":
            same_track_latest
            / entries,
        "atLeast1":
            same_track_1,
        "atLeast1Rate":
            same_track_1
            / entries,
        "atLeast2":
            same_track_2,
        "atLeast2Rate":
            same_track_2
            / entries,
        "atLeast3":
            same_track_3,
        "atLeast3Rate":
            same_track_3
            / entries,
    },
    "repeatDistribution":
        dict(
            repeat_distribution
        ),
    "meetings":
        meeting_rows,
    "guardrails": {
        "currentTrackSource":
            "explicit verified race-day-prefix mapping",
        "historicalTrackSource":
            "history[].trackCode",
        "outcomesRead":
            False,
        "marketRead":
            False,
        "validationUsed":
            False,
        "championModified":
            False,
    },
}

output = Path(
    "data/experiments/"
    "track-feature-feasibility-v2.json"
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
