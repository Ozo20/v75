from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--predictions",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--outcomes",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    predictions = load(
        args.predictions
    )

    outcomes = load(
        args.outcomes
    )

    if (
        predictions["raceDayKey"]
        != outcomes["raceDayKey"]
    ):
        raise ValueError(
            "Prediction/outcome "
            "race-day mismatch"
        )

    outcome_by_leg = {
        leg["leg"]: leg
        for leg in outcomes["legs"]
    }

    top1_hits = 0
    top2_hits = 0
    top3_hits = 0

    random_top3_expected = 0.0

    print(
        "=== BASELINE V1 "
        "BACKTEST ==="
    )

    print(
        f"{predictions['raceDayName']} "
        f"{predictions['raceDate']}"
    )

    print()

    print(
        f"{'Leg':<7}"
        f"{'Winner':<10}"
        f"{'Model':<10}"
        f"{'Market':<10}"
        f"{'Top 3'}"
    )

    print("-" * 55)

    for leg in predictions["legs"]:
        outcome = outcome_by_leg[
            leg["leg"]
        ]

        winner = outcome[
            "winnerStartNumber"
        ]

        winner_rank = next(
            item["rank"]
            for item
            in leg["rankings"]
            if item["startNumber"]
            == winner
        )

        market_rank = outcome.get(
            "winnerV75MarketRank"
        )

        top3 = leg[
            "top3StartNumbers"
        ]

        top1_hits += (
            winner_rank <= 1
        )

        top2_hits += (
            winner_rank <= 2
        )

        top3_hits += (
            winner_rank <= 3
        )

        field_size = leg[
            "fieldSizeEligible"
        ]

        random_top3_expected += (
            min(3, field_size)
            / field_size
        )

        print(
            f"V75-{leg['leg']:<2}"
            f" #{winner:<8}"
            f" #{winner_rank:<8}"
            f" {str(market_rank):<9}"
            f" {', '.join(map(str, top3))}"
        )

    legs_count = len(
        predictions["legs"]
    )

    print()

    print(
        f"Top-1 hits: "
        f"{top1_hits}/{legs_count} "
        f"({100 * top1_hits / legs_count:.1f}%)"
    )

    print(
        f"Top-2 hits: "
        f"{top2_hits}/{legs_count} "
        f"({100 * top2_hits / legs_count:.1f}%)"
    )

    print(
        f"Top-3 hits: "
        f"{top3_hits}/{legs_count} "
        f"({100 * top3_hits / legs_count:.1f}%)"
    )

    print(
        "Random top-3 expectation "
        f"for these field sizes: "
        f"{random_top3_expected:.2f} "
        f"hits of {legs_count}"
    )

    print()
    print(
        "NOTE: one meeting is not "
        "statistically meaningful."
    )


if __name__ == "__main__":
    main()
