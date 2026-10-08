from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MODULE_PATH = (
    ROOT
    / "scripts"
    / "run_v75_core_cloud.py"
)

spec = importlib.util.spec_from_file_location(
    "run_v75_core_cloud",
    MODULE_PATH,
)

if spec is None or spec.loader is None:
    raise RuntimeError(
        "Could not load cloud adapter"
    )

module = importlib.util.module_from_spec(
    spec
)

spec.loader.exec_module(
    module
)


def make_target(
    *,
    race_date: str,
    start_time: str | None = None,
):
    return {
        "raceDayKey":
            f"TEST_NR_{race_date}",
        "raceDayName":
            "Test",
        "raceDate":
            race_date,
        "countryIsoCode":
            "NO",
        "singleTrack":
            True,
        "startTime":
            start_time,
    }


state = {
    "target":
        make_target(
            race_date="2026-10-10",
            start_time=
                "2026-10-10T14:00:00+02:00",
        )
}

target = module.extract_target(
    state
)

assert target is not None

allowed, reason = (
    module.pre_race_allowed(
        target,
        now=datetime(
            2026,
            10,
            10,
            10,
            0,
            tzinfo=timezone.utc,
        ),
    )
)

assert allowed is True
assert reason == "PRE_RACE_CONFIRMED"

allowed, reason = (
    module.pre_race_allowed(
        target,
        now=datetime(
            2026,
            10,
            10,
            13,
            0,
            tzinfo=timezone.utc,
        ),
    )
)

assert allowed is False
assert reason == "TARGET_ALREADY_STARTED"

future_without_time = make_target(
    race_date="2026-10-11",
)

allowed, reason = (
    module.pre_race_allowed(
        future_without_time,
        now=datetime(
            2026,
            10,
            10,
            10,
            0,
            tzinfo=timezone.utc,
        ),
    )
)

assert allowed is True
assert reason == "FUTURE_RACE_DATE"

today_without_time = make_target(
    race_date="2026-10-10",
)

allowed, reason = (
    module.pre_race_allowed(
        today_without_time,
        now=datetime(
            2026,
            10,
            10,
            10,
            0,
            tzinfo=timezone.utc,
        ),
    )
)

assert allowed is False
assert reason == "TARGET_START_TIME_UNKNOWN"

print(
    "PASS: V75 Core cloud target and "
    "pre-race gates behave as expected."
)
