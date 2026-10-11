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
    / "queue_v75_notification.py"
)

DECIDER_PATH = (
    ROOT
    / "scripts"
    / "decide_v75_notification.py"
)

OSLO = ZoneInfo("Europe/Oslo")


def load_module(
    path: Path,
    name: str,
):
    spec = (
        importlib.util
        .spec_from_file_location(
            name,
            path,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            f"Could not load {name}."
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


outbox = load_module(
    PATH,
    "notification_outbox",
)

decider = load_module(
    DECIDER_PATH,
    "notification_decider",
)


KEY = "BT_NR_2026-10-17"
NAME = "Bergen"

NOW = datetime(
    2026,
    10,
    17,
    18,
    0,
    tzinfo=OSLO,
)


def make_decision(
    minutes,
    *,
    opportunity="UNKNOWN",
    recommendation="PENDING",
    stake=0,
    sent=(),
):
    return (
        decider.decide_notification(
            race_day_key=KEY,
            race_day_name=NAME,
            minutes_to_start=minutes,
            opportunity=opportunity,
            recommendation=
                recommendation,
            stake_nok=stake,
            sent_keys=set(sent),
        )
    )


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    silent = make_decision(
        61,
        opportunity="INTERESTING",
    )

    result = (
        outbox.enqueue_notification(
            decision=silent,
            output_root=root,
            now=NOW,
        )
    )

    assert (
        result["state"]
        == "SKIPPED_SILENT"
    )

    assert list(
        root.iterdir()
    ) == []

    print(
        "PASS: SILENT decision creates "
        "no outbox record."
    )


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    heads_up = make_decision(
        60,
        opportunity="INTERESTING",
    )

    first = (
        outbox.enqueue_notification(
            decision=heads_up,
            output_root=root,
            now=NOW,
        )
    )

    assert (
        first["state"]
        == "QUEUED"
    )

    assert (
        first["notificationKey"]
        == f"{KEY}:HEADS_UP"
    )

    record = (
        root
        / KEY
        / "HEADS_UP"
        / "queued.json"
    )

    assert record.is_file()

    document = json.loads(
        record.read_text(
            encoding="utf-8"
        )
    )

    assert (
        document["state"]
        == "QUEUED"
    )

    assert (
        document["deliveryState"]
        == "PENDING"
    )

    assert (
        document["notificationKey"]
        == f"{KEY}:HEADS_UP"
    )

    assert (
        document["message"]
        == heads_up["message"]
    )

    assert (
        document["guardrails"][
            "notificationSent"
        ]
        is False
    )

    print(
        "PASS: HEADS_UP creates one "
        "immutable pending queue record."
    )

    original_bytes = (
        record.read_bytes()
    )

    second = (
        outbox.enqueue_notification(
            decision=heads_up,
            output_root=root,
            now=datetime(
                2026,
                10,
                17,
                18,
                1,
                tzinfo=OSLO,
            ),
        )
    )

    assert (
        second["state"]
        == "ALREADY_QUEUED"
    )

    assert (
        second["samePayload"]
        is True
    )

    assert (
        record.read_bytes()
        == original_bytes
    )

    print(
        "PASS: identical notification "
        "is idempotent and immutable."
    )


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    value = make_decision(
        15,
        opportunity="INTERESTING",
        recommendation="VALUE",
        stake=200,
    )

    queued = (
        outbox.enqueue_notification(
            decision=value,
            output_root=root,
            now=NOW,
        )
    )

    assert (
        queued["state"]
        == "QUEUED"
    )

    record = (
        root
        / KEY
        / "FINAL"
        / "queued.json"
    )

    original = json.loads(
        record.read_text(
            encoding="utf-8"
        )
    )

    assert (
        original["action"]
        == "PLAY"
    )

    assert (
        "VALUE 200 kr"
        in original["message"]
    )

    changed = make_decision(
        10,
        opportunity="INTERESTING",
        recommendation="ATTACK",
        stake=400,
    )

    duplicate = (
        outbox.enqueue_notification(
            decision=changed,
            output_root=root,
            now=datetime(
                2026,
                10,
                17,
                18,
                5,
                tzinfo=OSLO,
            ),
        )
    )

    assert (
        duplicate["state"]
        == "ALREADY_QUEUED"
    )

    assert (
        duplicate["samePayload"]
        is False
    )

    after = json.loads(
        record.read_text(
            encoding="utf-8"
        )
    )

    assert after == original

    assert (
        "VALUE 200 kr"
        in after["message"]
    )

    print(
        "PASS: changed recommendation "
        "cannot replace or duplicate "
        "an immutable FINAL record."
    )


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    heads_up = make_decision(
        60,
        opportunity="INTERESTING",
    )

    final = make_decision(
        15,
        opportunity="INTERESTING",
        recommendation="VALUE",
        stake=200,
    )

    last_call = make_decision(
        5,
        recommendation="VALUE",
        stake=200,
    )

    for decision in (
        heads_up,
        final,
        last_call,
    ):
        result = (
            outbox.enqueue_notification(
                decision=decision,
                output_root=root,
                now=NOW,
            )
        )

        assert (
            result["state"]
            == "QUEUED"
        )

    records = sorted(
        root.glob(
            f"{KEY}/*/queued.json"
        )
    )

    assert len(records) == 3

    assert {
        path.parent.name
        for path in records
    } == {
        "HEADS_UP",
        "FINAL",
        "LAST_CALL",
    }

    print(
        "PASS: each notification stage "
        "has an independent dedup record."
    )


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    invalid = make_decision(
        15,
        recommendation="VALUE",
        stake=200,
    )

    invalid[
        "notificationKey"
    ] = (
        f"{KEY}:LAST_CALL"
    )

    try:
        outbox.enqueue_notification(
            decision=invalid,
            output_root=root,
            now=NOW,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Invalid notification key "
            "did not fail closed."
        )

    assert list(
        root.iterdir()
    ) == []

    print(
        "PASS: malformed notification "
        "key fails before any write."
    )


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    invalid = make_decision(
        15,
        recommendation="VALUE",
        stake=200,
    )

    invalid["stage"] = (
        "LAST_CALL"
    )

    try:
        outbox.enqueue_notification(
            decision=invalid,
            output_root=root,
            now=NOW,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Action/stage mismatch "
            "did not fail closed."
        )

    assert list(
        root.iterdir()
    ) == []

    print(
        "PASS: action/stage mismatch "
        "fails before any write."
    )


try:
    outbox.enqueue_notification(
        decision=make_decision(
            60,
            opportunity="INTERESTING",
        ),
        output_root=
            ROOT / "runtime-notifications",
        now=NOW,
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Repository outbox path "
        "did not fail closed."
    )

print(
    "PASS: notification runtime data "
    "cannot be written inside repo."
)


source = PATH.read_text(
    encoding="utf-8"
)

for forbidden in (
    "urllib",
    "requests",
    "playwright",
    "subprocess",
    "smtplib",
    "telegram",
    "pushover",
    "twilio",
):
    assert forbidden not in source

assert (
    "providerInvoked"
    in source
)

assert (
    '"x"'
    in source
)

print(
    "PASS: outbox v1 is offline and "
    "uses exclusive immutable writes."
)
