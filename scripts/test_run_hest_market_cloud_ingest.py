from __future__ import annotations

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RUNNER_PATH = (
    ROOT
    / "scripts"
    / "run_hest_market_cloud_ingest.py"
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


runner = load_module(
    RUNNER_PATH,
    "hest_market_runner_tested",
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

        self.list_calls: list[
            str
        ] = []

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
        assert content_type

        if key in self.objects:
            return False

        self.objects[
            key
        ] = body

        return True

    def list_keys(
        self,
        prefix: str,
    ):
        self.list_calls.append(
            prefix
        )

        return sorted(
            key
            for key
            in self.objects
            if key.startswith(
                prefix
            )
        )


STATE_KEY = "state/upcoming.json"

TARGET_DATE = "2026-10-17"
TARGET_RACE = "BT_NR_2026-10-17"

OTHER_DATE = "2026-10-18"
OTHER_RACE = "BI_NR_2026-10-18"


def json_bytes(
    payload,
):
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode(
        "utf-8"
    )


def seed_state(
    store: FakeStore,
    *,
    target: dict | None,
):
    store.objects[
        STATE_KEY
    ] = json_bytes(
        {
            "schemaVersion":
                "2.0",
            "target":
                target,
        }
    )


def source_capture(
    *,
    race_date: str,
    race_day_key: str,
    stamp: str,
    captured_at: str,
    start_time: str,
    raw_body: bytes,
    status:
        str = "MARKET_AVAILABLE",
    response_sha:
        str | None = None,
):
    base = (
        f"market/{race_date}/"
        f"{race_day_key}/{stamp}"
    )

    manifest_key = (
        f"{base}/manifest.json"
    )

    raw_key = (
        f"{base}/"
        "investment-response.json"
    )

    sha = hashlib.sha256(
        raw_body
    ).hexdigest()

    manifest = {
        "schemaVersion":
            "2.0",
        "collector":
            "v75-market-cloud-v2",
        "capturedAt":
            captured_at,
        "localDate":
            race_date,
        "localDateTime":
            captured_at[:19],
        "raceDate":
            race_date,
        "raceDayKey":
            race_day_key,
        "raceDayName":
            "Test",
        "firstRaceNumber":
            5,
        "startTime":
            start_time,
        "minutesToStart":
            60.0,
        "endpoint":
            (
                f"/api/game/"
                f"{race_day_key}/"
                "betdistribution/"
                "investment/V75"
                "?raceNumber=5"
            ),
        "status":
            status,
        "responseSha256":
            (
                response_sha
                if response_sha
                is not None
                else sha
            ),
        "updatedTimes": [
            captured_at,
        ],
        "updatedTimeZone":
            "Europe/Oslo",
        "scratchCount":
            0,
        "guardrails": {
            "preRaceCollectionPurpose":
                True,
            "resultOutcomeEndpointUsed":
                False,
            "outcomesUsed":
                False,
            "modelUsed":
                False,
            "modelRetuned":
                False,
        },
    }

    return (
        manifest_key,
        raw_key,
        manifest,
        raw_body,
    )


def add_capture(
    store: FakeStore,
    capture,
):
    (
        manifest_key,
        raw_key,
        manifest,
        raw_body,
    ) = capture

    store.objects[
        manifest_key
    ] = json_bytes(
        manifest
    )

    store.objects[
        raw_key
    ] = raw_body

    return (
        manifest_key,
        raw_key,
    )


# 1. Target-mode sync discovers only
# current target Market manifests.
store = FakeStore()

seed_state(
    store,
    target={
        "raceDate":
            TARGET_DATE,
        "raceDayKey":
            TARGET_RACE,
    },
)

raw1 = (
    b'{"capture":1,'
    b'"percentage":18.2}\n'
)

raw2 = (
    b'{"capture":2,'
    b'"percentage":20.1}\n'
)

raw_unavailable = (
    b'{"capture":3,'
    b'"market":[]}\n'
)

key1, raw_key1 = add_capture(
    store,
    source_capture(
        race_date=
            TARGET_DATE,
        race_day_key=
            TARGET_RACE,
        stamp=
            "20261017T150000000Z",
        captured_at=
            "2026-10-17T15:00:00.000Z",
        start_time=
            "2026-10-17T19:00:00+02:00",
        raw_body=raw1,
    ),
)

key2, raw_key2 = add_capture(
    store,
    source_capture(
        race_date=
            TARGET_DATE,
        race_day_key=
            TARGET_RACE,
        stamp=
            "20261017T153000000Z",
        captured_at=
            "2026-10-17T15:30:00.000Z",
        start_time=
            "2026-10-17T19:00:00+02:00",
        raw_body=raw2,
    ),
)

key_unavailable, _ = add_capture(
    store,
    source_capture(
        race_date=
            TARGET_DATE,
        race_day_key=
            TARGET_RACE,
        stamp=
            "20261017T140000000Z",
        captured_at=
            "2026-10-17T14:00:00.000Z",
        start_time=
            "2026-10-17T19:00:00+02:00",
        raw_body=
            raw_unavailable,
        status=(
            "V75_FOUND_MARKET_"
            "NOT_AVAILABLE"
        ),
    ),
)

other_key, other_raw_key = add_capture(
    store,
    source_capture(
        race_date=
            OTHER_DATE,
        race_day_key=
            OTHER_RACE,
        stamp=
            "20261018T150000000Z",
        captured_at=
            "2026-10-18T15:00:00.000Z",
        start_time=
            "2026-10-18T19:00:00+02:00",
        raw_body=
            b'{"other":true}\n',
    ),
)

store.objects[
    (
        f"market/{TARGET_DATE}/"
        f"{TARGET_RACE}/"
        "README.txt"
    )
] = b"ignore me\n"

source_before = {
    key:
        bytes(value)
    for key, value
    in store.objects.items()
    if key.startswith(
        "market/"
    )
}

first = runner.run_sync(
    store=store,
    state_key=STATE_KEY,
    hest_prefix=
        "hest-data-test",
)

assert (
    first["state"]
    == "SYNC_COMPLETE"
)

assert (
    first["mode"]
    == "TARGET"
)

assert (
    first["sourcePrefix"]
    ==
    (
        f"market/{TARGET_DATE}/"
        f"{TARGET_RACE}/"
    )
)

assert (
    first["sourceManifestCount"]
    == 3
)

assert (
    first["eligibleManifestCount"]
    == 2
)

assert (
    first["registered"]
    == 2
)

assert (
    first["alreadyRegistered"]
    == 0
)

assert (
    first[
        "skippedMarketUnavailable"
    ]
    == 1
)

assert (
    set(
        first[
            "ingestedManifestKeys"
        ]
    )
    == {
        key1,
        key2,
    }
)

assert (
    other_key
    not in first[
        "ingestedManifestKeys"
    ]
)

print(
    "PASS: target runner ingests "
    "only current-target available "
    "Market captures."
)


# 2. Source objects are read-only.
for key, body in (
    source_before.items()
):
    assert (
        store.objects[key]
        == body
    )

assert (
    store.objects[
        raw_key1
    ]
    == raw1
)

assert (
    store.objects[
        raw_key2
    ]
    == raw2
)

assert (
    store.objects[
        other_raw_key
    ]
    == b'{"other":true}\n'
)

print(
    "PASS: source Market objects "
    "are never modified."
)


# 3. Resulting Hest observations
# preserve both raw captures.
hest_raw_keys = sorted(
    key
    for key
    in store.objects
    if key.startswith(
        "hest-data-test/raw/"
        "rikstoto-market-cloud/"
    )
)

hest_observation_keys = sorted(
    key
    for key
    in store.objects
    if key.startswith(
        "hest-data-test/"
        "observations/"
        "rikstoto-market-cloud/"
    )
)

assert len(
    hest_raw_keys
) == 2

assert len(
    hest_observation_keys
) == 2

assert {
    store.objects[key]
    for key
    in hest_raw_keys
} == {
    raw1,
    raw2,
}

print(
    "PASS: every available Market "
    "capture becomes its own immutable "
    "Hest observation."
)


# 4. A repeated run is idempotent.
second = runner.run_sync(
    store=store,
    state_key=STATE_KEY,
    hest_prefix=
        "hest-data-test",
)

assert (
    second["registered"]
    == 0
)

assert (
    second["alreadyRegistered"]
    == 2
)

assert (
    second[
        "skippedMarketUnavailable"
    ]
    == 1
)

assert len(
    [
        key
        for key
        in store.objects
        if key.startswith(
            "hest-data-test/"
        )
    ]
) == 4

print(
    "PASS: repeated runner is "
    "idempotent across cron runs."
)


# 5. Target mode only lists the
# current race prefix.
expected_prefix = (
    f"market/{TARGET_DATE}/"
    f"{TARGET_RACE}/"
)

assert store.list_calls
assert all(
    value
    == expected_prefix
    for value
    in store.list_calls
)

print(
    "PASS: normal cron mode limits "
    "listing to the current target."
)


# 6. No target is a clean no-op.
no_target = FakeStore()

seed_state(
    no_target,
    target=None,
)

result = runner.run_sync(
    store=no_target,
    state_key=STATE_KEY,
    hest_prefix=
        "hest-data-test",
)

assert (
    result["state"]
    == "NO_TARGET"
)

assert (
    result["sourceManifestCount"]
    == 0
)

assert (
    no_target.list_calls
    == []
)

print(
    "PASS: missing current target "
    "is a clean no-op."
)


# 7. Malformed available capture
# fails closed rather than being skipped.
bad_store = FakeStore()

seed_state(
    bad_store,
    target={
        "raceDate":
            TARGET_DATE,
        "raceDayKey":
            TARGET_RACE,
    },
)

add_capture(
    bad_store,
    source_capture(
        race_date=
            TARGET_DATE,
        race_day_key=
            TARGET_RACE,
        stamp=
            "20261017T160000000Z",
        captured_at=
            "2026-10-17T16:00:00.000Z",
        start_time=
            "2026-10-17T19:00:00+02:00",
        raw_body=
            b'{"bad":"sha"}\n',
        response_sha=
            "0" * 64,
    ),
)

try:
    runner.run_sync(
        store=bad_store,
        state_key=
            STATE_KEY,
        hest_prefix=
            "hest-data-test",
    )
except ValueError as exc:
    assert (
        "SHA256"
        in str(exc)
    )
else:
    raise AssertionError(
        "Malformed available Market "
        "capture was silently skipped."
    )

print(
    "PASS: malformed source capture "
    "fails closed."
)


# 8. Explicit all-market mode can
# backfill multiple race days.
backfill = FakeStore()

seed_state(
    backfill,
    target=None,
)

backfill_target, _ = add_capture(
    backfill,
    source_capture(
        race_date=
            TARGET_DATE,
        race_day_key=
            TARGET_RACE,
        stamp=
            "20261017T150000000Z",
        captured_at=
            "2026-10-17T15:00:00.000Z",
        start_time=
            "2026-10-17T19:00:00+02:00",
        raw_body=
            b'{"backfill":1}\n',
    ),
)

backfill_other, _ = add_capture(
    backfill,
    source_capture(
        race_date=
            OTHER_DATE,
        race_day_key=
            OTHER_RACE,
        stamp=
            "20261018T150000000Z",
        captured_at=
            "2026-10-18T15:00:00.000Z",
        start_time=
            "2026-10-18T19:00:00+02:00",
        raw_body=
            b'{"backfill":2}\n',
    ),
)

backfill_result = (
    runner.run_sync(
        store=backfill,
        state_key=
            STATE_KEY,
        hest_prefix=
            "hest-data-test",
        all_market=True,
    )
)

assert (
    backfill_result["mode"]
    == "ALL_MARKET"
)

assert (
    backfill_result["sourcePrefix"]
    == "market/"
)

assert (
    backfill_result[
        "sourceManifestCount"
    ]
    == 2
)

assert (
    backfill_result["registered"]
    == 2
)

assert (
    set(
        backfill_result[
            "ingestedManifestKeys"
        ]
    )
    == {
        backfill_target,
        backfill_other,
    }
)

print(
    "PASS: explicit all-market mode "
    "supports one-time historical "
    "backfill."
)


# 9. Unsafe source prefixes fail closed.
for value in (
    "../market",
    "pre-race",
    "market/../state",
    "",
):
    try:
        runner.validate_source_prefix(
            value
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Unsafe source prefix "
            f"accepted: {value!r}"
        )

print(
    "PASS: source-prefix boundaries "
    "fail closed."
)


# 10. Runner itself has no Rikstoto
# HTTP calls, results APIs, model logic,
# notifications or betting.
source = RUNNER_PATH.read_text(
    encoding="utf-8"
)

for forbidden in (
    "urllib.request",
    "requests.get",
    "rikstoto.no/api",
    "eventualvalues",
    "raceresults",
    "pushover.net",
    "optimize_budget",
    "candidate_v2a",
    "submit_bet",
):
    assert (
        forbidden not in source
    )

print(
    "PASS: runner uses only our "
    "existing S3 capture archive."
)

print()
print(
    "PASS: Hest Cloud Market "
    "Ingest Runner v1 offline "
    "contract green."
)
