from __future__ import annotations

import argparse
import json
import math
from math import prod
from pathlib import Path
from statistics import mean


BETA = 2.872

THRESHOLDS = (
    0.50,
    0.60,
    0.70,
    0.80,
    0.90,
)


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def probabilities(scores):
    scaled = [
        BETA * score
        for score in scores
    ]

    maximum = max(scaled)

    exp_values = [
        math.exp(
            value - maximum
        )
        for value in scaled
    ]

    denominator = sum(
        exp_values
    )

    return [
        value / denominator
        for value in exp_values
    ]


def minimum_k_for_mass(
    probs,
    threshold,
):
    cumulative = 0.0

    for i, probability in enumerate(
        probs,
        1,
    ):
        cumulative += probability

        if cumulative >= threshold:
            return i, cumulative

    return len(probs), 1.0


def main():
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

    stats = {
        threshold: {
            "selectedCounts": [],
            "covered": [],
            "actualMass": [],
        }
        for threshold in THRESHOLDS
    }

    meeting_rows = {
        threshold: []
        for threshold in THRESHOLDS
    }

    meeting_full_cover = {
        threshold: []
        for threshold in THRESHOLDS
    }

    banker_stats = {
        0.25: [],
        0.30: [],
        0.35: [],
        0.40: [],
    }

    print(
        "=== PROBABILITY-DRIVEN "
        "SYSTEM COVERAGE ==="
    )

    print(
        f"Model: candidate-v2a-speed"
    )

    print(
        f"Calibration beta: {BETA}"
    )

    print()

    total_races = 0

    for date in args.dates:
        base = (
            args.root
            / date
        )

        predictions = load(
            base
            / "candidate-v2a-speed-predictions.json"
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

        meeting_counts = {
            threshold: []
            for threshold in THRESHOLDS
        }

        meeting_hits = {
            threshold: []
            for threshold in THRESHOLDS
        }

        print(
            f"{date} "
            f"{predictions['raceDayName']}"
        )

        for leg in predictions[
            "legs"
        ]:
            rankings = sorted(
                leg["rankings"],
                key=lambda row: (
                    int(row["rank"])
                )
            )

            scores = [
                float(row["score"])
                for row in rankings
            ]

            probs = probabilities(
                scores
            )

            winner = int(
                outcome_by_leg[
                    leg["leg"]
                ][
                    "winnerStartNumber"
                ]
            )

            winner_index = next(
                i
                for i, row
                in enumerate(rankings)
                if int(
                    row["startNumber"]
                )
                == winner
            )

            top1_probability = probs[0]

            for cutoff in banker_stats:
                if (
                    top1_probability
                    >= cutoff
                ):
                    banker_stats[
                        cutoff
                    ].append(
                        int(
                            winner_index == 0
                        )
                    )

            for threshold in THRESHOLDS:
                k, actual_mass = (
                    minimum_k_for_mass(
                        probs,
                        threshold,
                    )
                )

                covered = int(
                    winner_index < k
                )

                stats[
                    threshold
                ][
                    "selectedCounts"
                ].append(k)

                stats[
                    threshold
                ][
                    "covered"
                ].append(
                    covered
                )

                stats[
                    threshold
                ][
                    "actualMass"
                ].append(
                    actual_mass
                )

                meeting_counts[
                    threshold
                ].append(k)

                meeting_hits[
                    threshold
                ].append(
                    covered
                )

            total_races += 1

        for threshold in THRESHOLDS:
            rows = prod(
                meeting_counts[
                    threshold
                ]
            )

            meeting_rows[
                threshold
            ].append(rows)

            meeting_full_cover[
                threshold
            ].append(
                int(
                    all(
                        meeting_hits[
                            threshold
                        ]
                    )
                )
            )

    print()
    print(
        "=== RACE-LEVEL ADAPTIVE COVERAGE ==="
    )

    for threshold in THRESHOLDS:
        row = stats[
            threshold
        ]

        selected = row[
            "selectedCounts"
        ]

        covered = row[
            "covered"
        ]

        mass = row[
            "actualMass"
        ]

        print()
        print(
            f"Target mass "
            f"{threshold:.0%}:"
        )

        print(
            f"  Actual mean mass: "
            f"{mean(mass):.1%}"
        )

        print(
            f"  Mean horses:      "
            f"{mean(selected):.2f}"
        )

        print(
            f"  Min/max horses:   "
            f"{min(selected)}/"
            f"{max(selected)}"
        )

        print(
            f"  Winner coverage:  "
            f"{sum(covered)}/"
            f"{len(covered)} "
            f"({mean(covered):.1%})"
        )

    print()
    print(
        "=== COMPLETE 7/7 MEETING COVERAGE ==="
    )

    for threshold in THRESHOLDS:
        hits = sum(
            meeting_full_cover[
                threshold
            ]
        )

        total = len(
            meeting_full_cover[
                threshold
            ]
        )

        rows = meeting_rows[
            threshold
        ]

        print(
            f"{threshold:.0%} mass: "
            f"{hits}/{total} meetings "
            f"| rows "
            f"min={min(rows)} "
            f"avg={mean(rows):.1f} "
            f"max={max(rows)}"
        )

    print()
    print(
        "=== BANKER CONFIDENCE DIAGNOSTIC ==="
    )

    for cutoff, hits in (
        banker_stats.items()
    ):
        if not hits:
            print(
                f"P1 >= {cutoff:.0%}: "
                f"0 qualifying races"
            )
            continue

        print(
            f"P1 >= {cutoff:.0%}: "
            f"{len(hits)} races | "
            f"winner="
            f"{sum(hits)}/"
            f"{len(hits)} "
            f"({mean(hits):.1%})"
        )

    report = {
        "schemaVersion":
            "1.0",
        "model":
            "candidate-v2a-speed",
        "beta":
            BETA,
        "scope":
            "independent-robustness",
        "dates":
            args.dates,
        "thresholds": {},
        "bankerDiagnostics": {},
    }

    for threshold in THRESHOLDS:
        row = stats[
            threshold
        ]

        report[
            "thresholds"
        ][str(threshold)] = {
            "meanSelectedHorses":
                mean(
                    row[
                        "selectedCounts"
                    ]
                ),
            "minSelectedHorses":
                min(
                    row[
                        "selectedCounts"
                    ]
                ),
            "maxSelectedHorses":
                max(
                    row[
                        "selectedCounts"
                    ]
                ),
            "winnerCoverage":
                mean(
                    row[
                        "covered"
                    ]
                ),
            "meanActualProbabilityMass":
                mean(
                    row[
                        "actualMass"
                    ]
                ),
            "fullMeetingHits":
                sum(
                    meeting_full_cover[
                        threshold
                    ]
                ),
            "meetings":
                len(
                    meeting_full_cover[
                        threshold
                    ]
                ),
            "meanRows":
                mean(
                    meeting_rows[
                        threshold
                    ]
                ),
        }

    for cutoff, hits in (
        banker_stats.items()
    ):
        report[
            "bankerDiagnostics"
        ][str(cutoff)] = {
            "qualifyingRaces":
                len(hits),
            "wins":
                sum(hits),
            "observedWinRate":
                (
                    mean(hits)
                    if hits
                    else None
                ),
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
