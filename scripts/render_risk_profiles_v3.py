from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from v75.system_optimizer_v3_profiles import (
    build_risk_profiles,
)


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def horse_name(
    row: dict[str, Any],
) -> str | None:
    for key in (
        "horseName",
        "name",
    ):
        value = row.get(key)

        if (
            isinstance(
                value,
                str,
            )
            and value.strip()
        ):
            return value.strip()

    horse = row.get(
        "horse"
    )

    if isinstance(
        horse,
        dict,
    ):
        value = horse.get(
            "name"
        )

        if (
            isinstance(
                value,
                str,
            )
            and value.strip()
        ):
            return value.strip()

    return None


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--predictions",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--budget-nok",
        required=True,
        type=float,
    )

    parser.add_argument(
        "--row-price-nok",
        required=True,
        type=float,
    )

    parser.add_argument(
        "--min-banker-probability",
        default=0.35,
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

    if len(
        prediction["legs"]
    ) != 7:
        raise ValueError(
            "Expected exactly 7 V75 legs."
        )

    result = build_risk_profiles(
        prediction["legs"],
        total_budget_nok=
            args.budget_nok,
        row_price_nok=
            args.row_price_nok,
        min_banker_probability=
            args.min_banker_probability,
    )

    names = {}

    for leg in prediction[
        "legs"
    ]:
        leg_number = int(
            leg["leg"]
        )

        names[
            leg_number
        ] = {}

        for ranking in leg[
            "rankings"
        ]:
            number = int(
                ranking[
                    "startNumber"
                ]
            )

            name = horse_name(
                ranking
            )

            if name:
                names[
                    leg_number
                ][
                    number
                ] = name

    output = {
        **result,
        "raceDate":
            prediction.get(
                "raceDate"
            ),
        "raceDayName":
            prediction.get(
                "raceDayName"
            ),
        "raceDayKey":
            prediction.get(
                "raceDayKey"
            ),
        "horseModel":
            prediction.get(
                "model"
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
        "=== V75 RISK PROFILE "
        "COMPARISON ==="
    )

    print(
        f"{output['raceDate']} "
        f"{output['raceDayName']}"
    )

    print(
        f"Budget: "
        f"{args.budget_nok:.2f} NOK"
    )

    print(
        f"Row price: "
        f"{args.row_price_nok:.2f} NOK"
    )

    print(
        "Weak-banker threshold: "
        f"{100*args.min_banker_probability:.1f}%"
    )

    print()

    max_profile = next(
        row
        for row
        in result[
            "profiles"
        ]
        if row[
            "profile"
        ] == "MAX_P7"
    )

    max_p7 = max_profile[
        "estimatedCoverage"
    ][
        "all7"
    ]

    for profile in result[
        "profiles"
    ]:
        coverage = profile[
            "estimatedCoverage"
        ]

        p7_cost = (
            max_p7
            - coverage[
                "all7"
            ]
        )

        bankers = [
            leg
            for leg
            in profile[
                "legs"
            ]
            if int(
                leg["k"]
            ) == 1
        ]

        print(
            f"--- {profile['profile']} ---"
        )

        print(
            f"Rows: "
            f"{profile['actualRows']} "
            f"| Cost: "
            f"{profile['actualCostNok']:.2f} NOK "
            f"| Unused: "
            f"{profile['unusedBudgetNok']:.2f} NOK"
        )

        print(
            f"P5+: "
            f"{100*coverage['atLeast5']:.2f}% "
            f"| P6+: "
            f"{100*coverage['atLeast6']:.2f}% "
            f"| P7: "
            f"{100*coverage['all7']:.2f}% "
            f"| E: "
            f"{coverage['expectedCoveredWinners']:.2f}/7"
        )

        print(
            f"P7 cost vs MAX_P7: "
            f"{100*p7_cost:.3f} percentage points"
        )

        if bankers:
            banker_text = []

            for leg in bankers:
                leg_number = int(
                    leg["leg"]
                )

                number = int(
                    leg[
                        "selectedStartNumbers"
                    ][0]
                )

                name = (
                    names[
                        leg_number
                    ].get(
                        number
                    )
                )

                top_prob = result[
                    "topProbabilitiesByLeg"
                ][
                    str(
                        leg_number
                    )
                ]

                label = (
                    f"V75-{leg_number} "
                    f"#{number}"
                )

                if name:
                    label += (
                        f" {name}"
                    )

                label += (
                    f" "
                    f"({100*top_prob:.1f}%)"
                )

                banker_text.append(
                    label
                )

            print(
                "Bankers: "
                + "; ".join(
                    banker_text
                )
            )
        else:
            print(
                "Bankers: none"
            )

        print()

        for leg in profile[
            "legs"
        ]:
            leg_number = int(
                leg["leg"]
            )

            numbers = [
                int(value)
                for value
                in leg[
                    "selectedStartNumbers"
                ]
            ]

            number_text = ", ".join(
                str(value)
                for value
                in numbers
            )

            print(
                f"V75-{leg_number}: "
                f"{number_text:<24} "
                f"| k={leg['k']} "
                f"| leg cover="
                f"{100*leg['probabilityMass']:.1f}%"
            )

        print()

    print(
        "NOTE: risk profiles use the same "
        "horse probabilities and budget. "
        "Only banker constraints differ."
    )

    print(
        "NOTE: probabilities remain "
        "provisional model estimates."
    )

    print()
    print(
        "Report:",
        args.output,
    )


if __name__ == "__main__":
    main()
