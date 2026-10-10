from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PATH = (
    ROOT
    / "scripts"
    / "discover_v75_days.py"
)


def load_module():
    spec = (
        importlib.util
        .spec_from_file_location(
            "discover_v75_days_contract",
            PATH,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Could not load discovery module."
        )

    module = (
        importlib.util
        .module_from_spec(spec)
    )

    spec.loader.exec_module(
        module
    )

    return module


module = load_module()

bergen = {
    "raceDayName":
        "Bergen",
    "raceDay":
        "BT_NR_2026-10-10",
    "countryIsoCode":
        "NO",
    "isDomestic":
        True,
}

nested_payload = {
    "success": True,
    "result": [
        {
            "date":
                "2026-10-10",
            "raceDays": [
                bergen,
            ],
        }
    ],
}

race_days = module.extract_race_days(
    nested_payload
)

assert race_days == [bergen]

print(
    "PASS: current nested race-day "
    "list response is unwrapped."
)

legacy_payload = [
    {
        **bergen,
        "raceDayKey":
            "BT_NR_2026-10-10",
    }
]

legacy_days = module.extract_race_days(
    legacy_payload
)

assert len(legacy_days) == 1

print(
    "PASS: direct race-day lists remain "
    "compatible."
)

try:
    module.extract_race_days(
        {"unexpected": True}
    )
except RuntimeError:
    pass
else:
    raise AssertionError(
        "Unexpected response shape "
        "did not fail closed."
    )

source = PATH.read_text(
    encoding="utf-8"
)

assert (
    "/api/results/racedays/"
    in source
)

assert (
    "/api/racedays/dates/"
    not in source
)

print(
    "PASS: discovery uses the current "
    "read-only race-day list endpoint."
)
