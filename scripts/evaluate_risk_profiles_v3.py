from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean

from v75.system_optimizer_v3_profiles import (
    build_risk_profiles,
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
        "--budget-nok",
        required=True,
        type=float,
    )

    parser.add_argument(
        "--row-price-nok",
        required=True,
        type=float,
    )

    parser.add_argument(
        "--min-banker-probability",
        required=True,
        type=float,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    aggregates = {}
    meetings = []

    for date in DATES:
        base = (
            args.root
            / date
        )

        prediction = load(
            base
            / "candidate-v2a-speed-predictions.json"
        )

        outcomes = load(
            base
            / "outcomes.json"
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

        result = build_risk_profiles(
            prediction["legs"],
            total_budget_nok=
                args.budget_nok,
            row_price_nok=
                args.row_price_nok,
            min_banker_probability=
                args.min_banker_probability,
        )

        meeting = {
            "date":
                date,
            "raceDayName":
                prediction[
                    "raceDayName"
                ],
            "profiles":
                {},
        }

        for profile in result[
            "profiles"
        ]:
            name = profile[
                "profile"
            ]

            hits = []
            banker_count = 0
            weak_banker_count = 0

            for leg in profile[
                "legs"
            ]:
                leg_number = int(
                    leg["leg"]
                )

                selected = {
                    int(value)
                    for value
                    in leg[
                        "selectedStartNumbers"
                    ]
                }

                winner = (
                    winner_by_leg[
                        leg_number
                    ]
                )

                hits.append(
                    int(
                        winner
                        in selected
                    )
                )

                if int(
                    leg["k"]
                ) == 1:
                    banker_count += 1

                    top_probability = (
                        result[
                            "topProbabilitiesByLeg"
                        ][
                            str(
                                leg_number
                            )
                        ]
                    )

                    if (
                        top_probability
                        < args.min_banker_probability
                    ):
                        weak_banker_count += 1

            covered = sum(
                hits
            )

            coverage = profile[
                "estimatedCoverage"
            ]

            row = {
                "actualRows":
                    int(
                        profile[
                            "actualRows"
                        ]
                    ),
                "actualCostNok":
                    float(
                        profile[
                            "actualCostNok"
                        ]
                    ),
                "coveredWinners":
                    covered,
                "has5Plus":
                    covered >= 5,
                "has6Plus":
                    covered >= 6,
                "has7":
                    covered == 7,
                "bankers":
                    banker_count,
                "weakBankers":
                    weak_banker_count,
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
                "ks": [
                    int(
                        leg["k"]
                    )
                    for leg
                    in profile[
                        "legs"
                    ]
                ],
            }

            meeting[
                "profiles"
            ][name] = row

            agg = aggregates.setdefault(
                name,
                {
                    "meetings":
                        0,
                    "covered":
                        [],
                    "fivePlus":
                        0,
                    "sixPlus":
                        0,
                    "seven":
                        0,
                    "bankers":
                        [],
                    "weakBankers":
                        [],
                    "estimatedP5":
                        [],
                    "estimatedP6":
                        [],
                    "estimatedP7":
                        [],
                    "costs":
                        [],
                },
            )

            agg["meetings"] += 1

            agg[
                "covered"
            ].append(
                covered
            )

            agg[
                "fivePlus"
            ] += int(
                covered >= 5
            )

            agg[
                "sixPlus"
            ] += int(
                covered >= 6
            )

            agg[
                "seven"
            ] += int(
                covered == 7
            )

            agg[
                "bankers"
            ].append(
                banker_count
            )

            agg[
                "weakBankers"
            ].append(
                weak_banker_count
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
                "costs"
            ].append(
                profile[
                    "actualCostNok"
                ]
            )

        meetings.append(
            meeting
        )

    pairwise = Counter()

    for meeting in meetings:
        rows = meeting[
            "profiles"
        ]

        max_hits = rows[
            "MAX_P7"
        ][
            "coveredWinners"
        ]

        weak_hits = rows[
            "NO_WEAK_BANKER"
        ][
            "coveredWinners"
        ]

        no_hits = rows[
            "NO_BANKER"
        ][
            "coveredWinners"
        ]

        if weak_hits > max_hits:
            pairwise[
                "NO_WEAK_BETTER_THAN_MAX"
            ] += 1
        elif weak_hits < max_hits:
            pairwise[
                "MAX_BETTER_THAN_NO_WEAK"
            ] += 1
        else:
            pairwise[
                "MAX_EQUAL_NO_WEAK"
            ] += 1

        if no_hits > max_hits:
            pairwise[
                "NO_BANKER_BETTER_THAN_MAX"
            ] += 1
        elif no_hits < max_hits:
            pairwise[
                "MAX_BETTER_THAN_NO_BANKER"
            ] += 1
        else:
            pairwise[
                "MAX_EQUAL_NO_BANKER"
            ] += 1

    print(
        "=== V75 RISK PROFILE "
        "HISTORICAL DIAGNOSTIC ==="
    )

    print(
        f"Meetings: {len(meetings)}"
    )

    print(
        f"Budget: "
        f"{args.budget_nok:.2f} NOK"
    )

    print(
        f"Row price: "
        f"{args.row_price_nok:.2f} NOK"
    )

    print(
        "Weak-banker threshold: "
        f"{100*args.min_banker_probability:.1f}%"
    )

    print()
    print(
        "=== AGGREGATE ==="
    )

    summary = {}

    for name in (
        "MAX_P7",
        "NO_WEAK_BANKER",
        "NO_BANKER",
    ):
        agg = aggregates[
            name
        ]

        n = agg[
            "meetings"
        ]

        row = {
            "meetings":
                n,
            "meanCoveredWinners":
                mean(
                    agg[
                        "covered"
                    ]
                ),
            "fivePlusMeetings":
                agg[
                    "fivePlus"
                ],
            "sixPlusMeetings":
                agg[
                    "sixPlus"
                ],
            "sevenMeetings":
                agg[
                    "seven"
                ],
            "meanBankers":
                mean(
                    agg[
                        "bankers"
                    ]
                ),
            "meanWeakBankers":
                mean(
                    agg[
                        "weakBankers"
                    ]
                ),
            "meanEstimatedP5":
                mean(
                    agg[
                        "estimatedP5"
                    ]
                ),
            "meanEstimatedP6":
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
            "meanActualCostNok":
                mean(
                    agg[
                        "costs"
                    ]
                ),
        }

        summary[
            name
        ] = row

        print(
            f"{name:<16} "
            f"| actual avg="
            f"{row['meanCoveredWinners']:.2f}/7 "
            f"| 5+="
            f"{row['fivePlusMeetings']}/{n} "
            f"| 6+="
            f"{row['sixPlusMeetings']}/{n} "
            f"| 7="
            f"{row['sevenMeetings']}/{n} "
            f"| bankers avg="
            f"{row['meanBankers']:.2f} "
            f"| weak avg="
            f"{row['meanWeakBankers']:.2f} "
            f"| est P7="
            f"{100*row['meanEstimatedP7']:.2f}%"
        )

    print()
    print(
        "=== PAIRWISE ACTUAL COVERAGE ==="
    )

    for key in (
        "NO_WEAK_BETTER_THAN_MAX",
        "MAX_BETTER_THAN_NO_WEAK",
        "MAX_EQUAL_NO_WEAK",
        "NO_BANKER_BETTER_THAN_MAX",
        "MAX_BETTER_THAN_NO_BANKER",
        "MAX_EQUAL_NO_BANKER",
    ):
        print(
            f"{key:<32} "
            f"{pairwise[key]}"
        )

    print()
    print(
        "=== PER MEETING ==="
    )

    for meeting in meetings:
        print(
            f"{meeting['date']} "
            f"{meeting['raceDayName']:<14}",
            end="",
        )

        for name in (
            "MAX_P7",
            "NO_WEAK_BANKER",
            "NO_BANKER",
        ):
            row = meeting[
                "profiles"
            ][name]

            print(
                f" | {name}="
                f"{row['coveredWinners']}/7"
                f" b{row['bankers']}"
                f" w{row['weakBankers']}",
                end="",
            )

        print()

    output = {
        "schemaVersion":
            "3.0",
        "evaluation":
            "historical-risk-profile-diagnostic",
        "horseModel":
            "candidate-v2a-speed",
        "budgetNok":
            args.budget_nok,
        "rowPriceNok":
            args.row_price_nok,
        "minBankerProbability":
            args.min_banker_probability,
        "dates":
            DATES,
        "summary":
            summary,
        "pairwiseActualCoverage":
            dict(
                pairwise
            ),
        "meetings":
            meetings,
        "guardrails": {
            "retrospectiveOnly":
                True,
            "thresholdFixedBeforeEvaluation":
                True,
            "thresholdTunedOnOutcomes":
                False,
            "horseModelModified":
                False,
            "optimizerModified":
                False,
            "marketUsed":
                False,
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
