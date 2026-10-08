from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date
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

from v75.driver_identity import (
    canonical_driver_name,
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

PRIOR_STRENGTH = 10.0
MIN_OTHER_HORSE_VALID_FINISHES = 3


VARIANTS = {
    "v2a-speed": {
        "base": 0.70,
        "speed": 0.30,
        "driverWin": 0.00,
        "driverTop3": 0.00,
    },
    "v2f-driver-win": {
        "base": 0.63,
        "speed": 0.27,
        "driverWin": 0.10,
        "driverTop3": 0.00,
    },
    "v2f-driver-top3": {
        "base": 0.63,
        "speed": 0.27,
        "driverWin": 0.00,
        "driverTop3": 0.10,
    },
    "v2f-driver-combined": {
        "base": 0.63,
        "speed": 0.27,
        "driverWin": 0.05,
        "driverTop3": 0.05,
    },
}


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def norm_name(
    value: Any,
) -> str | None:
    return canonical_driver_name(
        value
    )


def row_date(
    row: dict[str, Any],
) -> date | None:
    value = row.get(
        "raceDate"
    )

    if not value:
        return None

    try:
        return date.fromisoformat(
            str(value)[:10]
        )
    except ValueError:
        return None


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


def add_stats(
    stats: dict[str, int],
    place: int,
) -> None:
    stats["valid"] += 1

    if place == 1:
        stats["wins"] += 1

    if place <= 3:
        stats["top3"] += 1


def subtract_stats(
    total: dict[str, int],
    own_horse: dict[str, int],
) -> dict[str, int]:
    return {
        key:
            total.get(key, 0)
            - own_horse.get(key, 0)
        for key in (
            "valid",
            "wins",
            "top3",
        )
    }


def build_driver_corpus(
    snapshots: dict[str, Any],
    target_day: str,
):
    target_date = date.fromisoformat(
        target_day
    )

    deduped = {}

    for source_day in DATES:
        if source_day > target_day:
            continue

        pre = snapshots[
            source_day
        ]

        for leg in pre["legs"]:
            for entry in leg["entries"]:
                horse_id = str(
                    entry["horse"][
                        "registrationNumber"
                    ]
                )

                for row in (
                    entry.get("history")
                    or []
                ):
                    race_date = (
                        row_date(row)
                    )

                    if (
                        race_date is None
                        or race_date
                        >= target_date
                    ):
                        continue

                    driver = norm_name(
                        row.get("driver")
                    )

                    form_key = row.get(
                        "formRowKey"
                    )

                    if (
                        not driver
                        or not form_key
                    ):
                        continue

                    identity = str(
                        form_key
                    )

                    record = {
                        "horseId":
                            horse_id,
                        "driver":
                            driver,
                        "place":
                            finish_position(
                                row.get(
                                    "placeRaw"
                                )
                            ),
                    }

                    existing = (
                        deduped.get(
                            identity
                        )
                    )

                    if existing is None:
                        deduped[
                            identity
                        ] = record
                    elif existing != record:
                        raise RuntimeError(
                            "Conflicting duplicate "
                            f"formRowKey {identity!r}"
                        )

    global_stats = {
        "valid": 0,
        "wins": 0,
        "top3": 0,
    }

    driver_stats = defaultdict(
        lambda: {
            "valid": 0,
            "wins": 0,
            "top3": 0,
        }
    )

    driver_horse_stats = defaultdict(
        lambda: {
            "valid": 0,
            "wins": 0,
            "top3": 0,
        }
    )

    for record in (
        deduped.values()
    ):
        place = record[
            "place"
        ]

        if place <= 0:
            continue

        driver = record[
            "driver"
        ]

        horse_id = record[
            "horseId"
        ]

        add_stats(
            global_stats,
            place,
        )

        add_stats(
            driver_stats[
                driver
            ],
            place,
        )

        add_stats(
            driver_horse_stats[
                (
                    driver,
                    horse_id,
                )
            ],
            place,
        )

    if global_stats["valid"] == 0:
        raise RuntimeError(
            "No valid historical finishes."
        )

    global_win_rate = (
        global_stats["wins"]
        / global_stats["valid"]
    )

    global_top3_rate = (
        global_stats["top3"]
        / global_stats["valid"]
    )

    return {
        "dedupedStarts":
            len(deduped),
        "globalStats":
            global_stats,
        "globalWinRate":
            global_win_rate,
        "globalTop3Rate":
            global_top3_rate,
        "driverStats":
            driver_stats,
        "driverHorseStats":
            driver_horse_stats,
    }


def driver_strength(
    corpus,
    entry: dict[str, Any],
):
    driver = norm_name(
        (
            entry.get("driver")
            or {}
        ).get("name")
    )

    horse_id = str(
        entry["horse"][
            "registrationNumber"
        ]
    )

    if not driver:
        return {
            "valid":
                0,
            "winRate":
                None,
            "top3Rate":
                None,
        }

    total = corpus[
        "driverStats"
    ].get(
        driver,
        {
            "valid": 0,
            "wins": 0,
            "top3": 0,
        },
    )

    own_horse = corpus[
        "driverHorseStats"
    ].get(
        (
            driver,
            horse_id,
        ),
        {
            "valid": 0,
            "wins": 0,
            "top3": 0,
        },
    )

    other = subtract_stats(
        total,
        own_horse,
    )

    n = other[
        "valid"
    ]

    if (
        n
        < MIN_OTHER_HORSE_VALID_FINISHES
    ):
        return {
            "valid":
                n,
            "winRate":
                None,
            "top3Rate":
                None,
        }

    win_rate = (
        other["wins"]
        + PRIOR_STRENGTH
        * corpus[
            "globalWinRate"
        ]
    ) / (
        n
        + PRIOR_STRENGTH
    )

    top3_rate = (
        other["top3"]
        + PRIOR_STRENGTH
        * corpus[
            "globalTop3Rate"
        ]
    ) / (
        n
        + PRIOR_STRENGTH
    )

    return {
        "valid":
            n,
        "wins":
            other["wins"],
        "top3":
            other["top3"],
        "winRate":
            win_rate,
        "top3Rate":
            top3_rate,
    }


def evaluate_ranks(
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


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    snapshots = {
        day: load(
            args.root
            / day
            / "pre-race.json"
        )
        for day in DATES
    }

    outcomes = {
        day: load(
            args.root
            / day
            / "outcomes.json"
        )
        for day in DATES
    }

    winner_ranks = {
        name: []
        for name in VARIANTS
    }

    comparisons = {
        name: Counter()
        for name in VARIANTS
        if name != "v2a-speed"
    }

    meeting_top3 = {
        name: Counter()
        for name in VARIANTS
        if name != "v2a-speed"
    }

    feature_stats = Counter()
    per_meeting = []

    corpus_summary = []

    for target_day in DATES:
        pre = snapshots[
            target_day
        ]

        corpus = (
            build_driver_corpus(
                snapshots,
                target_day,
            )
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
                        "globalStats"
                    ][
                        "valid"
                    ],
                "globalWinRate":
                    corpus[
                        "globalWinRate"
                    ],
                "globalTop3Rate":
                    corpus[
                        "globalTop3Rate"
                    ],
            }
        )

        outcome_by_leg = {
            row["leg"]: row
            for row
            in outcomes[
                target_day
            ]["legs"]
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

                strength = (
                    driver_strength(
                        corpus,
                        entry,
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
                    strength
                )

                feature_stats[
                    "entries"
                ] += 1

                if (
                    strength[
                        "winRate"
                    ]
                    is not None
                ):
                    feature_stats[
                        "driverStrengthAvailable"
                    ] += 1

                for threshold in (
                    3,
                    5,
                    10,
                    20,
                    30,
                ):
                    if (
                        strength[
                            "valid"
                        ]
                        >= threshold
                    ):
                        feature_stats[
                            f"validAtLeast{threshold}"
                        ] += 1

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

            win_pct = (
                percentile_scores(
                    [
                        row[
                            "winRate"
                        ]
                        for row
                        in driver_rows
                    ],
                    lower_is_better=False,
                )
            )

            top3_pct = (
                percentile_scores(
                    [
                        row[
                            "top3Rate"
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
                    score = (
                        weights[
                            "base"
                        ]
                        * base_pct[i]
                        + weights[
                            "speed"
                        ]
                        * speed_pct[i]
                        + weights[
                            "driverWin"
                        ]
                        * win_pct[i]
                        + weights[
                            "driverTop3"
                        ]
                        * top3_pct[i]
                    )

                    rows.append(
                        {
                            "startNumber":
                                entry[
                                    "startNumber"
                                ],
                            "score":
                                score,
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

                if name == "v2a-speed":
                    continue

                if rank < baseline_rank:
                    comparisons[
                        name
                    ][
                        "improved"
                    ] += 1

                elif rank > baseline_rank:
                    comparisons[
                        name
                    ][
                        "worse"
                    ] += 1

                else:
                    comparisons[
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

        base_top3 = (
            meeting_results[
                "v2a-speed"
            ][
                "top3"
            ]
        )

        for name in VARIANTS:
            if name == "v2a-speed":
                continue

            candidate = (
                meeting_results[
                    name
                ][
                    "top3"
                ]
            )

            if candidate > base_top3:
                meeting_top3[
                    name
                ][
                    "better"
                ] += 1
            elif candidate < base_top3:
                meeting_top3[
                    name
                ][
                    "worse"
                ] += 1
            else:
                meeting_top3[
                    name
                ][
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
                "variants":
                    meeting_results,
            }
        )

    print(
        "=== FEATURE V2F CROSS-HORSE "
        "DRIVER-STRENGTH DEVELOPMENT ==="
    )

    print(
        f"Meetings: {len(DATES)}"
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

    print(
        "=== FEATURE COVERAGE ==="
    )

    total_entries = (
        feature_stats[
            "entries"
        ]
    )

    for key in (
        "driverStrengthAvailable",
        "validAtLeast3",
        "validAtLeast5",
        "validAtLeast10",
        "validAtLeast20",
        "validAtLeast30",
    ):
        count = feature_stats[
            key
        ]

        print(
            f"{key:<27} "
            f"{count:>4}/"
            f"{total_entries} "
            f"({100*count/total_entries:5.1f}%)"
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
            f"{name:<22} "
            f"T1="
            f"{result['top1']:>2}/{total} "
            f"({100*result['top1']/total:5.1f}%) "
            f"T2="
            f"{result['top2']:>2}/{total} "
            f"({100*result['top2']/total:5.1f}%) "
            f"T3="
            f"{result['top3']:>2}/{total} "
            f"({100*result['top3']/total:5.1f}%) "
            f"T5="
            f"{result['top5']:>2}/{total} "
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

        row = comparisons[
            name
        ]

        print(
            f"{name:<22} "
            f"improved="
            f"{row['improved']:>2} "
            f"equal="
            f"{row['equal']:>2} "
            f"worse="
            f"{row['worse']:>2}"
        )

    print()
    print(
        "=== MEETING TOP-3 VS V2A ==="
    )

    for name in VARIANTS:
        if name == "v2a-speed":
            continue

        row = meeting_top3[
            name
        ]

        print(
            f"{name:<22} "
            f"better="
            f"{row['better']} "
            f"equal="
            f"{row['equal']} "
            f"worse="
            f"{row['worse']}"
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
            result = (
                meeting[
                    "variants"
                ][name]
            )

            print(
                f" | "
                f"{name}="
                f"{result['top3']}/7",
                end="",
            )

        print()

    report = {
        "schemaVersion":
            "1.0",
        "experiment":
            "feature-v2f-cross-horse-driver-strength",
        "scope":
            "development-only-point-in-time",
        "dates":
            DATES,
        "featureDesign": {
            "driverIdentity":
                "normalized driver name",
            "sameHorseRowsExcluded":
                True,
            "minimumOtherHorseValidFinishes":
                MIN_OTHER_HORSE_VALID_FINISHES,
            "priorStrength":
                PRIOR_STRENGTH,
            "winRate":
                "Bayesian shrinkage toward point-in-time global win rate",
            "top3Rate":
                "Bayesian shrinkage toward point-in-time global top3 rate",
            "corpus":
                "deduplicated historical form rows from development snapshots <= target date",
            "historyFilter":
                "raceDate strictly before target date",
        },
        "featureStats":
            dict(feature_stats),
        "variants":
            VARIANTS,
        "results":
            results,
        "raceComparisonsVsV2A": {
            name:
                dict(row)
            for name, row
            in comparisons.items()
        },
        "meetingTop3ComparisonsVsV2A": {
            name:
                dict(row)
            for name, row
            in meeting_top3.items()
        },
        "corpusSummary":
            corpus_summary,
        "perMeeting":
            per_meeting,
        "guardrails": {
            "developmentOnly":
                True,
            "sameHorseHistoryExcludedFromDriverStrength":
                True,
            "futureSnapshotsUsed":
                False,
            "historyAtOrAfterTargetUsed":
                False,
            "validationUsed":
                False,
            "oldHoldoutUsed":
                False,
            "robustnessSetUsed":
                False,
            "freshSystemSetUsed":
                False,
            "marketUsed":
                False,
            "annualStatisticsUsed":
                False,
            "driverContinuityUsed":
                False,
            "trackUsed":
                False,
            "equipmentUsed":
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
        f"Report: {args.output}"
    )


if __name__ == "__main__":
    main()
