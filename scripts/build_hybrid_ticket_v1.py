from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


SELECTOR = "CONSERVATIVE_ONE_SWAP_V1"


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


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--classified-input",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
    )

    args = parser.parse_args()

    doc = load(
        args.classified_input
    )

    if (
        doc.get("package")
        != "v75-hybrid-input"
    ):
        raise ValueError(
            "Expected v75-hybrid-input."
        )

    if (
        doc.get("hybrid", {}).get(
            "status"
        )
        != "CLASSIFIED_AWAITING_SELECTOR"
    ):
        raise ValueError(
            "Input must be classified "
            "before selector is applied."
        )

    stalltips = doc.get(
        "stalltips",
        {},
    )

    if (
        stalltips.get("status")
        != "RECORDED"
    ):
        raise ValueError(
            "Stalltips not recorded."
        )

    synthetic = bool(
        stalltips.get(
            "synthetic",
            False,
        )
    )

    if (
        synthetic
        and not args.allow_synthetic
    ):
        raise ValueError(
            "Synthetic Stalltips refused. "
            "Use --allow-synthetic only "
            "for contract testing."
        )

    model_ticket = doc[
        "modelTicket"
    ]

    row_price = float(
        model_ticket[
            "rowPriceNok"
        ]
    )

    expected_rows = int(
        model_ticket[
            "actualRows"
        ]
    )

    ticket_legs = []
    swaps = []
    banker_flags = []

    for leg in doc["legs"]:
        leg_no = int(
            leg["leg"]
        )

        horses = leg[
            "horses"
        ]

        selected_model = [
            horse
            for horse in horses
            if horse[
                "modelTicketSelected"
            ]
        ]

        if not selected_model:
            raise ValueError(
                f"V75-{leg_no} has no "
                "model selections."
            )

        k = len(
            selected_model
        )

        selected_numbers = {
            int(
                horse["startNumber"]
            )
            for horse
            in selected_model
        }

        consensus = [
            horse
            for horse in horses
            if (
                horse[
                    "hybridClassification"
                ]
                == "CONSENSUS"
            )
        ]

        model_only = [
            horse
            for horse in horses
            if (
                horse[
                    "hybridClassification"
                ]
                == "MODEL_ONLY"
            )
        ]

        stalltips_only = [
            horse
            for horse in horses
            if (
                horse[
                    "hybridClassification"
                ]
                == "STALLTIPS_ONLY"
            )
        ]

        action = "UNCHANGED"
        added = None
        removed = None
        banker_disagreement = False

        if k == 1:
            model_horse = (
                selected_model[0]
            )

            if (
                model_horse[
                    "hybridClassification"
                ]
                == "MODEL_ONLY"
                and stalltips_only
            ):
                banker_disagreement = True

                banker_flags.append(
                    {
                        "leg":
                            leg_no,
                        "modelBanker":
                            int(
                                model_horse[
                                    "startNumber"
                                ]
                            ),
                        "stalltipsOnly":
                            [
                                int(
                                    horse[
                                        "startNumber"
                                    ]
                                )
                                for horse
                                in sorted(
                                    stalltips_only,
                                    key=lambda h: (
                                        -float(
                                            h[
                                                "v2aProbability"
                                            ]
                                        ),
                                        int(
                                            h[
                                                "v2aRank"
                                            ]
                                        ),
                                    ),
                                )
                            ],
                        "action":
                            "FLAG_ONLY_NO_AUTOMATIC_BANKER_SWAP",
                    }
                )

        elif (
            model_only
            and stalltips_only
        ):
            promote = min(
                stalltips_only,
                key=lambda horse: (
                    -float(
                        horse[
                            "v2aProbability"
                        ]
                    ),
                    int(
                        horse[
                            "v2aRank"
                        ]
                    ),
                    int(
                        horse[
                            "startNumber"
                        ]
                    ),
                ),
            )

            demote = min(
                model_only,
                key=lambda horse: (
                    float(
                        horse[
                            "v2aProbability"
                        ]
                    ),
                    -int(
                        horse[
                            "v2aRank"
                        ]
                    ),
                    int(
                        horse[
                            "startNumber"
                        ]
                    ),
                ),
            )

            added = int(
                promote[
                    "startNumber"
                ]
            )

            removed = int(
                demote[
                    "startNumber"
                ]
            )

            selected_numbers.remove(
                removed
            )

            selected_numbers.add(
                added
            )

            action = "ONE_SWAP"

            swaps.append(
                {
                    "leg":
                        leg_no,
                    "addedStartNumber":
                        added,
                    "addedHorseName":
                        promote.get(
                            "horseName"
                        ),
                    "addedV2aRank":
                        int(
                            promote[
                                "v2aRank"
                            ]
                        ),
                    "addedV2aProbability":
                        float(
                            promote[
                                "v2aProbability"
                            ]
                        ),
                    "removedStartNumber":
                        removed,
                    "removedHorseName":
                        demote.get(
                            "horseName"
                        ),
                    "removedV2aRank":
                        int(
                            demote[
                                "v2aRank"
                            ]
                        ),
                    "removedV2aProbability":
                        float(
                            demote[
                                "v2aProbability"
                            ]
                        ),
                    "reason":
                        (
                            "Highest-V2A-probability "
                            "STALLTIPS_ONLY replaces "
                            "lowest-V2A-probability "
                            "MODEL_ONLY; maximum one "
                            "swap per non-banker leg."
                        ),
                }
            )

        if (
            len(selected_numbers)
            != k
        ):
            raise RuntimeError(
                f"V75-{leg_no} changed k."
            )

        selected_horses = sorted(
            (
                horse
                for horse in horses
                if int(
                    horse[
                        "startNumber"
                    ]
                )
                in selected_numbers
            ),
            key=lambda horse:
                int(
                    horse[
                        "v2aRank"
                    ]
                ),
        )

        # Consensus is protected by construction.
        consensus_numbers = {
            int(
                horse[
                    "startNumber"
                ]
            )
            for horse
            in consensus
            if horse[
                "modelTicketSelected"
            ]
        }

        if not (
            consensus_numbers
            <= selected_numbers
        ):
            raise RuntimeError(
                f"V75-{leg_no} removed "
                "a consensus selection."
            )

        ticket_legs.append(
            {
                "leg":
                    leg_no,
                "k":
                    k,
                "action":
                    action,
                "bankerDisagreement":
                    banker_disagreement,
                "addedStartNumber":
                    added,
                "removedStartNumber":
                    removed,
                "selectedStartNumbers":
                    [
                        int(
                            horse[
                                "startNumber"
                            ]
                        )
                        for horse
                        in selected_horses
                    ],
                "selections":
                    [
                        {
                            "startNumber":
                                int(
                                    horse[
                                        "startNumber"
                                    ]
                                ),
                            "horseName":
                                horse.get(
                                    "horseName"
                                ),
                            "v2aRank":
                                int(
                                    horse[
                                        "v2aRank"
                                    ]
                                ),
                            "v2aProbability":
                                float(
                                    horse[
                                        "v2aProbability"
                                    ]
                                ),
                            "classification":
                                horse[
                                    "hybridClassification"
                                ],
                        }
                        for horse
                        in selected_horses
                    ],
            }
        )

    actual_rows = math.prod(
        int(
            leg["k"]
        )
        for leg
        in ticket_legs
    )

    if (
        actual_rows
        != expected_rows
    ):
        raise RuntimeError(
            "Hybrid selector changed "
            f"row structure: "
            f"{actual_rows} != "
            f"{expected_rows}."
        )

    actual_cost = (
        actual_rows
        * row_price
    )

    output = {
        "schemaVersion":
            "1.0",
        "package":
            "v75-hybrid-ticket",
        "selector":
            SELECTOR,

        "raceDate":
            doc["raceDate"],
        "raceDayKey":
            doc["raceDayKey"],
        "raceDayName":
            doc["raceDayName"],

        "horseModel":
            doc["horseModel"],

        "stalltips": {
            "source":
                stalltips.get(
                    "source"
                ),
            "recordedPreRace":
                bool(
                    stalltips.get(
                        "recordedPreRace"
                    )
                ),
            "synthetic":
                synthetic,
        },

        "baseModelTicket": {
            "policy":
                model_ticket[
                    "policy"
                ],
            "rows":
                expected_rows,
            "costNok":
                float(
                    model_ticket[
                        "actualCostNok"
                    ]
                ),
        },

        "hybridTicket": {
            "actualRows":
                actual_rows,
            "rowPriceNok":
                row_price,
            "actualCostNok":
                actual_cost,
            "legs":
                ticket_legs,
        },

        "changes": {
            "swapCount":
                len(swaps),
            "swaps":
                swaps,
            "bankerDisagreementCount":
                len(
                    banker_flags
                ),
            "bankerDisagreements":
                banker_flags,
        },

        "hybridProbabilityEstimate":
            None,

        "hybridProbabilityEstimateReason":
            (
                "No calibrated Stalltips "
                "per-horse probabilities are "
                "available. V2A probabilities "
                "are retained for transparency "
                "but are not presented as a "
                "calibrated hybrid P7 estimate."
            ),

        "guardrails": {
            "outcomesUsed":
                False,
            "v2aRetuned":
                False,
            "selectorFrozenRule":
                True,
            "maximumOneSwapPerNonBankerLeg":
                True,
            "consensusProtected":
                True,
            "automaticBankerSwap":
                False,
            "rowStructurePreserved":
                True,
            "hybridProbabilityFabricated":
                False,
            "syntheticSmokeTest":
                synthetic,
        },
    }

    save(
        args.output,
        output,
    )

    print(
        "=== HYBRID SELECTOR V1 ==="
    )

    print(
        f"Race: "
        f"{output['raceDate']} "
        f"{output['raceDayName']}"
    )

    print(
        f"Selector: {SELECTOR}"
    )

    print(
        f"Rows: {actual_rows}"
    )

    print(
        f"Cost: {actual_cost:.2f} NOK"
    )

    print(
        f"Swaps: {len(swaps)}"
    )

    print(
        f"Banker disagreements: "
        f"{len(banker_flags)}"
    )

    print()

    for leg in ticket_legs:
        picks = ", ".join(
            str(value)
            for value
            in leg[
                "selectedStartNumbers"
            ]
        )

        print(
            f"V75-{leg['leg']}: "
            f"{picks} | "
            f"k={leg['k']} | "
            f"{leg['action']}"
        )

    print()

    print(
        "PASS: row structure preserved."
    )

    print(
        "PASS: no hybrid probability "
        "fabricated."
    )

    print(
        "Output:",
        args.output,
    )


if __name__ == "__main__":
    main()
