from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


Json = Any


def load_json(
    path: Path,
) -> dict[str, Any]:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def classify_delta(
    delta: float,
) -> str:
    absolute = abs(delta)

    if absolute < 0.10:
        return "STABLE"

    if absolute < 0.25:
        return (
            "UP"
            if delta > 0
            else "DOWN"
        )

    return (
        "LARGE_UP"
        if delta > 0
        else "LARGE_DOWN"
    )


def horse_map(
    leg: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    return {
        int(row["startNumber"]): row
        for row in leg["horses"]
    }


def banker_map(
    leg: dict[str, Any],
) -> dict[int, float]:
    return {
        int(row["startNumber"]):
            float(row["bankerFrequency"])
        for row in leg[
            "bankerCandidates"
        ]
    }


def compare(
    earlier: dict[str, Any],
    later: dict[str, Any],
) -> dict[str, Any]:
    earlier_group = earlier[
        "selectedGroup"
    ]

    later_group = later[
        "selectedGroup"
    ]

    identity_fields = (
        "raceDayKey",
        "raceDate",
        "trackCode",
        "product",
        "requestedStakeOre",
        "rowPriceOre",
    )

    for field in identity_fields:
        if (
            earlier_group.get(field)
            != later_group.get(field)
        ):
            raise ValueError(
                f"Observation mismatch for {field}: "
                f"{earlier_group.get(field)!r} != "
                f"{later_group.get(field)!r}"
            )

    earlier_legs = {
        int(row["legNumber"]): row
        for row in earlier["legs"]
    }

    later_legs = {
        int(row["legNumber"]): row
        for row in later["legs"]
    }

    if set(earlier_legs) != set(later_legs):
        raise ValueError(
            "Observations contain different legs"
        )

    compared_legs = []

    for leg_number in sorted(
        earlier_legs
    ):
        before_leg = earlier_legs[
            leg_number
        ]

        after_leg = later_legs[
            leg_number
        ]

        before_horses = horse_map(
            before_leg
        )

        after_horses = horse_map(
            after_leg
        )

        before_bankers = banker_map(
            before_leg
        )

        after_bankers = banker_map(
            after_leg
        )

        horse_numbers = sorted(
            set(before_horses)
            | set(after_horses)
        )

        horses = []

        for number in horse_numbers:
            before = before_horses.get(
                number
            )

            after = after_horses.get(
                number
            )

            selection_before = (
                float(
                    before[
                        "selectionFrequency"
                    ]
                )
                if before
                else 0.0
            )

            selection_after = (
                float(
                    after[
                        "selectionFrequency"
                    ]
                )
                if after
                else 0.0
            )

            banker_before = (
                before_bankers.get(
                    number,
                    0.0,
                )
            )

            banker_after = (
                after_bankers.get(
                    number,
                    0.0,
                )
            )

            selection_delta = (
                selection_after
                - selection_before
            )

            banker_delta = (
                banker_after
                - banker_before
            )

            horses.append(
                {
                    "startNumber":
                        number,
                    "selection": {
                        "earlier":
                            round(
                                selection_before,
                                6,
                            ),
                        "later":
                            round(
                                selection_after,
                                6,
                            ),
                        "delta":
                            round(
                                selection_delta,
                                6,
                            ),
                        "deltaPercentagePoints":
                            round(
                                selection_delta
                                * 100,
                                1,
                            ),
                        "changeBand":
                            classify_delta(
                                selection_delta
                            ),
                    },
                    "banker": {
                        "earlier":
                            round(
                                banker_before,
                                6,
                            ),
                        "later":
                            round(
                                banker_after,
                                6,
                            ),
                        "delta":
                            round(
                                banker_delta,
                                6,
                            ),
                        "deltaPercentagePoints":
                            round(
                                banker_delta
                                * 100,
                                1,
                            ),
                        "changeBand":
                            classify_delta(
                                banker_delta
                            ),
                    },
                    "alwaysSelectedEarlier":
                        bool(
                            before
                            and before.get(
                                "alwaysSelected"
                            )
                        ),
                    "alwaysSelectedLater":
                        bool(
                            after
                            and after.get(
                                "alwaysSelected"
                            )
                        ),
                }
            )

        compared_legs.append(
            {
                "legNumber":
                    leg_number,
                "alwaysSelectedEarlier":
                    before_leg[
                        "alwaysSelected"
                    ],
                "alwaysSelectedLater":
                    after_leg[
                        "alwaysSelected"
                    ],
                "gainedAlwaysSelected":
                    sorted(
                        set(
                            after_leg[
                                "alwaysSelected"
                            ]
                        )
                        - set(
                            before_leg[
                                "alwaysSelected"
                            ]
                        )
                    ),
                "lostAlwaysSelected":
                    sorted(
                        set(
                            before_leg[
                                "alwaysSelected"
                            ]
                        )
                        - set(
                            after_leg[
                                "alwaysSelected"
                            ]
                        )
                    ),
                "horses":
                    horses,
            }
        )

    return {
        "schemaVersion":
            "1.0",
        "analysisType":
            "stalltips-temporal-comparison",
        "identity": {
            field:
                earlier_group.get(
                    field
                )
            for field in identity_fields
        },
        "earlierObservation":
            earlier["observation"],
        "laterObservation":
            later["observation"],
        "sampleCounts": {
            "earlier":
                earlier_group[
                    "sampleCount"
                ],
            "later":
                later_group[
                    "sampleCount"
                ],
        },
        "changeBands": {
            "STABLE":
                "absolute delta < 10 percentage points",
            "UP_DOWN":
                "10 <= absolute delta < 25 percentage points",
            "LARGE_UP_DOWN":
                "absolute delta >= 25 percentage points",
        },
        "legs":
            compared_legs,
        "guardrails": {
            "descriptiveOnly":
                True,
            "statisticalSignificanceClaimed":
                False,
            "generatorFrequencyIsNotWinProbability":
                True,
            "outcomesUsed":
                False,
            "marketUsed":
                False,
            "coreModelUsed":
                False,
        },
    }


def print_summary(
    result: dict[str, Any],
) -> None:
    print()
    print(
        "=== STALLTIPS TEMPORAL COMPARISON ==="
    )

    print(
        "Earlier samples:",
        result[
            "sampleCounts"
        ][
            "earlier"
        ],
    )

    print(
        "Later samples:  ",
        result[
            "sampleCounts"
        ][
            "later"
        ],
    )

    for leg in result[
        "legs"
    ]:
        print()
        print(
            f"V75-{leg['legNumber']}"
        )

        for horse in leg[
            "horses"
        ]:
            selection = horse[
                "selection"
            ]

            banker = horse[
                "banker"
            ]

            if (
                selection[
                    "changeBand"
                ]
                != "STABLE"
                or banker[
                    "changeBand"
                ]
                != "STABLE"
                or horse[
                    "alwaysSelectedEarlier"
                ]
                != horse[
                    "alwaysSelectedLater"
                ]
            ):
                print(
                    f"  #{horse['startNumber']:<2} "
                    f"selection "
                    f"{selection['earlier'] * 100:5.1f}% "
                    f"→ "
                    f"{selection['later'] * 100:5.1f}% "
                    f"({selection['deltaPercentagePoints']:+5.1f} pp, "
                    f"{selection['changeBand']}); "
                    f"banker "
                    f"{banker['earlier'] * 100:5.1f}% "
                    f"→ "
                    f"{banker['later'] * 100:5.1f}% "
                    f"({banker['deltaPercentagePoints']:+5.1f} pp, "
                    f"{banker['changeBand']})"
                )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--earlier",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--later",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    result = compare(
        load_json(
            args.earlier
        ),
        load_json(
            args.later
        ),
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print_summary(
        result
    )

    print()
    print(
        "Saved:",
        args.output,
    )


if __name__ == "__main__":
    main()
