from __future__ import annotations

import argparse
import json
from pathlib import Path

from v75.baseline import (
    MODEL_NAME,
    score_entry,
)


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save(path: Path, payload):
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

    source = load(args.input)

    if (
        source.get("datasetType")
        != "v75-pre-race"
    ):
        raise ValueError(
            "Runner accepts only "
            "v75-pre-race datasets"
        )

    # Important leakage guardrail:
    # the runner receives NO outcomes path.
    encoded_source = json.dumps(
        source,
        ensure_ascii=False,
    )

    forbidden = (
        "winnerStartNumber",
        "winnerV75MarketRank",
    )

    for field in forbidden:
        if field in encoded_source:
            raise ValueError(
                "DATA LEAKAGE: "
                f"{field} found in "
                "prediction input"
            )

    prediction_legs = []

    for leg in source["legs"]:
        ranked = []

        for entry in leg["entries"]:
            if not entry["start"][
                "eligibleForPrediction"
            ]:
                continue

            result = score_entry(entry)

            ranked.append(
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
                        result["score"],
                    "features":
                        result["features"],
                    "components":
                        result[
                            "components"
                        ],
                }
            )

        ranked.sort(
            key=lambda item: (
                -item["score"],
                item["startNumber"],
            )
        )

        for rank, item in enumerate(
            ranked,
            1,
        ):
            item["rank"] = rank

        prediction_legs.append(
            {
                "leg": leg["leg"],
                "raceKey":
                    leg["raceKey"],
                "raceNumber":
                    leg["raceNumber"],
                "fieldSizeEligible":
                    len(ranked),
                "rankings": ranked,
                "top3StartNumbers": [
                    item["startNumber"]
                    for item in ranked[:3]
                ],
            }
        )

    prediction = {
        "schemaVersion": "1.0",
        "datasetType":
            "v75-predictions",
        "model": MODEL_NAME,
        "raceDate":
            source["raceDate"],
        "raceDayKey":
            source["raceDayKey"],
        "raceDayName":
            source["raceDayName"],
        "guardrails": {
            "outcomesAvailableToModel":
                False,
            "scratchedExcluded":
                True,
        },
        "legs": prediction_legs,
    }

    save(
        args.output,
        prediction,
    )

    print(
        "=== BASELINE V1 "
        "PREDICTION COMPLETE ==="
    )

    print(
        f"Race day: "
        f"{source['raceDayName']} "
        f"{source['raceDate']}"
    )

    print()

    for leg in prediction_legs:
        print(
            f"V75-{leg['leg']} "
            f"(race "
            f"{leg['raceNumber']}, "
            f"{leg['fieldSizeEligible']} "
            f"starters)"
        )

        for item in (
            leg["rankings"][:3]
        ):
            print(
                f"  {item['rank']}. "
                f"#{item['startNumber']:2d} "
                f"{item['horseName']:<25} "
                f"{item['score']:7.2f}"
            )

    print(
        f"\nPredictions: "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()
