from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BRIDGE_PATH = (
    ROOT
    / "scripts"
    / "ingest_v75_market_cloud_to_hest.py"
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


bridge = load_module(
    BRIDGE_PATH,
    "market_cloud_to_hest_tested",
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
        assert content_type

        if key in self.objects:
            return False

        self.objects[
            key
        ] = body

        return True


MANIFEST_KEY = (
    "market/"
    "2026-10-17/"
    "BT_NR_2026-10-17/"
    "20261017T160000000Z/"
    "manifest.json"
)

RAW_KEY = (
    "market/"
    "2026-10-17/"
    "BT_NR_2026-10-17/"
    "20261017T160000000Z/"
    "investment-response.json"
)

RAW = (
    b'{"success":true,"result":['
    b'{"raceNumber":5,'
    b'"updatedTime":"2026-10-17T17:59:40+02:00",'
    b'"investmentDistribution":['
    b'{"startNumber":7,'
    b'"percentage":18.2,'
    b'"ranking":3,'
    b'"investment":182000}'
    b']}]}\n'
)


def manifest(
    *,
    raw_body:
        bytes = RAW,
    response_sha:
        str | None = None,
    status:
        str = "MARKET_AVAILABLE",
    collector:
        str = "v75-market-cloud-v2",
    captured_at:
        str = "2026-10-17T16:00:00.000Z",
    start_time:
        str | None = "2026-10-17T19:00:00+02:00",
    outcomes_used:
        bool = False,
) -> dict:
    actual_sha = hashlib.sha256(
        raw_body
    ).hexdigest()

    return {
        "schemaVersion":
            "2.0",
        "collector":
            collector,
        "capturedAt":
            captured_at,
        "localDate":
            "2026-10-17",
        "localDateTime":
            "2026-10-17T18:00:00",
        "raceDate":
            "2026-10-17",
        "raceDayKey":
            "BT_NR_2026-10-17",
        "raceDayName":
            "Bergen",
        "firstRaceNumber":
            5,
        "startTime":
            start_time,
        "minutesToStart":
            60.0,
        "endpoint":
            (
                "/api/game/"
                "BT_NR_2026-10-17/"
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
                else actual_sha
            ),
        "updatedTimes": [
            (
                "2026-10-17"
                "T17:59:40+02:00"
            ),
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
                outcomes_used,
            "modelUsed":
                False,
            "modelRetuned":
                False,
        },
    }


def seed_store(
    *,
    manifest_doc: dict | None = None,
    raw_body:
        bytes = RAW,
) -> FakeStore:
    store = FakeStore()

    if manifest_doc is None:
        manifest_doc = manifest(
            raw_body=raw_body
        )

    store.objects[
        MANIFEST_KEY
    ] = (
        json.dumps(
            manifest_doc,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode(
        "utf-8"
    )

    store.objects[
        RAW_KEY
    ] = raw_body

    return store


# 1. Existing Railway capture becomes
# immutable Hest pre-race data.
store = seed_store()

first = (
    bridge
    .ingest_cloud_capture(
        store=store,
        manifest_key=
            MANIFEST_KEY,
        prefix=
            "hest-data-test",
    )
)

assert (
    first["state"]
    == "REGISTERED"
)

assert (
    first["ingest"]
    == "v75-market-cloud-to-hest-v1"
)

assert (
    first["sourceCollector"]
    == "v75-market-cloud-v2"
)

assert (
    first[
        "sourceManifestKey"
    ]
    == MANIFEST_KEY
)

assert (
    first[
        "sourceRawKey"
    ]
    == RAW_KEY
)

assert (
    first[
        "sourceRawSha256Verified"
    ]
    is True
)

assert (
    first["knowledgePhase"]
    == "PRE_RACE"
)

assert (
    first[
        "eligibleForPreRaceFeatures"
    ]
    is True
)

print(
    "PASS: existing Railway Market "
    "capture becomes immutable "
    "pre-race Hest data."
)


# 2. Source raw bytes are preserved
# exactly, not reserialized JSON.
assert (
    store.objects[
        first[
            "rawObjectKey"
        ]
    ]
    == RAW
)

assert (
    first["rawSha256"]
    == hashlib.sha256(
        RAW
    ).hexdigest()
)

print(
    "PASS: Railway Market raw bytes "
    "survive bridge exactly."
)


# 3. Provenance is retained.
observation = json.loads(
    store.objects[
        first[
            "observationObjectKey"
        ]
    ].decode(
        "utf-8"
    )
)

assert (
    observation[
        "source"
    ][
        "name"
    ]
    == "rikstoto-market-cloud"
)

assert (
    observation[
        "source"
    ][
        "category"
    ]
    == "MARKET"
)

assert (
    observation[
        "source"
    ][
        "locator"
    ]
    ==
    (
        "https://www.rikstoto.no"
        "/api/game/"
        "BT_NR_2026-10-17/"
        "betdistribution/"
        "investment/V75"
        "?raceNumber=5"
    )
)

assert (
    observation[
        "subject"
    ][
        "entities"
    ][
        "firstRaceNumber"
    ]
    == "5"
)

assert (
    observation[
        "observation"
    ][
        "capturedAt"
    ]
    == "2026-10-17T18:00:00+02:00"
)

assert (
    observation[
        "observation"
    ][
        "raceStartAt"
    ]
    == "2026-10-17T19:00:00+02:00"
)

print(
    "PASS: Railway Market provenance "
    "and timing are retained."
)


# 4. Re-ingest is idempotent.
second = (
    bridge
    .ingest_cloud_capture(
        store=store,
        manifest_key=
            MANIFEST_KEY,
        prefix=
            "hest-data-test",
    )
)

assert (
    second["state"]
    == "ALREADY_REGISTERED"
)

print(
    "PASS: repeated cloud Market "
    "bridge is idempotent."
)


# 5. Tampered source bytes fail before
# Hest storage can occur.
tampered_store = seed_store(
    manifest_doc=manifest(
        response_sha="0" * 64
    )
)

initial_keys = set(
    tampered_store.objects
)

try:
    bridge.ingest_cloud_capture(
        store=tampered_store,
        manifest_key=
            MANIFEST_KEY,
        prefix=
            "hest-data-test",
    )
except ValueError as exc:
    assert (
        "SHA256"
        in str(exc)
    )
else:
    raise AssertionError(
        "Tampered cloud Market "
        "capture was accepted."
    )

assert (
    set(
        tampered_store.objects
    )
    == initial_keys
)

print(
    "PASS: cloud raw/manifest SHA "
    "mismatch fails closed."
)


# 6. Outcome contamination is rejected.
outcome_store = seed_store(
    manifest_doc=manifest(
        outcomes_used=True
    )
)

try:
    bridge.ingest_cloud_capture(
        store=outcome_store,
        manifest_key=
            MANIFEST_KEY,
        prefix=
            "hest-data-test",
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Outcome-contaminated "
        "cloud capture accepted."
    )

print(
    "PASS: outcome-contaminated "
    "cloud Market capture fails closed."
)


# 7. Unknown collector identity is
# rejected.
wrong_collector = seed_store(
    manifest_doc=manifest(
        collector="unknown-cloud"
    )
)

try:
    bridge.ingest_cloud_capture(
        store=wrong_collector,
        manifest_key=
            MANIFEST_KEY,
        prefix=
            "hest-data-test",
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Unknown cloud collector accepted."
    )

print(
    "PASS: unknown cloud collector "
    "identity is rejected."
)


# 8. Market-not-available capture is
# not promoted to data lake.
not_available = seed_store(
    manifest_doc=manifest(
        status=
            "V75_FOUND_MARKET_NOT_AVAILABLE"
    )
)

try:
    bridge.ingest_cloud_capture(
        store=not_available,
        manifest_key=
            MANIFEST_KEY,
        prefix=
            "hest-data-test",
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Unavailable cloud Market "
        "capture accepted."
    )

print(
    "PASS: unavailable cloud Market "
    "capture is rejected."
)


# 9. Post-start capture can be archived,
# but can never become a pre-race feature.
post_start = seed_store(
    manifest_doc=manifest(
        captured_at=
            "2026-10-17T17:01:00.000Z",
        start_time=
            "2026-10-17T19:00:00+02:00",
    )
)

post = (
    bridge
    .ingest_cloud_capture(
        store=post_start,
        manifest_key=
            MANIFEST_KEY,
        prefix=
            "hest-data-test",
    )
)

assert (
    post["knowledgePhase"]
    == "POST_START"
)

assert (
    post[
        "eligibleForPreRaceFeatures"
    ]
    is False
)

print(
    "PASS: post-start cloud Market "
    "data is retained but "
    "leakage-blocked."
)


# 10. Missing start time remains UNKNOWN,
# not fabricated as PRE_RACE.
unknown_time = seed_store(
    manifest_doc=manifest(
        start_time=None
    )
)

unknown = (
    bridge
    .ingest_cloud_capture(
        store=unknown_time,
        manifest_key=
            MANIFEST_KEY,
        prefix=
            "hest-data-test",
    )
)

assert (
    unknown["knowledgePhase"]
    == "UNKNOWN"
)

assert (
    unknown[
        "eligibleForPreRaceFeatures"
    ]
    is False
)

print(
    "PASS: unknown cloud timing "
    "remains leakage-safe."
)


# 11. Unexpected source paths fail
# closed.
for bad_key in (
    "../market/manifest.json",
    "pre-race/2026/manifest.json",
    "market/manifest.json",
    "",
):
    try:
        bridge.validate_manifest_key(
            bad_key
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Unsafe/unexpected manifest "
            f"key accepted: {bad_key!r}"
        )

print(
    "PASS: cloud source key contract "
    "fails closed."
)


# 12. Bridge contains no network fetch
# to Rikstoto, model execution or
# notification provider.
source = BRIDGE_PATH.read_text(
    encoding="utf-8"
)

for forbidden in (
    "urllib.request",
    "requests.get",
    "fetch(",
    "eventualvalues",
    "raceresults",
    "pushover.net",
    "optimize_budget",
    "candidate_v2a",
):
    assert (
        forbidden not in source
    )

print(
    "PASS: cloud bridge reads only "
    "existing S3 capture data."
)

print()
print(
    "PASS: Cloud Market → Hest "
    "bridge v1 offline contract green."
)
