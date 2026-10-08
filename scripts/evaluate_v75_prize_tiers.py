from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def convolve(
    left: list[int],
    right: list[int],
) -> list[int]:
    result = [
        0
        for _ in range(
            len(left)
            + len(right)
            - 1
        )
    ]

    for i, a in enumerate(left):
        for j, b in enumerate(right):
            result[i + j] += (
                a * b
            )

    return result


def evaluate_system(
    system,
    outcome_by_leg,
):
    """
    Polynomial interpretation of a V75 system.

    For a leg where the winner IS included
    among k selected horses:

        1 selection gives a correct result
        k-1 selections give an incorrect result

    factor:
        (k-1) + x

    For a leg where the winner is NOT included:

        all k choices are wrong

    factor:
        k

    The coefficient of x^r after multiplying
    all seven factors is exactly the number of
    rows with r correct.
    """

    coefficients = [1]

    leg_results = []

    max_correct = 0

    for leg in system["legs"]:
        k = int(
            leg["k"]
        )

        winner = int(
            outcome_by_leg[
                leg["leg"]
            ][
                "winnerStartNumber"
            ]
        )

        selected = {
            int(value)
            for value
            in leg[
                "selectedStartNumbers"
            ]
        }

        hit = (
            winner in selected
        )

        if hit:
            max_correct += 1

            factor = [
                k - 1,
                1,
            ]
        else:
            factor = [k]

        coefficients = convolve(
            coefficients,
            factor,
        )

        leg_results.append(
            {
                "leg":
                    int(
                        leg["leg"]
                    ),
                "k":
                    k,
                "winner":
                    winner,
                "winnerIncluded":
                    hit,
            }
        )

    actual_rows = int(
        system["actualRows"]
    )

    if (
        sum(coefficients)
        != actual_rows
    ):
        raise AssertionError(
            "Row polynomial does not "
            f"sum to actualRows: "
            f"{sum(coefficients)} "
            f"!= {actual_rows}"
        )

    def exact_rows(correct):
        if correct >= len(
            coefficients
        ):
            return 0

        return int(
            coefficients[correct]
        )

    rows5 = exact_rows(5)
    rows6 = exact_rows(6)
    rows7 = exact_rows(7)

    return {
        "maxCorrect":
            max_correct,
        "rowsWith5":
            rows5,
        "rowsWith6":
            rows6,
        "rowsWith7":
            rows7,
        "totalPrizeRows":
            rows5
            + rows6
            + rows7,
        "hasPrizeTier":
            max_correct >= 5,
        "has6Plus":
            max_correct >= 6,
        "has7":
            max_correct == 7,
        "correctRowDistribution": {
            str(correct):
                exact_rows(correct)
            for correct
            in range(0, 8)
        },
        "legs":
            leg_results,
    }


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

    aggregates = {}
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
            int(row["leg"]):
                row
            for row
            in outcomes["legs"]
        }

        meeting = {
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
                system[
                    "maxRows"
                ]
            )

            result = evaluate_system(
                system,
                outcome_by_leg,
            )

            result[
                "actualRows"
            ] = int(
                system[
                    "actualRows"
                ]
            )

            meeting[
                "budgets"
            ][str(budget)] = (
                result
            )

            agg = aggregates.setdefault(
                budget,
                {
                    "meetings":
                        0,
                    "prizeMeetings":
                        0,
                    "sixPlusMeetings":
                        0,
                    "sevenMeetings":
                        0,
                    "rows5":
                        0,
                    "rows6":
                        0,
                    "rows7":
                        0,
                    "totalPrizeRows":
                        0,
                    "actualRows":
                        0,
                    "maxCorrectDistribution":
                        Counter(),
                },
            )

            agg["meetings"] += 1

            agg[
                "prizeMeetings"
            ] += int(
                result[
                    "hasPrizeTier"
                ]
            )

            agg[
                "sixPlusMeetings"
            ] += int(
                result[
                    "has6Plus"
                ]
            )

            agg[
                "sevenMeetings"
            ] += int(
                result["has7"]
            )

            agg["rows5"] += (
                result[
                    "rowsWith5"
                ]
            )

            agg["rows6"] += (
                result[
                    "rowsWith6"
                ]
            )

            agg["rows7"] += (
                result[
                    "rowsWith7"
                ]
            )

            agg[
                "totalPrizeRows"
            ] += result[
                "totalPrizeRows"
            ]

            agg[
                "actualRows"
            ] += result[
                "actualRows"
            ]

            agg[
                "maxCorrectDistribution"
            ][
                result[
                    "maxCorrect"
                ]
            ] += 1

        per_meeting.append(
            meeting
        )

    print(
        "=== V75 PRIZE-TIER "
        "SYSTEM EVALUATION ==="
    )

    print(
        f"Meetings: "
        f"{len(args.dates)}"
    )

    print()

    print(
        "Prize tiers evaluated: "
        "5 / 6 / 7 correct"
    )

    print()

    final_results = {}

    for budget in sorted(
        aggregates
    ):
        agg = aggregates[
            budget
        ]

        n = agg[
            "meetings"
        ]

        distribution = (
            agg[
                "maxCorrectDistribution"
            ]
        )

        print(
            f"Budget {budget:>4} rows | "
            f"5+={agg['prizeMeetings']}/{n} "
            f"| 6+={agg['sixPlusMeetings']}/{n} "
            f"| 7={agg['sevenMeetings']}/{n}"
        )

        print(
            f"    max correct: "
            f"5={distribution.get(5, 0)} "
            f"6={distribution.get(6, 0)} "
            f"7={distribution.get(7, 0)}"
        )

        print(
            f"    winning rows: "
            f"5-right={agg['rows5']} "
            f"6-right={agg['rows6']} "
            f"7-right={agg['rows7']} "
            f"| total="
            f"{agg['totalPrizeRows']}"
        )

        print(
            f"    total played rows: "
            f"{agg['actualRows']}"
        )

        final_results[
            str(budget)
        ] = {
            "meetings":
                n,
            "meetingsWith5Plus":
                agg[
                    "prizeMeetings"
                ],
            "meetingsWith6Plus":
                agg[
                    "sixPlusMeetings"
                ],
            "meetingsWith7":
                agg[
                    "sevenMeetings"
                ],
            "rowsWith5Correct":
                agg[
                    "rows5"
                ],
            "rowsWith6Correct":
                agg[
                    "rows6"
                ],
            "rowsWith7Correct":
                agg[
                    "rows7"
                ],
            "totalPrizeRows":
                agg[
                    "totalPrizeRows"
                ],
            "totalPlayedRows":
                agg[
                    "actualRows"
                ],
            "maxCorrectDistribution": {
                str(key): value
                for key, value
                in sorted(
                    distribution.items()
                )
            },
        }

    print()
    print(
        "=== PER MEETING MAX CORRECT ==="
    )

    for meeting in per_meeting:
        print(
            f"{meeting['date']} "
            f"{meeting['raceDayName']:<14}",
            end="",
        )

        for budget in sorted(
            int(key)
            for key
            in meeting[
                "budgets"
            ]
        ):
            result = (
                meeting[
                    "budgets"
                ][str(budget)]
            )

            max_correct = (
                result[
                    "maxCorrect"
                ]
            )

            prize_rows = (
                result[
                    "totalPrizeRows"
                ]
            )

            marker = (
                f"{max_correct}/7"
            )

            if max_correct >= 5:
                marker += (
                    f" "
                    f"({prize_rows} "
                    f"prize rows)"
                )

            print(
                f" | "
                f"{budget}:"
                f"{marker}",
                end="",
            )

        print()

    report = {
        "schemaVersion":
            "1.0",
        "evaluation":
            "v75-prize-tier-evaluation-v1",
        "prizeTiers": [
            5,
            6,
            7,
        ],
        "dates":
            args.dates,
        "results":
            final_results,
        "perMeeting":
            per_meeting,
        "note":
            "Prize-row counts are combinatorial row counts only. Monetary payout is not evaluated here."
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
