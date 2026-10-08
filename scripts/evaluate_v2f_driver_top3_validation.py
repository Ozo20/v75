from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from v75.candidate_v2a_speed import (
    score_field as score_v2a,
)

from v75.candidate_v2f_driver_top3 import (
    build_driver_corpus,
    score_field as score_v2f,
)


DEVELOPMENT_DATES = [
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

VALIDATION_DATES = [
    "2026-08-29",
    "2026-09-05",
    "2026-09-12",
    "2026-09-19",
]

ALL_PRE_RACE_DATES = (
    DEVELOPMENT_DATES
    + VALIDATION_DATES
)


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def metrics(
    ranks: list[int],
):
    return {
        "races":
            len(ranks),
        "top1":
            sum(
                rank <= 1
                for rank in ranks
            ),
        "top2":
            sum(
                rank <= 2
                for rank in ranks
            ),
        "top3":
            sum(
                rank <= 3
                for rank in ranks
            ),
        "top5":
            sum(
                rank <= 5
                for rank in ranks
            ),
        "averageWinnerRank":
            mean(ranks),
    }


snapshots = {
    day: load(
        Path("data/normalized")
        / day
        / "pre-race.json"
    )
    for day in (
        ALL_PRE_RACE_DATES
    )
}


all_ranks = {
    "v2a-speed": [],
    "v2f-driver-top3": [],
}

race_comparison = {
    "improved": 0,
    "equal": 0,
    "worse": 0,
}

meeting_comparison = {
    "better": 0,
    "equal": 0,
    "worse": 0,
}

per_meeting = []
corpus_summary = []


for target_day in (
    VALIDATION_DATES
):
    pre = snapshots[
        target_day
    ]

    corpus = (
        build_driver_corpus(
            snapshots,
            target_day,
        )
    )

    # Scores are generated entirely
    # from pre-race data before outcomes
    # are loaded for evaluation.
    scored_legs = []

    for leg in pre["legs"]:
        entries = [
            entry
            for entry
            in leg["entries"]
            if entry["start"][
                "eligibleForPrediction"
            ]
        ]

        v2a_rows = (
            score_v2a(
                entries
            )
        )

        v2f_rows = (
            score_v2f(
                entries,
                corpus,
            )
        )

        scored_legs.append(
            {
                "leg":
                    leg["leg"],
                "v2a": {
                    row[
                        "startNumber"
                    ]:
                        row["rank"]
                    for row
                    in v2a_rows
                },
                "v2f": {
                    row[
                        "startNumber"
                    ]:
                        row["rank"]
                    for row
                    in v2f_rows
                },
            }
        )

    outcomes = load(
        Path("data/normalized")
        / target_day
        / "outcomes.json"
    )

    outcomes_by_leg = {
        row["leg"]: row
        for row
        in outcomes["legs"]
    }

    meeting_ranks = {
        "v2a-speed": [],
        "v2f-driver-top3": [],
    }

    for scored in scored_legs:
        winner = int(
            outcomes_by_leg[
                scored["leg"]
            ][
                "winnerStartNumber"
            ]
        )

        rank_a = (
            scored[
                "v2a"
            ][winner]
        )

        rank_f = (
            scored[
                "v2f"
            ][winner]
        )

        all_ranks[
            "v2a-speed"
        ].append(
            rank_a
        )

        all_ranks[
            "v2f-driver-top3"
        ].append(
            rank_f
        )

        meeting_ranks[
            "v2a-speed"
        ].append(
            rank_a
        )

        meeting_ranks[
            "v2f-driver-top3"
        ].append(
            rank_f
        )

        if rank_f < rank_a:
            race_comparison[
                "improved"
            ] += 1
        elif rank_f > rank_a:
            race_comparison[
                "worse"
            ] += 1
        else:
            race_comparison[
                "equal"
            ] += 1

    base_metrics = metrics(
        meeting_ranks[
            "v2a-speed"
        ]
    )

    candidate_metrics = metrics(
        meeting_ranks[
            "v2f-driver-top3"
        ]
    )

    if (
        candidate_metrics[
            "top3"
        ]
        > base_metrics[
            "top3"
        ]
    ):
        meeting_comparison[
            "better"
        ] += 1

    elif (
        candidate_metrics[
            "top3"
        ]
        < base_metrics[
            "top3"
        ]
    ):
        meeting_comparison[
            "worse"
        ] += 1

    else:
        meeting_comparison[
            "equal"
        ] += 1

    per_meeting.append(
        {
            "date":
                target_day,
            "raceDayName":
                pre[
                    "raceDayName"
                ],
            "v2a":
                base_metrics,
            "v2f":
                candidate_metrics,
        }
    )

    corpus_summary.append(
        {
            "date":
                target_day,
            "dedupedStarts":
                corpus[
                    "dedupedStarts"
                ],
            "globalValid":
                corpus[
                    "globalValid"
                ],
            "globalTop3Rate":
                corpus[
                    "globalTop3Rate"
                ],
        }
    )


results = {
    name:
        metrics(ranks)
    for name, ranks
    in all_ranks.items()
}


print(
    "=== V2F DRIVER-TOP3 LOCKED VALIDATION ==="
)

print(
    f"Meetings: "
    f"{len(VALIDATION_DATES)}"
)

print(
    f"Races: "
    f"{results['v2a-speed']['races']}"
)

print()

for name in (
    "v2a-speed",
    "v2f-driver-top3",
):
    row = results[name]
    total = row["races"]

    print(
        f"{name:<20} "
        f"T1="
        f"{row['top1']}/{total} "
        f"({100*row['top1']/total:.1f}%) "
        f"T2="
        f"{row['top2']}/{total} "
        f"({100*row['top2']/total:.1f}%) "
        f"T3="
        f"{row['top3']}/{total} "
        f"({100*row['top3']/total:.1f}%) "
        f"T5="
        f"{row['top5']}/{total} "
        f"({100*row['top5']/total:.1f}%) "
        f"avgRank="
        f"{row['averageWinnerRank']:.2f}"
    )

print()

print(
    "Race-by-race vs V2A: "
    f"improved="
    f"{race_comparison['improved']} "
    f"equal="
    f"{race_comparison['equal']} "
    f"worse="
    f"{race_comparison['worse']}"
)

print(
    "Meeting Top3 vs V2A: "
    f"better="
    f"{meeting_comparison['better']} "
    f"equal="
    f"{meeting_comparison['equal']} "
    f"worse="
    f"{meeting_comparison['worse']}"
)

print()

print(
    "=== PER MEETING ==="
)

for row in per_meeting:
    print(
        f"{row['date']} "
        f"{row['raceDayName']:<14} "
        f"| V2A "
        f"T3="
        f"{row['v2a']['top3']}/7 "
        f"avg="
        f"{row['v2a']['averageWinnerRank']:.2f} "
        f"| V2F "
        f"T3="
        f"{row['v2f']['top3']}/7 "
        f"avg="
        f"{row['v2f']['averageWinnerRank']:.2f}"
    )

print()

print(
    "=== POINT-IN-TIME CORPUS ==="
)

for row in corpus_summary:
    print(
        f"{row['date']} "
        f"dedupStarts="
        f"{row['dedupedStarts']} "
        f"valid="
        f"{row['globalValid']} "
        f"globalTop3="
        f"{row['globalTop3Rate']:.4f}"
    )


report = {
    "schemaVersion":
        "1.0",
    "experiment":
        "v2f-driver-top3-validation",
    "scope":
        "locked-validation",
    "developmentDates":
        DEVELOPMENT_DATES,
    "validationDates":
        VALIDATION_DATES,
    "results":
        results,
    "raceComparisonVsV2A":
        race_comparison,
    "meetingTop3ComparisonVsV2A":
        meeting_comparison,
    "corpusSummary":
        corpus_summary,
    "perMeeting":
        per_meeting,
    "guardrails": {
        "candidateFrozenBeforeValidation":
            True,
        "weightsFrozenBeforeValidation":
            True,
        "sameHorseRowsExcluded":
            True,
        "preRaceSnapshotsOnlyForFeatures":
            True,
        "historyStrictlyBeforeTarget":
            True,
        "validationOutcomesLoadedOnlyAfterScoring":
            True,
        "marketUsed":
            False,
        "annualStatisticsUsed":
            False,
        "developmentRetunedAfterValidation":
            False,
    },
}

output = Path(
    "data/experiments/"
    "v2f-driver-top3-validation.json"
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
