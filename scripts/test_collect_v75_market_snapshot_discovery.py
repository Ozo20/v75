from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PATH = (
    ROOT
    / "scripts"
    / "collect_v75_market_snapshot.py"
)


def load_module():
    spec = (
        importlib.util
        .spec_from_file_location(
            "market_snapshot_discovery",
            PATH,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Could not load market "
            "snapshot collector."
        )

    module = (
        importlib.util
        .module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


module = load_module()


physical_races = [
    {
        "raceNumber": number,
        "startTime":
            (
                "2026-10-10T19:00:00"
                if number == 3
                else None
            ),
    }
    for number
    in range(1, 10)
]


bergen = {
    "raceDayName":
        "Bergen",
    "raceDay":
        "BT_NR_2026-10-10",
    "countryIsoCode":
        "NO",
    "isDomestic":
        True,
    "races":
        physical_races,
    "pools": [
        {
            "product":
                "V75",
            "poolKey":
                "BT_NR_2026-10-10#V75#3",
            "isMultiTrack":
                False,
            "races":
                [],
            "raceNumbers":
                [3, 4, 5, 6, 7, 8, 9],
            "startTime":
                None,
        }
    ],
}


nested_payload = {
    "success": True,
    "result": [
        {
            "date":
                "2026-10-10T00:00:00",
            "raceDays": [
                bergen,
                {
                    "raceDay":
                        "S1_NR_2026-10-10",
                    "raceDayName":
                        "Foreign",
                    "countryIsoCode":
                        "SE",
                    "isDomestic":
                        False,
                    "pools": [
                        {
                            "product":
                                "V75",
                            "isMultiTrack":
                                False,
                            "raceNumbers":
                                [
                                    1, 2, 3, 4,
                                    5, 6, 7,
                                ],
                        }
                    ],
                },
            ],
        }
    ],
}


race_days = (
    module.extract_race_days(
        nested_payload
    )
)

assert len(race_days) == 2

print(
    "PASS: nested race-day list "
    "response is unwrapped."
)


meetings = (
    module.normalize_v75_meetings(
        nested_payload
    )
)

assert len(meetings) == 1

meeting = meetings[0]

assert (
    meeting["raceDayKey"]
    == "BT_NR_2026-10-10"
)

assert (
    meeting["raceNumbers"]
    == [3, 4, 5, 6, 7, 8, 9]
)

assert (
    meeting["raceKeys"]
    == [
        f"BT_NR_2026-10-10#{number}"
        for number
        in range(3, 10)
    ]
)

assert (
    meeting["firstRaceNumber"]
    == 3
)

assert (
    meeting["firstRaceStartTime"]
    == "2026-10-10T19:00:00"
)

assert (
    meeting["singleTrack"]
    is True
)

print(
    "PASS: raceNumbers fallback, "
    "domestic filtering and exact "
    "V75-1 start time are preserved."
)


legacy_payload = {
    "success": True,
    "result": [
        {
            "raceDayKey":
                "BT_NR_2026-10-10",
            "raceDayName":
                "Bergen",
            "countryIsoCode":
                "NO",
            "isDomestic":
                True,
            "pools": [
                {
                    "product":
                        "V75",
                    "poolKey":
                        "BT_NR_2026-10-10#V75#3",
                    "isMultiTrack":
                        False,
                    "races": [
                        f"BT_NR_2026-10-10#{number}"
                        for number
                        in range(3, 10)
                    ],
                    "startTime":
                        "2026-10-10T19:00:00",
                }
            ],
        }
    ],
}


legacy = (
    module.normalize_v75_meetings(
        legacy_payload
    )
)

assert len(legacy) == 1

assert (
    legacy[0][
        "firstRaceStartTime"
    ]
    == "2026-10-10T19:00:00"
)

print(
    "PASS: direct race-day list "
    "shape remains compatible."
)


try:
    module.extract_race_days(
        {
            "success": True,
            "result": {
                "unexpected": True,
            },
        }
    )
except RuntimeError:
    pass
else:
    raise AssertionError(
        "Unexpected response shape "
        "did not fail closed."
    )

print(
    "PASS: unexpected discovery "
    "shape fails closed."
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

assert (
    '"outcomeEndpointUsed":'
    in source
)

print(
    "PASS: collector uses the current "
    "schedule-list endpoint without "
    "claiming outcome use."
)
