from __future__ import annotations

import importlib.util
import json
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

PATH = (
    ROOT
    / "scripts"
    / "run_v75_market_snapshot_scheduler.py"
)

OSLO = ZoneInfo("Europe/Oslo")


def load_module():
    spec = (
        importlib.util
        .spec_from_file_location(
            "snapshot_execution",
            PATH,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Could not load execution layer."
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


meeting = {
    "raceDayKey":
        "BT_NR_2026-10-10",
    "raceDayName":
        "Bergen",
    "poolKey":
        "BT_NR_2026-10-10#V75#3",
    "singleTrack":
        True,
    "firstRaceNumber":
        3,
    "firstRaceStartTime":
        "2026-10-10T19:00:00",
}


def fake_discovery(
    _from_date,
    _to_date,
):
    return (
        b'{"success":true}',
        {
            "success":
                True,
        },
        [meeting],
    )


collector_calls: list[
    str
] = []


def fake_collector(
    selected,
    attempt_dir,
):
    collector_calls.append(
        selected[
            "raceDayKey"
        ]
    )

    snapshot_path = (
        attempt_dir
        / "fake-snapshot.json"
    )

    snapshot = {
        "schemaVersion":
            "1.2",
        "collector":
            "v75-market-snapshot-v2",
        "capturedAt":
            "2026-10-10T13:00:01+02:00",
        "status":
            "MARKET_AVAILABLE",
        "meeting": {
            "raceDayKey":
                selected[
                    "raceDayKey"
                ],
            "firstRaceNumber":
                selected[
                    "firstRaceNumber"
                ],
        },
        "timing": {
            "firstV75StartAt":
                "2026-10-10T19:00:00+02:00",
        },
        "turnover": {
            "estimateNok":
                2127575.0,
        },
    }

    snapshot_path.write_text(
        json.dumps(
            snapshot,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return (
        snapshot_path,
        snapshot,
    )


with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)

    no_meeting = (
        module.execute_once(
            output_root=out,
            now=datetime(
                2026,
                10,
                10,
                10,
                0,
                tzinfo=OSLO,
            ),
            discover_fn=(
                lambda _a, _b: (
                    b"{}",
                    {},
                    [],
                )
            ),
            collector_runner=
                fake_collector,
        )
    )

    assert (
        no_meeting["state"]
        == "NO_UPCOMING_V75"
    )

    assert len(
        collector_calls
    ) == 0

    print(
        "PASS: no discovered meeting "
        "does not invoke collector."
    )


with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)

    early = module.execute_once(
        output_root=out,
        now=datetime(
            2026,
            10,
            10,
            6,
            0,
            tzinfo=OSLO,
        ),
        discover_fn=
            fake_discovery,
        collector_runner=
            fake_collector,
    )

    assert (
        early["state"]
        == "TOO_EARLY"
    )

    assert len(
        collector_calls
    ) == 0

    assert list(
        out.iterdir()
    ) == []

    print(
        "PASS: TOO_EARLY creates no "
        "capture state."
    )


collector_calls.clear()

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)

    first = module.execute_once(
        output_root=out,
        now=datetime(
            2026,
            10,
            10,
            13,
            0,
            tzinfo=OSLO,
        ),
        discover_fn=
            fake_discovery,
        collector_runner=
            fake_collector,
    )

    assert (
        first["state"]
        == "CAPTURED"
    )

    assert (
        first["decision"][
            "slot"
        ][
            "label"
        ]
        == "T-6H"
    )

    assert len(
        collector_calls
    ) == 1

    receipt = (
        out
        / "BT_NR_2026-10-10"
        / "T-6H"
        / "complete.json"
    )

    assert receipt.is_file()

    receipt_doc = json.loads(
        receipt.read_text(
            encoding="utf-8"
        )
    )

    assert (
        receipt_doc["state"]
        == "COMPLETE"
    )

    assert (
        receipt_doc[
            "actualMinutesToStart"
        ]
        == 360.0
    )

    assert (
        receipt_doc[
            "turnoverEstimateNok"
        ]
        == 2127575.0
    )

    assert not (
        out
        / "BT_NR_2026-10-10"
        / "T-6H"
        / ".capture.lock"
    ).exists()

    print(
        "PASS: DUE slot creates one "
        "immutable completion receipt."
    )

    second = module.execute_once(
        output_root=out,
        now=datetime(
            2026,
            10,
            10,
            13,
            30,
            tzinfo=OSLO,
        ),
        discover_fn=
            fake_discovery,
        collector_runner=
            fake_collector,
    )

    assert (
        second["state"]
        == "ALREADY_CAPTURED"
    )

    assert len(
        collector_calls
    ) == 1

    print(
        "PASS: completed slot is "
        "idempotent."
    )

    next_slot = module.execute_once(
        output_root=out,
        now=datetime(
            2026,
            10,
            10,
            15,
            0,
            tzinfo=OSLO,
        ),
        discover_fn=
            fake_discovery,
        collector_runner=
            fake_collector,
    )

    assert (
        next_slot["state"]
        == "CAPTURED"
    )

    assert (
        next_slot["decision"][
            "slot"
        ][
            "label"
        ]
        == "T-4H"
    )

    assert len(
        collector_calls
    ) == 2

    print(
        "PASS: earlier receipts do not "
        "block a later due slot."
    )


collector_calls.clear()

failure_calls = 0


def failing_collector(
    _selected,
    _attempt_dir,
):
    global failure_calls

    failure_calls += 1

    raise RuntimeError(
        "synthetic market unavailable"
    )


with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)

    failed = module.execute_once(
        output_root=out,
        now=datetime(
            2026,
            10,
            10,
            16,
            0,
            tzinfo=OSLO,
        ),
        discover_fn=
            fake_discovery,
        collector_runner=
            failing_collector,
    )

    assert (
        failed["state"]
        == "CAPTURE_FAILED"
    )

    receipt = (
        out
        / "BT_NR_2026-10-10"
        / "T-3H"
        / "complete.json"
    )

    assert not receipt.exists()

    failures = list(
        (
            out
            / "BT_NR_2026-10-10"
            / "T-3H"
            / "attempts"
        ).glob(
            "*/failure.json"
        )
    )

    assert len(failures) == 1

    retried = module.execute_once(
        output_root=out,
        now=datetime(
            2026,
            10,
            10,
            16,
            1,
            tzinfo=OSLO,
        ),
        discover_fn=
            fake_discovery,
        collector_runner=
            fake_collector,
    )

    assert (
        retried["state"]
        == "CAPTURED"
    )

    assert receipt.is_file()

    print(
        "PASS: failed capture remains "
        "auditable and retryable."
    )


with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)

    lock = (
        out
        / "BT_NR_2026-10-10"
        / "T-2H"
        / ".capture.lock"
    )

    lock.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lock.write_text(
        "synthetic\n",
        encoding="utf-8",
    )

    locked = module.execute_once(
        output_root=out,
        now=datetime(
            2026,
            10,
            10,
            17,
            0,
            tzinfo=OSLO,
        ),
        discover_fn=
            fake_discovery,
        collector_runner=
            fake_collector,
    )

    assert (
        locked["state"]
        == "CAPTURE_IN_PROGRESS"
    )

    print(
        "PASS: existing lock prevents "
        "duplicate collector execution."
    )


with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)

    second_meeting = {
        **meeting,
        "raceDayKey":
            "BI_NR_2026-10-10",
        "raceDayName":
            "Biri",
        "poolKey":
            "BI_NR_2026-10-10#V75#4",
        "firstRaceNumber":
            4,
        "firstRaceStartTime":
            "2026-10-10T20:00:00",
    }

    ambiguous = (
        module.execute_once(
            output_root=out,
            now=datetime(
                2026,
                10,
                10,
                13,
                0,
                tzinfo=OSLO,
            ),
            discover_fn=(
                lambda _a, _b: (
                    b"{}",
                    {},
                    [
                        meeting,
                        second_meeting,
                    ],
                )
            ),
            collector_runner=
                fake_collector,
        )
    )

    assert (
        ambiguous["state"]
        == "AMBIGUOUS_V75_DAY"
    )

    print(
        "PASS: multiple same-day "
        "single-track pools fail closed."
    )


with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)

    past = {
        **meeting,
        "raceDayKey":
            "BT_NR_2026-10-09",
        "firstRaceStartTime":
            "2026-10-09T19:00:00",
    }

    future = {
        **meeting,
        "raceDayKey":
            "BT_NR_2026-10-17",
        "poolKey":
            "BT_NR_2026-10-17#V75#3",
        "firstRaceStartTime":
            "2026-10-17T19:00:00",
    }

    selected = (
        module.select_meeting(
            [
                past,
                future,
            ],
            datetime(
                2026,
                10,
                10,
                12,
                0,
                tzinfo=OSLO,
            ),
        )
    )

    assert selected is future

    print(
        "PASS: earliest future meeting "
        "is preferred over past meetings."
    )


with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)
    now = datetime(2026, 10, 10, 20, 0, tzinfo=OSLO)

    assert module.select_meeting([past], now) is None
    expired = module.execute_once(
        output_root=out,
        now=now,
        discover_fn=lambda _a, _b: (b"{}", {}, [past]),
        collector_runner=fake_collector,
    )
    assert expired["state"] == "NO_UPCOMING_V75"
    assert expired["discovery"]["alreadyStartedCount"] == 1
    assert expired["discovery"]["missingStartTimeCount"] == 0
    print("PASS: past-only discovery does not select an expired target.")

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)
    unknown_start = {
        **future,
        "firstRaceStartTime": None,
    }
    unresolved = module.execute_once(
        output_root=out,
        now=datetime(2026, 10, 10, 12, 0, tzinfo=OSLO),
        discover_fn=lambda _a, _b: (b"{}", {}, [unknown_start]),
        collector_runner=fake_collector,
    )
    assert unresolved["state"] == "NO_UPCOMING_V75"
    assert unresolved["discovery"]["singleTrackCandidateCount"] == 1
    assert unresolved["discovery"]["missingStartTimeCount"] == 1
    print("PASS: missing V75-1 start time is reported, not guessed.")


try:
    module.execute_once(
        output_root=
            ROOT / "runtime-output",
        now=datetime(
            2026,
            10,
            10,
            13,
            0,
            tzinfo=OSLO,
        ),
        discover_fn=
            fake_discovery,
        collector_runner=
            fake_collector,
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Repository output root "
        "did not fail closed."
    )

print(
    "PASS: execution data cannot be "
    "written inside repository."
)


source = PATH.read_text(
    encoding="utf-8"
)

assert (
    "raceresults"
    not in source
)

assert (
    "eventualvalues"
    not in source
)

assert (
    "prizepayout"
    not in source
)

assert (
    "subprocess.run"
    in source
)

print(
    "PASS: execution layer delegates "
    "market capture without outcome APIs."
)
