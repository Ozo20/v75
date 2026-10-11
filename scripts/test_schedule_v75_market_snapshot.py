from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

PATH = (
    ROOT
    / "scripts"
    / "schedule_v75_market_snapshot.py"
)

OSLO = ZoneInfo("Europe/Oslo")


def load_module():
    spec = (
        importlib.util
        .spec_from_file_location(
            "snapshot_scheduler",
            PATH,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Could not load scheduler."
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


assert module.SLOTS == (
    ("T-12H", 720.0),
    ("T-6H", 360.0),
    ("T-4H", 240.0),
    ("T-3H", 180.0),
    ("T-2H", 120.0),
    ("T-1H", 60.0),
    ("T-30M", 30.0),
    ("T-15M", 15.0),
    ("T-5M", 5.0),
)

print(
    "PASS: exact prospective slot "
    "contract is frozen."
)


start = datetime(
    2026,
    10,
    10,
    19,
    0,
    tzinfo=OSLO,
)


def decision(
    hour: int,
    minute: int,
    *,
    captured=(),
):
    return (
        module.decide_snapshot_slot(
            now=datetime(
                2026,
                10,
                10,
                hour,
                minute,
                tzinfo=OSLO,
            ),
            first_v75_start_at=start,
            captured_slots=set(
                captured
            ),
        )
    )


no_meeting = (
    module.decide_snapshot_slot(
        now=datetime(
            2026,
            10,
            10,
            10,
            0,
            tzinfo=OSLO,
        ),
        first_v75_start_at=None,
        captured_slots=set(),
    )
)

assert (
    no_meeting["state"]
    == "NO_UPCOMING_V75"
)

assert (
    no_meeting[
        "guardrails"
    ][
        "networkUsed"
    ]
    is False
)

print(
    "PASS: no meeting returns "
    "NO_UPCOMING_V75."
)


too_early = decision(
    6,
    0,
)

assert (
    too_early["state"]
    == "TOO_EARLY"
)

assert (
    too_early[
        "nextSlot"
    ][
        "label"
    ]
    == "T-12H"
)

print(
    "PASS: outside horizon returns "
    "TOO_EARLY."
)


twelve = decision(
    7,
    0,
)

assert (
    twelve["state"]
    == "DUE"
)

assert (
    twelve["slot"]["label"]
    == "T-12H"
)

assert (
    twelve["slot"][
        "latenessMinutes"
    ]
    == 0.0
)

print(
    "PASS: exact T-12H boundary is DUE."
)


before_six = decision(
    12,
    59,
)

assert (
    before_six["slot"]["label"]
    == "T-12H"
)

at_six = decision(
    13,
    0,
)

assert (
    at_six["slot"]["label"]
    == "T-6H"
)

print(
    "PASS: slot transitions occur "
    "at exact target boundaries."
)


bergen_live_window = (
    module.decide_snapshot_slot(
        now=datetime(
            2026,
            10,
            10,
            14,
            10,
            48,
            tzinfo=OSLO,
        ),
        first_v75_start_at=start,
        captured_slots=set(),
    )
)

assert (
    bergen_live_window[
        "state"
    ]
    == "DUE"
)

assert (
    bergen_live_window[
        "slot"
    ][
        "label"
    ]
    == "T-6H"
)

assert (
    70.7
    < bergen_live_window[
        "slot"
    ][
        "latenessMinutes"
    ]
    < 71.0
)

print(
    "PASS: Bergen 14:10 control "
    "maps deterministically to T-6H."
)


four_hour = decision(
    15,
    0,
)

assert (
    four_hour["slot"]["label"]
    == "T-4H"
)

three_hour = decision(
    16,
    0,
)

assert (
    three_hour["slot"]["label"]
    == "T-3H"
)

two_hour = decision(
    17,
    0,
)

assert (
    two_hour["slot"]["label"]
    == "T-2H"
)

one_hour = decision(
    18,
    0,
)

assert (
    one_hour["slot"]["label"]
    == "T-1H"
)

half_hour = decision(
    18,
    30,
)

assert (
    half_hour["slot"]["label"]
    == "T-30M"
)

quarter_hour = decision(
    18,
    45,
)

assert (
    quarter_hour["slot"]["label"]
    == "T-15M"
)

five_minute = decision(
    18,
    55,
)

assert (
    five_minute["slot"]["label"]
    == "T-5M"
)

print(
    "PASS: all near-start slot "
    "boundaries resolve correctly."
)


captured = decision(
    13,
    30,
    captured=("T-6H",),
)

assert (
    captured["state"]
    == "ALREADY_CAPTURED"
)

assert (
    captured["slot"]["label"]
    == "T-6H"
)

print(
    "PASS: current slot is idempotent "
    "after capture."
)


old_capture_does_not_block = (
    decision(
        15,
        1,
        captured=("T-12H", "T-6H"),
    )
)

assert (
    old_capture_does_not_block[
        "state"
    ]
    == "DUE"
)

assert (
    old_capture_does_not_block[
        "slot"
    ][
        "label"
    ]
    == "T-4H"
)

print(
    "PASS: earlier captured slots do "
    "not block the current slot."
)


last_window = decision(
    18,
    59,
)

assert (
    last_window["state"]
    == "DUE"
)

assert (
    last_window["slot"]["label"]
    == "T-5M"
)

at_start = decision(
    19,
    0,
)

assert (
    at_start["state"]
    == "DUE"
)

assert (
    at_start["slot"]["label"]
    == "T-5M"
)

print(
    "PASS: final slot remains active "
    "through scheduled start."
)


after_start = (
    module.decide_snapshot_slot(
        now=datetime(
            2026,
            10,
            10,
            19,
            0,
            1,
            tzinfo=OSLO,
        ),
        first_v75_start_at=start,
        captured_slots=set(),
    )
)

assert (
    after_start["state"]
    == "TOO_LATE"
)

assert (
    after_start["slot"]
    is None
)

print(
    "PASS: post-start execution fails "
    "closed as TOO_LATE."
)


parsed_naive = (
    module.parse_datetime(
        "2026-10-10T19:00:00"
    )
)

assert (
    parsed_naive.isoformat()
    == "2026-10-10T19:00:00+02:00"
)

parsed_utc = (
    module.parse_datetime(
        "2026-10-10T17:00:00Z"
    )
)

assert (
    parsed_utc.isoformat()
    == "2026-10-10T19:00:00+02:00"
)

print(
    "PASS: scheduler time parsing "
    "normalizes to Europe/Oslo."
)


try:
    module.decide_snapshot_slot(
        now=datetime(
            2026,
            10,
            10,
            13,
            0,
            tzinfo=OSLO,
        ),
        first_v75_start_at=start,
        captured_slots={
            "T-BOGUS"
        },
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Unknown slot did not fail closed."
    )

print(
    "PASS: unknown captured slot "
    "fails closed."
)


source = PATH.read_text(
    encoding="utf-8"
)

for forbidden in (
    "urllib",
    "requests",
    "playwright",
    "subprocess",
):
    assert forbidden not in source

assert (
    "collect_v75_market_snapshot"
    not in source
)

print(
    "PASS: scheduler v1 decision layer "
    "has no network or collector calls."
)
