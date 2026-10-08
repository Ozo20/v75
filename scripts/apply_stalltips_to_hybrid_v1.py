from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


STALLTIPS_PACKAGE = "v75-stalltips-input"
HYBRID_PACKAGE = "v75-hybrid-input"


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save(
    path: Path,
    payload: Any,
) -> None:
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


def classify(
    model_selected: bool,
    stalltips_selected: bool,
) -> str:
    if (
        model_selected
        and stalltips_selected
    ):
        return "CONSENSUS"

    if model_selected:
        return "MODEL_ONLY"

    if stalltips_selected:
        return "STALLTIPS_ONLY"

    return "NEITHER"


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--hybrid-input",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--stalltips",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    hybrid = load(
        args.hybrid_input
    )

    stalltips = load(
        args.stalltips
    )

    if (
        hybrid.get("package")
        != HYBRID_PACKAGE
    ):
        raise ValueError(
            "Expected v75-hybrid-input."
        )

    if (
        stalltips.get("package")
        != STALLTIPS_PACKAGE
    ):
        raise ValueError(
            "Expected v75-stalltips-input."
        )

    for key in (
        "raceDate",
        "raceDayKey",
    ):
        if (
            hybrid.get(key)
            != stalltips.get(key)
        ):
            raise ValueError(
                f"Hybrid/Stalltips "
                f"mismatch for {key}."
            )

    recorded_pre_race = (
        stalltips.get(
            "recordedPreRace"
        )
    )

    synthetic = stalltips.get(
        "synthetic"
    )

    if not isinstance(
        recorded_pre_race,
        bool,
    ):
        raise ValueError(
            "recordedPreRace must "
            "be boolean."
        )

    if not isinstance(
        synthetic,
        bool,
    ):
        raise ValueError(
            "synthetic must be boolean."
        )

    if (
        synthetic
        and recorded_pre_race
    ):
        raise ValueError(
            "Synthetic Stalltips cannot "
            "be recordedPreRace=true."
        )

    raw_selections = (
        stalltips.get(
            "selections"
        )
    )

    if not isinstance(
        raw_selections,
        dict,
    ):
        raise ValueError(
            "Stalltips selections must "
            "be an object."
        )

    result = copy.deepcopy(
        hybrid
    )

    expected_legs = {
        int(leg["leg"])
        for leg
        in result["legs"]
    }

    supplied_legs = {
        int(key)
        for key
        in raw_selections
    }

    if (
        supplied_legs
        != expected_legs
    ):
        raise ValueError(
            "Stalltips must supply "
            "exactly all seven legs."
        )

    total_counts = {
        "CONSENSUS": 0,
        "MODEL_ONLY": 0,
        "STALLTIPS_ONLY": 0,
        "NEITHER": 0,
    }

    per_leg_summary = []

    for leg in result[
        "legs"
    ]:
        leg_number = int(
            leg["leg"]
        )

        supplied = raw_selections[
            str(leg_number)
        ]

        if not isinstance(
            supplied,
            list,
        ):
            raise ValueError(
                f"V75-{leg_number} "
                "selection must be a list."
            )

        numbers = [
            int(value)
            for value
            in supplied
        ]

        if not numbers:
            raise ValueError(
                f"V75-{leg_number} "
                "has no Stalltips selections."
            )

        if (
            len(numbers)
            != len(set(numbers))
        ):
            raise ValueError(
                f"V75-{leg_number} "
                "contains duplicate "
                "Stalltips selections."
            )

        eligible = {
            int(
                horse["startNumber"]
            )
            for horse
            in leg["horses"]
        }

        unknown = (
            set(numbers)
            - eligible
        )

        if unknown:
            raise ValueError(
                f"V75-{leg_number} "
                f"contains unknown starts: "
                f"{sorted(unknown)}"
            )

        stalltips_set = set(
            numbers
        )

        leg[
            "stalltipsSelectedStartNumbers"
        ] = numbers

        leg_counts = {
            "CONSENSUS": 0,
            "MODEL_ONLY": 0,
            "STALLTIPS_ONLY": 0,
            "NEITHER": 0,
        }

        for horse in leg[
            "horses"
        ]:
            number = int(
                horse["startNumber"]
            )

            model_selected = bool(
                horse[
                    "modelTicketSelected"
                ]
            )

            stalltips_selected = (
                number
                in stalltips_set
            )

            category = classify(
                model_selected,
                stalltips_selected,
            )

            horse[
                "stalltipsSelected"
            ] = stalltips_selected

            horse[
                "hybridClassification"
            ] = category

            leg_counts[
                category
            ] += 1

            total_counts[
                category
            ] += 1

        per_leg_summary.append(
            {
                "leg":
                    leg_number,
                "stalltipsSelections":
                    numbers,
                "counts":
                    leg_counts,
            }
        )

    result["stalltips"] = {
        "status":
            "RECORDED",
        "recordedPreRace":
            recorded_pre_race,
        "source":
            stalltips.get(
                "source"
            ),
        "synthetic":
            synthetic,
    }

    result["hybrid"] = {
        "status":
            "CLASSIFIED_AWAITING_SELECTOR",
        "selectorVersion":
            None,
        "ticketGenerated":
            False,
        "classificationSummary": {
            "total":
                total_counts,
            "byLeg":
                per_leg_summary,
        },
    }

    result[
        "guardrails"
    ][
        "preRaceOnly"
    ] = bool(
        hybrid[
            "guardrails"
        ][
            "preRaceOnly"
        ]
        and recorded_pre_race
        and not synthetic
    )

    result[
        "guardrails"
    ][
        "outcomesUsed"
    ] = False

    result[
        "guardrails"
    ][
        "stalltipsFabricated"
    ] = synthetic

    result[
        "guardrails"
    ][
        "stalltipsRecordedPreRace"
    ] = recorded_pre_race

    result[
        "guardrails"
    ][
        "hybridRulesApplied"
    ] = False

    result[
        "guardrails"
    ][
        "v2aRetuned"
    ] = False

    save(
        args.output,
        result,
    )

    print(
        "=== STALLTIPS CLASSIFICATION V1 ==="
    )

    print(
        f"Race: "
        f"{result['raceDate']} "
        f"{result['raceDayName']}"
    )

    print(
        f"Source: "
        f"{result['stalltips']['source']}"
    )

    print(
        f"Recorded pre-race: "
        f"{recorded_pre_race}"
    )

    print(
        f"Synthetic: "
        f"{synthetic}"
    )

    print()

    for row in per_leg_summary:
        counts = row[
            "counts"
        ]

        print(
            f"V75-{row['leg']}: "
            f"CONSENSUS="
            f"{counts['CONSENSUS']} | "
            f"MODEL_ONLY="
            f"{counts['MODEL_ONLY']} | "
            f"STALLTIPS_ONLY="
            f"{counts['STALLTIPS_ONLY']} | "
            f"NEITHER="
            f"{counts['NEITHER']}"
        )

    print()

    print(
        "TOTAL:",
        total_counts,
    )

    print(
        "PASS: classification only; "
        "no hybrid ticket generated."
    )

    print(
        "Output:",
        args.output,
    )


if __name__ == "__main__":
    main()
