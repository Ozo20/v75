from __future__ import annotations

import argparse
import json
from pathlib import Path

from v75.baseline_safe_v1 import (
    build_safe_projection,
    score_entry,
)

from v75.context_speed_v2b import (
    context_weighted_speed,
)

from v75.form_features_v2 import (
    percentile_scores,
)


BASE_WEIGHT = 0.70
SPEED_WEIGHT = 0.30


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def percentile_high(values):
    lo = min(values)
    hi = max(values)

    if hi == lo:
        return [1.0 for _ in values]

    return [
        (value - lo) / (hi - lo)
        for value in values
    ]


def main():
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

    result_legs = []

    for leg in source["legs"]:
        entries = [
            row
            for row in leg["entries"]
            if row["start"][
                "eligibleForPrediction"
            ]
        ]

        base_scores = []
        context_times = []

        for entry in entries:
            safe = build_safe_projection(
                entry
            )

            baseline = score_entry(
                safe
            )

            base_scores.append(
                float(
                    baseline["score"]
                )
            )

            context = (
                context_weighted_speed(
                    entry.get("history")
                    or [],
                    current_distance=int(
                        leg["race"][
                            "distance"
                        ]
                    ),
                    current_start_method=
                        leg["race"][
                            "startMethod"
                        ],
                )
            )

            context_times.append(
                context["contextKmTime"]
            )

        base_pct = percentile_high(
            base_scores
        )

        speed_pct = percentile_scores(
            context_times,
            lower_is_better=True,
        )

        rankings = []

        for i, entry in enumerate(
            entries
        ):
            score = (
                BASE_WEIGHT
                * base_pct[i]
                + SPEED_WEIGHT
                * speed_pct[i]
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
                        round(
                            score,
                            8,
                        ),
                }
            )

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

        result_legs.append(
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
            "candidate-v2b-context",
        "weights": {
            "safeBaseline": 0.70,
            "contextSpeed": 0.30
        },
        "raceDate":
            source["raceDate"],
        "raceDayKey":
            source["raceDayKey"],
        "raceDayName":
            source["raceDayName"],
        "legs":
            result_legs,
    }

    args.output.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
