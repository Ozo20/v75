from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from v75.system_optimizer_v2 import (
    optimize_budget_frontier,
)


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

        if isinstance(value, str):
            value = value.strip()

            if value:
                return value

    horse = row.get("horse")

    if isinstance(horse, dict):
        value = horse.get("name")

        if isinstance(value, str):
            value = value.strip()

            if value:
                return value

    return None


def name_map(
    prediction_leg: dict[str, Any],
) -> dict[int, str]:
    result = {}

    for row in prediction_leg[
        "rankings"
    ]:
        number = int(
            row["startNumber"]
        )

        name = horse_name(
            row
        )

        if name:
            result[number] = name

    return result


def money(
    value: float,
) -> str:
    return (
        f"{value:,.2f}"
        .replace(",", " ")
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
        "--budgets-nok",
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
                *args.budgets_nok,
                args.selected_budget_nok,
            ]
        )
    )

    frontier = (
        optimize_budget_frontier(
            prediction["legs"],
            budgets_nok=budgets,
            row_price_nok=
                args.row_price_nok,
        )
    )

    selected = next(
        (
            point
            for point
            in frontier["points"]
            if abs(
                point["budgetNok"]
                - args.selected_budget_nok
            ) < 1e-9
        ),
        None,
    )

    if selected is None:
        raise RuntimeError(
            "Selected budget not found "
            "in frontier."
        )

    prediction_legs = {
        int(leg["leg"]):
            leg
        for leg
        in prediction["legs"]
    }

    ticket_legs = []

    for leg in selected["legs"]:
        leg_number = int(
            leg["leg"]
        )

        names = name_map(
            prediction_legs[
                leg_number
            ]
        )

        selections = []

        for number in leg[
            "selectedStartNumbers"
        ]:
            number = int(number)

            selections.append(
                {
                    "startNumber":
                        number,
                    "horseName":
                        names.get(
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

    report = {
        "schemaVersion":
            "2.0",
        "view":
            "budget-advisor-ticket",
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
        "rowPriceNok":
            args.row_price_nok,
        "selectedBudgetNok":
            args.selected_budget_nok,
        "frontier":
            frontier["points"],
        "ticket": {
            "budgetNok":
                selected[
                    "budgetNok"
                ],
            "actualCostNok":
                selected[
                    "actualCostNok"
                ],
            "unusedBudgetNok":
                selected[
                    "unusedBudgetNok"
                ],
            "actualRows":
                selected[
                    "actualRows"
                ],
            "estimatedCoverage":
                selected[
                    "estimatedCoverage"
                ],
            "legs":
                ticket_legs,
        },
        "probabilityWarning":
            (
                "Model-estimated coverage. "
                "Absolute probabilities are "
                "provisional and are not "
                "guaranteed real-world odds."
            ),
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

    print(
        "=== V75 BUDGET ADVISOR V2 ==="
    )

    print(
        f"{prediction.get('raceDate')} "
        f"{prediction.get('raceDayName')}"
    )

    print(
        "Horse model:",
        prediction.get(
            "model"
        ),
    )

    print(
        "Row price:",
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
                point["budgetNok"]
                - args.selected_budget_nok
            ) < 1e-9
            else ""
        )

        if previous is None:
            marginal_text = (
                "n/a"
            )
        else:
            delta_cost = (
                point[
                    "actualCostNok"
                ]
                - previous[
                    "actualCostNok"
                ]
            )

            delta_p7 = (
                coverage["all7"]
                - previous[
                    "estimatedCoverage"
                ][
                    "all7"
                ]
            )

            if delta_cost > 0:
                pp_per_100 = (
                    100.0
                    * delta_p7
                    * 100.0
                    / delta_cost
                )

                marginal_text = (
                    f"{pp_per_100:.3f} pp "
                    f"P7 / 100 NOK"
                )
            else:
                marginal_text = (
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
            f"| E="
            f"{coverage['expectedCoveredWinners']:.2f}/7 "
            f"| marginal="
            f"{marginal_text}"
            f"{marker}"
        )

        previous = point

    print()
    print(
        "=== SELECTED V75 TICKET ==="
    )

    coverage = selected[
        "estimatedCoverage"
    ]

    print(
        f"Budget: "
        f"{money(selected['budgetNok'])} NOK"
    )

    print(
        f"Actual cost: "
        f"{money(selected['actualCostNok'])} NOK"
    )

    print(
        f"Unused: "
        f"{money(selected['unusedBudgetNok'])} NOK"
    )

    print(
        f"Rows: "
        f"{selected['actualRows']}"
    )

    print(
        f"Estimated coverage: "
        f"P5+={100*coverage['atLeast5']:.2f}% "
        f"P6+={100*coverage['atLeast6']:.2f}% "
        f"P7={100*coverage['all7']:.2f}%"
    )

    print()

    for leg in ticket_legs:
        numbers = [
            row[
                "startNumber"
            ]
            for row
            in leg["selections"]
        ]

        label = (
            "BANKER"
            if leg["k"] == 1
            else (
                f"{leg['k']} horses"
            )
        )

        joined = ", ".join(
            str(number)
            for number in numbers
        )

        print(
            f"V75-{leg['leg']}: "
            f"{joined:<24} "
            f"| {label:<9} "
            f"| leg cover="
            f"{100*leg['probabilityMass']:.1f}%"
        )

        named = [
            row
            for row
            in leg["selections"]
            if row[
                "horseName"
            ]
        ]

        if named:
            name_text = "; ".join(
                (
                    f"{row['startNumber']} "
                    f"{row['horseName']}"
                )
                for row
                in named
            )

            print(
                "        "
                + name_text
            )

    print()
    print(
        "NOTE: probabilities are "
        "model estimates, not guarantees."
    )

    print()
    print(
        "Report:",
        args.output,
    )


if __name__ == "__main__":
    main()
