from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any


PREDICTION_FILE = (
    "candidate-v2a-speed-predictions.json"
)


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def race_cases(
    root: Path,
    dates: list[str],
):
    cases = []

    for date in dates:
        base = root / date

        prediction = load(
            base / PREDICTION_FILE
        )

        outcomes = load(
            base / "outcomes.json"
        )

        outcome_by_leg = {
            row["leg"]: row
            for row
            in outcomes["legs"]
        }

        for leg in prediction["legs"]:
            winner = int(
                outcome_by_leg[
                    leg["leg"]
                ]["winnerStartNumber"]
            )

            rows = sorted(
                leg["rankings"],
                key=lambda row: (
                    -float(row["score"]),
                    int(row["startNumber"]),
                ),
            )

            scores = [
                float(row["score"])
                for row in rows
            ]

            starts = [
                int(row["startNumber"])
                for row in rows
            ]

            winner_index = (
                starts.index(winner)
            )

            cases.append(
                {
                    "date": date,
                    "leg": leg["leg"],
                    "scores": scores,
                    "winnerIndex":
                        winner_index,
                }
            )

    return cases


def probabilities(
    scores: list[float],
    beta: float,
):
    scaled = [
        beta * score
        for score in scores
    ]

    maximum = max(scaled)

    exp_values = [
        math.exp(
            value - maximum
        )
        for value in scaled
    ]

    denominator = sum(
        exp_values
    )

    return [
        value / denominator
        for value in exp_values
    ]


def nll(
    cases,
    beta: float,
):
    losses = []

    for case in cases:
        probs = probabilities(
            case["scores"],
            beta,
        )

        winner_probability = max(
            probs[
                case["winnerIndex"]
            ],
            1e-15,
        )

        losses.append(
            -math.log(
                winner_probability
            )
        )

    return mean(losses)


def fit_beta(cases):
    """
    Deterministic one-dimensional search.

    beta >= 0 preserves V2A ordering.
    beta=0 is uniform probability.

    Coarse grid followed by fine grid.
    """

    coarse = [
        i * 0.05
        for i in range(
            0,
            801,
        )
    ]

    coarse_scores = [
        (
            nll(cases, beta),
            beta,
        )
        for beta in coarse
    ]

    _, coarse_best = min(
        coarse_scores
    )

    lower = max(
        0.0,
        coarse_best - 0.10,
    )

    upper = (
        coarse_best + 0.10
    )

    fine = [
        lower + i * 0.001
        for i in range(
            int(
                round(
                    (upper - lower)
                    / 0.001
                )
            )
            + 1
        )
    ]

    fine_scores = [
        (
            nll(cases, beta),
            beta,
        )
        for beta in fine
    ]

    best_loss, best_beta = min(
        fine_scores
    )

    if best_beta >= 39.9:
        raise RuntimeError(
            "Calibration optimum is at "
            "search boundary; expand search."
        )

    return (
        best_beta,
        best_loss,
    )


def metrics(
    cases,
    beta: float,
):
    log_losses = []
    briers = []

    winner_probabilities = []

    cumulative_probability = {
        1: [],
        2: [],
        3: [],
        5: [],
    }

    coverage = {
        1: [],
        2: [],
        3: [],
        5: [],
    }

    top1_probabilities = []
    top1_hits = []

    for case in cases:
        probs = probabilities(
            case["scores"],
            beta,
        )

        winner_index = (
            case["winnerIndex"]
        )

        winner_probability = max(
            probs[winner_index],
            1e-15,
        )

        winner_probabilities.append(
            winner_probability
        )

        log_losses.append(
            -math.log(
                winner_probability
            )
        )

        race_brier = 0.0

        for i, probability in enumerate(
            probs
        ):
            actual = (
                1.0
                if i == winner_index
                else 0.0
            )

            race_brier += (
                probability - actual
            ) ** 2

        briers.append(
            race_brier
        )

        top1_probabilities.append(
            probs[0]
        )

        top1_hits.append(
            int(
                winner_index == 0
            )
        )

        for k in (
            1,
            2,
            3,
            5,
        ):
            actual_k = min(
                k,
                len(probs),
            )

            cumulative_probability[
                k
            ].append(
                sum(
                    probs[
                        :actual_k
                    ]
                )
            )

            coverage[
                k
            ].append(
                int(
                    winner_index
                    < actual_k
                )
            )

    result = {
        "races":
            len(cases),
        "beta":
            beta,
        "meanLogLoss":
            mean(
                log_losses
            ),
        "meanRaceBrier":
            mean(
                briers
            ),
        "meanWinnerProbability":
            mean(
                winner_probabilities
            ),
        "top1": {
            "meanPredictedProbability":
                mean(
                    top1_probabilities
                ),
            "observedHitRate":
                mean(
                    top1_hits
                ),
        },
    }

    result[
        "cumulativeCoverage"
    ] = {}

    for k in (
        1,
        2,
        3,
        5,
    ):
        predicted = mean(
            cumulative_probability[k]
        )

        actual = mean(
            coverage[k]
        )

        result[
            "cumulativeCoverage"
        ][str(k)] = {
            "meanPredictedMass":
                predicted,
            "observedCoverage":
                actual,
            "gap":
                predicted - actual,
        }

    return result


def uniform_metrics(cases):
    log_losses = []
    briers = []

    for case in cases:
        n = len(
            case["scores"]
        )

        p = 1.0 / n

        log_losses.append(
            -math.log(p)
        )

        # One winner and n-1 losers.
        race_brier = (
            (p - 1.0) ** 2
            + (n - 1)
            * (p ** 2)
        )

        briers.append(
            race_brier
        )

    return {
        "meanLogLoss":
            mean(log_losses),
        "meanRaceBrier":
            mean(briers),
    }


def print_metrics(
    title,
    result,
    uniform,
):
    print(
        f"=== {title} ==="
    )

    print(
        f"Races:               "
        f"{result['races']}"
    )

    print(
        f"Beta:                "
        f"{result['beta']:.3f}"
    )

    print(
        f"Mean log loss:       "
        f"{result['meanLogLoss']:.4f}"
    )

    print(
        f"Uniform log loss:    "
        f"{uniform['meanLogLoss']:.4f}"
    )

    print(
        f"Mean race Brier:     "
        f"{result['meanRaceBrier']:.4f}"
    )

    print(
        f"Uniform race Brier:  "
        f"{uniform['meanRaceBrier']:.4f}"
    )

    print()

    print(
        "Probability mass vs "
        "observed winner coverage:"
    )

    for k in (
        1,
        2,
        3,
        5,
    ):
        row = (
            result[
                "cumulativeCoverage"
            ][str(k)]
        )

        print(
            f"Top-{k}: "
            f"predicted="
            f"{100 * row['meanPredictedMass']:5.1f}% "
            f"observed="
            f"{100 * row['observedCoverage']:5.1f}% "
            f"gap="
            f"{100 * row['gap']:+5.1f} pp"
        )

    print()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--train-dates",
        nargs="+",
        required=True,
    )

    parser.add_argument(
        "--test-dates",
        nargs="+",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    train = race_cases(
        args.root,
        args.train_dates,
    )

    test = race_cases(
        args.root,
        args.test_dates,
    )

    beta, train_loss = (
        fit_beta(train)
    )

    train_result = metrics(
        train,
        beta,
    )

    test_result = metrics(
        test,
        beta,
    )

    train_uniform = (
        uniform_metrics(
            train
        )
    )

    test_uniform = (
        uniform_metrics(
            test
        )
    )

    print(
        "=== V2A PROBABILITY "
        "CALIBRATION ==="
    )

    print(
        "Fit: development only"
    )

    print(
        "Test: independent "
        "robustness only"
    )

    print(
        "Ranking weights: unchanged"
    )

    print()

    print(
        f"Fitted beta: "
        f"{beta:.3f}"
    )

    print(
        f"Training optimum NLL: "
        f"{train_loss:.4f}"
    )

    print()

    print_metrics(
        "DEVELOPMENT / FIT",
        train_result,
        train_uniform,
    )

    print_metrics(
        "INDEPENDENT ROBUSTNESS",
        test_result,
        test_uniform,
    )

    report = {
        "schemaVersion":
            "1.0",
        "model":
            "candidate-v2a-speed",
        "calibration":
            "softmax-single-beta",
        "rankingChanged":
            False,
        "fitScope":
            "development-only",
        "testScope":
            "independent-robustness",
        "trainDates":
            args.train_dates,
        "testDates":
            args.test_dates,
        "beta":
            beta,
        "development":
            train_result,
        "developmentUniform":
            train_uniform,
        "robustness":
            test_result,
        "robustnessUniform":
            test_uniform,
        "guardrails": {
            "validationDatesUsed":
                False,
            "priorHoldoutDatesUsed":
                False,
            "marketUsed":
                False,
            "v2aWeightsChanged":
                False,
        },
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

    print(
        f"Report: {args.output}"
    )


if __name__ == "__main__":
    main()
