from __future__ import annotations

import json
from pathlib import Path

from v75.candidate_v2a_speed import (
    score_field as score_v2a,
)

from v75.candidate_v2f_driver_top3_identity_v2 import (
    build_driver_corpus,
    score_field as score_v2f,
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


snapshots = {
    day: load(
        Path("data/normalized")
        / day
        / "pre-race.json"
    )
    for day in DATES
}

ranks_a = []
ranks_f = []

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


for day in DATES:
    pre = snapshots[day]

    corpus = build_driver_corpus(
        snapshots,
        day,
    )

    scored = []

    for leg in pre["legs"]:
        entries = [
            entry
            for entry
            in leg["entries"]
            if entry["start"][
                "eligibleForPrediction"
            ]
        ]

        a_rows = score_v2a(
            entries
        )

        f_rows = score_v2f(
            entries,
            corpus,
        )

        scored.append(
            {
                "leg": leg["leg"],
                "a": {
                    row["startNumber"]:
                        row["rank"]
                    for row in a_rows
                },
                "f": {
                    row["startNumber"]:
                        row["rank"]
                    for row in f_rows
                },
            }
        )

    # Outcomes are loaded only after
    # all pre-race scores for the meeting
    # have been generated.
    outcomes = load(
        Path("data/normalized")
        / day
        / "outcomes.json"
    )

    outcome_by_leg = {
        row["leg"]: row
        for row in outcomes["legs"]
    }

    meeting_a = []
    meeting_f = []

    for row in scored:
        winner = int(
            outcome_by_leg[
                row["leg"]
            ][
                "winnerStartNumber"
            ]
        )

        rank_a = row["a"][winner]
        rank_f = row["f"][winner]

        ranks_a.append(rank_a)
        ranks_f.append(rank_f)

        meeting_a.append(rank_a)
        meeting_f.append(rank_f)

        if rank_f < rank_a:
            comparison["improved"] += 1
        elif rank_f > rank_a:
            comparison["worse"] += 1
        else:
            comparison["equal"] += 1

    top3_a = sum(
        rank <= 3
        for rank in meeting_a
    )

    top3_f = sum(
        rank <= 3
        for rank in meeting_f
    )

    if top3_f > top3_a:
        meeting_comparison[
            "better"
        ] += 1
    elif top3_f < top3_a:
        meeting_comparison[
            "worse"
        ] += 1
    else:
        meeting_comparison[
            "equal"
        ] += 1


def metrics(ranks):
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
        "rankSum":
            sum(ranks),
        "averageWinnerRank":
            sum(ranks)
            / len(ranks),
    }


result_a = metrics(
    ranks_a
)

result_f = metrics(
    ranks_f
)


print(
    "=== V2F IDENTITY-V2 DEVELOPMENT REPRODUCTION ==="
)

print(
    "V2A:",
    result_a,
)

print(
    "V2F:",
    result_f,
)

print(
    "Race comparison:",
    comparison,
)

print(
    "Meeting Top3:",
    meeting_comparison,
)


expected_v2f = {
    "races": 84,
    "top1": 22,
    "top2": 36,
    "top3": 47,
    "top5": 62,
    "rankSum": 314,
}

for key, expected in (
    expected_v2f.items()
):
    actual = result_f[key]

    if actual != expected:
        raise SystemExit(
            "REFUSING: corrected frozen "
            "candidate does not reproduce "
            f"development {key}: "
            f"expected {expected}, "
            f"got {actual}."
        )


expected_comparison = {
    "improved": 12,
    "equal": 65,
    "worse": 7,
}

if comparison != expected_comparison:
    raise SystemExit(
        "REFUSING: race comparison changed. "
        f"{comparison}"
    )


expected_meeting = {
    "better": 2,
    "equal": 10,
    "worse": 0,
}

if meeting_comparison != expected_meeting:
    raise SystemExit(
        "REFUSING: meeting comparison changed. "
        f"{meeting_comparison}"
    )


print()
print(
    "PASS: frozen identity-v2 candidate "
    "exactly reproduces selected "
    "development result."
)
