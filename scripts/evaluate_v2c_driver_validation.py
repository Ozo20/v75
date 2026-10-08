from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from v75.candidate_v2a_speed import (
    score_field as score_v2a,
)

from v75.candidate_v2c_driver_continuity import (
    score_field as score_v2c,
)


DATES = [
    "2026-08-29",
    "2026-09-05",
    "2026-09-12",
    "2026-09-19",
]


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


all_ranks = {
    "v2a-speed": [],
    "v2c-continuity": [],
}

comparison = {
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


for date in DATES:
    root = (
        Path("data/normalized")
        / date
    )

    pre = load(
        root
        / "pre-race.json"
    )

    outcomes = load(
        root
        / "outcomes.json"
    )

    outcomes_by_leg = {
        row["leg"]: row
        for row
        in outcomes["legs"]
    }

    meeting_ranks = {
        "v2a-speed": [],
        "v2c-continuity": [],
    }

    for leg in pre["legs"]:
        entries = [
            entry
            for entry
            in leg["entries"]
            if entry["start"][
                "eligibleForPrediction"
            ]
        ]

        v2a_rows = score_v2a(
            entries
        )

        v2c_rows = score_v2c(
            entries
        )

        v2a_rank = {
            row["startNumber"]:
                row["rank"]
            for row
            in v2a_rows
        }

        v2c_rank = {
            row["startNumber"]:
                row["rank"]
            for row
            in v2c_rows
        }

        winner = int(
            outcomes_by_leg[
                leg["leg"]
            ][
                "winnerStartNumber"
            ]
        )

        rank_a = (
            v2a_rank[winner]
        )

        rank_c = (
            v2c_rank[winner]
        )

        all_ranks[
            "v2a-speed"
        ].append(
            rank_a
        )

        all_ranks[
            "v2c-continuity"
        ].append(
            rank_c
        )

        meeting_ranks[
            "v2a-speed"
        ].append(
            rank_a
        )

        meeting_ranks[
            "v2c-continuity"
        ].append(
            rank_c
        )

        if rank_c < rank_a:
            comparison[
                "improved"
            ] += 1
        elif rank_c > rank_a:
            comparison[
                "worse"
            ] += 1
        else:
            comparison[
                "equal"
            ] += 1

    v2a_metrics = metrics(
        meeting_ranks[
            "v2a-speed"
        ]
    )

    v2c_metrics = metrics(
        meeting_ranks[
            "v2c-continuity"
        ]
    )

    if (
        v2c_metrics["top3"]
        > v2a_metrics["top3"]
    ):
        meeting_comparison[
            "better"
        ] += 1
    elif (
        v2c_metrics["top3"]
        < v2a_metrics["top3"]
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
                date,
            "raceDayName":
                pre[
                    "raceDayName"
                ],
            "v2a":
                v2a_metrics,
            "v2c":
                v2c_metrics,
        }
    )


results = {
    name:
        metrics(ranks)
    for name, ranks
    in all_ranks.items()
}


print(
    "=== V2C DRIVER CONTINUITY "
    "VALIDATION ==="
)

print(
    f"Meetings: {len(DATES)}"
)

print(
    f"Races: "
    f"{results['v2a-speed']['races']}"
)

print()

for name in (
    "v2a-speed",
    "v2c-continuity",
):
    row = results[name]
    total = row["races"]

    print(
        f"{name:<18} "
        f"T1={row['top1']}/{total} "
        f"({100*row['top1']/total:.1f}%) "
        f"T2={row['top2']}/{total} "
        f"({100*row['top2']/total:.1f}%) "
        f"T3={row['top3']}/{total} "
        f"({100*row['top3']/total:.1f}%) "
        f"T5={row['top5']}/{total} "
        f"({100*row['top5']/total:.1f}%) "
        f"avgRank="
        f"{row['averageWinnerRank']:.2f}"
    )

print()

print(
    "Race-by-race vs V2A: "
    f"improved={comparison['improved']} "
    f"equal={comparison['equal']} "
    f"worse={comparison['worse']}"
)

print(
    "Meeting Top3 vs V2A: "
    f"better={meeting_comparison['better']} "
    f"equal={meeting_comparison['equal']} "
    f"worse={meeting_comparison['worse']}"
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
        f"T3={row['v2a']['top3']}/7 "
        f"avg={row['v2a']['averageWinnerRank']:.2f} "
        f"| V2C "
        f"T3={row['v2c']['top3']}/7 "
        f"avg={row['v2c']['averageWinnerRank']:.2f}"
    )


report = {
    "schemaVersion":
        "1.0",
    "experiment":
        "v2c-driver-continuity-validation",
    "scope":
        "locked-validation",
    "dates":
        DATES,
    "results":
        results,
    "raceComparisonVsV2A":
        comparison,
    "meetingTop3ComparisonVsV2A":
        meeting_comparison,
    "perMeeting":
        per_meeting,
    "guardrails": {
        "weightsFrozenBeforeValidation":
            True,
        "developmentRetunedAfterValidation":
            False,
        "marketUsed":
            False,
        "annualStatisticsUsed":
            False,
    },
}

output = Path(
    "data/experiments/"
    "v2c-driver-continuity-validation.json"
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
