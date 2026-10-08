from __future__ import annotations

import json
import re
from pathlib import Path


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


TIME_RE = re.compile(
    r"^\s*(\d+)[,.](\d+)"
)


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def clean_numeric_time(raw):
    if raw is None:
        return False

    text = str(raw).strip().lower()

    match = TIME_RE.match(text)

    if not match:
        return False

    if "g" in text:
        return False

    if text.startswith("d"):
        return False

    if text.startswith("br"):
        return False

    return True


def historical_method(raw):
    """
    Conservative method inference.

    'a' suffix => AUTO.
    Clean numeric without 'a' => NON_AUTO.

    We do not claim NON_AUTO always equals volt;
    this is only a coverage diagnostic.
    """
    if raw is None:
        return "UNKNOWN"

    text = str(raw).strip().lower()

    if not clean_numeric_time(text):
        return "UNKNOWN"

    if "a" in text:
        return "AUTO"

    return "NON_AUTO"


def current_method(value):
    text = str(value or "").upper()

    if "AUTO" in text:
        return "AUTO"

    if "VOLT" in text:
        return "NON_AUTO"

    return "UNKNOWN"


entries = 0

with_clean = 0
with_exact_distance = 0
with_100m = 0
with_200m = 0

with_same_method = 0
with_same_method_200m = 0

total_clean_rows = 0
total_exact_distance_rows = 0
total_100m_rows = 0
total_200m_rows = 0
total_same_method_rows = 0
total_same_method_200m_rows = 0


for date in DATES:
    pre = load(
        Path("data/normalized")
        / date
        / "pre-race.json"
    )

    for leg in pre["legs"]:
        current_distance = int(
            leg["race"]["distance"]
        )

        method = current_method(
            leg["race"]["startMethod"]
        )

        for entry in leg["entries"]:
            if not entry["start"][
                "eligibleForPrediction"
            ]:
                continue

            entries += 1

            clean = 0
            exact = 0
            near100 = 0
            near200 = 0
            same_method = 0
            same_method_200 = 0

            for row in (
                entry.get("history")
                or []
            ):
                if not clean_numeric_time(
                    row.get("timeRaw")
                ):
                    continue

                try:
                    distance = int(
                        row.get("distance")
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                clean += 1

                delta = abs(
                    distance
                    - current_distance
                )

                if delta == 0:
                    exact += 1

                if delta <= 100:
                    near100 += 1

                if delta <= 200:
                    near200 += 1

                hist_method = (
                    historical_method(
                        row.get("timeRaw")
                    )
                )

                if (
                    method != "UNKNOWN"
                    and hist_method
                    == method
                ):
                    same_method += 1

                    if delta <= 200:
                        same_method_200 += 1

            total_clean_rows += clean
            total_exact_distance_rows += exact
            total_100m_rows += near100
            total_200m_rows += near200
            total_same_method_rows += same_method
            total_same_method_200m_rows += (
                same_method_200
            )

            with_clean += int(
                clean > 0
            )

            with_exact_distance += int(
                exact > 0
            )

            with_100m += int(
                near100 > 0
            )

            with_200m += int(
                near200 > 0
            )

            with_same_method += int(
                same_method > 0
            )

            with_same_method_200m += int(
                same_method_200 > 0
            )


def show(label, count):
    print(
        f"{label:<35} "
        f"{count:>4}/{entries} "
        f"({100 * count / entries:5.1f}%)"
    )


print(
    "=== SPEED CONTEXT COVERAGE ==="
)

print(
    f"Development entries: "
    f"{entries}"
)

print()

show(
    "Any clean historical time:",
    with_clean,
)

show(
    "Exact current distance:",
    with_exact_distance,
)

show(
    "Within 100 m of distance:",
    with_100m,
)

show(
    "Within 200 m of distance:",
    with_200m,
)

show(
    "Same inferred start method:",
    with_same_method,
)

show(
    "Same method + within 200 m:",
    with_same_method_200m,
)

print()
print(
    "=== HISTORICAL ROW COUNTS ==="
)

print(
    f"Clean rows:                 "
    f"{total_clean_rows}"
)

print(
    f"Exact-distance rows:        "
    f"{total_exact_distance_rows}"
)

print(
    f"Within-100m rows:           "
    f"{total_100m_rows}"
)

print(
    f"Within-200m rows:           "
    f"{total_200m_rows}"
)

print(
    f"Same-method rows:           "
    f"{total_same_method_rows}"
)

print(
    f"Same-method + within 200m:  "
    f"{total_same_method_200m_rows}"
)
