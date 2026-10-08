from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def evaluate(
    prediction_file: str,
    root: Path,
    dates: list[str],
):
    ranks = []

    for date in dates:
        base = root / date

        predictions = load(
            base / prediction_file
        )

        outcomes = load(
            base / "outcomes.json"
        )

        outcome_by_leg = {
            row["leg"]: row
            for row
            in outcomes["legs"]
        }

        for leg in predictions[
            "legs"
        ]:
            winner = outcome_by_leg[
                leg["leg"]
            ]["winnerStartNumber"]

            match = [
                row
                for row
                in leg["rankings"]
                if row["startNumber"]
                == winner
            ]

            assert len(match) == 1

            ranks.append(
                int(
                    match[0]["rank"]
                )
            )

    total = len(ranks)

    return {
        "top1":
            sum(
                rank <= 1
                for rank in ranks
            ),
        "top2":
            sum(
                rank <= 2
                for rank in ranks
            ),
        "top3":
            sum(
                rank <= 3
                for rank in ranks
            ),
        "top5":
            sum(
                rank <= 5
                for rank in ranks
            ),
        "averageWinnerRank":
            mean(ranks),
        "races":
            total,
    }


def print_result(
    name,
    result,
):
    total = result[
        "races"
    ]

    print(
        f"{name:<20} "
        f"T1={result['top1']:>2}/{total} "
        f"({100 * result['top1'] / total:5.1f}%) "
        f"T2={result['top2']:>2}/{total} "
        f"({100 * result['top2'] / total:5.1f}%) "
        f"T3={result['top3']:>2}/{total} "
        f"({100 * result['top3'] / total:5.1f}%) "
        f"T5={result['top5']:>2}/{total} "
        f"({100 * result['top5'] / total:5.1f}%) "
        f"avgRank="
        f"{result['averageWinnerRank']:.2f}"
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

    safe = evaluate(
        "baseline-safe-v1-predictions.json",
        args.root,
        args.dates,
    )

    candidate = evaluate(
        "candidate-v2a-speed-predictions.json",
        args.root,
        args.dates,
    )

    print(
        "=== LOCKED VALIDATION ==="
    )
    print()

    print_result(
        "baseline-safe-v1",
        safe,
    )

    print_result(
        "candidate-v2a-speed",
        candidate,
    )

    print()
    print(
        "Delta candidate - baseline:"
    )

    print(
        f"Top-1: "
        f"{candidate['top1'] - safe['top1']:+d}"
    )

    print(
        f"Top-2: "
        f"{candidate['top2'] - safe['top2']:+d}"
    )

    print(
        f"Top-3: "
        f"{candidate['top3'] - safe['top3']:+d}"
    )

    print(
        f"Top-5: "
        f"{candidate['top5'] - safe['top5']:+d}"
    )

    print(
        f"Average rank: "
        f"{candidate['averageWinnerRank'] - safe['averageWinnerRank']:+.2f}"
    )

    report = {
        "scope":
            "locked-validation",
        "dates":
            args.dates,
        "baseline":
            safe,
        "candidate":
            candidate,
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


if __name__ == "__main__":
    main()
