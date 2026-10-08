from __future__ import annotations

import argparse
import json
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

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    total_legs = 0

    model_top1 = 0
    model_top2 = 0
    model_top3 = 0

    market_available = 0
    market_top1 = 0
    market_top2 = 0
    market_top3 = 0

    model_ranks = []
    market_ranks = []

    random_top3_expected = 0.0

    print(
        "=== BASELINE SAFE V1 "
        "AGGREGATE BACKTEST ==="
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

        if (
            predictions["model"]
            != "baseline-safe-v1"
        ):
            raise ValueError(
                "Unexpected model"
            )

        if (
            predictions[
                "raceDayKey"
            ]
            != outcomes[
                "raceDayKey"
            ]
        ):
            raise ValueError(
                f"Race-day mismatch "
                f"{date}"
            )

        outcome_by_leg = {
            row["leg"]: row
            for row
            in outcomes[
                "legs"
            ]
        }

        meeting_top1 = 0
        meeting_top2 = 0
        meeting_top3 = 0

        meeting_ranks = []

        for leg in predictions[
            "legs"
        ]:
            outcome = (
                outcome_by_leg[
                    leg["leg"]
                ]
            )

            winner = outcome[
                "winnerStartNumber"
            ]

            rows = [
                row
                for row
                in leg[
                    "rankings"
                ]
                if row[
                    "startNumber"
                ]
                == winner
            ]

            if len(rows) != 1:
                raise ValueError(
                    f"Winner missing: "
                    f"{date} "
                    f"V75-{leg['leg']} "
                    f"#{winner}"
                )

            rank = rows[0][
                "rank"
            ]

            model_ranks.append(
                rank
            )

            meeting_ranks.append(
                rank
            )

            model_top1 += int(
                rank <= 1
            )

            model_top2 += int(
                rank <= 2
            )

            model_top3 += int(
                rank <= 3
            )

            meeting_top1 += int(
                rank <= 1
            )

            meeting_top2 += int(
                rank <= 2
            )

            meeting_top3 += int(
                rank <= 3
            )

            market_rank = (
                outcome.get(
                    "winnerV75MarketRank"
                )
            )

            if market_rank is not None:
                market_rank = int(
                    market_rank
                )

                market_available += 1

                market_ranks.append(
                    market_rank
                )

                market_top1 += int(
                    market_rank <= 1
                )

                market_top2 += int(
                    market_rank <= 2
                )

                market_top3 += int(
                    market_rank <= 3
                )

            size = leg[
                "fieldSizeEligible"
            ]

            random_top3_expected += (
                min(3, size)
                / size
            )

            total_legs += 1

        print(
            f"{date} "
            f"{predictions['raceDayName']:<14} "
            f"T1={meeting_top1}/7 "
            f"T2={meeting_top2}/7 "
            f"T3={meeting_top3}/7 "
            f"avgRank="
            f"{mean(meeting_ranks):.2f}"
        )

    print()
    print("--- OVERALL ---")

    print(
        f"Meetings:         "
        f"{len(args.dates)}"
    )

    print(
        f"V75 legs:         "
        f"{total_legs}"
    )

    print(
        f"Model Top-1:      "
        f"{model_top1}/"
        f"{total_legs} "
        f"({100 * model_top1 / total_legs:.1f}%)"
    )

    print(
        f"Model Top-2:      "
        f"{model_top2}/"
        f"{total_legs} "
        f"({100 * model_top2 / total_legs:.1f}%)"
    )

    print(
        f"Model Top-3:      "
        f"{model_top3}/"
        f"{total_legs} "
        f"({100 * model_top3 / total_legs:.1f}%)"
    )

    print(
        f"Average winner "
        f"rank:            "
        f"{mean(model_ranks):.2f}"
    )

    print(
        f"Random Top-3 "
        f"expected:        "
        f"{random_top3_expected:.2f}/"
        f"{total_legs}"
    )

    print()

    print(
        f"Market Top-1:     "
        f"{market_top1}/"
        f"{market_available} "
        f"({100 * market_top1 / market_available:.1f}%)"
    )

    print(
        f"Market Top-2:     "
        f"{market_top2}/"
        f"{market_available} "
        f"({100 * market_top2 / market_available:.1f}%)"
    )

    print(
        f"Market Top-3:     "
        f"{market_top3}/"
        f"{market_available} "
        f"({100 * market_top3 / market_available:.1f}%)"
    )

    print(
        f"Market avg winner "
        f"rank:           "
        f"{mean(market_ranks):.2f}"
    )

    result = {
        "schemaVersion":
            "1.0",
        "model":
            "baseline-safe-v1",
        "meetings":
            len(args.dates),
        "legs":
            total_legs,
        "modelMetrics": {
            "top1Hits":
                model_top1,
            "top2Hits":
                model_top2,
            "top3Hits":
                model_top3,
            "top1Rate":
                model_top1
                / total_legs,
            "top2Rate":
                model_top2
                / total_legs,
            "top3Rate":
                model_top3
                / total_legs,
            "averageWinnerRank":
                mean(
                    model_ranks
                ),
        },
        "marketMetrics": {
            "available":
                market_available,
            "top1Hits":
                market_top1,
            "top2Hits":
                market_top2,
            "top3Hits":
                market_top3,
            "averageWinnerRank":
                mean(
                    market_ranks
                ),
        },
        "randomTop3ExpectedHits":
            random_top3_expected,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            result,
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
