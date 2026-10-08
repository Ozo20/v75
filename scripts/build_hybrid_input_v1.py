from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from v75.system_optimizer_v1 import (
    BETA,
    softmax_probabilities,
)


PACKAGE = "v75-hybrid-input"
SCHEMA_VERSION = "1.0"


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


def horse_name(
    row: dict[str, Any],
) -> str | None:
    for key in (
        "horseName",
        "name",
    ):
        value = row.get(key)

        if (
            isinstance(value, str)
            and value.strip()
        ):
            return value.strip()

    horse = row.get("horse")

    if isinstance(horse, dict):
        value = horse.get("name")

        if (
            isinstance(value, str)
            and value.strip()
        ):
            return value.strip()

    return None


def ticket_selection_by_leg(
    ticket: dict[str, Any],
    *,
    policy: str,
) -> dict[int, set[int]]:
    tickets = ticket.get(
        "tickets"
    )

    if not isinstance(
        tickets,
        dict,
    ):
        raise ValueError(
            "Ticket has no tickets object."
        )

    selected_ticket = (
        tickets.get(policy)
    )

    if not isinstance(
        selected_ticket,
        dict,
    ):
        raise ValueError(
            f"Ticket has no policy "
            f"{policy!r}."
        )

    legs = selected_ticket.get(
        "legs"
    )

    if not isinstance(
        legs,
        list,
    ):
        raise ValueError(
            f"Policy {policy!r} "
            "has no legs list."
        )

    result: dict[
        int,
        set[int],
    ] = {}

    for leg in legs:
        leg_number = int(
            leg["leg"]
        )

        selections = leg.get(
            "selections"
        )

        if not isinstance(
            selections,
            list,
        ):
            raise ValueError(
                f"Ticket V75-{leg_number} "
                "has no selections list."
            )

        numbers: set[int] = set()

        for selection in selections:
            if (
                not isinstance(
                    selection,
                    dict,
                )
                or "startNumber"
                not in selection
            ):
                raise ValueError(
                    f"Invalid selection in "
                    f"V75-{leg_number}."
                )

            numbers.add(
                int(
                    selection[
                        "startNumber"
                    ]
                )
            )

        expected_k = int(
            leg["k"]
        )

        if len(numbers) != expected_k:
            raise ValueError(
                f"V75-{leg_number} selection "
                f"count {len(numbers)} "
                f"!= k={expected_k}."
            )

        result[
            leg_number
        ] = numbers

    return result


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--predictions",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--ticket",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--policy",
        default="MAX_P7",
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

    ticket = load(
        args.ticket
    )

    if (
        prediction.get(
            "datasetType"
        )
        != "v75-predictions"
    ):
        raise ValueError(
            "Expected v75-predictions."
        )

    if (
        prediction.get("model")
        != "candidate-v2a-speed"
    ):
        raise ValueError(
            "Hybrid input v1 expects "
            "candidate-v2a-speed."
        )

    if (
        ticket.get("package")
        != "live-v75-ticket"
    ):
        raise ValueError(
            "Expected live-v75-ticket."
        )

    for key in (
        "raceDate",
        "raceDayKey",
        "raceDayName",
    ):
        if (
            prediction.get(key)
            != ticket.get(key)
        ):
            raise ValueError(
                f"Prediction/ticket "
                f"mismatch for {key}."
            )

    if (
        ticket.get("horseModel")
        != prediction.get("model")
    ):
        raise ValueError(
            "Prediction/ticket horse "
            "model mismatch."
        )

    selected_by_leg = (
        ticket_selection_by_leg(
            ticket,
            policy=args.policy,
        )
    )

    hybrid_legs = []

    for leg in prediction[
        "legs"
    ]:
        leg_number = int(
            leg["leg"]
        )

        rankings = sorted(
            leg["rankings"],
            key=lambda row:
                int(row["rank"]),
        )

        if not rankings:
            raise ValueError(
                f"V75-{leg_number} "
                "has no rankings."
            )

        scores = [
            float(row["score"])
            for row
            in rankings
        ]

        probabilities = (
            softmax_probabilities(
                scores
            )
        )

        selected = (
            selected_by_leg.get(
                leg_number
            )
        )

        if selected is None:
            raise ValueError(
                f"Ticket missing "
                f"V75-{leg_number}."
            )

        horses = []

        for row, probability in zip(
            rankings,
            probabilities,
        ):
            number = int(
                row["startNumber"]
            )

            horses.append(
                {
                    "startNumber":
                        number,
                    "horseName":
                        horse_name(row),
                    "v2aRank":
                        int(
                            row["rank"]
                        ),
                    "v2aScore":
                        float(
                            row["score"]
                        ),
                    "v2aProbability":
                        probability,
                    "v2aProbabilityPct":
                        round(
                            probability
                            * 100.0,
                            2,
                        ),
                    "modelTicketSelected":
                        number
                        in selected,

                    # Deliberately empty until
                    # an actual pre-race Stalltips
                    # ticket is recorded.
                    "stalltipsSelected":
                        None,

                    # Filled only after Stalltips
                    # has been supplied.
                    "hybridClassification":
                        None,
                }
            )

        hybrid_legs.append(
            {
                "leg":
                    leg_number,
                "raceKey":
                    leg.get(
                        "raceKey"
                    ),
                "raceNumber":
                    leg.get(
                        "raceNumber"
                    ),
                "fieldSizeEligible":
                    len(horses),
                "modelTicketSelectedStartNumbers":
                    sorted(
                        selected
                    ),
                "stalltipsSelectedStartNumbers":
                    None,
                "horses":
                    horses,
            }
        )

    payload = {
        "schemaVersion":
            SCHEMA_VERSION,
        "package":
            PACKAGE,

        "raceDate":
            prediction[
                "raceDate"
            ],
        "raceDayKey":
            prediction[
                "raceDayKey"
            ],
        "raceDayName":
            prediction[
                "raceDayName"
            ],

        "horseModel":
            prediction[
                "model"
            ],
        "probabilityCalibration": {
            "method":
                "existing-v1-softmax",
            "beta":
                BETA,
        },

        "modelTicket": {
            "policy":
                args.policy,
            "selectedBudgetNok":
                ticket[
                    "selectedBudgetNok"
                ],
            "rowPriceNok":
                ticket[
                    "rowPriceNok"
                ],
            "actualRows":
                ticket[
                    "tickets"
                ][
                    args.policy
                ][
                    "actualRows"
                ],
            "actualCostNok":
                ticket[
                    "tickets"
                ][
                    args.policy
                ][
                    "actualCostNok"
                ],
        },

        "stalltips": {
            "status":
                "NOT_RECORDED",
            "recordedPreRace":
                False,
            "source":
                None,
        },

        "hybrid": {
            "status":
                "AWAITING_STALLTIPS",
            "selectorVersion":
                None,
            "ticketGenerated":
                False,
        },

        "legs":
            hybrid_legs,

        "guardrails": {
            "preRaceOnly":
                True,
            "outcomesUsed":
                False,
            "marketUsedByV2A":
                False,
            "stalltipsFabricated":
                False,
            "hybridRulesApplied":
                False,
            "v2aRetuned":
                False,
        },

        "warning": (
            "V2A probabilities are "
            "provisional calibrated model "
            "estimates. Stalltips fields "
            "must be populated only from "
            "an actual pre-race ticket."
        ),
    }

    save(
        args.output,
        payload,
    )

    print(
        "=== HYBRID INPUT V1 ==="
    )

    print(
        f"Race: "
        f"{payload['raceDate']} "
        f"{payload['raceDayName']}"
    )

    print(
        f"Model: "
        f"{payload['horseModel']}"
    )

    print(
        f"Policy: "
        f"{args.policy}"
    )

    print(
        f"Budget: "
        f"{payload['modelTicket']['selectedBudgetNok']:.2f} NOK"
    )

    print(
        f"Rows: "
        f"{payload['modelTicket']['actualRows']}"
    )

    print()

    for leg in hybrid_legs:
        print(
            f"V75-{leg['leg']} "
            f"model ticket: "
            + ", ".join(
                str(value)
                for value
                in leg[
                    "modelTicketSelectedStartNumbers"
                ]
            )
        )

        for horse in (
            leg["horses"][:5]
        ):
            marker = (
                "*"
                if horse[
                    "modelTicketSelected"
                ]
                else " "
            )

            print(
                f"  {marker} "
                f"#{horse['startNumber']:<2} "
                f"r{horse['v2aRank']:<2} "
                f"{horse['v2aProbabilityPct']:>5.1f}% "
                f"{horse['horseName'] or ''}"
            )

    print()
    print(
        "PASS: no Stalltips values "
        "fabricated."
    )

    print(
        "PASS: no hybrid selection "
        "rules applied."
    )

    print(
        "Output:",
        args.output,
    )


if __name__ == "__main__":
    main()
