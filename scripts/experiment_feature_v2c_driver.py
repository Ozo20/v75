from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from v75.baseline_safe_v1 import (
    build_safe_projection,
    finish_position,
    score_entry,
)

from v75.form_features_v2 import (
    extract_form_features,
    percentile_scores,
)


VARIANTS = {
    "v2a-speed": {
        "base": 0.70,
        "speed": 0.30,
        "continuity": 0.00,
        "pairEffect": 0.00,
    },
    "v2c-continuity": {
        "base": 0.63,
        "speed": 0.27,
        "continuity": 0.10,
        "pairEffect": 0.00,
    },
    "v2c-pair-effect": {
        "base": 0.63,
        "speed": 0.27,
        "continuity": 0.00,
        "pairEffect": 0.10,
    },
    "v2c-combined": {
        "base": 0.63,
        "speed": 0.27,
        "continuity": 0.05,
        "pairEffect": 0.05,
    },
}


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def normalize_name(
    value: Any,
) -> str | None:
    if value is None:
        return None

    text = re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    )

    if not text:
        return None

    return text.casefold()


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


def mean_or_none(
    values: list[int],
) -> float | None:
    if not values:
        return None

    return mean(values)


def driver_features(
    entry: dict[str, Any],
) -> dict[str, Any]:
    current_driver = normalize_name(
        (
            entry.get("driver")
            or {}
        ).get("name")
    )

    rows = sorted(
        entry.get("history")
        or [],
        key=lambda row: (
            datetime.fromisoformat(
                row["raceDate"]
            )
        ),
        reverse=True,
    )

    history_count = len(rows)

    if not current_driver:
        return {
            "historyCount":
                history_count,
            "pairCount":
                0,
            "pairShare":
                0.0,
            "sameDriverLatest":
                False,
            "continuityRaw":
                0.0,
            "pairPlacementCount":
                0,
            "overallPlacementCount":
                0,
            "pairMeanFinish":
                None,
            "overallMeanFinish":
                None,
            "pairEffectRaw":
                None,
        }

    pair_rows = [
        row
        for row in rows
        if normalize_name(
            row.get("driver")
        )
        == current_driver
    ]

    pair_count = len(
        pair_rows
    )

    pair_share = (
        pair_count
        / history_count
        if history_count
        else 0.0
    )

    same_driver_latest = (
        bool(rows)
        and normalize_name(
            rows[0].get("driver")
        )
        == current_driver
    )

    # Continuity contains no result data:
    # 50% latest-start continuity,
    # 50% share of recent starts
    # with today's driver.
    continuity_raw = (
        0.50
        * float(
            same_driver_latest
        )
        + 0.50
        * pair_share
    )

    overall_places = []

    for row in rows:
        place = finish_position(
            row.get("placeRaw")
        )

        if place > 0:
            overall_places.append(
                place
            )

    pair_places = []

    for row in pair_rows:
        place = finish_position(
            row.get("placeRaw")
        )

        if place > 0:
            pair_places.append(
                place
            )

    overall_mean = mean_or_none(
        overall_places
    )

    pair_mean = mean_or_none(
        pair_places
    )

    # Conservative horse × driver
    # interaction:
    #
    # positive = horse historically
    # finishes better with today's driver
    # than in its recent history overall.
    #
    # Require >=2 prior starts together,
    # then shrink toward zero:
    #
    # n / (n + 2)
    #
    # If all recent starts have the same
    # driver, pair mean == overall mean and
    # this interaction is naturally zero.
    pair_effect = None

    if (
        pair_count >= 2
        and pair_mean is not None
        and overall_mean is not None
    ):
        raw_delta = (
            overall_mean
            - pair_mean
        )

        shrink = (
            pair_count
            / (pair_count + 2.0)
        )

        pair_effect = (
            raw_delta
            * shrink
        )

    return {
        "historyCount":
            history_count,
        "pairCount":
            pair_count,
        "pairShare":
            pair_share,
        "sameDriverLatest":
            same_driver_latest,
        "continuityRaw":
            continuity_raw,
        "pairPlacementCount":
            len(pair_places),
        "overallPlacementCount":
            len(overall_places),
        "pairMeanFinish":
            pair_mean,
        "overallMeanFinish":
            overall_mean,
        "pairEffectRaw":
            pair_effect,
    }


def evaluate_ranks(
    ranks: list[int],
) -> dict[str, Any]:
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

    feature_stats = Counter()

    pair_effect_values = []

    per_meeting = []

    race_comparisons = {
        name: Counter()
        for name in VARIANTS
        if name != "v2a-speed"
    }

    meeting_top3_comparisons = {
        name: Counter()
        for name in VARIANTS
        if name != "v2a-speed"
    }

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
                if entry["start"][
                    "eligibleForPrediction"
                ]
            ]

            base_scores = []
            speed_values = []
            driver_rows = []

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

                form = (
                    extract_form_features(
                        entry.get(
                            "history"
                        )
                        or []
                    )
                )

                driver = (
                    driver_features(
                        entry
                    )
                )

                base_scores.append(
                    float(
                        baseline[
                            "score"
                        ]
                    )
                )

                speed_values.append(
                    form[
                        "recentWeightedCleanKmTime"
                    ]
                )

                driver_rows.append(
                    driver
                )

                feature_stats[
                    "entries"
                ] += 1

                if driver[
                    "sameDriverLatest"
                ]:
                    feature_stats[
                        "sameDriverLatest"
                    ] += 1

                pair_count = driver[
                    "pairCount"
                ]

                if pair_count >= 1:
                    feature_stats[
                        "pairAtLeast1"
                    ] += 1

                if pair_count >= 2:
                    feature_stats[
                        "pairAtLeast2"
                    ] += 1

                if pair_count >= 3:
                    feature_stats[
                        "pairAtLeast3"
                    ] += 1

                if (
                    driver[
                        "pairEffectRaw"
                    ]
                    is not None
                ):
                    feature_stats[
                        "pairEffectAvailable"
                    ] += 1

                    pair_effect_values.append(
                        driver[
                            "pairEffectRaw"
                        ]
                    )

            base_pct = (
                percentile_high(
                    base_scores
                )
            )

            speed_pct = (
                percentile_scores(
                    speed_values,
                    lower_is_better=True,
                )
            )

            continuity_pct = (
                percentile_high(
                    [
                        row[
                            "continuityRaw"
                        ]
                        for row
                        in driver_rows
                    ]
                )
            )

            pair_effect_pct = (
                percentile_scores(
                    [
                        row[
                            "pairEffectRaw"
                        ]
                        for row
                        in driver_rows
                    ],
                    lower_is_better=False,
                )
            )

            rankings = {}

            for (
                name,
                weights,
            ) in VARIANTS.items():
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
                            "continuity"
                        ]
                        * continuity_pct[i]
                        + weights[
                            "pairEffect"
                        ]
                        * pair_effect_pct[i]
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

            baseline_rank = (
                rankings[
                    "v2a-speed"
                ][winner]
            )

            for name in VARIANTS:
                rank = (
                    rankings[
                        name
                    ][winner]
                )

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

                if name != "v2a-speed":
                    if rank < baseline_rank:
                        race_comparisons[
                            name
                        ][
                            "improved"
                        ] += 1
                    elif rank > baseline_rank:
                        race_comparisons[
                            name
                        ][
                            "worse"
                        ] += 1
                    else:
                        race_comparisons[
                            name
                        ][
                            "equal"
                        ] += 1

        meeting_results = {
            name:
                evaluate_ranks(
                    ranks
                )
            for name, ranks
            in meeting_ranks.items()
        }

        baseline_top3 = (
            meeting_results[
                "v2a-speed"
            ][
                "top3"
            ]
        )

        for name in VARIANTS:
            if name == "v2a-speed":
                continue

            candidate_top3 = (
                meeting_results[
                    name
                ][
                    "top3"
                ]
            )

            if (
                candidate_top3
                > baseline_top3
            ):
                meeting_top3_comparisons[
                    name
                ][
                    "better"
                ] += 1
            elif (
                candidate_top3
                < baseline_top3
            ):
                meeting_top3_comparisons[
                    name
                ][
                    "worse"
                ] += 1
            else:
                meeting_top3_comparisons[
                    name
                ][
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
                "variants":
                    meeting_results,
            }
        )

    print(
        "=== FEATURE V2C HORSE × DRIVER "
        "DEVELOPMENT EXPERIMENT ==="
    )

    print(
        f"Meetings: "
        f"{len(args.dates)}"
    )

    print(
        f"Races: "
        f"{len(winner_ranks['v2a-speed'])}"
    )

    print(
        f"Entries: "
        f"{feature_stats['entries']}"
    )

    print()

    total_entries = (
        feature_stats[
            "entries"
        ]
    )

    print(
        "=== DRIVER FEATURE COVERAGE ==="
    )

    for key in (
        "sameDriverLatest",
        "pairAtLeast1",
        "pairAtLeast2",
        "pairAtLeast3",
        "pairEffectAvailable",
    ):
        count = (
            feature_stats[key]
        )

        print(
            f"{key:<22} "
            f"{count:>4}/"
            f"{total_entries} "
            f"({100*count/total_entries:5.1f}%)"
        )

    if pair_effect_values:
        print()
        print(
            "Pair-effect raw range: "
            f"{min(pair_effect_values):.3f} "
            f"to "
            f"{max(pair_effect_values):.3f}"
        )

        print(
            "Pair-effect raw mean:  "
            f"{mean(pair_effect_values):.3f}"
        )

    print()
    print(
        "=== DEVELOPMENT RESULTS ==="
    )

    results = {}

    for name, ranks in (
        winner_ranks.items()
    ):
        result = (
            evaluate_ranks(
                ranks
            )
        )

        results[name] = result

        total = result[
            "races"
        ]

        print(
            f"{name:<20} "
            f"T1="
            f"{result['top1']:>2}/"
            f"{total} "
            f"({100*result['top1']/total:5.1f}%) "
            f"T2="
            f"{result['top2']:>2}/"
            f"{total} "
            f"({100*result['top2']/total:5.1f}%) "
            f"T3="
            f"{result['top3']:>2}/"
            f"{total} "
            f"({100*result['top3']/total:5.1f}%) "
            f"T5="
            f"{result['top5']:>2}/"
            f"{total} "
            f"({100*result['top5']/total:5.1f}%) "
            f"avgRank="
            f"{result['averageWinnerRank']:.2f}"
        )

    print()
    print(
        "=== RACE-BY-RACE VS V2A ==="
    )

    for name in VARIANTS:
        if name == "v2a-speed":
            continue

        comparison = (
            race_comparisons[
                name
            ]
        )

        print(
            f"{name:<20} "
            f"improved="
            f"{comparison['improved']:>2} "
            f"equal="
            f"{comparison['equal']:>2} "
            f"worse="
            f"{comparison['worse']:>2}"
        )

    print()
    print(
        "=== MEETING TOP-3 VS V2A ==="
    )

    for name in VARIANTS:
        if name == "v2a-speed":
            continue

        comparison = (
            meeting_top3_comparisons[
                name
            ]
        )

        print(
            f"{name:<20} "
            f"better="
            f"{comparison['better']} "
            f"equal="
            f"{comparison['equal']} "
            f"worse="
            f"{comparison['worse']}"
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
            "feature-v2c-horse-driver",
        "scope":
            "development-only",
        "dates":
            args.dates,
        "identityContract": {
            "current":
                "normalized driver.name",
            "history":
                "history[].driver",
            "normalization":
                "trim whitespace + collapse whitespace + casefold",
            "driverIdUsed":
                False,
            "reason":
                "six verified raw-program driver ID mismatches",
        },
        "featureDesign": {
            "continuity": {
                "sameDriverLatestWeight":
                    0.50,
                "pairShareWeight":
                    0.50,
            },
            "pairEffect": {
                "minimumPairStarts":
                    2,
                "definition":
                    "overallMeanFinish - pairMeanFinish",
                "shrinkage":
                    "pairCount / (pairCount + 2)",
                "missingPolicy":
                    "neutral field-relative 0.5",
            },
        },
        "featureStats":
            dict(feature_stats),
        "variants":
            VARIANTS,
        "results":
            results,
        "raceComparisonsVsV2A": {
            name:
                dict(values)
            for name, values
            in race_comparisons.items()
        },
        "meetingTop3ComparisonsVsV2A": {
            name:
                dict(values)
            for name, values
            in meeting_top3_comparisons.items()
        },
        "perMeeting":
            per_meeting,
        "guardrails": {
            "developmentOnly":
                True,
            "validationUsed":
                False,
            "oldHoldoutUsed":
                False,
            "freshSystemSetUsed":
                False,
            "marketUsed":
                False,
            "annualStatisticsUsed":
                False,
            "championModified":
                False,
        },
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
