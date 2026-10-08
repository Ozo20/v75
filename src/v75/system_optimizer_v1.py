from __future__ import annotations

import math
from typing import Any


BETA = 2.872


def softmax_probabilities(
    scores: list[float],
) -> list[float]:
    scaled = [
        BETA * score
        for score in scores
    ]

    maximum = max(scaled)

    values = [
        math.exp(
            value - maximum
        )
        for value in scaled
    ]

    denominator = sum(values)

    return [
        value / denominator
        for value in values
    ]


def leg_options(
    rankings: list[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    ordered = sorted(
        rankings,
        key=lambda row: (
            int(row["rank"])
        ),
    )

    probs = softmax_probabilities(
        [
            float(row["score"])
            for row in ordered
        ]
    )

    cumulative = 0.0
    options = []

    for k, probability in enumerate(
        probs,
        1,
    ):
        cumulative += probability

        options.append(
            {
                "k": k,
                "mass": cumulative,
                "selectedStartNumbers": [
                    int(
                        row["startNumber"]
                    )
                    for row
                    in ordered[:k]
                ],
            }
        )

    return options


def optimize_system(
    legs: list[
        dict[str, Any]
    ],
    *,
    max_rows: int,
) -> dict[str, Any]:
    """
    Maximise estimated probability that all
    seven winners are covered, subject to
    product(k_leg) <= max_rows.

    Objective:
        maximise product(probability mass)

    Equivalent numerical objective:
        maximise sum(log(probability mass)).
    """

    if max_rows < 1:
        raise ValueError(
            "max_rows must be >= 1"
        )

    all_options = [
        leg_options(
            leg["rankings"]
        )
        for leg in legs
    ]

    # rows -> (log_probability, choices)
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
                    * option["k"]
                )

                if new_rows > max_rows:
                    continue

                new_logp = (
                    existing_logp
                    + math.log(
                        max(
                            option["mass"],
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
                "No feasible system state"
            )

        # Pareto prune:
        # if a cheaper state already has
        # equal or greater probability,
        # the more expensive state is useless.
        pruned = {}

        best_logp = (
            -math.inf
        )

        for rows in sorted(
            next_states
        ):
            logp, choices = (
                next_states[rows]
            )

            if logp > (
                best_logp + 1e-15
            ):
                pruned[rows] = (
                    logp,
                    choices,
                )

                best_logp = logp

        states = pruned

    best_rows, (
        best_logp,
        best_choices,
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
                    legs[i]["leg"],
                "k":
                    choice["k"],
                "probabilityMass":
                    choice["mass"],
                "selectedStartNumbers":
                    choice[
                        "selectedStartNumbers"
                    ],
            }
            for i, choice
            in enumerate(
                best_choices
            )
        ],
    }
