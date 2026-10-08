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

from v75.form_features_v2 import (
    extract_form_features,
    percentile_scores,
)

from v75.track_identity import (
    history_track_code_for_race_day_key,
)


VARIANTS = {
    "v2a-speed": {
        "base": 0.70,
        "speed": 0.30,
        "trackExperience": 0.00,
        "trackSpeedEffect": 0.00,
    },
    "v2d-track-experience": {
        "base": 0.63,
        "speed": 0.27,
        "trackExperience": 0.10,
        "trackSpeedEffect": 0.00,
    },
    "v2d-track-speed": {
        "base": 0.63,
        "speed": 0.27,
        "trackExperience": 0.00,
        "trackSpeedEffect": 0.10,
    },
    "v2d-track-combined": {
        "base": 0.63,
        "speed": 0.27,
        "trackExperience": 0.05,
        "trackSpeedEffect": 0.05,
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


def track_features(
    entry: dict[str, Any],
    current_track: str,
) -> dict[str, Any]:

    history = sorted(
        entry.get("history")
        or [],
        key=lambda row: (
            row.get("raceDate")
            or ""
        ),
        reverse=True,
    )

    same_track_rows = [
        row
        for row in history
        if str(
            row.get("trackCode")
            or ""
        ).strip()
        == current_track
    ]

    history_count = len(history)
    same_track_count = len(
        same_track_rows
    )

    same_track_share = (
        same_track_count
        / history_count
        if history_count
        else 0.0
    )

    same_track_latest = (
        bool(history)
        and str(
            history[0].get(
                "trackCode"
            )
            or ""
        ).strip()
        == current_track
    )

    # Familiarity / continuity only.
    # Contains no result information.
    experience_raw = (
        0.50
        * float(
            same_track_latest
        )
        + 0.50
        * same_track_share
    )

    overall_form = (
        extract_form_features(
            history
        )
    )

    same_track_form = (
        extract_form_features(
            same_track_rows
        )
    )

    overall_speed = (
        overall_form.get(
            "recentWeightedCleanKmTime"
        )
    )

    same_track_speed = (
        same_track_form.get(
            "recentWeightedCleanKmTime"
        )
    )

    # Positive means the horse's clean
    # kilometre time has historically
    # been faster on today's track.
    #
    # Require >=2 same-track starts and
    # shrink small samples toward zero.
    track_speed_effect = None

    if (
        same_track_count >= 2
        and overall_speed is not None
        and same_track_speed is not None
    ):
        raw_delta = (
            float(overall_speed)
            - float(same_track_speed)
        )

        shrink = (
            same_track_count
            / (
                same_track_count
                + 2.0
            )
        )

        track_speed_effect = (
            raw_delta
            * shrink
        )

    return {
        "historyCount":
            history_count,
        "sameTrackCount":
            same_track_count,
        "sameTrackShare":
            same_track_share,
        "sameTrackLatest":
            same_track_latest,
        "experienceRaw":
            experience_raw,
        "overallSpeed":
            overall_speed,
        "sameTrackSpeed":
            same_track_speed,
        "trackSpeedEffectRaw":
            track_speed_effect,
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

    speed_effect_values = []

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

    per_meeting = []

    for date in args.dates:
        root = (
            args.root
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

        current_track = (
            history_track_code_for_race_day_key(
                pre["raceDayKey"]
            )
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
            track_rows = []

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

                track = (
                    track_features(
                        entry,
                        current_track,
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

                track_rows.append(
                    track
                )

                feature_stats[
                    "entries"
                ] += 1

                if track[
                    "sameTrackLatest"
                ]:
                    feature_stats[
                        "sameTrackLatest"
                    ] += 1

                count = track[
                    "sameTrackCount"
                ]

                if count >= 1:
                    feature_stats[
                        "sameTrackAtLeast1"
                    ] += 1

                if count >= 2:
                    feature_stats[
                        "sameTrackAtLeast2"
                    ] += 1

                if count >= 3:
                    feature_stats[
                        "sameTrackAtLeast3"
                    ] += 1

                if (
                    track[
                        "trackSpeedEffectRaw"
                    ]
                    is not None
                ):
                    feature_stats[
                        "trackSpeedEffectAvailable"
                    ] += 1

                    speed_effect_values.append(
                        track[
                            "trackSpeedEffectRaw"
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

            experience_pct = (
                percentile_high(
                    [
                        row[
                            "experienceRaw"
                        ]
                        for row
                        in track_rows
                    ]
                )
            )

            track_speed_pct = (
                percentile_scores(
                    [
                        row[
                            "trackSpeedEffectRaw"
                        ]
                        for row
                        in track_rows
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
                            "trackExperience"
                        ]
                        * experience_pct[i]
                        + weights[
                            "trackSpeedEffect"
                        ]
                        * track_speed_pct[i]
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
                "trackCode":
                    current_track,
                "variants":
                    meeting_results,
            }
        )

    print(
        "=== FEATURE V2D HORSE × TRACK "
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
        "=== TRACK FEATURE COVERAGE ==="
    )

    for key in (
        "sameTrackLatest",
        "sameTrackAtLeast1",
        "sameTrackAtLeast2",
        "sameTrackAtLeast3",
        "trackSpeedEffectAvailable",
    ):
        count = (
            feature_stats[key]
        )

        print(
            f"{key:<26} "
            f"{count:>4}/"
            f"{total_entries} "
            f"({100*count/total_entries:5.1f}%)"
        )

    if speed_effect_values:
        print()

        print(
            "Track-speed effect range: "
            f"{min(speed_effect_values):.4f} "
            f"to "
            f"{max(speed_effect_values):.4f}"
        )

        print(
            "Track-speed effect mean:  "
            f"{mean(speed_effect_values):.4f}"
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
            f"{name:<22} "
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
            f"{name:<22} "
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
            f"{meeting['raceDayName']:<14} "
            f"[{meeting['trackCode']}]",
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
            "feature-v2d-horse-track",
        "scope":
            "development-only",
        "dates":
            args.dates,
        "featureDesign": {
            "trackIdentity":
                "verified history trackCode via explicit race-day-prefix mapping",
            "experience": {
                "sameTrackLatestWeight":
                    0.50,
                "sameTrackShareWeight":
                    0.50,
            },
            "trackSpeedEffect": {
                "minimumSameTrackStarts":
                    2,
                "definition":
                    "overall recent weighted clean km time minus same-track recent weighted clean km time",
                "positiveMeaning":
                    "historically faster on today's track",
                "shrinkage":
                    "sameTrackCount / (sameTrackCount + 2)",
                "missingPolicy":
                    "neutral field-relative value",
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
            "driverFeatureUsed":
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
