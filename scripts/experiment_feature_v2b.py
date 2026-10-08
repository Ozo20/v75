from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from v75.baseline_safe_v1 import (
    build_safe_projection,
    score_entry,
)

from v75.context_speed_v2b import (
    context_weighted_speed,
)

from v75.form_features_v2 import (
    extract_form_features,
    percentile_scores,
)


BASE_WEIGHT = 0.70
SPEED_WEIGHT = 0.30


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def percentile_high(
    values: list[float],
) -> list[float]:
    if not values:
        return []

    lo = min(values)
    hi = max(values)

    if lo == hi:
        return [
            1.0
            for _ in values
        ]

    return [
        (value - lo)
        / (hi - lo)
        for value in values
    ]


def metrics(
    ranks: list[int],
) -> dict[str, Any]:
    total = len(ranks)

    return {
        "races": total,
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


def rank_scores(
    entries,
    combined_scores,
):
    rows = [
        {
            "startNumber":
                entry[
                    "startNumber"
                ],
            "score":
                combined_scores[i],
        }
        for i, entry
        in enumerate(entries)
    ]

    rows.sort(
        key=lambda row: (
            -row["score"],
            row["startNumber"],
        )
    )

    return {
        row["startNumber"]:
            rank
        for rank, row
        in enumerate(
            rows,
            1,
        )
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--dates",
        nargs="+",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    winner_ranks = {
        "safe-v1": [],
        "v2a-speed": [],
        "v2b-context": [],
    }

    tier_counts = Counter()

    per_meeting = []

    total_entries = 0

    for date in args.dates:
        base = (
            args.root
            / date
        )

        pre = load(
            base
            / "pre-race.json"
        )

        outcomes = load(
            base
            / "outcomes.json"
        )

        outcome_by_leg = {
            row["leg"]: row
            for row
            in outcomes["legs"]
        }

        meeting_ranks = {
            key: []
            for key
            in winner_ranks
        }

        for leg in pre["legs"]:
            entries = [
                entry
                for entry
                in leg["entries"]
                if entry[
                    "start"
                ][
                    "eligibleForPrediction"
                ]
            ]

            current_distance = int(
                leg["race"][
                    "distance"
                ]
            )

            current_method = (
                leg["race"][
                    "startMethod"
                ]
            )

            safe_raw_scores = []
            v2a_speed_values = []
            v2b_speed_values = []

            for entry in entries:
                total_entries += 1

                safe = (
                    build_safe_projection(
                        entry
                    )
                )

                safe_result = (
                    score_entry(
                        safe
                    )
                )

                safe_raw_scores.append(
                    float(
                        safe_result[
                            "score"
                        ]
                    )
                )

                form = (
                    extract_form_features(
                        entry.get(
                            "history"
                        )
                        or []
                    )
                )

                v2a_speed_values.append(
                    form[
                        "recentWeightedCleanKmTime"
                    ]
                )

                context = (
                    context_weighted_speed(
                        entry.get(
                            "history"
                        )
                        or [],
                        current_distance=
                            current_distance,
                        current_start_method=
                            current_method,
                    )
                )

                v2b_speed_values.append(
                    context[
                        "contextKmTime"
                    ]
                )

                tier_counts[
                    context["tier"]
                ] += 1

            safe_pct = (
                percentile_high(
                    safe_raw_scores
                )
            )

            v2a_speed_pct = (
                percentile_scores(
                    v2a_speed_values,
                    lower_is_better=True,
                )
            )

            v2b_speed_pct = (
                percentile_scores(
                    v2b_speed_values,
                    lower_is_better=True,
                )
            )

            safe_rank = rank_scores(
                entries,
                safe_pct,
            )

            v2a_combined = [
                (
                    BASE_WEIGHT
                    * safe_pct[i]
                    + SPEED_WEIGHT
                    * v2a_speed_pct[i]
                )
                for i
                in range(
                    len(entries)
                )
            ]

            v2b_combined = [
                (
                    BASE_WEIGHT
                    * safe_pct[i]
                    + SPEED_WEIGHT
                    * v2b_speed_pct[i]
                )
                for i
                in range(
                    len(entries)
                )
            ]

            v2a_rank = rank_scores(
                entries,
                v2a_combined,
            )

            v2b_rank = rank_scores(
                entries,
                v2b_combined,
            )

            winner = int(
                outcome_by_leg[
                    leg["leg"]
                ][
                    "winnerStartNumber"
                ]
            )

            ranks = {
                "safe-v1":
                    safe_rank[
                        winner
                    ],
                "v2a-speed":
                    v2a_rank[
                        winner
                    ],
                "v2b-context":
                    v2b_rank[
                        winner
                    ],
            }

            for name, rank in (
                ranks.items()
            ):
                winner_ranks[
                    name
                ].append(
                    rank
                )

                meeting_ranks[
                    name
                ].append(
                    rank
                )

        per_meeting.append(
            {
                "date": date,
                "raceDayName":
                    pre[
                        "raceDayName"
                    ],
                "metrics": {
                    name:
                        metrics(
                            ranks
                        )
                    for name, ranks
                    in meeting_ranks.items()
                },
            }
        )

    print(
        "=== V2B CONTEXT SPEED "
        "DEVELOPMENT EXPERIMENT ==="
    )

    print(
        f"Meetings: "
        f"{len(args.dates)}"
    )

    print(
        f"Races: "
        f"{len(winner_ranks['safe-v1'])}"
    )

    print(
        f"Entries: "
        f"{total_entries}"
    )

    print()
    print(
        "=== CONTEXT TIERS ==="
    )

    for tier, count in (
        tier_counts.most_common()
    ):
        print(
            f"{tier:<28} "
            f"{count:>4} "
            f"({100 * count / total_entries:5.1f}%)"
        )

    print()
    print(
        "=== OVERALL ==="
    )

    results = {}

    for name in (
        "safe-v1",
        "v2a-speed",
        "v2b-context",
    ):
        result = metrics(
            winner_ranks[name]
        )

        results[name] = result

        n = result[
            "races"
        ]

        print(
            f"{name:<16} "
            f"T1="
            f"{result['top1']:>2}/{n} "
            f"({100 * result['top1'] / n:5.1f}%) "
            f"T2="
            f"{result['top2']:>2}/{n} "
            f"({100 * result['top2'] / n:5.1f}%) "
            f"T3="
            f"{result['top3']:>2}/{n} "
            f"({100 * result['top3'] / n:5.1f}%) "
            f"T5="
            f"{result['top5']:>2}/{n} "
            f"({100 * result['top5'] / n:5.1f}%) "
            f"avgRank="
            f"{result['averageWinnerRank']:.2f}"
        )

    print()
    print(
        "=== PER MEETING TOP-3 ==="
    )

    for meeting in per_meeting:
        print(
            f"{meeting['date']} "
            f"{meeting['raceDayName']:<14}",
            end="",
        )

        for name in (
            "safe-v1",
            "v2a-speed",
            "v2b-context",
        ):
            value = (
                meeting[
                    "metrics"
                ][name][
                    "top3"
                ]
            )

            print(
                f" | {name}="
                f"{value}/7",
                end="",
            )

        print()

    report = {
        "schemaVersion":
            "1.0",
        "experiment":
            "feature-v2b-context-speed",
        "scope":
            "development-only",
        "dates":
            args.dates,
        "weights": {
            "safeBaseline":
                BASE_WEIGHT,
            "speed":
                SPEED_WEIGHT,
        },
        "contextPriority": [
            "same-method + within-200m",
            "same-method",
            "within-200m",
            "any-clean"
        ],
        "tierCounts":
            dict(
                tier_counts
            ),
        "results":
            results,
        "perMeeting":
            per_meeting,
    }

    args.output.write_text(
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
        f"Report: "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()
