from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

from v75.system_optimizer_v2 import (
    optimize_budget_frontier,
)


DATES = [
    "2026-01-06",
    "2026-01-10",
    "2026-01-17",
    "2026-01-24",
    "2026-01-31",
    "2026-02-07",
    "2026-02-14",
    "2026-02-21",
    "2026-02-28",
    "2026-03-07",
    "2026-03-21",
]


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
        "--row-price-nok",
        required=True,
        type=float,
    )

    parser.add_argument(
        "--budgets-nok",
        required=True,
        nargs="+",
        type=float,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    aggregate = {
        float(budget): {
            "meetings":
                0,
            "actualCosts":
                [],
            "actualRows":
                [],
            "coveredLegs":
                [],
            "atLeast5Actual":
                0,
            "atLeast6Actual":
                0,
            "all7Actual":
                0,
            "estimatedP5":
                [],
            "estimatedP6":
                [],
            "estimatedP7":
                [],
            "expectedCovered":
                [],
        }
        for budget in args.budgets_nok
    }

    meetings = []

    for date in DATES:
        base = (
            args.root
            / date
        )

        prediction_path = (
            base
            / "candidate-v2a-speed-predictions.json"
        )

        outcome_path = (
            base
            / "outcomes.json"
        )

        if not prediction_path.exists():
            raise FileNotFoundError(
                prediction_path
            )

        if not outcome_path.exists():
            raise FileNotFoundError(
                outcome_path
            )

        prediction = load(
            prediction_path
        )

        outcomes = load(
            outcome_path
        )

        if prediction["model"] != (
            "candidate-v2a-speed"
        ):
            raise AssertionError(
                "Unexpected horse model: "
                f"{prediction['model']}"
            )

        frontier = (
            optimize_budget_frontier(
                prediction["legs"],
                budgets_nok=
                    args.budgets_nok,
                row_price_nok=
                    args.row_price_nok,
            )
        )

        winner_by_leg = {
            int(row["leg"]):
                int(
                    row[
                        "winnerStartNumber"
                    ]
                )
            for row
            in outcomes["legs"]
        }

        meeting = {
            "date":
                date,
            "raceDayName":
                prediction[
                    "raceDayName"
                ],
            "budgets":
                {},
        }

        for point in frontier[
            "points"
        ]:
            budget = float(
                point["budgetNok"]
            )

            hits = []

            for leg in point[
                "legs"
            ]:
                winner = (
                    winner_by_leg[
                        int(
                            leg["leg"]
                        )
                    ]
                )

                selected = {
                    int(value)
                    for value
                    in leg[
                        "selectedStartNumbers"
                    ]
                }

                hits.append(
                    int(
                        winner
                        in selected
                    )
                )

            covered = sum(
                hits
            )

            coverage = point[
                "estimatedCoverage"
            ]

            ks = [
                int(leg["k"])
                for leg
                in point["legs"]
            ]

            meeting[
                "budgets"
            ][str(budget)] = {
                "actualRows":
                    int(
                        point[
                            "actualRows"
                        ]
                    ),
                "actualCostNok":
                    float(
                        point[
                            "actualCostNok"
                        ]
                    ),
                "unusedBudgetNok":
                    float(
                        point[
                            "unusedBudgetNok"
                        ]
                    ),
                "ks":
                    ks,
                "coveredWinners":
                    covered,
                "has5Plus":
                    covered >= 5,
                "has6Plus":
                    covered >= 6,
                "has7":
                    covered == 7,
                "estimatedP5Plus":
                    float(
                        coverage[
                            "atLeast5"
                        ]
                    ),
                "estimatedP6Plus":
                    float(
                        coverage[
                            "atLeast6"
                        ]
                    ),
                "estimatedP7":
                    float(
                        coverage[
                            "all7"
                        ]
                    ),
                "expectedCoveredWinners":
                    float(
                        coverage[
                            "expectedCoveredWinners"
                        ]
                    ),
                "marginalFromPrevious":
                    point[
                        "marginalFromPrevious"
                    ],
                "legs": [
                    {
                        "leg":
                            int(
                                leg["leg"]
                            ),
                        "k":
                            int(
                                leg["k"]
                            ),
                        "selectedStartNumbers":
                            [
                                int(value)
                                for value
                                in leg[
                                    "selectedStartNumbers"
                                ]
                            ],
                        "probabilityMass":
                            float(
                                leg[
                                    "probabilityMass"
                                ]
                            ),
                        "winnerIncluded":
                            bool(
                                hits[index]
                            ),
                    }
                    for index, leg
                    in enumerate(
                        point["legs"]
                    )
                ],
            }

            agg = aggregate[
                budget
            ]

            agg["meetings"] += 1

            agg[
                "actualCosts"
            ].append(
                point[
                    "actualCostNok"
                ]
            )

            agg[
                "actualRows"
            ].append(
                point[
                    "actualRows"
                ]
            )

            agg[
                "coveredLegs"
            ].append(
                covered
            )

            agg[
                "atLeast5Actual"
            ] += int(
                covered >= 5
            )

            agg[
                "atLeast6Actual"
            ] += int(
                covered >= 6
            )

            agg[
                "all7Actual"
            ] += int(
                covered == 7
            )

            agg[
                "estimatedP5"
            ].append(
                coverage[
                    "atLeast5"
                ]
            )

            agg[
                "estimatedP6"
            ].append(
                coverage[
                    "atLeast6"
                ]
            )

            agg[
                "estimatedP7"
            ].append(
                coverage[
                    "all7"
                ]
            )

            agg[
                "expectedCovered"
            ].append(
                coverage[
                    "expectedCoveredWinners"
                ]
            )

        meetings.append(
            meeting
        )

    results = {}

    print(
        "=== V75 BUDGET FRONTIER "
        "— HISTORICAL SYSTEM DIAGNOSTIC ==="
    )

    print(
        f"Meetings: {len(meetings)}"
    )

    print(
        f"Row price scenario: "
        f"{args.row_price_nok:.2f} NOK"
    )

    print()

    print(
        "=== AGGREGATE ==="
    )

    for budget in sorted(
        aggregate
    ):
        agg = aggregate[
            budget
        ]

        n = agg[
            "meetings"
        ]

        result = {
            "budgetNok":
                budget,
            "meetings":
                n,
            "meanActualCostNok":
                mean(
                    agg[
                        "actualCosts"
                    ]
                ),
            "meanActualRows":
                mean(
                    agg[
                        "actualRows"
                    ]
                ),
            "meanCoveredWinners":
                mean(
                    agg[
                        "coveredLegs"
                    ]
                ),
            "actual5PlusMeetings":
                agg[
                    "atLeast5Actual"
                ],
            "actual6PlusMeetings":
                agg[
                    "atLeast6Actual"
                ],
            "actual7Meetings":
                agg[
                    "all7Actual"
                ],
            "actual5PlusRate":
                agg[
                    "atLeast5Actual"
                ]
                / n,
            "actual6PlusRate":
                agg[
                    "atLeast6Actual"
                ]
                / n,
            "actual7Rate":
                agg[
                    "all7Actual"
                ]
                / n,
            "meanEstimatedP5Plus":
                mean(
                    agg[
                        "estimatedP5"
                    ]
                ),
            "meanEstimatedP6Plus":
                mean(
                    agg[
                        "estimatedP6"
                    ]
                ),
            "meanEstimatedP7":
                mean(
                    agg[
                        "estimatedP7"
                    ]
                ),
            "meanExpectedCoveredWinners":
                mean(
                    agg[
                        "expectedCovered"
                    ]
                ),
        }

        results[
            str(budget)
        ] = result

        print(
            f"{budget:>7.0f} NOK "
            f"| cost avg="
            f"{result['meanActualCostNok']:7.2f} "
            f"| rows avg="
            f"{result['meanActualRows']:7.1f} "
            f"| actual avg="
            f"{result['meanCoveredWinners']:.2f}/7 "
            f"| 5+="
            f"{result['actual5PlusMeetings']:>2}/{n} "
            f"| 6+="
            f"{result['actual6PlusMeetings']:>2}/{n} "
            f"| 7="
            f"{result['actual7Meetings']:>2}/{n} "
            f"| est P5+="
            f"{100*result['meanEstimatedP5Plus']:6.2f}% "
            f"| P6+="
            f"{100*result['meanEstimatedP6Plus']:6.2f}% "
            f"| P7="
            f"{100*result['meanEstimatedP7']:6.2f}%"
        )

    print()
    print(
        "=== PER MEETING ==="
    )

    for meeting in meetings:
        print()
        print(
            f"{meeting['date']} "
            f"{meeting['raceDayName']}"
        )

        previous_p7 = None

        for budget in sorted(
            aggregate
        ):
            row = meeting[
                "budgets"
            ][
                str(budget)
            ]

            p7 = row[
                "estimatedP7"
            ]

            delta = (
                None
                if previous_p7 is None
                else (
                    p7
                    - previous_p7
                )
            )

            delta_text = (
                "   n/a"
                if delta is None
                else f"{100*delta:6.2f}pp"
            )

            print(
                f"  {budget:>4.0f} NOK "
                f"| cost="
                f"{row['actualCostNok']:7.2f} "
                f"| rows="
                f"{row['actualRows']:>5} "
                f"| k="
                f"{row['ks']} "
                f"| actual="
                f"{row['coveredWinners']}/7 "
                f"| P7="
                f"{100*p7:6.2f}% "
                f"| ΔP7="
                f"{delta_text}"
            )

            previous_p7 = p7

    output = {
        "schemaVersion":
            "2.0",
        "evaluation":
            "historical-budget-frontier-diagnostic",
        "horseModel":
            "candidate-v2a-speed",
        "systemModel":
            "v75-system-optimizer-v2-budget-frontier",
        "rowPriceScenarioNok":
            args.row_price_nok,
        "budgetsNok":
            sorted(
                float(value)
                for value
                in args.budgets_nok
            ),
        "dates":
            DATES,
        "results":
            results,
        "meetings":
            meetings,
        "guardrails": {
            "retrospectiveSystemDiagnostic":
                True,
            "horseModelTuned":
                False,
            "validationUsedForHorseTuning":
                False,
            "marketUsed":
                False,
            "absoluteProbabilitiesProvisional":
                True,
        },
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "Report:",
        args.output,
    )


if __name__ == "__main__":
    main()
