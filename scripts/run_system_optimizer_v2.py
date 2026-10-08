from __future__ import annotations

import argparse
import json
from pathlib import Path

from v75.system_optimizer_v2 import (
    optimize_budget_frontier,
)


def load(
    path: Path,
):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
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
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    prediction = load(
        args.predictions
    )

    legs = prediction[
        "legs"
    ]

    if len(legs) != 7:
        raise ValueError(
            "V75 requires exactly 7 legs"
        )

    frontier = (
        optimize_budget_frontier(
            legs,
            budgets_nok=
                args.budgets_nok,
            row_price_nok=
                args.row_price_nok,
        )
    )

    output = {
        **frontier,
        "horseModel":
            prediction.get(
                "model",
                "unknown",
            ),
        "raceDate":
            prediction.get(
                "raceDate"
            ),
        "raceDayKey":
            prediction.get(
                "raceDayKey"
            ),
        "raceDayName":
            prediction.get(
                "raceDayName"
            ),
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "=== V75 SYSTEM OPTIMIZER V2 "
        "— BUDGET FRONTIER ==="
    )

    print(
        "Horse model:",
        output["horseModel"],
    )

    print(
        "Row price:",
        f"{args.row_price_nok:.2f} NOK",
    )

    print()

    for point in output[
        "points"
    ]:
        coverage = point[
            "estimatedCoverage"
        ]

        ks = [
            leg["k"]
            for leg in point[
                "legs"
            ]
        ]

        print(
            f"Budget "
            f"{point['budgetNok']:7.2f} NOK "
            f"| cost "
            f"{point['actualCostNok']:7.2f} "
            f"| rows "
            f"{point['actualRows']:>6} "
            f"| k={ks} "
            f"| P5+="
            f"{100*coverage['atLeast5']:6.2f}% "
            f"| P6+="
            f"{100*coverage['atLeast6']:6.2f}% "
            f"| P7="
            f"{100*coverage['all7']:6.2f}% "
            f"| E[hits]="
            f"{coverage['expectedCoveredWinners']:.2f}"
        )

        marginal = point[
            "marginalFromPrevious"
        ]

        if (
            marginal
            and marginal[
                "additionalActualCostNok"
            ] > 0
        ):
            print(
                " " * 9
                + "marginal: "
                + f"+{100*marginal['deltaAll7']:.3f} "
                + "percentage points P7 "
                + "for "
                + f"{marginal['additionalActualCostNok']:.2f} NOK "
                + "extra actual spend"
            )

    print()

    print(
        "Report:",
        args.output,
    )


if __name__ == "__main__":
    main()
