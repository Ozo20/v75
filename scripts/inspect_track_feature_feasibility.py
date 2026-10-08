from __future__ import annotations

import json
import re
from collections import Counter
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


def current_track_code(
    race_day_key: str,
):
    match = re.match(
        r"^(.+?)_NR_",
        race_day_key,
    )

    if not match:
        return None

    return match.group(1)


entries = 0
history_rows = 0
history_track_present = 0

same_track_1 = 0
same_track_2 = 0
same_track_3 = 0
same_track_latest = 0

current_tracks = Counter()
history_tracks = Counter()
repeat_distribution = Counter()

meeting_rows = []


for date in DATES:
    pre = load(
        Path("data/normalized")
        / date
        / "pre-race.json"
    )

    track = current_track_code(
        pre["raceDayKey"]
    )

    current_tracks[
        track or "<missing>"
    ] += 1

    meeting_entries = 0
    meeting_same_1 = 0

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

                if code:
                    history_track_present += 1

                    code = str(
                        code
                    ).strip()

                    history_tracks[
                        code
                    ] += 1

                    codes.append(
                        code
                    )

            repeats = sum(
                code == track
                for code in codes
            )

            repeat_distribution[
                repeats
            ] += 1

            if repeats >= 1:
                same_track_1 += 1
                meeting_same_1 += 1

            if repeats >= 2:
                same_track_2 += 1

            if repeats >= 3:
                same_track_3 += 1

            if (
                codes
                and codes[0] == track
            ):
                same_track_latest += 1

    meeting_rows.append(
        {
            "date": date,
            "raceDayKey":
                pre["raceDayKey"],
            "raceDayName":
                pre["raceDayName"],
            "derivedTrackCode":
                track,
            "entries":
                meeting_entries,
            "entriesWithPriorSameTrack":
                meeting_same_1,
        }
    )


print(
    "=== TRACK FEATURE FEASIBILITY ==="
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
    "=== CURRENT TRACK IDENTITY ==="
)

for row in meeting_rows:
    print(
        f"{row['date']} "
        f"{row['raceDayName']:<14} "
        f"key={row['raceDayKey']:<28} "
        f"track={row['derivedTrackCode']}"
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
    "=== MOST COMMON HISTORICAL TRACKS ==="
)

for track, count in (
    history_tracks.most_common(25)
):
    print(
        f"{count:>4}  {track}"
    )

print()

print(
    "=== PER MEETING SAME-TRACK COVERAGE ==="
)

for row in meeting_rows:
    count = row[
        "entriesWithPriorSameTrack"
    ]

    total = row["entries"]

    print(
        f"{row['date']} "
        f"{row['raceDayName']:<14} "
        f"{count:>3}/{total:<3} "
        f"({100*count/total:5.1f}%)"
    )


report = {
    "schemaVersion":
        "1.0",
    "scope":
        "development-only-read-only",
    "dates":
        DATES,
    "meetings":
        meeting_rows,
    "entries":
        entries,
    "historyRows":
        history_rows,
    "historyTrackCoverage":
        history_track_present
        / history_rows,
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
    "guardrails": {
        "currentTrackDerivedFromRaceDayKey":
            True,
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
    "track-feature-feasibility.json"
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
