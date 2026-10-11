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

DELIVERY_PATH = (
    ROOT
    / "scripts"
    / "deliver_v75_notification_s3_pushover.py"
)

OSLO = ZoneInfo("Europe/Oslo")

KEY = "BT_NR_2026-10-17"
NAME = "Bergen"

APP_TOKEN = "TEST_APP_SECRET_NEVER_PERSIST"
USER_KEY = "TEST_USER_SECRET_NEVER_PERSIST"

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
    "cloud_delivery_test_decider",
)

s3_outbox = load_module(
    S3_OUTBOX_PATH,
    "cloud_delivery_test_outbox",
)

delivery = load_module(
    DELIVERY_PATH,
    "cloud_delivery_test_adapter",
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


def make_decision(
    *,
    minutes=60,
    opportunity="INTERESTING",
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


def queue(
    store,
    decision,
):
    result = (
        s3_outbox.enqueue_cloud(
            decision=decision,
            store=store,
            now=NOW,
        )
    )

    assert (
        result["state"]
        == "QUEUED"
    )

    return result["objectKey"]


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
            "fake-cloud-request-001",
    }


store = FakeStore()

queued_key = queue(
    store,
    make_decision(),
)

first = delivery.deliver_cloud(
    queued_key=queued_key,
    store=store,
    now=NOW,
    app_token=APP_TOKEN,
    user_key=USER_KEY,
    provider_fn=fake_provider,
)

assert first["state"] == "DELIVERED"
assert first["attemptNumber"] == 1
assert len(provider_calls) == 1

base = (
    f"notifications/{KEY}/HEADS_UP"
)

assert (
    f"{base}/delivery-attempts/"
    "0001/attempt.json"
    in store.objects
)

assert (
    f"{base}/delivery-attempts/"
    "0001/provider-result.json"
    in store.objects
)

assert (
    f"{base}/delivered.json"
    in store.objects
)

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
    "PASS: cloud HEADS_UP delivers once "
    "and persists no credentials."
)


second = delivery.deliver_cloud(
    queued_key=queued_key,
    store=store,
    now=NOW,
    app_token=APP_TOKEN,
    user_key=USER_KEY,
    provider_fn=fake_provider,
)

assert (
    second["state"]
    == "ALREADY_DELIVERED"
)

assert len(provider_calls) == 1

print(
    "PASS: delivered cloud notification "
    "cannot invoke provider twice."
)


# Crash window after provider acceptance:
# provider-result exists but delivered.json
# is missing. Recovery must create the
# receipt without calling Pushover again.
store = FakeStore()

queued_key = queue(
    store,
    make_decision(),
)

record = json.loads(
    store.objects[
        queued_key
    ].decode("utf-8")
)

profile = {
    "title":
        "Hest V75 – Heads up",
    "priority":
        0,
    "ttl":
        3600,
}

attempt_root = (
    f"notifications/{KEY}/HEADS_UP/"
    "delivery-attempts/0001"
)

attempt = {
    "schemaVersion":
        "1.0",
    "delivery":
        "v75-s3-pushover-delivery-v1",
    "state":
        "STARTED",
    "attemptNumber":
        1,
    "notificationKey":
        record["notificationKey"],
    "startedAt":
        NOW.isoformat(),
    "queuedPayloadSha256":
        record["payloadSha256"],
    "provider":
        "pushover",
    "providerPayload": {
        "message":
            record["message"],
        "title":
            profile["title"],
        "priority":
            profile["priority"],
        "ttl":
            profile["ttl"],
    },
    "guardrails": {
        "credentialsPersisted":
            False,
        "notificationSent":
            False,
        "repoWrites":
            False,
    },
}

provider_result = {
    "schemaVersion":
        "1.0",
    "state":
        "PROVIDER_ACCEPTED",
    "provider":
        "pushover",
    "attemptNumber":
        1,
    "notificationKey":
        record["notificationKey"],
    "request":
        "accepted-before-crash",
    "acceptedAt":
        NOW.isoformat(),
}

store.objects[
    f"{attempt_root}/attempt.json"
] = s3_outbox.json_bytes(
    attempt
)

store.objects[
    f"{attempt_root}/provider-result.json"
] = s3_outbox.json_bytes(
    provider_result
)

before = len(
    provider_calls
)

recovered = delivery.deliver_cloud(
    queued_key=queued_key,
    store=store,
    now=NOW,
    app_token=APP_TOKEN,
    user_key=USER_KEY,
    provider_fn=fake_provider,
)

assert (
    recovered["state"]
    == "DELIVERED_RECOVERED"
)

assert len(
    provider_calls
) == before

assert (
    f"notifications/{KEY}/HEADS_UP/"
    "delivered.json"
    in store.objects
)

print(
    "PASS: accepted provider result "
    "recovers delivered receipt without "
    "duplicate send."
)


# Definite provider rejection can safely
# use the next deterministic attempt.
store = FakeStore()

queued_key = queue(
    store,
    make_decision(),
)

def rejected_provider(
    _payload,
    _app_token,
    _user_key,
):
    raise RuntimeError(
        "HTTP 400: synthetic rejection"
    )


failed = delivery.deliver_cloud(
    queued_key=queued_key,
    store=store,
    now=NOW,
    app_token=APP_TOKEN,
    user_key=USER_KEY,
    provider_fn=
        rejected_provider,
)

assert (
    failed["state"]
    == "DELIVERY_FAILED"
)

assert (
    failed["failureClass"]
    == "DEFINITE_REJECTION"
)

assert (
    failed["retryable"]
    is True
)

retry_calls = []


def retry_provider(
    payload,
    _app_token,
    _user_key,
):
    retry_calls.append(
        dict(payload)
    )

    return {
        "status":
            1,
        "request":
            "retry-success",
    }


retried = delivery.deliver_cloud(
    queued_key=queued_key,
    store=store,
    now=NOW,
    app_token=APP_TOKEN,
    user_key=USER_KEY,
    provider_fn=
        retry_provider,
)

assert (
    retried["state"]
    == "DELIVERED"
)

assert (
    retried["attemptNumber"]
    == 2
)

assert len(retry_calls) == 1

print(
    "PASS: definite rejection retries "
    "through next immutable attempt slot."
)


# Ambiguous network result must fail
# closed forever unless manually resolved.
store = FakeStore()

queued_key = queue(
    store,
    make_decision(),
)

ambiguous_calls = 0


def ambiguous_provider(
    _payload,
    _app_token,
    _user_key,
):
    global ambiguous_calls

    ambiguous_calls += 1

    raise RuntimeError(
        "Pushover network error: "
        "synthetic timeout"
    )


uncertain = delivery.deliver_cloud(
    queued_key=queued_key,
    store=store,
    now=NOW,
    app_token=APP_TOKEN,
    user_key=USER_KEY,
    provider_fn=
        ambiguous_provider,
)

assert (
    uncertain["state"]
    == "DELIVERY_UNCERTAIN"
)

assert (
    uncertain["retryable"]
    is False
)

assert ambiguous_calls == 1

again = delivery.deliver_cloud(
    queued_key=queued_key,
    store=store,
    now=NOW,
    app_token=APP_TOKEN,
    user_key=USER_KEY,
    provider_fn=
        ambiguous_provider,
)

assert (
    again["state"]
    == "DELIVERY_UNCERTAIN"
)

assert ambiguous_calls == 1

print(
    "PASS: ambiguous provider result "
    "fails closed without duplicate retry."
)


# A concurrent worker that sees an
# acquired attempt but no terminal result
# must not invoke the provider.
store = FakeStore()

queued_key = queue(
    store,
    make_decision(),
)

record = json.loads(
    store.objects[
        queued_key
    ].decode("utf-8")
)

attempt_root = (
    f"notifications/{KEY}/HEADS_UP/"
    "delivery-attempts/0001"
)

store.objects[
    f"{attempt_root}/attempt.json"
] = s3_outbox.json_bytes(
    {
        "schemaVersion":
            "1.0",
        "delivery":
            "v75-s3-pushover-delivery-v1",
        "state":
            "STARTED",
        "attemptNumber":
            1,
        "notificationKey":
            record["notificationKey"],
        "startedAt":
            NOW.isoformat(),
        "queuedPayloadSha256":
            record["payloadSha256"],
        "provider":
            "pushover",
        "providerPayload": {
            "message":
                record["message"],
            "title":
                "Hest V75 – Heads up",
            "priority":
                0,
            "ttl":
                3600,
        },
        "guardrails": {
            "credentialsPersisted":
                False,
            "notificationSent":
                False,
            "repoWrites":
                False,
        },
    }
)

before = len(
    provider_calls
)

concurrent = delivery.deliver_cloud(
    queued_key=queued_key,
    store=store,
    now=NOW,
    app_token=APP_TOKEN,
    user_key=USER_KEY,
    provider_fn=fake_provider,
)

assert (
    concurrent["state"]
    == "DELIVERY_UNCERTAIN"
)

assert (
    concurrent["reason"]
    == "ATTEMPT_IN_PROGRESS_OR_CRASHED"
)

assert len(
    provider_calls
) == before

print(
    "PASS: concurrent/crashed attempt "
    "cannot trigger a second provider call."
)


# Queue identity mismatch must fail before
# any attempt or provider invocation.
store = FakeStore()

queued_key = queue(
    store,
    make_decision(),
)

document = json.loads(
    store.objects[
        queued_key
    ].decode("utf-8")
)

document[
    "notificationKey"
] = f"{KEY}:FINAL"

store.objects[
    queued_key
] = s3_outbox.json_bytes(
    document
)

before_count = len(
    store.objects
)

try:
    delivery.deliver_cloud(
        queued_key=queued_key,
        store=store,
        now=NOW,
        app_token=APP_TOKEN,
        user_key=USER_KEY,
        provider_fn=fake_provider,
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Malformed cloud queue identity "
        "did not fail closed."
    )

assert len(
    store.objects
) == before_count

print(
    "PASS: malformed cloud queue identity "
    "fails before delivery attempt."
)


source = DELIVERY_PATH.read_text(
    encoding="utf-8"
)

assert (
    "pushover_provider"
    in source
)

assert (
    "IfNoneMatch"
    not in source
)

assert (
    "put_if_absent"
    in source
)

assert (
    "delete_object"
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
    "AMBIGUOUS"
    in source
)

print(
    "PASS: cloud delivery v1 uses "
    "immutable receipts and conservative "
    "duplicate protection."
)
