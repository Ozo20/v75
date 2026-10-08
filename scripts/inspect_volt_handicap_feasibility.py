from __future__ import annotations

import json
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


entries = 0
volt_entries = 0
auto_entries = 0

volt_races = 0
auto_races = 0

volt_multi_band_races = 0
volt_single_band_races = 0

extra_counts = Counter()
race_band_counts = Counter()

start_numbers_by_extra = {}
post_positions_by_extra = {}

race_rows = []


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


for day in DATES:
    pre = load(
        Path("data/normalized")
        / day
        / "pre-race.json"
    )

    for leg in pre["legs"]:
        method = str(
            leg["race"].get(
                "startMethod"
            )
            or ""
        )

        eligible = [
            entry
            for entry
            in leg["entries"]
            if entry["start"][
                "eligibleForPrediction"
            ]
        ]

        extras = []

        for entry in eligible:
            entries += 1

            extra = int(
                (
                    entry.get("start")
                    or {}
                ).get(
                    "extraDistance"
                )
                or 0
            )

            extras.append(extra)

            if method == "Volt":
                volt_entries += 1
                extra_counts[extra] += 1

                start_numbers_by_extra.setdefault(
                    extra,
                    [],
                ).append(
                    int(
                        entry[
                            "startNumber"
                        ]
                    )
                )

                post = (
                    entry.get("start")
                    or {}
                ).get(
                    "postPosition"
                )

                if post is not None:
                    try:
                        post = int(post)
                    except (
                        TypeError,
                        ValueError,
                    ):
                        post = None

                if post is not None:
                    post_positions_by_extra.setdefault(
                        extra,
                        [],
                    ).append(post)

            elif method == "Auto":
                auto_entries += 1

        if method == "Volt":
            volt_races += 1

            bands = sorted(
                set(extras)
            )

            race_band_counts[
                tuple(bands)
            ] += 1

            if len(bands) > 1:
                volt_multi_band_races += 1
            else:
                volt_single_band_races += 1

            race_rows.append(
                {
                    "date":
                        day,
                    "raceDayName":
                        pre[
                            "raceDayName"
                        ],
                    "leg":
                        leg["leg"],
                    "baseDistance":
                        leg["race"][
                            "distance"
                        ],
                    "bands":
                        bands,
                    "entries":
                        len(eligible),
                    "countsByExtra": {
                        str(extra):
                            extras.count(
                                extra
                            )
                        for extra in bands
                    },
                }
            )

        elif method == "Auto":
            auto_races += 1


print(
    "=== VOLT HANDICAP FEASIBILITY ==="
)

print(
    f"Development entries:      "
    f"{entries}"
)

print(
    f"Volt entries:             "
    f"{volt_entries}"
)

print(
    f"Auto entries:             "
    f"{auto_entries}"
)

print()

print(
    f"Volt races:               "
    f"{volt_races}"
)

print(
    f"Volt multi-band races:    "
    f"{volt_multi_band_races}/"
    f"{volt_races}"
)

print(
    f"Volt single-band races:   "
    f"{volt_single_band_races}/"
    f"{volt_races}"
)

print(
    f"Auto races:               "
    f"{auto_races}"
)

print()

print(
    "=== VOLT EXTRA DISTANCE DISTRIBUTION ==="
)

for extra, count in sorted(
    extra_counts.items()
):
    print(
        f"+{extra:>2} m: "
        f"{count:>4} entries"
    )

print()

print(
    "=== VOLT RACE BAND PATTERNS ==="
)

for bands, count in (
    race_band_counts.most_common()
):
    label = ", ".join(
        f"+{value}m"
        for value in bands
    )

    print(
        f"{count:>2} races: "
        f"{label}"
    )

print()

print(
    "=== START NUMBER BY HANDICAP BAND ==="
)

for extra in sorted(
    start_numbers_by_extra
):
    values = (
        start_numbers_by_extra[
            extra
        ]
    )

    print(
        f"+{extra:>2} m "
        f"n={len(values):>3} "
        f"min={min(values):>2} "
        f"max={max(values):>2} "
        f"mean="
        f"{sum(values)/len(values):.2f}"
    )

print()

print(
    "=== POST POSITION BY HANDICAP BAND ==="
)

if not post_positions_by_extra:
    print(
        "No usable postPosition values."
    )
else:
    for extra in sorted(
        post_positions_by_extra
    ):
        values = (
            post_positions_by_extra[
                extra
            ]
        )

        print(
            f"+{extra:>2} m "
            f"n={len(values):>3} "
            f"min={min(values):>2} "
            f"max={max(values):>2} "
            f"mean="
            f"{sum(values)/len(values):.2f}"
        )

print()

print(
    "=== MULTI-BAND VOLT RACES ==="
)

for row in race_rows:
    if len(
        row["bands"]
    ) <= 1:
        continue

    print(
        f"{row['date']} "
        f"{row['raceDayName']:<14} "
        f"leg={row['leg']} "
        f"base={row['baseDistance']} "
        f"bands={row['bands']} "
        f"counts={row['countsByExtra']}"
    )


report = {
    "schemaVersion":
        "1.0",
    "scope":
        "development-only-read-only",
    "entries":
        entries,
    "voltEntries":
        volt_entries,
    "autoEntries":
        auto_entries,
    "voltRaces":
        volt_races,
    "autoRaces":
        auto_races,
    "voltMultiBandRaces":
        volt_multi_band_races,
    "voltSingleBandRaces":
        volt_single_band_races,
    "extraDistanceCounts":
        {
            str(key): value
            for key, value
            in sorted(
                extra_counts.items()
            )
        },
    "raceBandPatterns": {
        ",".join(
            str(value)
            for value in key
        ):
            count
        for key, count
        in race_band_counts.items()
    },
    "multiBandRaceDetails": [
        row
        for row in race_rows
        if len(
            row["bands"]
        ) > 1
    ],
    "guardrails": {
        "developmentOnly":
            True,
        "outcomesRead":
            False,
        "marketRead":
            False,
        "validationUsed":
            False,
        "modelsModified":
            False,
    },
}

output = Path(
    "data/experiments/"
    "volt-handicap-feasibility.json"
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
