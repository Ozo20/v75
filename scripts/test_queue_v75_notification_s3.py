from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

DECIDER_PATH = (
    ROOT
    / "scripts"
    / "decide_v75_notification.py"
)

CLOUD_PATH = (
    ROOT
    / "scripts"
    / "queue_v75_notification_s3.py"
)

OSLO = ZoneInfo("Europe/Oslo")

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


decider = load_module(
    DECIDER_PATH,
    "s3_test_decider",
)

cloud = load_module(
    CLOUD_PATH,
    "s3_test_outbox",
)


class FakeStore:
    network_used = False

    def __init__(
        self,
    ):
        self.objects: dict[
            str,
            bytes,
        ] = {}

        self.put_calls = 0
        self.get_calls = 0

    def get_bytes(
        self,
        key: str,
    ):
        self.get_calls += 1

        return self.objects.get(
            key
        )

    def put_if_absent(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str,
    ):
        assert (
            content_type
            == "application/json"
        )

        self.put_calls += 1

        if key in self.objects:
            return False

        self.objects[key] = body
        return True


class RacingStore(
    FakeStore
):
    def __init__(
        self,
        winner_body: bytes,
    ):
        super().__init__()

        self.winner_body = (
            winner_body
        )

    def put_if_absent(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str,
    ):
        assert (
            content_type
            == "application/json"
        )

        self.put_calls += 1

        if key not in self.objects:
            self.objects[key] = (
                self.winner_body
            )

        return False


def decision(
    minutes,
    *,
    opportunity="UNKNOWN",
    recommendation="PENDING",
    stake=0,
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
            sent_keys=set(),
        )
    )


store = FakeStore()

silent = decision(
    61,
    opportunity="INTERESTING",
)

result = cloud.enqueue_cloud(
    decision=silent,
    store=store,
    now=NOW,
)

assert (
    result["state"]
    == "SKIPPED_SILENT"
)

assert store.objects == {}
assert store.put_calls == 0

print(
    "PASS: SILENT creates no cloud "
    "outbox object."
)


store = FakeStore()

heads_up = decision(
    60,
    opportunity="INTERESTING",
)

first = cloud.enqueue_cloud(
    decision=heads_up,
    store=store,
    now=NOW,
)

expected_key = (
    "notifications/"
    f"{KEY}/HEADS_UP/queued.json"
)

assert (
    first["state"]
    == "QUEUED"
)

assert (
    first["objectKey"]
    == expected_key
)

assert (
    set(
        store.objects
    )
    == {
        expected_key,
    }
)

document = json.loads(
    store.objects[
        expected_key
    ].decode(
        "utf-8"
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
    document["guardrails"][
        "immutableQueueRecord"
    ]
    is True
)

assert (
    document["guardrails"][
        "notificationSent"
    ]
    is False
)

original_bytes = (
    store.objects[
        expected_key
    ]
)

print(
    "PASS: HEADS_UP creates exact "
    "immutable S3 queue key."
)


second = cloud.enqueue_cloud(
    decision=heads_up,
    store=store,
    now=datetime(
        2026,
        10,
        17,
        18,
        1,
        tzinfo=OSLO,
    ),
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
    store.objects[
        expected_key
    ]
    == original_bytes
)

assert store.put_calls == 1

print(
    "PASS: identical cloud enqueue "
    "is idempotent without overwrite."
)


store = FakeStore()

value = decision(
    15,
    opportunity="INTERESTING",
    recommendation="VALUE",
    stake=200,
)

first = cloud.enqueue_cloud(
    decision=value,
    store=store,
    now=NOW,
)

assert (
    first["state"]
    == "QUEUED"
)

final_key = (
    "notifications/"
    f"{KEY}/FINAL/queued.json"
)

original = store.objects[
    final_key
]

attack = decision(
    10,
    opportunity="INTERESTING",
    recommendation="ATTACK",
    stake=400,
)

second = cloud.enqueue_cloud(
    decision=attack,
    store=store,
    now=datetime(
        2026,
        10,
        17,
        18,
        5,
        tzinfo=OSLO,
    ),
)

assert (
    second["state"]
    == "ALREADY_QUEUED"
)

assert (
    second["samePayload"]
    is False
)

assert (
    store.objects[
        final_key
    ]
    == original
)

print(
    "PASS: changed FINAL recommendation "
    "cannot overwrite cloud outbox."
)


# Simulate two workers that both observed
# the key as absent. The other worker wins
# the conditional create.
seed_store = FakeStore()

seed_result = cloud.enqueue_cloud(
    decision=heads_up,
    store=seed_store,
    now=NOW,
)

assert (
    seed_result["state"]
    == "QUEUED"
)

winner_body = (
    seed_store.objects[
        expected_key
    ]
)

racing_store = RacingStore(
    winner_body
)

race_result = cloud.enqueue_cloud(
    decision=heads_up,
    store=racing_store,
    now=NOW,
)

assert (
    race_result["state"]
    == "ALREADY_QUEUED"
)

assert (
    race_result["samePayload"]
    is True
)

assert (
    racing_store.put_calls
    == 1
)

print(
    "PASS: atomic conditional-create "
    "race resolves to existing winner."
)


store = FakeStore()

store.objects[
    expected_key
] = (
    b'{"state":"BROKEN"}\n'
)

try:
    cloud.enqueue_cloud(
        decision=heads_up,
        store=store,
        now=NOW,
    )
except RuntimeError:
    pass
else:
    raise AssertionError(
        "Malformed existing cloud "
        "record did not fail closed."
    )

assert store.put_calls == 0

print(
    "PASS: malformed existing S3 record "
    "fails closed without overwrite."
)


assert (
    cloud.queue_key(
        prefix="notifications/",
        race_day_key=KEY,
        stage="LAST_CALL",
    )
    ==
    "notifications/"
    f"{KEY}/LAST_CALL/queued.json"
)

print(
    "PASS: cloud object-key contract "
    "is deterministic."
)


try:
    cloud.queue_key(
        prefix="../notifications",
        race_day_key=KEY,
        stage="HEADS_UP",
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Unsafe S3 prefix did not fail."
    )

print(
    "PASS: unsafe S3 prefix fails closed."
)


source = CLOUD_PATH.read_text(
    encoding="utf-8"
)

assert (
    'IfNoneMatch="*"'
    in source
)

assert (
    "delete_object"
    not in source
)

assert (
    "copy_object"
    not in source
)

assert (
    "pushover.net"
    not in source
)

assert (
    "eventualvalues"
    not in source
)

assert (
    "raceresults"
    not in source
)

print(
    "PASS: production adapter uses "
    "conditional immutable S3 create "
    "without delivery or outcome APIs."
)
