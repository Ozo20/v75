from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from v75.form_features_v2 import (
    extract_form_features,
)


DATES = [
    "2026-06-13",
    "2026-06-16",
    "2026-06-20",
    "2026-06-27",
    "2026-07-04",
    "2026-07-11",
    "2026-07-18",
    "2026-07-25",
    "2026-08-01",
    "2026-08-08",
    "2026-08-15",
    "2026-08-22",
]


VALID_SHOES = {
    "Both",
    "None",
    "Fore",
    "Hind",
}


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def canonical_shoes(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    return (
        value
        if value in VALID_SHOES
        else None
    )


def canonical_sulky(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if value in {
        "Sulky",
        "StandardSulky",
    }:
        return "StandardSulky"

    if value == "AmericanSulky":
        return "AmericanSulky"

    # NoSulky behaves like missing
    # historical equipment in this data.
    if value == "NoSulky":
        return None

    return None


entries = 0

stats = Counter()

shoe_repeat_dist = Counter()
sulky_repeat_dist = Counter()
setup_repeat_dist = Counter()

shoe_current_values = Counter()
sulky_current_values = Counter()

shoe_change_values = Counter()
sulky_change_values = Counter()

shoe_speed_effect_values = []
sulky_speed_effect_values = []
setup_speed_effect_values = []


def speed_effect(
    history: list[dict[str, Any]],
    matched: list[dict[str, Any]],
) -> float | None:
    if len(matched) < 2:
        return None

    overall = (
        extract_form_features(
            history
        ).get(
            "recentWeightedCleanKmTime"
        )
    )

    matched_speed = (
        extract_form_features(
            matched
        ).get(
            "recentWeightedCleanKmTime"
        )
    )

    if (
        overall is None
        or matched_speed is None
    ):
        return None

    count = len(matched)

    shrink = (
        count
        / (count + 2.0)
    )

    # Positive = historically faster
    # with today's equipment.
    return (
        (
            float(overall)
            - float(matched_speed)
        )
        * shrink
    )


for date in DATES:
    pre = load(
        Path("data/normalized")
        / date
        / "pre-race.json"
    )

    for leg in pre["legs"]:
        for entry in leg["entries"]:
            if not entry["start"][
                "eligibleForPrediction"
            ]:
                continue

            entries += 1

            equipment = (
                entry.get("equipment")
                or {}
            )

            current_shoes = (
                canonical_shoes(
                    equipment.get(
                        "shoes"
                    )
                )
            )

            current_sulky = (
                canonical_sulky(
                    equipment.get(
                        "sulky"
                    )
                )
            )

            if current_shoes:
                stats[
                    "currentShoesKnown"
                ] += 1

                shoe_current_values[
                    current_shoes
                ] += 1

            if current_sulky:
                stats[
                    "currentSulkyKnown"
                ] += 1

                sulky_current_values[
                    current_sulky
                ] += 1

            if (
                current_shoes
                and current_sulky
            ):
                stats[
                    "currentFullSetupKnown"
                ] += 1

            history = sorted(
                entry.get("history")
                or [],
                key=lambda row: (
                    row.get("raceDate")
                    or ""
                ),
                reverse=True,
            )

            shoe_rows = []
            sulky_rows = []
            setup_rows = []

            for row in history:
                hist_shoes = (
                    canonical_shoes(
                        row.get("shoes")
                    )
                )

                hist_sulky = (
                    canonical_sulky(
                        row.get("sulky")
                    )
                )

                if (
                    current_shoes
                    and hist_shoes
                    == current_shoes
                ):
                    shoe_rows.append(
                        row
                    )

                if (
                    current_sulky
                    and hist_sulky
                    == current_sulky
                ):
                    sulky_rows.append(
                        row
                    )

                if (
                    current_shoes
                    and current_sulky
                    and hist_shoes
                    == current_shoes
                    and hist_sulky
                    == current_sulky
                ):
                    setup_rows.append(
                        row
                    )

            shoe_count = len(
                shoe_rows
            )

            sulky_count = len(
                sulky_rows
            )

            setup_count = len(
                setup_rows
            )

            shoe_repeat_dist[
                shoe_count
            ] += 1

            sulky_repeat_dist[
                sulky_count
            ] += 1

            setup_repeat_dist[
                setup_count
            ] += 1

            for threshold in (
                1,
                2,
                3,
            ):
                if shoe_count >= threshold:
                    stats[
                        f"sameShoesAtLeast{threshold}"
                    ] += 1

                if sulky_count >= threshold:
                    stats[
                        f"sameSulkyAtLeast{threshold}"
                    ] += 1

                if setup_count >= threshold:
                    stats[
                        f"sameSetupAtLeast{threshold}"
                    ] += 1

            shoe_effect = speed_effect(
                history,
                shoe_rows,
            )

            sulky_effect = speed_effect(
                history,
                sulky_rows,
            )

            setup_effect = speed_effect(
                history,
                setup_rows,
            )

            if shoe_effect is not None:
                stats[
                    "shoeSpeedEffectAvailable"
                ] += 1

                shoe_speed_effect_values.append(
                    shoe_effect
                )

            if sulky_effect is not None:
                stats[
                    "sulkySpeedEffectAvailable"
                ] += 1

                sulky_speed_effect_values.append(
                    sulky_effect
                )

            if setup_effect is not None:
                stats[
                    "setupSpeedEffectAvailable"
                ] += 1

                setup_speed_effect_values.append(
                    setup_effect
                )

            if history:
                previous_shoes = (
                    canonical_shoes(
                        history[0].get(
                            "shoes"
                        )
                    )
                )

                previous_sulky = (
                    canonical_sulky(
                        history[0].get(
                            "sulky"
                        )
                    )
                )

                if (
                    current_shoes
                    and previous_shoes
                ):
                    stats[
                        "shoeChangeComparable"
                    ] += 1

                    if (
                        current_shoes
                        != previous_shoes
                    ):
                        stats[
                            "shoeChanged"
                        ] += 1

                    shoe_change_values[
                        (
                            previous_shoes,
                            current_shoes,
                        )
                    ] += 1

                if (
                    current_sulky
                    and previous_sulky
                ):
                    stats[
                        "sulkyChangeComparable"
                    ] += 1

                    if (
                        current_sulky
                        != previous_sulky
                    ):
                        stats[
                            "sulkyChanged"
                        ] += 1

                    sulky_change_values[
                        (
                            previous_sulky,
                            current_sulky,
                        )
                    ] += 1


print(
    "=== SAME-EQUIPMENT FEATURE FEASIBILITY ==="
)

print(
    f"Development entries:         "
    f"{entries}"
)

print()

print(
    "=== CURRENT EQUIPMENT ==="
)

for key in (
    "currentShoesKnown",
    "currentSulkyKnown",
    "currentFullSetupKnown",
):
    count = stats[key]

    print(
        f"{key:<28} "
        f"{count:>4}/{entries} "
        f"({100*count/entries:5.1f}%)"
    )

print()

print(
    "Current shoes:",
    dict(shoe_current_values),
)

print(
    "Current sulky:",
    dict(sulky_current_values),
)

print()

print(
    "=== SAME-EQUIPMENT HISTORY ==="
)

for label in (
    "Shoes",
    "Sulky",
    "Setup",
):
    prefix = (
        label[0].lower()
        + label[1:]
    )

    for threshold in (
        1,
        2,
        3,
    ):
        key = (
            f"same{label}"
            f"AtLeast{threshold}"
        )

        count = stats[key]

        print(
            f"{key:<28} "
            f"{count:>4}/{entries} "
            f"({100*count/entries:5.1f}%)"
        )

print()

print(
    "=== SPEED-EFFECT AVAILABILITY ==="
)

for key in (
    "shoeSpeedEffectAvailable",
    "sulkySpeedEffectAvailable",
    "setupSpeedEffectAvailable",
):
    count = stats[key]

    print(
        f"{key:<28} "
        f"{count:>4}/{entries} "
        f"({100*count/entries:5.1f}%)"
    )

print()


def print_effect(
    name,
    values,
):
    if not values:
        print(
            f"{name}: none"
        )
        return

    print(
        f"{name}: "
        f"n={len(values)} "
        f"range="
        f"{min(values):.4f}.."
        f"{max(values):.4f} "
        f"mean="
        f"{sum(values)/len(values):.4f}"
    )


print_effect(
    "shoe speed effect",
    shoe_speed_effect_values,
)

print_effect(
    "sulky speed effect",
    sulky_speed_effect_values,
)

print_effect(
    "full setup speed effect",
    setup_speed_effect_values,
)

print()

print(
    "=== CHANGE COVERAGE ==="
)

shoe_comp = stats[
    "shoeChangeComparable"
]

sulky_comp = stats[
    "sulkyChangeComparable"
]

print(
    f"Shoe comparable: "
    f"{shoe_comp}/{entries}"
)

print(
    f"Shoe changed:    "
    f"{stats['shoeChanged']}/"
    f"{shoe_comp if shoe_comp else 1} "
    f"("
    f"{100*stats['shoeChanged']/shoe_comp if shoe_comp else 0:.1f}%"
    f")"
)

print(
    f"Sulky comparable:"
    f" {sulky_comp}/{entries}"
)

print(
    f"Sulky changed:   "
    f"{stats['sulkyChanged']}/"
    f"{sulky_comp if sulky_comp else 1} "
    f"("
    f"{100*stats['sulkyChanged']/sulky_comp if sulky_comp else 0:.1f}%"
    f")"
)

print()

print(
    "=== SHOE TRANSITIONS ==="
)

for (
    previous,
    current,
), count in (
    shoe_change_values.most_common()
):
    print(
        f"{count:>4} "
        f"{previous:<5} -> "
        f"{current:<5}"
    )

print()

print(
    "=== SULKY TRANSITIONS ==="
)

for (
    previous,
    current,
), count in (
    sulky_change_values.most_common()
):
    print(
        f"{count:>4} "
        f"{previous:<14} -> "
        f"{current:<14}"
    )


report = {
    "schemaVersion":
        "1.0",
    "scope":
        "development-only-read-only",
    "entries":
        entries,
    "stats":
        dict(stats),
    "currentShoes":
        dict(shoe_current_values),
    "currentSulky":
        dict(sulky_current_values),
    "shoeRepeatDistribution":
        dict(shoe_repeat_dist),
    "sulkyRepeatDistribution":
        dict(sulky_repeat_dist),
    "setupRepeatDistribution":
        dict(setup_repeat_dist),
    "shoeTransitions": {
        f"{a}->{b}": count
        for (
            a,
            b,
        ), count in (
            shoe_change_values.items()
        )
    },
    "sulkyTransitions": {
        f"{a}->{b}": count
        for (
            a,
            b,
        ), count in (
            sulky_change_values.items()
        )
    },
    "speedEffectAvailability": {
        "shoes":
            len(
                shoe_speed_effect_values
            ),
        "sulky":
            len(
                sulky_speed_effect_values
            ),
        "fullSetup":
            len(
                setup_speed_effect_values
            ),
    },
    "semantics": {
        "NoSulky":
            "UNKNOWN_OR_MISSING",
        "historicalSulky":
            "Sulky => StandardSulky",
        "previousStartSource":
            "latest history row",
    },
    "guardrails": {
        "developmentOnly":
            True,
        "outcomesRead":
            False,
        "marketRead":
            False,
        "validationUsed":
            False,
        "modelChanged":
            False,
    },
}

output = Path(
    "data/experiments/"
    "equipment-match-feasibility.json"
)

output.write_text(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

print()
print(
    f"Report: {output}"
)
