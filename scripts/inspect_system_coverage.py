from __future__ import annotations

import argparse
import json
from collections import Counter
from math import prod
from pathlib import Path
from statistics import mean


PREDICTION_FILE = (
    "baseline-safe-v1-predictions.json"
)


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def main() -> None:
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

    args = parser.parse_args()

    all_winner_ranks: list[int] = []
    rank_histogram = Counter()

    race_coverage = {
        k: 0
        for k in range(1, 6)
    }

    meeting_coverage = {
        k: 0
        for k in range(1, 6)
    }

    uniform_rows = {
        k: []
        for k in range(1, 6)
    }

    oracle_rows = []

    print(
        "=== V75 SYSTEM COVERAGE DIAGNOSTIC ==="
    )
    print(
        "Model: baseline-safe-v1"
    )
    print()

    for date in args.dates:
        base = args.root / date

        predictions = load(
            base / PREDICTION_FILE
        )

        outcomes = load(
            base / "outcomes.json"
        )

        outcome_by_leg = {
            leg["leg"]: leg
            for leg
            in outcomes["legs"]
        }

        winner_ranks = []
        field_sizes = []

        for leg in predictions["legs"]:
            outcome = outcome_by_leg[
                leg["leg"]
            ]

            winner = outcome[
                "winnerStartNumber"
            ]

            winner_rows = [
                row
                for row
                in leg["rankings"]
                if row["startNumber"]
                == winner
            ]

            if len(winner_rows) != 1:
                raise ValueError(
                    f"Winner missing: "
                    f"{date} "
                    f"V75-{leg['leg']} "
                    f"#{winner}"
                )

            rank = int(
                winner_rows[0]["rank"]
            )

            winner_ranks.append(
                rank
            )

            field_sizes.append(
                int(
                    leg[
                        "fieldSizeEligible"
                    ]
                )
            )

            all_winner_ranks.append(
                rank
            )

            rank_histogram[
                rank
            ] += 1

            for k in range(1, 6):
                race_coverage[k] += int(
                    rank <= k
                )

        for k in range(1, 6):
            meeting_coverage[k] += int(
                all(
                    rank <= k
                    for rank
                    in winner_ranks
                )
            )

            rows = prod(
                min(k, size)
                for size
                in field_sizes
            )

            uniform_rows[k].append(
                rows
            )

        # Diagnostic only:
        # theoretical minimum rows if we
        # magically knew exactly how deep
        # we needed to cover each leg.
        oracle = prod(
            winner_ranks
        )

        oracle_rows.append(
            oracle
        )

        print(
            f"{date} "
            f"{predictions['raceDayName']:<14} "
            f"winner ranks="
            f"{winner_ranks} "
            f"max={max(winner_ranks)} "
            f"oracleRows={oracle}"
        )

    races = len(
        all_winner_ranks
    )

    meetings = len(
        args.dates
    )

    print()
    print(
        "=== RACE-LEVEL COVERAGE ==="
    )

    for k in range(1, 6):
        hits = race_coverage[k]

        print(
            f"Top-{k}: "
            f"{hits}/{races} "
            f"({100 * hits / races:.1f}%)"
        )

    print()
    print(
        "=== COMPLETE 7/7 MEETING COVERAGE ==="
    )

    for k in range(1, 6):
        hits = meeting_coverage[k]

        print(
            f"Take Top-{k} in every leg: "
            f"{hits}/{meetings} meetings"
        )

    print()
    print(
        "=== UNIFORM SYSTEM SIZE ==="
    )

    for k in range(1, 6):
        values = uniform_rows[k]

        print(
            f"Top-{k} every leg: "
            f"min={min(values)} "
            f"max={max(values)} "
            f"avg={mean(values):.1f} rows"
        )

    print()
    print(
        "=== WINNER-RANK DISTRIBUTION ==="
    )

    cumulative = 0

    for rank in sorted(
        rank_histogram
    ):
        count = rank_histogram[
            rank
        ]

        cumulative += count

        print(
            f"Rank {rank:>2}: "
            f"{count:>2} races | "
            f"cumulative "
            f"{cumulative}/{races} "
            f"({100 * cumulative / races:.1f}%)"
        )

    print()
    print(
        f"Average winner rank: "
        f"{mean(all_winner_ranks):.2f}"
    )

    print(
        f"Average diagnostic oracle rows: "
        f"{mean(oracle_rows):.1f}"
    )

    print()
    print(
        "NOTE: oracleRows is NOT a playable "
        "strategy. It only describes how deep "
        "the model would have needed to cover "
        "each race after the fact."
    )


if __name__ == "__main__":
    main()
