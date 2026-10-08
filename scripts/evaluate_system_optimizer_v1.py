from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


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

    aggregate = {}

    per_meeting = []

    for date in args.dates:
        base = (
            args.root
            / date
        )

        system_file = load(
            base
            / "system-optimizer-v1.json"
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

        meeting_result = {
            "date":
                date,
            "raceDayName":
                system_file[
                    "raceDayName"
                ],
            "budgets": {},
        }

        for system in system_file[
            "systems"
        ]:
            budget = int(
                system["maxRows"]
            )

            hits = []
            random_leg_probs = []

            for leg in system[
                "legs"
            ]:
                outcome = (
                    outcome_by_leg[
                        leg["leg"]
                    ]
                )

                winner = int(
                    outcome[
                        "winnerStartNumber"
                    ]
                )

                hit = int(
                    winner
                    in leg[
                        "selectedStartNumbers"
                    ]
                )

                hits.append(hit)

                # Get field size from
                # V2A prediction file.
                prediction = load(
                    base
                    / "candidate-v2a-speed-predictions.json"
                )

                pred_leg = next(
                    row
                    for row
                    in prediction["legs"]
                    if row["leg"]
                    == leg["leg"]
                )

                field_size = int(
                    pred_leg[
                        "fieldSizeEligible"
                    ]
                )

                random_leg_probs.append(
                    leg["k"]
                    / field_size
                )

            full_hit = int(
                all(hits)
            )

            random_all7 = 1.0

            for value in (
                random_leg_probs
            ):
                random_all7 *= value

            key = str(budget)

            aggregate.setdefault(
                key,
                {
                    "budget":
                        budget,
                    "meetings":
                        0,
                    "fullHits":
                        0,
                    "legsCovered":
                        0,
                    "totalLegs":
                        0,
                    "rows":
                        [],
                    "estimatedCoverage":
                        [],
                    "randomAll7":
                        [],
                },
            )

            agg = aggregate[key]

            agg["meetings"] += 1
            agg["fullHits"] += (
                full_hit
            )
            agg["legsCovered"] += (
                sum(hits)
            )
            agg["totalLegs"] += (
                len(hits)
            )
            agg["rows"].append(
                system[
                    "actualRows"
                ]
            )
            agg[
                "estimatedCoverage"
            ].append(
                system[
                    "estimatedAll7Coverage"
                ]
            )
            agg[
                "randomAll7"
            ].append(
                random_all7
            )

            meeting_result[
                "budgets"
            ][key] = {
                "actualRows":
                    system[
                        "actualRows"
                    ],
                "ks": [
                    leg["k"]
                    for leg
                    in system[
                        "legs"
                    ]
                ],
                "legsCovered":
                    sum(hits),
                "full7":
                    bool(full_hit),
                "estimatedAll7Coverage":
                    system[
                        "estimatedAll7Coverage"
                    ],
                "randomAll7Coverage":
                    random_all7,
            }

        per_meeting.append(
            meeting_result
        )

    print(
        "=== FRESH V75 SYSTEM "
        "OPTIMIZER EVALUATION ==="
    )

    print(
        f"Meetings: "
        f"{len(args.dates)}"
    )

    print(
        f"Races: "
        f"{len(args.dates) * 7}"
    )

    print()

    results = {}

    for key in sorted(
        aggregate,
        key=int,
    ):
        agg = aggregate[key]

        meetings = agg[
            "meetings"
        ]

        total_legs = agg[
            "totalLegs"
        ]

        result = {
            "budgetRows":
                agg["budget"],
            "meetings":
                meetings,
            "full7Hits":
                agg[
                    "fullHits"
                ],
            "full7Rate":
                agg[
                    "fullHits"
                ]
                / meetings,
            "legsCovered":
                agg[
                    "legsCovered"
                ],
            "totalLegs":
                total_legs,
            "legCoverage":
                agg[
                    "legsCovered"
                ]
                / total_legs,
            "meanActualRows":
                mean(
                    agg["rows"]
                ),
            "meanEstimatedAll7Coverage":
                mean(
                    agg[
                        "estimatedCoverage"
                    ]
                ),
            "meanRandomAll7Coverage":
                mean(
                    agg[
                        "randomAll7"
                    ]
                ),
        }

        results[key] = result

        print(
            f"Budget "
            f"{agg['budget']:>4} rows | "
            f"actual avg="
            f"{result['meanActualRows']:7.1f} | "
            f"legs="
            f"{result['legsCovered']}/"
            f"{total_legs} "
            f"({100 * result['legCoverage']:5.1f}%) | "
            f"7/7="
            f"{result['full7Hits']}/"
            f"{meetings} | "
            f"model est="
            f"{100 * result['meanEstimatedAll7Coverage']:5.2f}% | "
            f"random est="
            f"{100 * result['meanRandomAll7Coverage']:5.2f}%"
        )

    print()
    print(
        "=== PER MEETING ==="
    )

    for meeting in per_meeting:
        print(
            f"{meeting['date']} "
            f"{meeting['raceDayName']:<14}",
            end="",
        )

        for key in sorted(
            meeting["budgets"],
            key=int,
        ):
            row = (
                meeting[
                    "budgets"
                ][key]
            )

            marker = (
                "7/7"
                if row["full7"]
                else f"{row['legsCovered']}/7"
            )

            print(
                f" | "
                f"{key}:{marker}",
                end="",
            )

        print()

    report = {
        "schemaVersion":
            "1.0",
        "evaluation":
            "fresh-system-evaluation-v1",
        "horseModel":
            "candidate-v2a-speed",
        "beta":
            2.872,
        "optimizer":
            "maximize-product-probability-mass",
        "dates":
            args.dates,
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
