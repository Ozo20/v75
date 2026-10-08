from __future__ import annotations

import argparse
import json
from pathlib import Path

from v75.baseline_safe_v1 import (
    MODEL_NAME,
    build_safe_projection,
    score_entry,
)


FORBIDDEN_MODEL_INPUT_KEYS = (
    "annualStatistics",
    "career",
    "totalEarnings",
    "winPercentage",
    "triplePercentage",
    "gallopPercentage",
    "winnerStartNumber",
    "winnerV75MarketRank",
)


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save(
    path: Path,
    payload,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    source = load(
        args.input
    )

    if (
        source.get("datasetType")
        != "v75-pre-race"
    ):
        raise ValueError(
            "Expected v75-pre-race input"
        )

    prediction_legs = []

    scored = 0

    for leg in source["legs"]:
        rankings = []

        for entry in leg["entries"]:
            if not entry["start"][
                "eligibleForPrediction"
            ]:
                continue

            safe_entry = (
                build_safe_projection(
                    entry
                )
            )

            encoded = json.dumps(
                safe_entry,
                ensure_ascii=False,
            )

            for key in (
                FORBIDDEN_MODEL_INPUT_KEYS
            ):
                if key in encoded:
                    raise ValueError(
                        "LEAKAGE GUARDRAIL: "
                        f"{key} reached model"
                    )

            result = score_entry(
                safe_entry
            )

            rankings.append(
                {
                    "startNumber":
                        entry[
                            "startNumber"
                        ],
                    "horseName":
                        entry["horse"][
                            "name"
                        ],
                    "score":
                        result[
                            "score"
                        ],
                    "features":
                        result[
                            "features"
                        ],
                    "components":
                        result[
                            "components"
                        ],
                }
            )

            scored += 1

        rankings.sort(
            key=lambda row: (
                -row["score"],
                row["startNumber"],
            )
        )

        for rank, row in enumerate(
            rankings,
            1,
        ):
            row["rank"] = rank

        prediction_legs.append(
            {
                "leg":
                    leg["leg"],
                "raceKey":
                    leg["raceKey"],
                "raceNumber":
                    leg[
                        "raceNumber"
                    ],
                "fieldSizeEligible":
                    len(rankings),
                "top3StartNumbers": [
                    row[
                        "startNumber"
                    ]
                    for row
                    in rankings[:3]
                ],
                "rankings":
                    rankings,
            }
        )

    output = {
        "schemaVersion": "1.0",
        "datasetType":
            "v75-predictions",
        "model":
            MODEL_NAME,
        "raceDate":
            source["raceDate"],
        "raceDayKey":
            source[
                "raceDayKey"
            ],
        "raceDayName":
            source[
                "raceDayName"
            ],
        "guardrails": {
            "outcomesAvailableToModel":
                False,
            "annualStatisticsAvailableToModel":
                False,
            "careerAggregatesAvailableToModel":
                False,
            "modelInputRestrictedTo":
                [
                    "historical form placing",
                    "current start post position"
                ],
        },
        "legs":
            prediction_legs,
    }

    save(
        args.output,
        output,
    )

    print(
        f"{source['raceDate']} "
        f"{source['raceDayName']:<14} "
        f"scored={scored}"
    )


if __name__ == "__main__":
    main()
