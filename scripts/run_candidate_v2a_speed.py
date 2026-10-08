from __future__ import annotations

import argparse
import json
from pathlib import Path

from v75.candidate_v2a_speed import (
    BASE_WEIGHT,
    MODEL_NAME,
    SPEED_WEIGHT,
    score_field,
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

    assert (
        source["datasetType"]
        == "v75-pre-race"
    )

    prediction_legs = []

    for leg in source["legs"]:
        entries = [
            entry
            for entry
            in leg["entries"]
            if entry["start"][
                "eligibleForPrediction"
            ]
        ]

        rankings = score_field(
            entries
        )

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
        "weights": {
            "safeBaseline":
                BASE_WEIGHT,
            "speed":
                SPEED_WEIGHT,
        },
        "raceDate":
            source["raceDate"],
        "raceDayKey":
            source["raceDayKey"],
        "raceDayName":
            source["raceDayName"],
        "guardrails": {
            "outcomesAvailableToModel":
                False,
            "annualStatisticsAvailableToModel":
                False,
            "marketAvailableToModel":
                False,
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
        f"legs={len(prediction_legs)}"
    )


if __name__ == "__main__":
    main()
