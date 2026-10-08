from __future__ import annotations

import math
from typing import Any

from v75.system_optimizer_v1 import (
    leg_options,
    optimize_system,
)
from v75.system_optimizer_v2 import (
    coverage_distribution,
    max_rows_from_budget,
)


def optimize_system_constrained(
    legs: list[dict[str, Any]],
    *,
    max_rows: int,
    min_k_by_leg: dict[int, int] | None = None,
) -> dict[str, Any]:
    """
    Same objective as System Optimizer v1:

        maximise estimated P(all 7 winners covered)

    but optionally require a minimum number
    of selected horses in individual legs.
    """

    if max_rows < 1:
        raise ValueError(
            "max_rows must be >= 1"
        )

    minimums = (
        min_k_by_leg
        or {}
    )

    all_options = []

    for leg in legs:
        leg_number = int(
            leg["leg"]
        )

        options = leg_options(
            leg["rankings"]
        )

        requested_min = int(
            minimums.get(
                leg_number,
                1,
            )
        )

        if requested_min < 1:
            raise ValueError(
                "Minimum k must be >= 1"
            )

        filtered = [
            option
            for option in options
            if int(
                option["k"]
            ) >= requested_min
        ]

        if not filtered:
            raise ValueError(
                f"No legal options for leg "
                f"{leg_number} with min k="
                f"{requested_min}"
            )

        all_options.append(
            filtered
        )

    states = {
        1: (
            0.0,
            [],
        )
    }

    for options in all_options:
        next_states = {}

        for (
            existing_rows,
            (
                existing_logp,
                existing_choices,
            ),
        ) in states.items():

            for option in options:
                new_rows = (
                    existing_rows
                    * int(
                        option["k"]
                    )
                )

                if new_rows > max_rows:
                    continue

                new_logp = (
                    existing_logp
                    + math.log(
                        max(
                            float(
                                option[
                                    "mass"
                                ]
                            ),
                            1e-15,
                        )
                    )
                )

                candidate = (
                    new_logp,
                    existing_choices
                    + [option],
                )

                previous = (
                    next_states.get(
                        new_rows
                    )
                )

                if (
                    previous is None
                    or new_logp
                    > previous[0]
                ):
                    next_states[
                        new_rows
                    ] = candidate

        if not next_states:
            raise RuntimeError(
                "No feasible constrained "
                "system state"
            )

        pruned = {}
        best_logp = -math.inf

        for rows in sorted(
            next_states
        ):
            (
                logp,
                choices,
            ) = next_states[
                rows
            ]

            if logp > (
                best_logp
                + 1e-15
            ):
                pruned[
                    rows
                ] = (
                    logp,
                    choices,
                )

                best_logp = logp

        states = pruned

    (
        best_rows,
        (
            best_logp,
            best_choices,
        ),
    ) = max(
        states.items(),
        key=lambda item: (
            item[1][0],
            -item[0],
        ),
    )

    return {
        "maxRows":
            max_rows,
        "actualRows":
            best_rows,
        "estimatedAll7Coverage":
            math.exp(
                best_logp
            ),
        "legs": [
            {
                "leg":
                    int(
                        legs[index][
                            "leg"
                        ]
                    ),
                "k":
                    int(
                        choice[
                            "k"
                        ]
                    ),
                "probabilityMass":
                    float(
                        choice[
                            "mass"
                        ]
                    ),
                "selectedStartNumbers":
                    [
                        int(value)
                        for value
                        in choice[
                            "selectedStartNumbers"
                        ]
                    ],
            }
            for index, choice
            in enumerate(
                best_choices
            )
        ],
    }


def build_risk_profiles(
    legs: list[dict[str, Any]],
    *,
    total_budget_nok: float,
    row_price_nok: float,
    min_banker_probability: float = 0.35,
) -> dict[str, Any]:
    if not (
        0.0
        <= min_banker_probability
        <= 1.0
    ):
        raise ValueError(
            "min_banker_probability must "
            "be between 0 and 1"
        )

    max_rows = max_rows_from_budget(
        total_budget_nok,
        row_price_nok,
    )

    # Existing optimizer result is canonical
    # MAX P7 reference.
    max_p7 = optimize_system(
        legs,
        max_rows=max_rows,
    )

    weak_banker_minimums = {}
    no_banker_minimums = {}

    top_probabilities = {}

    for leg in legs:
        leg_number = int(
            leg["leg"]
        )

        options = leg_options(
            leg["rankings"]
        )

        top_probability = float(
            options[0][
                "mass"
            ]
        )

        top_probabilities[
            leg_number
        ] = top_probability

        field_size = len(
            options
        )

        if (
            field_size >= 2
            and top_probability
            < min_banker_probability
        ):
            weak_banker_minimums[
                leg_number
            ] = 2

        if field_size >= 2:
            no_banker_minimums[
                leg_number
            ] = 2

    no_weak = (
        optimize_system_constrained(
            legs,
            max_rows=max_rows,
            min_k_by_leg=
                weak_banker_minimums,
        )
    )

    no_banker = (
        optimize_system_constrained(
            legs,
            max_rows=max_rows,
            min_k_by_leg=
                no_banker_minimums,
        )
    )

    systems = [
        (
            "MAX_P7",
            max_p7,
            {},
        ),
        (
            "NO_WEAK_BANKER",
            no_weak,
            weak_banker_minimums,
        ),
        (
            "NO_BANKER",
            no_banker,
            no_banker_minimums,
        ),
    ]

    profiles = []

    for (
        name,
        system,
        minimums,
    ) in systems:
        coverage = (
            coverage_distribution(
                system
            )
        )

        cost = (
            int(
                system[
                    "actualRows"
                ]
            )
            * float(
                row_price_nok
            )
        )

        profiles.append(
            {
                "profile":
                    name,
                "maxRows":
                    max_rows,
                "actualRows":
                    int(
                        system[
                            "actualRows"
                        ]
                    ),
                "actualCostNok":
                    cost,
                "unusedBudgetNok":
                    float(
                        total_budget_nok
                    )
                    - cost,
                "estimatedCoverage":
                    coverage,
                "estimatedAll7Coverage":
                    float(
                        system[
                            "estimatedAll7Coverage"
                        ]
                    ),
                "minimumSelections":
                    {
                        str(key):
                            value
                        for key, value
                        in minimums.items()
                    },
                "legs":
                    system["legs"],
            }
        )

    return {
        "schemaVersion":
            "3.0",
        "systemModel":
            "v75-system-risk-profiles-v3",
        "objective":
            "maximize-estimated-all7-coverage",
        "budgetNok":
            float(
                total_budget_nok
            ),
        "rowPriceNok":
            float(
                row_price_nok
            ),
        "maxRows":
            max_rows,
        "minBankerProbability":
            min_banker_probability,
        "topProbabilitiesByLeg":
            {
                str(key):
                    value
                for key, value
                in top_probabilities.items()
            },
        "profiles":
            profiles,
        "semantics": {
            "MAX_P7":
                (
                    "No banker restriction; "
                    "pure mathematical optimum."
                ),
            "NO_WEAK_BANKER":
                (
                    "A leg cannot be banked if "
                    "the model probability for "
                    "its top horse is below the "
                    "configured threshold."
                ),
            "NO_BANKER":
                (
                    "At least two horses are "
                    "selected in every leg with "
                    "two or more eligible horses."
                ),
        },
    }
