from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from v75.candidate_v2a_speed import (
    score_field as score_v2a,
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


starter_counts = Counter()
winner_counts = Counter()
v2a_top_counts = Counter()
v2a_correct_counts = Counter()

relative_winner = Counter()
relative_v2a_top = Counter()

miss_direction = Counter()

volt_races = 0
v2a_correct = 0

rows = []


for day in DATES:
    root = (
        Path("data/normalized")
        / day
    )

    pre = load(
        root / "pre-race.json"
    )

    outcomes = load(
        root / "outcomes.json"
    )

    outcomes_by_leg = {
        row["leg"]: row
        for row in outcomes["legs"]
    }

    for leg in pre["legs"]:
        if (
            leg["race"][
                "startMethod"
            ]
            != "Volt"
        ):
            continue

        volt_races += 1

        entries = [
            entry
            for entry in leg["entries"]
            if entry["start"][
                "eligibleForPrediction"
            ]
        ]

        entry_by_number = {
            int(entry["startNumber"]):
                entry
            for entry in entries
        }

        extras = {
            int(entry["startNumber"]):
                int(
                    (
                        entry.get("start")
                        or {}
                    ).get(
                        "extraDistance"
                    )
                    or 0
                )
            for entry in entries
        }

        for extra in extras.values():
            starter_counts[
                extra
            ] += 1

        bands = sorted(
            set(
                extras.values()
            )
        )

        if len(bands) < 2:
            raise RuntimeError(
                "Expected multi-band Volt race."
            )

        min_extra = bands[0]
        max_extra = bands[-1]

        winner_number = int(
            outcomes_by_leg[
                leg["leg"]
            ][
                "winnerStartNumber"
            ]
        )

        if winner_number not in entry_by_number:
            raise RuntimeError(
                f"Winner {winner_number} "
                "not eligible/present."
            )

        winner_extra = extras[
            winner_number
        ]

        winner_counts[
            winner_extra
        ] += 1

        v2a_rows = score_v2a(
            entries
        )

        top = next(
            row
            for row in v2a_rows
            if row["rank"] == 1
        )

        top_number = int(
            top["startNumber"]
        )

        top_extra = extras[
            top_number
        ]

        v2a_top_counts[
            top_extra
        ] += 1

        correct = (
            top_number
            == winner_number
        )

        if correct:
            v2a_correct += 1

            v2a_correct_counts[
                winner_extra
            ] += 1

        def relative_label(
            extra: int,
        ) -> str:
            if extra == min_extra:
                return "FRONT"

            if extra == max_extra:
                return "BACK"

            return "MIDDLE"

        relative_winner[
            relative_label(
                winner_extra
            )
        ] += 1

        relative_v2a_top[
            relative_label(
                top_extra
            )
        ] += 1

        if not correct:
            if winner_extra < top_extra:
                miss_direction[
                    "WINNER_CLOSER_TO_FRONT"
                ] += 1

            elif winner_extra > top_extra:
                miss_direction[
                    "WINNER_FARTHER_BACK"
                ] += 1

            else:
                miss_direction[
                    "SAME_HANDICAP_BAND"
                ] += 1

        rows.append(
            {
                "date":
                    day,
                "raceDayName":
                    pre[
                        "raceDayName"
                    ],
                "leg":
                    leg["leg"],
                "bands":
                    bands,
                "winnerStartNumber":
                    winner_number,
                "winnerHorse":
                    entry_by_number[
                        winner_number
                    ][
                        "horse"
                    ][
                        "name"
                    ],
                "winnerExtraDistance":
                    winner_extra,
                "winnerRelativeBand":
                    relative_label(
                        winner_extra
                    ),
                "v2aTopStartNumber":
                    top_number,
                "v2aTopHorse":
                    entry_by_number[
                        top_number
                    ][
                        "horse"
                    ][
                        "name"
                    ],
                "v2aTopExtraDistance":
                    top_extra,
                "v2aTopRelativeBand":
                    relative_label(
                        top_extra
                    ),
                "v2aCorrect":
                    correct,
            }
        )


print(
    "=== VOLT HANDICAP WINNER DIAGNOSTIC ==="
)

print(
    f"Development Volt races: "
    f"{volt_races}"
)

print(
    f"V2A Top1 correct:       "
    f"{v2a_correct}/{volt_races} "
    f"({100*v2a_correct/volt_races:.1f}%)"
)

print()

print(
    "=== ABSOLUTE HANDICAP BANDS ==="
)

all_bands = sorted(
    set(starter_counts)
    | set(winner_counts)
)

for extra in all_bands:
    starters = starter_counts[
        extra
    ]

    winners = winner_counts[
        extra
    ]

    top_picks = v2a_top_counts[
        extra
    ]

    correct = v2a_correct_counts[
        extra
    ]

    win_rate = (
        winners / starters
        if starters
        else 0.0
    )

    print(
        f"+{extra:>2} m "
        f"| starters={starters:>3} "
        f"| winners={winners:>2} "
        f"| win/start="
        f"{100*win_rate:5.1f}% "
        f"| V2A top picks={top_picks:>2} "
        f"| V2A correct={correct:>2}"
    )

print()

print(
    "=== RELATIVE BAND OF ACTUAL WINNER ==="
)

for key in (
    "FRONT",
    "MIDDLE",
    "BACK",
):
    count = relative_winner[
        key
    ]

    print(
        f"{key:<8} "
        f"{count:>2}/{volt_races} "
        f"({100*count/volt_races:5.1f}%)"
    )

print()

print(
    "=== RELATIVE BAND OF V2A TOP PICK ==="
)

for key in (
    "FRONT",
    "MIDDLE",
    "BACK",
):
    count = relative_v2a_top[
        key
    ]

    print(
        f"{key:<8} "
        f"{count:>2}/{volt_races} "
        f"({100*count/volt_races:5.1f}%)"
    )

print()

print(
    "=== V2A MISSES: HANDICAP DIRECTION ==="
)

misses = (
    volt_races
    - v2a_correct
)

for key in (
    "WINNER_CLOSER_TO_FRONT",
    "SAME_HANDICAP_BAND",
    "WINNER_FARTHER_BACK",
):
    count = miss_direction[
        key
    ]

    print(
        f"{key:<24} "
        f"{count:>2}/{misses}"
    )

print()

print(
    "Interpretation guide:"
)

print(
    "- WINNER_CLOSER_TO_FRONT: "
    "a front-band preference might have helped."
)

print(
    "- WINNER_FARTHER_BACK: "
    "a generic distance penalty might have hurt."
)

print(
    "- SAME_HANDICAP_BAND: "
    "extraDistance alone cannot fix the miss."
)

print()

print(
    "=== PER VOLT RACE ==="
)

for row in rows:
    marker = (
        "CORRECT"
        if row["v2aCorrect"]
        else "MISS"
    )

    print(
        f"{row['date']} "
        f"{row['raceDayName']:<14} "
        f"leg={row['leg']} "
        f"| winner "
        f"#{row['winnerStartNumber']} "
        f"{row['winnerHorse']} "
        f"+{row['winnerExtraDistance']}m "
        f"({row['winnerRelativeBand']}) "
        f"| V2A "
        f"#{row['v2aTopStartNumber']} "
        f"{row['v2aTopHorse']} "
        f"+{row['v2aTopExtraDistance']}m "
        f"({row['v2aTopRelativeBand']}) "
        f"| {marker}"
    )


report = {
    "schemaVersion":
        "1.0",
    "scope":
        "development-only-outcome-diagnostic",
    "voltRaces":
        volt_races,
    "v2aTop1Correct":
        v2a_correct,
    "starterCountsByExtraDistance":
        dict(starter_counts),
    "winnerCountsByExtraDistance":
        dict(winner_counts),
    "v2aTopPickCountsByExtraDistance":
        dict(v2a_top_counts),
    "v2aCorrectCountsByExtraDistance":
        dict(v2a_correct_counts),
    "relativeWinnerBand":
        dict(relative_winner),
    "relativeV2aTopBand":
        dict(relative_v2a_top),
    "v2aMissDirection":
        dict(miss_direction),
    "races":
        rows,
    "guardrails": {
        "developmentOnly":
            True,
        "validationUsed":
            False,
        "marketUsed":
            False,
        "modelsModified":
            False,
        "diagnosticOnly":
            True,
    },
}

output = Path(
    "data/experiments/"
    "volt-handicap-winner-diagnostic.json"
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
