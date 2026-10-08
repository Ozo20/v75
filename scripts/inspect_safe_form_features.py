from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean


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


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def text(value):
    if value is None:
        return "<NULL>"

    value = str(value).strip()

    return value or "<EMPTY>"


place_values = Counter()
time_values = Counter()
time_shapes = Counter()
odds_values = Counter()
odds_shapes = Counter()
prize_values = Counter()

distances = Counter()
tracks = Counter()
drivers = Counter()

favorite_values = Counter()
shoes_values = Counter()
sulky_values = Counter()
monte_values = Counter()

rows_per_entry = []

total_entries = 0
total_rows = 0


def time_shape(value: str) -> str:
    if value in {
        "<NULL>",
        "<EMPTY>",
    }:
        return value

    lower = value.lower()

    if re.match(
        r"^\d+[,.]\d",
        lower,
    ):
        if "g" in lower:
            return "NUMERIC_GALLOP"

        if "a" in lower:
            return "NUMERIC_AUTO"

        return "NUMERIC_OTHER"

    if lower.startswith("dg"):
        return "DISQUALIFIED_GALLOP"

    if lower.startswith("d"):
        return "DISQUALIFIED_OTHER"

    if lower.startswith("br"):
        return "BROKEN_OFF"

    return "OTHER"


def odds_shape(value: str) -> str:
    if value in {
        "<NULL>",
        "<EMPTY>",
    }:
        return value

    normalized = (
        value
        .replace(",", ".")
        .strip()
    )

    try:
        float(normalized)
        return "NUMERIC"
    except ValueError:
        return "OTHER"


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

            total_entries += 1

            history = (
                entry.get("history")
                or []
            )

            rows_per_entry.append(
                len(history)
            )

            for row in history:
                total_rows += 1

                place = text(
                    row.get("placeRaw")
                )

                time_raw = text(
                    row.get("timeRaw")
                )

                odds = text(
                    row.get("winOddsRaw")
                )

                prize = text(
                    row.get("firstPrizeRaw")
                )

                place_values[place] += 1
                time_values[time_raw] += 1
                time_shapes[
                    time_shape(time_raw)
                ] += 1

                odds_values[odds] += 1
                odds_shapes[
                    odds_shape(odds)
                ] += 1

                prize_values[prize] += 1

                distances[
                    text(
                        row.get(
                            "distance"
                        )
                    )
                ] += 1

                tracks[
                    text(
                        row.get(
                            "trackCode"
                        )
                    )
                ] += 1

                drivers[
                    text(
                        row.get(
                            "driver"
                        )
                    )
                ] += 1

                favorite_values[
                    text(
                        row.get(
                            "favorite"
                        )
                    )
                ] += 1

                shoes_values[
                    text(
                        row.get(
                            "shoes"
                        )
                    )
                ] += 1

                sulky_values[
                    text(
                        row.get(
                            "sulky"
                        )
                    )
                ] += 1

                monte_values[
                    text(
                        row.get(
                            "monte"
                        )
                    )
                ] += 1


print(
    "=== SAFE HISTORICAL FEATURE INVENTORY ==="
)

print()
print(
    f"Development meetings: "
    f"{len(DATES)}"
)

print(
    f"Eligible current entries: "
    f"{total_entries}"
)

print(
    f"Historical rows inspected: "
    f"{total_rows}"
)

print(
    f"Mean history rows/entry: "
    f"{mean(rows_per_entry):.2f}"
)

print()


def show_counter(
    title,
    counter,
    limit=20,
):
    print(
        f"=== {title} ==="
    )

    print(
        f"Unique values: "
        f"{len(counter)}"
    )

    for value, count in (
        counter.most_common(limit)
    ):
        print(
            f"{count:5d}  {value}"
        )

    print()


show_counter(
    "PLACE RAW",
    place_values,
    25,
)

show_counter(
    "TIME SHAPES",
    time_shapes,
    20,
)

show_counter(
    "TIME RAW EXAMPLES",
    time_values,
    30,
)

show_counter(
    "WIN ODDS SHAPES",
    odds_shapes,
    10,
)

show_counter(
    "WIN ODDS EXAMPLES",
    odds_values,
    20,
)

show_counter(
    "DISTANCES",
    distances,
    20,
)

show_counter(
    "TRACKS",
    tracks,
    20,
)

show_counter(
    "FAVORITE",
    favorite_values,
    10,
)

show_counter(
    "SHOES",
    shoes_values,
    20,
)

show_counter(
    "SULKY",
    sulky_values,
    20,
)

show_counter(
    "MONTE",
    monte_values,
    10,
)

show_counter(
    "FIRST PRIZE RAW",
    prize_values,
    25,
)

print(
    "=== DRIVER COVERAGE ==="
)

missing_driver = (
    drivers["<NULL>"]
    + drivers["<EMPTY>"]
)

print(
    f"Unique drivers: "
    f"{len(drivers)}"
)

print(
    f"Missing driver rows: "
    f"{missing_driver}/"
    f"{total_rows}"
)
