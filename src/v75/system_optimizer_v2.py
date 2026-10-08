from __future__ import annotations

from decimal import (
    Decimal,
    ROUND_FLOOR,
)
from typing import Any

from v75.system_optimizer_v1 import (
    optimize_system,
)


def _decimal(
    value: Any,
) -> Decimal:
    return Decimal(
        str(value)
    )


def max_rows_from_budget(
    total_budget_nok: Any,
    row_price_nok: Any,
) -> int:
    budget = _decimal(
        total_budget_nok
    )

    row_price = _decimal(
        row_price_nok
    )

    if budget <= 0:
        raise ValueError(
            "total_budget_nok must be > 0"
        )

    if row_price <= 0:
        raise ValueError(
            "row_price_nok must be > 0"
        )

    rows = int(
        (
            budget
            / row_price
        ).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )

    if rows < 1:
        raise ValueError(
            "Budget is smaller than one row"
        )

    return rows


def coverage_distribution(
    system: dict[str, Any],
) -> dict[str, Any]:
    """
    Probability distribution for how many
    V75 winners are included on the ticket.

    For each leg:
      q     = probability mass covered
      1 - q = probability winner is missed

    Polynomial factor:
      (1-q) + q*x

    Coefficient x^r after all legs gives
    estimated probability of covering
    exactly r winning horses.

    This assumes cross-leg independence,
    consistent with the existing all-7
    product objective.
    """

    probabilities = [
        float(
            leg["probabilityMass"]
        )
        for leg in system["legs"]
    ]

    coefficients = [1.0]

    for q in probabilities:
        if not (
            0.0 <= q <= 1.0
        ):
            raise ValueError(
                f"Invalid probability mass: {q}"
            )

        next_coefficients = [
            0.0
            for _ in range(
                len(coefficients) + 1
            )
        ]

        for correct, value in enumerate(
            coefficients
        ):
            next_coefficients[
                correct
            ] += (
                value
                * (1.0 - q)
            )

            next_coefficients[
                correct + 1
            ] += (
                value
                * q
            )

        coefficients = (
            next_coefficients
        )

    total = sum(
        coefficients
    )

    if abs(total - 1.0) > 1e-10:
        raise AssertionError(
            "Coverage distribution does "
            f"not sum to 1: {total}"
        )

    legs = len(
        probabilities
    )

    exact = {
        str(correct):
            coefficients[correct]
        for correct in range(
            legs + 1
        )
    }

    at_least_5 = (
        sum(coefficients[5:])
        if legs >= 5
        else 0.0
    )

    at_least_6 = (
        sum(coefficients[6:])
        if legs >= 6
        else 0.0
    )

    all_7 = (
        coefficients[7]
        if legs >= 7
        else 0.0
    )

    expected = sum(
        correct * probability
        for correct, probability
        in enumerate(
            coefficients
        )
    )

    return {
        "exact":
            exact,
        "atLeast5":
            at_least_5,
        "atLeast6":
            at_least_6,
        "all7":
            all_7,
        "expectedCoveredWinners":
            expected,
        "assumption":
            "cross-leg-independence",
    }


def optimize_budget_system(
    legs: list[
        dict[str, Any]
    ],
    *,
    total_budget_nok: Any,
    row_price_nok: Any,
) -> dict[str, Any]:
    budget = _decimal(
        total_budget_nok
    )

    row_price = _decimal(
        row_price_nok
    )

    max_rows = max_rows_from_budget(
        budget,
        row_price,
    )

    system = optimize_system(
        legs,
        max_rows=max_rows,
    )

    coverage = (
        coverage_distribution(
            system
        )
    )

    old_all7 = float(
        system[
            "estimatedAll7Coverage"
        ]
    )

    if abs(
        coverage["all7"]
        - old_all7
    ) > 1e-10:
        raise AssertionError(
            "V2 P(7) differs from "
            "existing V1 objective"
        )

    actual_rows = int(
        system["actualRows"]
    )

    actual_cost = (
        row_price
        * actual_rows
    )

    unused = (
        budget
        - actual_cost
    )

    if unused < 0:
        raise AssertionError(
            "Actual system exceeds budget"
        )

    return {
        "budgetNok":
            float(budget),
        "rowPriceNok":
            float(row_price),
        "maxRowsFromBudget":
            max_rows,
        "actualRows":
            actual_rows,
        "actualCostNok":
            float(actual_cost),
        "unusedBudgetNok":
            float(unused),
        "estimatedCoverage":
            coverage,
        "estimatedAll7Coverage":
            old_all7,
        "legs":
            system["legs"],
    }


def optimize_budget_frontier(
    legs: list[
        dict[str, Any]
    ],
    *,
    budgets_nok: list[Any],
    row_price_nok: Any,
) -> dict[str, Any]:
    if not budgets_nok:
        raise ValueError(
            "budgets_nok must not be empty"
        )

    unique_budgets = sorted(
        {
            _decimal(value)
            for value in budgets_nok
        }
    )

    points = []

    previous = None

    for budget in unique_budgets:
        point = (
            optimize_budget_system(
                legs,
                total_budget_nok=budget,
                row_price_nok=
                    row_price_nok,
            )
        )

        marginal = None

        if previous is not None:
            budget_delta = (
                point["budgetNok"]
                - previous[
                    "budgetNok"
                ]
            )

            cost_delta = (
                point["actualCostNok"]
                - previous[
                    "actualCostNok"
                ]
            )

            p5_delta = (
                point[
                    "estimatedCoverage"
                ][
                    "atLeast5"
                ]
                - previous[
                    "estimatedCoverage"
                ][
                    "atLeast5"
                ]
            )

            p6_delta = (
                point[
                    "estimatedCoverage"
                ][
                    "atLeast6"
                ]
                - previous[
                    "estimatedCoverage"
                ][
                    "atLeast6"
                ]
            )

            p7_delta = (
                point[
                    "estimatedCoverage"
                ][
                    "all7"
                ]
                - previous[
                    "estimatedCoverage"
                ][
                    "all7"
                ]
            )

            marginal = {
                "additionalBudgetNok":
                    budget_delta,
                "additionalActualCostNok":
                    cost_delta,
                "deltaAtLeast5":
                    p5_delta,
                "deltaAtLeast6":
                    p6_delta,
                "deltaAll7":
                    p7_delta,
                "deltaAll7Per100NokActualCost":
                    (
                        p7_delta
                        * 100.0
                        / cost_delta
                        if cost_delta > 0
                        else None
                    ),
            }

        point[
            "marginalFromPrevious"
        ] = marginal

        points.append(
            point
        )

        previous = point

    return {
        "schemaVersion":
            "2.0",
        "systemModel":
            "v75-system-optimizer-v2-budget-frontier",
        "objective":
            "maximize-estimated-all7-coverage",
        "rowPriceNok":
            float(
                _decimal(
                    row_price_nok
                )
            ),
        "points":
            points,
        "probabilitySemantics": {
            "atLeast5":
                "winning horse included in at least 5 of 7 legs",
            "atLeast6":
                "winning horse included in at least 6 of 7 legs",
            "all7":
                "winning horse included in all 7 legs",
            "warning":
                (
                    "Model-estimated probabilities, "
                    "not guaranteed real-world odds."
                ),
        },
    }
