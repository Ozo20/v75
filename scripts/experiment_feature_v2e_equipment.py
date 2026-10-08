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


VALID_SHOES = {
    "Both",
    "None",
    "Fore",
    "Hind",
}


VARIANTS = {
    "v2a-speed": {
        "base": 0.70,
        "speed": 0.30,
        "equipment": None,
    },
    "v2e-shoe-speed": {
        "base": 0.63,
        "speed": 0.27,
        "equipment": "shoe",
    },
    "v2e-sulky-speed": {
        "base": 0.63,
        "speed": 0.27,
        "equipment": "sulky",
    },
    "v2e-setup-speed": {
        "base": 0.63,
        "speed": 0.27,
        "equipment": "setup",
    },
}


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def canonical_shoes(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if value in VALID_SHOES:
        return value

    return None


def canonical_sulky(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if value in {
        "Sulky",
        "StandardSulky",
    }:
        return "StandardSulky"

    if value == "AmericanSulky":
        return "AmericanSulky"

    # Verified semantics:
    # NoSulky behaves as missing/unknown.
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


def equipment_features(
    entry: dict[str, Any],
) -> dict[str, Any]:

    equipment = (
        entry.get("equipment")
        or {}
    )

    current_shoes = (
        canonical_shoes(
            equipment.get("shoes")
        )
    )

    current_sulky = (
        canonical_sulky(
            equipment.get("sulky")
        )
    )

    history = sorted(
        entry.get("history")
        or [],
        key=lambda row: (
            row.get("raceDate")
            or ""
        ),
        reverse=True,
    )

    shoe_rows = []
    sulky_rows = []
    setup_rows = []

    for row in history:
        hist_shoes = (
            canonical_shoes(
                row.get("shoes")
            )
        )

        hist_sulky = (
            canonical_sulky(
                row.get("sulky")
            )
        )

        if (
            current_shoes
            and hist_shoes
            == current_shoes
        ):
            shoe_rows.append(
                row
            )

        if (
            current_sulky
            and hist_sulky
            == current_sulky
        ):
            sulky_rows.append(
                row
            )

        if (
            current_shoes
            and current_sulky
            and hist_shoes
            == current_shoes
            and hist_sulky
            == current_sulky
        ):
            setup_rows.append(
                row
            )

    overall_speed = (
        extract_form_features(
            history
        ).get(
            "recentWeightedCleanKmTime"
        )
    )

    def effect(
        matched_rows: list[
            dict[str, Any]
        ],
    ) -> float | None:

        # Require at least two starts with
        # today's equipment before deriving
        # a horse-specific effect.
        if len(matched_rows) < 2:
            return None

        matched_speed = (
            extract_form_features(
                matched_rows
            ).get(
                "recentWeightedCleanKmTime"
            )
        )

        if (
            overall_speed is None
            or matched_speed is None
        ):
            return None

        n = len(
            matched_rows
        )

        shrink = (
            n
            / (n + 2.0)
        )

        # Positive means faster with
        # today's equipment than the
        # horse's overall recent history.
        return (
            (
                float(overall_speed)
                - float(matched_speed)
            )
            * shrink
        )

    shoe_effect = effect(
        shoe_rows
    )

    sulky_effect = effect(
        sulky_rows
    )

    setup_effect = effect(
        setup_rows
    )

    return {
        "currentShoes":
            current_shoes,
        "currentSulky":
            current_sulky,
        "shoeMatchCount":
            len(shoe_rows),
        "sulkyMatchCount":
            len(sulky_rows),
        "setupMatchCount":
            len(setup_rows),
        "shoeEffect":
            shoe_effect,
        "sulkyEffect":
            sulky_effect,
        "setupEffect":
            setup_effect,
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

    effect_values = {
        "shoe": [],
        "sulky": [],
        "setup": [],
    }

    race_comparisons = {
        name: Counter()
        for name in VARIANTS
        if name != "v2a-speed"
    }

    meeting_top3 = {
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

            shoe_effects = []
            sulky_effects = []
            setup_effects = []

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

                equipment = (
                    equipment_features(
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

                shoe_effects.append(
                    equipment[
                        "shoeEffect"
                    ]
                )

                sulky_effects.append(
                    equipment[
                        "sulkyEffect"
                    ]
                )

                setup_effects.append(
                    equipment[
                        "setupEffect"
                    ]
                )

                feature_stats[
                    "entries"
                ] += 1

                for (
                    label,
                    field,
                ) in (
                    (
                        "shoe",
                        "shoeEffect",
                    ),
                    (
                        "sulky",
                        "sulkyEffect",
                    ),
                    (
                        "setup",
                        "setupEffect",
                    ),
                ):
                    value = (
                        equipment[field]
                    )

                    if value is not None:
                        feature_stats[
                            f"{label}EffectAvailable"
                        ] += 1

                        effect_values[
                            label
                        ].append(
                            value
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

            equipment_pct = {
                "shoe":
                    percentile_scores(
                        shoe_effects,
                        lower_is_better=False,
                    ),
                "sulky":
                    percentile_scores(
                        sulky_effects,
                        lower_is_better=False,
                    ),
                "setup":
                    percentile_scores(
                        setup_effects,
                        lower_is_better=False,
                    ),
            }

            rankings = {}

            for (
                name,
                config,
            ) in VARIANTS.items():

                rows = []

                for i, entry in enumerate(
                    entries
                ):
                    combined = (
                        config["base"]
                        * base_pct[i]
                        + config["speed"]
                        * speed_pct[i]
                    )

                    equipment_type = (
                        config[
                            "equipment"
                        ]
                    )

                    if equipment_type:
                        combined += (
                            0.10
                            * equipment_pct[
                                equipment_type
                            ][i]
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

                if name == "v2a-speed":
                    continue

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

            if candidate_top3 > baseline_top3:
                meeting_top3[
                    name
                ][
                    "better"
                ] += 1

            elif candidate_top3 < baseline_top3:
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
        "=== FEATURE V2E HORSE × EQUIPMENT "
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

    print(
        "=== EQUIPMENT EFFECT COVERAGE ==="
    )

    total_entries = (
        feature_stats[
            "entries"
        ]
    )

    for label in (
        "shoe",
        "sulky",
        "setup",
    ):
        key = (
            f"{label}EffectAvailable"
        )

        count = (
            feature_stats[
                key
            ]
        )

        print(
            f"{key:<26} "
            f"{count:>4}/"
            f"{total_entries} "
            f"({100*count/total_entries:5.1f}%)"
        )

    print()

    for label in (
        "shoe",
        "sulky",
        "setup",
    ):
        values = (
            effect_values[
                label
            ]
        )

        if not values:
            continue

        print(
            f"{label:<8} "
            f"n={len(values)} "
            f"range="
            f"{min(values):.4f}.."
            f"{max(values):.4f} "
            f"mean="
            f"{mean(values):.4f}"
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

        row = (
            race_comparisons[
                name
            ]
        )

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

        row = (
            meeting_top3[
                name
            ]
        )

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
            row = (
                meeting[
                    "variants"
                ][name]
            )

            print(
                f" | "
                f"{name}="
                f"{row['top3']}/7",
                end="",
            )

        print()

    report = {
        "schemaVersion":
            "1.0",
        "experiment":
            "feature-v2e-horse-equipment",
        "scope":
            "development-only",
        "dates":
            args.dates,
        "featureDesign": {
            "shoes": (
                "horse-specific clean-speed effect "
                "with today's shoe configuration"
            ),
            "sulky": (
                "horse-specific clean-speed effect "
                "with today's canonical sulky type"
            ),
            "setup": (
                "horse-specific clean-speed effect "
                "with today's exact shoe+sulky setup"
            ),
            "minimumMatchedStarts":
                2,
            "shrinkage":
                "n / (n + 2)",
            "NoSulky":
                "UNKNOWN_OR_MISSING",
            "historicalSulkyCanonicalization":
                "Sulky => StandardSulky",
            "weight":
                0.10,
            "baseSpeedWeights":
                [0.63, 0.27],
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
            in meeting_top3.items()
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
            "trackFeatureUsed":
                False,
            "equipmentChangeBonusUsed":
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
