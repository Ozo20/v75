from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from v75.baseline_safe_v1 import (
    build_safe_projection,
    score_entry,
)

from v75.form_features_v2 import (
    extract_form_features,
    percentile_scores,
)


VARIANTS = {
    "safe-v1": {
        "base": 1.00,
        "speed": 0.00,
        "stability": 0.00,
    },
    "v2a-speed": {
        "base": 0.70,
        "speed": 0.30,
        "stability": 0.00,
    },
    "v2a-stability": {
        "base": 0.80,
        "speed": 0.00,
        "stability": 0.20,
    },
    "v2a-speed-stability": {
        "base": 0.60,
        "speed": 0.25,
        "stability": 0.15,
    },
}


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


def evaluate_variant(
    ranks: list[int],
) -> dict[str, Any]:
    total = len(ranks)

    return {
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
        "races":
            total,
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
        name: []
        for name in VARIANTS
    }

    feature_stats = {
        "entries": 0,
        "withCleanSpeed": 0,
        "withoutCleanSpeed": 0,
    }

    per_meeting = []

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
            name: []
            for name in VARIANTS
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

            base_scores = []
            form_features = []

            for entry in entries:
                safe = (
                    build_safe_projection(
                        entry
                    )
                )

                baseline = (
                    score_entry(
                        safe
                    )
                )

                features = (
                    extract_form_features(
                        entry.get(
                            "history"
                        )
                        or []
                    )
                )

                base_scores.append(
                    float(
                        baseline[
                            "score"
                        ]
                    )
                )

                form_features.append(
                    features
                )

                feature_stats[
                    "entries"
                ] += 1

                if (
                    features[
                        "recentWeightedCleanKmTime"
                    ]
                    is not None
                ):
                    feature_stats[
                        "withCleanSpeed"
                    ] += 1
                else:
                    feature_stats[
                        "withoutCleanSpeed"
                    ] += 1

            base_pct = (
                percentile_high(
                    base_scores
                )
            )

            speed_pct = (
                percentile_scores(
                    [
                        f[
                            "recentWeightedCleanKmTime"
                        ]
                        for f
                        in form_features
                    ],
                    lower_is_better=True,
                )
            )

            # Combine overall and recent
            # incident rates before ranking.
            raw_stability = [
                (
                    0.50
                    * f[
                        "issueRate"
                    ]
                    + 0.50
                    * f[
                        "recentIssueRate"
                    ]
                )
                for f
                in form_features
            ]

            stability_pct = (
                percentile_scores(
                    raw_stability,
                    lower_is_better=True,
                )
            )

            rankings = {}

            for name, weights in (
                VARIANTS.items()
            ):
                rows = []

                for i, entry in enumerate(
                    entries
                ):
                    combined = (
                        weights[
                            "base"
                        ]
                        * base_pct[i]
                        + weights[
                            "speed"
                        ]
                        * speed_pct[i]
                        + weights[
                            "stability"
                        ]
                        * stability_pct[i]
                    )

                    rows.append(
                        {
                            "startNumber":
                                entry[
                                    "startNumber"
                                ],
                            "score":
                                combined,
                        }
                    )

                rows.sort(
                    key=lambda row: (
                        -row["score"],
                        row[
                            "startNumber"
                        ],
                    )
                )

                rankings[name] = {
                    row[
                        "startNumber"
                    ]: rank
                    for rank, row
                    in enumerate(
                        rows,
                        1,
                    )
                }

            winner = int(
                outcome_by_leg[
                    leg["leg"]
                ][
                    "winnerStartNumber"
                ]
            )

            for name in VARIANTS:
                rank = rankings[
                    name
                ][winner]

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
                "variants": {
                    name:
                        evaluate_variant(
                            ranks
                        )
                    for name, ranks
                    in meeting_ranks.items()
                },
            }
        )

    print(
        "=== FEATURE V2A "
        "DEVELOPMENT EXPERIMENT ==="
    )

    print(
        f"Meetings: "
        f"{len(args.dates)}"
    )

    print(
        f"Races: "
        f"{len(next(iter(winner_ranks.values())))}"
    )

    print(
        f"Entries evaluated: "
        f"{feature_stats['entries']}"
    )

    print(
        f"Entries with clean speed: "
        f"{feature_stats['withCleanSpeed']}"
    )

    print(
        f"Entries without clean speed: "
        f"{feature_stats['withoutCleanSpeed']}"
    )

    print()

    results = {}

    for name, ranks in (
        winner_ranks.items()
    ):
        result = (
            evaluate_variant(
                ranks
            )
        )

        results[name] = result

        total = result[
            "races"
        ]

        print(
            f"{name:<24} "
            f"T1="
            f"{result['top1']:>2}/"
            f"{total} "
            f"({100 * result['top1'] / total:5.1f}%) "
            f"T2="
            f"{result['top2']:>2}/"
            f"{total} "
            f"({100 * result['top2'] / total:5.1f}%) "
            f"T3="
            f"{result['top3']:>2}/"
            f"{total} "
            f"({100 * result['top3'] / total:5.1f}%) "
            f"T5="
            f"{result['top5']:>2}/"
            f"{total} "
            f"({100 * result['top5'] / total:5.1f}%) "
            f"avgRank="
            f"{result['averageWinnerRank']:.2f}"
        )

    print()
    print(
        "=== PER MEETING "
        "TOP-3 ==="
    )

    for meeting in per_meeting:
        print(
            f"{meeting['date']} "
            f"{meeting['raceDayName']:<14}",
            end="",
        )

        for name in VARIANTS:
            metric = (
                meeting[
                    "variants"
                ][name]
            )

            print(
                f" | "
                f"{name}="
                f"{metric['top3']}/7",
                end="",
            )

        print()

    report = {
        "schemaVersion":
            "1.0",
        "experiment":
            "feature-v2a",
        "scope":
            "development-only",
        "dates":
            args.dates,
        "featureStats":
            feature_stats,
        "variants":
            VARIANTS,
        "results":
            results,
        "perMeeting":
            per_meeting,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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
