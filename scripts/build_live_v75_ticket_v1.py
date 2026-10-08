from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from v75.system_optimizer_v2 import (
    optimize_budget_frontier,
)
from v75.system_optimizer_v3_profiles import (
    build_risk_profiles,
)


PROFILE_ORDER = [
    "MAX_P7",
    "NO_WEAK_BANKER",
]


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def horse_name(
    row: dict[str, Any],
) -> str | None:
    for key in (
        "horseName",
        "name",
    ):
        value = row.get(key)

        if (
            isinstance(value, str)
            and value.strip()
        ):
            return value.strip()

    horse = row.get("horse")

    if isinstance(horse, dict):
        value = horse.get("name")

        if (
            isinstance(value, str)
            and value.strip()
        ):
            return value.strip()

    return None


def build_name_maps(
    prediction: dict[str, Any],
) -> dict[int, dict[int, str]]:
    result = {}

    for leg in prediction["legs"]:
        leg_number = int(
            leg["leg"]
        )

        result[leg_number] = {}

        for row in leg["rankings"]:
            number = int(
                row["startNumber"]
            )

            name = horse_name(row)

            if name:
                result[
                    leg_number
                ][
                    number
                ] = name

    return result


def selection_text(
    leg: dict[str, Any],
) -> str:
    return ", ".join(
        str(int(value))
        for value
        in leg[
            "selectedStartNumbers"
        ]
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--predictions",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--row-price-nok",
        required=True,
        type=float,
    )

    parser.add_argument(
        "--budget-options-nok",
        required=True,
        nargs="+",
        type=float,
    )

    parser.add_argument(
        "--selected-budget-nok",
        required=True,
        type=float,
    )

    parser.add_argument(
        "--min-banker-probability",
        default=0.35,
        type=float,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    prediction = load(
        args.predictions
    )

    if len(
        prediction["legs"]
    ) != 7:
        raise ValueError(
            "Expected exactly 7 V75 legs."
        )

    budgets = sorted(
        set(
            [
                *args.budget_options_nok,
                args.selected_budget_nok,
            ]
        )
    )

    frontier = optimize_budget_frontier(
        prediction["legs"],
        budgets_nok=budgets,
        row_price_nok=
            args.row_price_nok,
    )

    profile_result = build_risk_profiles(
        prediction["legs"],
        total_budget_nok=
            args.selected_budget_nok,
        row_price_nok=
            args.row_price_nok,
        min_banker_probability=
            args.min_banker_probability,
    )

    profile_map = {
        row["profile"]:
            row
        for row
        in profile_result["profiles"]
    }

    names = build_name_maps(
        prediction
    )

    selected_frontier = next(
        point
        for point
        in frontier["points"]
        if abs(
            float(point["budgetNok"])
            - args.selected_budget_nok
        ) < 1e-9
    )

    tickets = {}

    for profile_name in PROFILE_ORDER:
        profile = profile_map[
            profile_name
        ]

        ticket_legs = []

        for leg in profile["legs"]:
            leg_number = int(
                leg["leg"]
            )

            selections = []

            for value in leg[
                "selectedStartNumbers"
            ]:
                number = int(value)

                selections.append(
                    {
                        "startNumber":
                            number,
                        "horseName":
                            names.get(
                                leg_number,
                                {},
                            ).get(
                                number
                            ),
                    }
                )

            ticket_legs.append(
                {
                    "leg":
                        leg_number,
                    "k":
                        int(
                            leg["k"]
                        ),
                    "probabilityMass":
                        float(
                            leg[
                                "probabilityMass"
                            ]
                        ),
                    "selections":
                        selections,
                }
            )

        tickets[
            profile_name
        ] = {
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
            "unusedBudgetNok":
                float(
                    profile[
                        "unusedBudgetNok"
                    ]
                ),
            "estimatedCoverage":
                profile[
                    "estimatedCoverage"
                ],
            "legs":
                ticket_legs,
        }

    max_ticket = tickets[
        "MAX_P7"
    ]

    challenger_ticket = tickets[
        "NO_WEAK_BANKER"
    ]

    differences = []

    max_by_leg = {
        row["leg"]:
            row
        for row
        in max_ticket["legs"]
    }

    challenger_by_leg = {
        row["leg"]:
            row
        for row
        in challenger_ticket["legs"]
    }

    for leg_number in range(
        1,
        8,
    ):
        max_numbers = [
            row["startNumber"]
            for row
            in max_by_leg[
                leg_number
            ][
                "selections"
            ]
        ]

        challenger_numbers = [
            row["startNumber"]
            for row
            in challenger_by_leg[
                leg_number
            ][
                "selections"
            ]
        ]

        if (
            max_numbers
            != challenger_numbers
        ):
            differences.append(
                {
                    "leg":
                        leg_number,
                    "maxP7":
                        max_numbers,
                    "noWeakBanker":
                        challenger_numbers,
                }
            )

    output = {
        "schemaVersion":
            "1.0",
        "package":
            "live-v75-ticket",
        "raceDate":
            prediction.get(
                "raceDate"
            ),
        "raceDayName":
            prediction.get(
                "raceDayName"
            ),
        "raceDayKey":
            prediction.get(
                "raceDayKey"
            ),
        "horseModel":
            prediction.get(
                "model"
            ),
        "selectedBudgetNok":
            args.selected_budget_nok,
        "rowPriceNok":
            args.row_price_nok,
        "minBankerProbability":
            args.min_banker_probability,
        "defaultPolicy":
            "MAX_P7",
        "challengerPolicy":
            "NO_WEAK_BANKER",
        "budgetFrontier":
            frontier["points"],
        "selectedFrontierPoint":
            selected_frontier,
        "tickets":
            tickets,
        "ticketDifferences":
            differences,
        "guardrails": {
            "preRaceOnly":
                True,
            "outcomesUsed":
                False,
            "marketUsed":
                False,
            "horseModelRetuned":
                False,
            "bankerThresholdRetuned":
                False,
        },
        "warning":
            (
                "Coverage probabilities are "
                "provisional model estimates, "
                "not guaranteed real-world odds."
            ),
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

    print(
        "=== LIVE V75 TICKET PACKAGE V1 ==="
    )

    print(
        f"{output['raceDate']} "
        f"{output['raceDayName']}"
    )

    print(
        "Horse model:",
        output["horseModel"],
    )

    print(
        f"Selected budget: "
        f"{args.selected_budget_nok:.2f} NOK"
    )

    print(
        f"Row price: "
        f"{args.row_price_nok:.2f} NOK"
    )

    print()

    print(
        "=== BUDGET FRONTIER ==="
    )

    previous = None

    for point in frontier[
        "points"
    ]:
        coverage = point[
            "estimatedCoverage"
        ]

        marker = (
            " <== SELECTED"
            if abs(
                float(
                    point[
                        "budgetNok"
                    ]
                )
                - args.selected_budget_nok
            ) < 1e-9
            else ""
        )

        if previous is None:
            marginal = "n/a"
        else:
            delta_cost = (
                float(
                    point[
                        "actualCostNok"
                    ]
                )
                - float(
                    previous[
                        "actualCostNok"
                    ]
                )
            )

            delta_p7 = (
                float(
                    coverage[
                        "all7"
                    ]
                )
                - float(
                    previous[
                        "estimatedCoverage"
                    ][
                        "all7"
                    ]
                )
            )

            if delta_cost > 0:
                pp_per_100 = (
                    delta_p7
                    * 100.0
                    * 100.0
                    / delta_cost
                )

                marginal = (
                    f"{pp_per_100:.3f} "
                    f"pp P7 / 100 NOK"
                )
            else:
                marginal = (
                    "no extra spend"
                )

        print(
            f"{point['budgetNok']:>7.0f} NOK "
            f"| cost="
            f"{point['actualCostNok']:>7.2f} "
            f"| rows="
            f"{point['actualRows']:>5} "
            f"| P5+="
            f"{100*coverage['atLeast5']:6.2f}% "
            f"| P6+="
            f"{100*coverage['atLeast6']:6.2f}% "
            f"| P7="
            f"{100*coverage['all7']:6.2f}% "
            f"| marginal="
            f"{marginal}"
            f"{marker}"
        )

        previous = point

    print()

    print(
        "=== TICKET COMPARISON ==="
    )

    max_p7_value = (
        max_ticket[
            "estimatedCoverage"
        ][
            "all7"
        ]
    )

    for profile_name in PROFILE_ORDER:
        ticket = tickets[
            profile_name
        ]

        coverage = ticket[
            "estimatedCoverage"
        ]

        delta = (
            max_p7_value
            - coverage[
                "all7"
            ]
        )

        label = (
            "DEFAULT"
            if profile_name
            == "MAX_P7"
            else "CHALLENGER"
        )

        print(
            f"--- {profile_name} "
            f"[{label}] ---"
        )

        print(
            f"Rows: "
            f"{ticket['actualRows']} "
            f"| Cost: "
            f"{ticket['actualCostNok']:.2f} NOK "
            f"| Unused: "
            f"{ticket['unusedBudgetNok']:.2f} NOK"
        )

        print(
            f"P5+: "
            f"{100*coverage['atLeast5']:.2f}% "
            f"| P6+: "
            f"{100*coverage['atLeast6']:.2f}% "
            f"| P7: "
            f"{100*coverage['all7']:.2f}%"
        )

        if profile_name != "MAX_P7":
            print(
                "P7 cost vs default: "
                f"{100*delta:.3f} pp"
            )

        for leg in ticket[
            "legs"
        ]:
            numbers = ", ".join(
                str(
                    row[
                        "startNumber"
                    ]
                )
                for row
                in leg[
                    "selections"
                ]
            )

            banker = (
                " BANKER"
                if leg["k"] == 1
                else ""
            )

            print(
                f"V75-{leg['leg']}: "
                f"{numbers:<24} "
                f"| k={leg['k']} "
                f"| cover="
                f"{100*leg['probabilityMass']:.1f}%"
                f"{banker}"
            )

            named = [
                row
                for row
                in leg[
                    "selections"
                ]
                if row[
                    "horseName"
                ]
            ]

            if named:
                print(
                    "        "
                    + "; ".join(
                        (
                            f"{row['startNumber']} "
                            f"{row['horseName']}"
                        )
                        for row
                        in named
                    )
                )

        print()

    print(
        "=== PROFILE DIFFERENCES ==="
    )

    if not differences:
        print(
            "Tickets are identical."
        )
    else:
        for row in differences:
            print(
                f"V75-{row['leg']}: "
                f"MAX_P7="
                f"{row['maxP7']} "
                f"| NO_WEAK_BANKER="
                f"{row['noWeakBanker']}"
            )

    print()
    print(
        "NOTE: no outcomes or market "
        "information used."
    )

    print(
        "NOTE: MAX_P7 remains default; "
        "35% policy remains frozen challenger."
    )

    print()
    print(
        "Report:",
        args.output,
    )


if __name__ == "__main__":
    main()
