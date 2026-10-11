from __future__ import annotations

import importlib.util
import json
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

DECIDER_PATH = (
    ROOT
    / "scripts"
    / "decide_v75_notification.py"
)

OUTBOX_PATH = (
    ROOT
    / "scripts"
    / "queue_v75_notification.py"
)

DELIVERY_PATH = (
    ROOT
    / "scripts"
    / "deliver_v75_notification_pushover.py"
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
    "delivery_test_decider",
)

outbox = load_module(
    OUTBOX_PATH,
    "delivery_test_outbox",
)

delivery = load_module(
    DELIVERY_PATH,
    "delivery_test_pushover",
)


def make_queue(
    root: Path,
    *,
    minutes: float,
    opportunity: str = "UNKNOWN",
    recommendation: str = "PENDING",
    stake: int = 0,
) -> Path:
    decision = (
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

    queued = (
        outbox.enqueue_notification(
            decision=decision,
            output_root=root,
            now=NOW,
        )
    )

    assert (
        queued["state"]
        == "QUEUED"
    )

    return (
        root
        / queued["recordPath"]
    )


provider_calls: list[
    dict
] = []


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
            "fake-request-001",
    }


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    queued = make_queue(
        root,
        minutes=60,
        opportunity="INTERESTING",
    )

    first = delivery.deliver(
        queued_json=queued,
        now=NOW,
        app_token=APP_TOKEN,
        user_key=USER_KEY,
        provider_fn=fake_provider,
    )

    assert (
        first["state"]
        == "DELIVERED"
    )

    assert (
        first["priority"]
        == 0
    )

    assert (
        first["title"]
        == "Hest V75 – Heads up"
    )

    assert len(
        provider_calls
    ) == 1

    delivered = (
        queued.parent
        / "delivered.json"
    )

    assert delivered.is_file()

    receipt = json.loads(
        delivered.read_text(
            encoding="utf-8"
        )
    )

    assert (
        receipt["state"]
        == "DELIVERED"
    )

    assert (
        receipt["provider"]
        == "pushover"
    )

    assert (
        receipt["providerRequest"]
        == "fake-request-001"
    )

    all_text = "\n".join(
        path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        for path in root.rglob("*")
        if path.is_file()
    )

    assert (
        APP_TOKEN
        not in all_text
    )

    assert (
        USER_KEY
        not in all_text
    )

    print(
        "PASS: HEADS_UP delivers with "
        "normal priority and persists "
        "no credentials."
    )

    second = delivery.deliver(
        queued_json=queued,
        now=datetime(
            2026,
            10,
            17,
            18,
            1,
            tzinfo=OSLO,
        ),
        app_token=APP_TOKEN,
        user_key=USER_KEY,
        provider_fn=fake_provider,
    )

    assert (
        second["state"]
        == "ALREADY_DELIVERED"
    )

    assert len(
        provider_calls
    ) == 1

    print(
        "PASS: delivered notification "
        "cannot be sent twice."
    )


provider_calls.clear()


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    queued = make_queue(
        root,
        minutes=15,
        opportunity="INTERESTING",
        recommendation="VALUE",
        stake=200,
    )

    result = delivery.deliver(
        queued_json=queued,
        now=NOW,
        app_token=APP_TOKEN,
        user_key=USER_KEY,
        provider_fn=fake_provider,
    )

    assert (
        result["state"]
        == "DELIVERED"
    )

    assert (
        result["priority"]
        == 1
    )

    assert (
        provider_calls[0][
            "ttl"
        ]
        == 1800
    )

    print(
        "PASS: FINAL play notification "
        "uses high priority."
    )


provider_calls.clear()


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    queued = make_queue(
        root,
        minutes=5,
        recommendation="VALUE",
        stake=200,
    )

    result = delivery.deliver(
        queued_json=queued,
        now=NOW,
        app_token=APP_TOKEN,
        user_key=USER_KEY,
        provider_fn=fake_provider,
    )

    assert (
        result["state"]
        == "DELIVERED"
    )

    assert (
        result["priority"]
        == 1
    )

    assert (
        provider_calls[0][
            "ttl"
        ]
        == 600
    )

    print(
        "PASS: LAST_CALL uses high "
        "priority and short TTL."
    )


failure_calls = 0


def failing_provider(
    _payload,
    app_token,
    user_key,
):
    global failure_calls

    failure_calls += 1

    raise RuntimeError(
        "synthetic failure "
        + app_token
        + " "
        + user_key
    )


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    queued = make_queue(
        root,
        minutes=15,
        recommendation="NO_BET",
        stake=0,
    )

    failed = delivery.deliver(
        queued_json=queued,
        now=NOW,
        app_token=APP_TOKEN,
        user_key=USER_KEY,
        provider_fn=failing_provider,
    )

    assert (
        failed["state"]
        == "DELIVERY_FAILED"
    )

    assert (
        failure_calls
        == 1
    )

    assert not (
        queued.parent
        / "delivered.json"
    ).exists()

    failure_files = list(
        (
            queued.parent
            / "delivery-attempts"
        ).glob(
            "*/failure.json"
        )
    )

    assert len(
        failure_files
    ) == 1

    failure_text = (
        failure_files[0]
        .read_text(
            encoding="utf-8"
        )
    )

    assert (
        APP_TOKEN
        not in failure_text
    )

    assert (
        USER_KEY
        not in failure_text
    )

    retry = delivery.deliver(
        queued_json=queued,
        now=datetime(
            2026,
            10,
            17,
            18,
            1,
            tzinfo=OSLO,
        ),
        app_token=APP_TOKEN,
        user_key=USER_KEY,
        provider_fn=fake_provider,
    )

    assert (
        retry["state"]
        == "DELIVERED"
    )

    print(
        "PASS: failed delivery is "
        "auditable, redacted and retryable."
    )


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    queued = make_queue(
        root,
        minutes=60,
        opportunity="INTERESTING",
    )

    unresolved = (
        queued.parent
        / "delivery-attempts"
        / "synthetic"
    )

    unresolved.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        unresolved
        / "attempt.json"
    ).write_text(
        json.dumps(
            {
                "state":
                    "STARTED",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    before = len(
        provider_calls
    )

    result = delivery.deliver(
        queued_json=queued,
        now=NOW,
        app_token=APP_TOKEN,
        user_key=USER_KEY,
        provider_fn=fake_provider,
    )

    assert (
        result["state"]
        == "DELIVERY_UNCERTAIN"
    )

    assert len(
        provider_calls
    ) == before

    print(
        "PASS: uncertain prior attempt "
        "fails closed instead of risking "
        "duplicate delivery."
    )


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    queued = make_queue(
        root,
        minutes=60,
        opportunity="INTERESTING",
    )

    record = json.loads(
        queued.read_text(
            encoding="utf-8"
        )
    )

    record[
        "notificationKey"
    ] = (
        f"{KEY}:FINAL"
    )

    queued.write_text(
        json.dumps(
            record,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        delivery.deliver(
            queued_json=queued,
            now=NOW,
            app_token=APP_TOKEN,
            user_key=USER_KEY,
            provider_fn=fake_provider,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Malformed queue identity "
            "did not fail closed."
        )

    print(
        "PASS: malformed queued identity "
        "fails before provider invocation."
    )


source = DELIVERY_PATH.read_text(
    encoding="utf-8"
)

assert (
    "https://api.pushover.net/1/messages.json"
    in source
)

assert (
    "PUSHOVER_APP_TOKEN"
    in source
)

assert (
    "PUSHOVER_USER_KEY"
    in source
)

assert (
    "priority"
    in source
)

assert (
    '"retry":'
    not in source
)

assert (
    '"expire":'
    not in source
)

print(
    "PASS: delivery v1 targets Pushover "
    "without emergency-priority semantics."
)
