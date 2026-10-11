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

S3_OUTBOX_PATH = (
    ROOT
    / "scripts"
    / "queue_v75_notification_s3.py"
)

RUNTIME_PATH = (
    ROOT
    / "scripts"
    / "run_v75_notification_runtime.py"
)

OSLO = ZoneInfo("Europe/Oslo")

KEY = "BT_NR_2026-10-17"
NAME = "Bergen"

APP_TOKEN = (
    "TEST_APP_SECRET_NEVER_PERSIST"
)

USER_KEY = (
    "TEST_USER_SECRET_NEVER_PERSIST"
)

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
    "runtime_test_decider",
)

s3_outbox = load_module(
    S3_OUTBOX_PATH,
    "runtime_test_s3_outbox",
)

runtime = load_module(
    RUNTIME_PATH,
    "runtime_test_runner",
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

    def get_bytes(
        self,
        key: str,
    ):
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

        if key in self.objects:
            return False

        self.objects[key] = body
        return True

    def list_keys(
        self,
        prefix: str,
    ):
        root = (
            prefix.rstrip("/")
            + "/"
        )

        return sorted(
            key
            for key
            in self.objects
            if key.startswith(
                root
            )
        )


def make_decision():
    return (
        decider.decide_notification(
            race_day_key=KEY,
            race_day_name=NAME,
            minutes_to_start=60,
            opportunity="INTERESTING",
            recommendation="PENDING",
            stake_nok=0,
            sent_keys=set(),
        )
    )


def queue(
    store,
    *,
    prefix="notifications",
):
    result = (
        s3_outbox.enqueue_cloud(
            decision=
                make_decision(),
            store=store,
            now=NOW,
            prefix=prefix,
        )
    )

    assert (
        result["state"]
        == "QUEUED"
    )

    return result[
        "objectKey"
    ]


provider_calls = []


def fake_provider(
    payload,
    app_token,
    user_key,
):
    assert (
        app_token
        == APP_TOKEN
    )

    assert (
        user_key
        == USER_KEY
    )

    provider_calls.append(
        dict(payload)
    )

    return {
        "status":
            1,
        "request":
            "runtime-provider-001",
    }


# Disabled is the production-safe default:
# discovery is allowed, provider is not.
store = FakeStore()

queued_key = queue(
    store
)

disabled = runtime.run_runtime(
    store=store,
    now=NOW,
    enabled=False,
)

assert (
    disabled["state"]
    == "DISABLED"
)

assert (
    disabled["queuedCount"]
    == 1
)

assert (
    disabled["processedCount"]
    == 0
)

assert provider_calls == []

assert not any(
    key.endswith(
        "/delivered.json"
    )
    for key
    in store.objects
)

print(
    "PASS: disabled runtime discovers "
    "queue but cannot deliver."
)


# Production prefix must not discover
# smoke-test notification objects.
queue(
    store,
    prefix=
        "notifications-smoke",
)

keys = (
    runtime.discover_queue_keys(
        store=store,
        prefix="notifications",
    )
)

assert keys == [
    queued_key,
]

print(
    "PASS: production runtime ignores "
    "notifications-smoke prefix."
)


# Enabled runtime delivers exactly once.
active = runtime.run_runtime(
    store=store,
    now=NOW,
    enabled=True,
    app_token=
        APP_TOKEN,
    user_key=
        USER_KEY,
    provider_fn=
        fake_provider,
)

assert (
    active["state"]
    == "ACTIVE"
)

assert (
    active["processedCount"]
    == 1
)

assert (
    active["counts"][
        "DELIVERED"
    ]
    == 1
)

assert len(
    provider_calls
) == 1

print(
    "PASS: enabled runtime delivers "
    "queued production notification."
)


# Next cron iteration must not send again.
again = runtime.run_runtime(
    store=store,
    now=NOW,
    enabled=True,
    app_token=
        APP_TOKEN,
    user_key=
        USER_KEY,
    provider_fn=
        fake_provider,
)

assert (
    again["state"]
    == "ACTIVE"
)

assert (
    again["counts"][
        "ALREADY_DELIVERED"
    ]
    == 1
)

assert len(
    provider_calls
) == 1

print(
    "PASS: repeated runtime is "
    "idempotent across cron executions."
)


# Credentials must never enter S3 objects.
all_text = "\n".join(
    body.decode(
        "utf-8",
        errors="replace",
    )
    for body
    in store.objects.values()
)

assert APP_TOKEN not in all_text
assert USER_KEY not in all_text

print(
    "PASS: runtime persists no "
    "Pushover credentials."
)


# Exact queue path shape only.
assert runtime.is_queue_key(
    key=(
        f"notifications/{KEY}/"
        "HEADS_UP/queued.json"
    ),
    prefix="notifications",
)

assert not runtime.is_queue_key(
    key=(
        f"notifications/{KEY}/"
        "HEADS_UP/delivered.json"
    ),
    prefix="notifications",
)

assert not runtime.is_queue_key(
    key=(
        f"notifications/{KEY}/"
        "HEADS_UP/delivery-attempts/"
        "0001/attempt.json"
    ),
    prefix="notifications",
)

print(
    "PASS: runtime only discovers "
    "canonical queued.json objects."
)


# Malformed queue content cannot reach
# the provider and degrades safely.
store = FakeStore()

bad_key = (
    f"notifications/{KEY}/"
    "HEADS_UP/queued.json"
)

store.objects[
    bad_key
] = (
    b'{"state":"BROKEN"}\n'
)

before = len(
    provider_calls
)

degraded = runtime.run_runtime(
    store=store,
    now=NOW,
    enabled=True,
    app_token=
        APP_TOKEN,
    user_key=
        USER_KEY,
    provider_fn=
        fake_provider,
)

assert (
    degraded["state"]
    == "DEGRADED"
)

assert (
    degraded["counts"][
        "RUNTIME_ERROR"
    ]
    == 1
)

assert len(
    provider_calls
) == before

assert (
    degraded["results"][0][
        "reason"
    ]
    ==
    "DELIVERY_RUNTIME_EXCEPTION"
)

print(
    "PASS: malformed queue fails closed "
    "without provider invocation."
)


# Unknown enable value must fail rather
# than accidentally enabling delivery.
try:
    runtime.parse_enabled(
        "maybe"
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Invalid enable flag "
        "did not fail closed."
    )

assert (
    runtime.parse_enabled(
        ""
    )
    is False
)

assert (
    runtime.parse_enabled(
        "false"
    )
    is False
)

assert (
    runtime.parse_enabled(
        "true"
    )
    is True
)

print(
    "PASS: production enable flag "
    "defaults and validates fail closed."
)


source = RUNTIME_PATH.read_text(
    encoding="utf-8"
)

assert (
    "V75_NOTIFICATION_DELIVERY_ENABLED"
    in source
)

assert (
    "notifications-smoke"
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

assert (
    "automaticBetSubmission"
    in source
)

print(
    "PASS: runtime v1 has no outcome "
    "or automatic betting capability."
)
