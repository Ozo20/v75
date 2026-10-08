from __future__ import annotations

import math

from v75.system_optimizer_v2 import (
    coverage_distribution,
    max_rows_from_budget,
    optimize_budget_frontier,
)


assert (
    max_rows_from_budget(
        400,
        1,
    )
    == 400
)

assert (
    max_rows_from_budget(
        400,
        0.5,
    )
    == 800
)

assert (
    max_rows_from_budget(
        400,
        2,
    )
    == 200
)

print(
    "PASS: NOK budget converts "
    "to row ceiling."
)


fake_system = {
    "estimatedAll7Coverage":
        0.5 ** 7,
    "legs": [
        {
            "probabilityMass":
                0.5,
        }
        for _ in range(7)
    ],
}

distribution = (
    coverage_distribution(
        fake_system
    )
)

for correct in range(8):
    expected = (
        math.comb(
            7,
            correct,
        )
        / 128.0
    )

    actual = distribution[
        "exact"
    ][
        str(correct)
    ]

    assert abs(
        actual - expected
    ) < 1e-12

assert abs(
    distribution["atLeast5"]
    - (29 / 128)
) < 1e-12

assert abs(
    distribution["atLeast6"]
    - (8 / 128)
) < 1e-12

assert abs(
    distribution["all7"]
    - (1 / 128)
) < 1e-12

assert abs(
    distribution[
        "expectedCoveredWinners"
    ]
    - 3.5
) < 1e-12

print(
    "PASS: exact 0-7 winner-coverage "
    "distribution verified."
)


legs = []

for leg_number in range(
    1,
    8,
):
    legs.append(
        {
            "leg":
                leg_number,
            "rankings": [
                {
                    "rank":
                        1,
                    "startNumber":
                        1,
                    "score":
                        1.0,
                },
                {
                    "rank":
                        2,
                    "startNumber":
                        2,
                    "score":
                        0.0,
                },
            ],
        }
    )


frontier = optimize_budget_frontier(
    legs,
    budgets_nok=[
        1,
        64,
        128,
        400,
    ],
    row_price_nok=1,
)

points = {
    int(
        point["budgetNok"]
    ):
        point
    for point
    in frontier["points"]
}

assert (
    points[1]["actualRows"]
    == 1
)

assert (
    points[64]["actualRows"]
    == 64
)

assert (
    points[128]["actualRows"]
    == 128
)

# Only 2 horses exist in each leg:
# 2^7 = 128 is the full field.
assert (
    points[400]["actualRows"]
    == 128
)

assert abs(
    points[128][
        "estimatedCoverage"
    ][
        "all7"
    ]
    - 1.0
) < 1e-12

assert abs(
    points[400][
        "estimatedCoverage"
    ][
        "all7"
    ]
    - 1.0
) < 1e-12

assert (
    points[400][
        "unusedBudgetNok"
    ]
    == 272.0
)

for point in frontier[
    "points"
]:
    exact_sum = sum(
        point[
            "estimatedCoverage"
        ][
            "exact"
        ].values()
    )

    assert abs(
        exact_sum - 1.0
    ) < 1e-10

    product = 1

    for leg in point["legs"]:
        product *= int(
            leg["k"]
        )

    assert (
        product
        == point[
            "actualRows"
        ]
    )

print(
    "PASS: budget frontier respects "
    "multiplicative row cost."
)

print(
    "PASS: unused budget is retained "
    "when no better legal system exists."
)

print(
    "PASS: System Optimizer v2 contract."
)
