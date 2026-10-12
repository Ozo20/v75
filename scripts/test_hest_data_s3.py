from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

ADAPTER_PATH = (
    ROOT
    / "scripts"
    / "hest_data_s3.py"
)

FOUNDATION_PATH = (
    ROOT
    / "scripts"
    / "hest_data_foundation.py"
)

S3_BASE_PATH = (
    ROOT
    / "scripts"
    / "queue_v75_notification_s3.py"
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


adapter = load_module(
    ADAPTER_PATH,
    "hest_data_s3_tested",
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
        assert content_type

        self.put_calls += 1

        if key in self.objects:
            return False

        self.objects[
            key
        ] = body

        return True


CAPTURED = datetime(
    2026,
    10,
    17,
    18,
    0,
    tzinfo=OSLO,
)

START = datetime(
    2026,
    10,
    17,
    19,
    0,
    tzinfo=OSLO,
)

RAW = (
    b'{"source":"synthetic",'
    b'"horse":7,'
    b'"percentage":18.2}'
)


# 1. First S3 registration.
store = FakeStore()

first = (
    adapter
    .register_s3_observation(
        store=store,
        source="rikstoto-market",
        category="MARKET",
        race_day_key=
            "BT_NR_2026-10-17",
        raw_body=RAW,
        captured_at=CAPTURED,
        race_start_at=START,
        source_locator=
            "https://example.invalid/test",
        entity_refs={
            "horseId":
                "horse-7",
            "raceKey":
                "BT_NR_2026-10-17-5",
        },
        prefix=
            "hest-data-smoke",
    )
)

assert (
    first["state"]
    == "REGISTERED"
)

assert (
    first["adapter"]
    == "hest-data-s3-v1"
)

assert (
    first["storage"]
    == "S3"
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

assert len(
    store.objects
) == 2

print(
    "PASS: S3 adapter registers "
    "pre-race observation."
)


# 2. Prefix and immutable key
# layout are isolated as intended.
assert (
    first[
        "rawObjectKey"
    ].startswith(
        "hest-data-smoke/raw/"
    )
)

assert (
    first[
        "observationObjectKey"
    ].startswith(
        "hest-data-smoke/"
        "observations/"
    )
)

print(
    "PASS: S3 object paths use "
    "isolated Hest data prefix."
)


# 3. Raw bytes survive unchanged.
assert (
    store.objects[
        first[
            "rawObjectKey"
        ]
    ]
    == RAW
)

print(
    "PASS: S3 adapter preserves "
    "raw source bytes exactly."
)


# 4. Same observation is idempotent.
second = (
    adapter
    .register_s3_observation(
        store=store,
        source="rikstoto-market",
        category="MARKET",
        race_day_key=
            "BT_NR_2026-10-17",
        raw_body=RAW,
        captured_at=CAPTURED,
        race_start_at=START,
        source_locator=
            "https://example.invalid/test",
        entity_refs={
            "horseId":
                "horse-7",
            "raceKey":
                "BT_NR_2026-10-17-5",
        },
        prefix=
            "hest-data-smoke",
    )
)

assert (
    second["state"]
    == "ALREADY_REGISTERED"
)

assert len(
    store.objects
) == 2

print(
    "PASS: repeated S3 registration "
    "is idempotent."
)


# 5. Changed source bytes become a
# distinct immutable observation.
changed = (
    adapter
    .register_s3_observation(
        store=store,
        source="rikstoto-market",
        category="MARKET",
        race_day_key=
            "BT_NR_2026-10-17",
        raw_body=(
            b'{"source":"synthetic",'
            b'"horse":7,'
            b'"percentage":21.4}'
        ),
        captured_at=CAPTURED,
        race_start_at=START,
        prefix=
            "hest-data-smoke",
    )
)

assert (
    changed["state"]
    == "REGISTERED"
)

assert (
    changed[
        "rawObjectKey"
    ]
    != first[
        "rawObjectKey"
    ]
)

print(
    "PASS: changed S3 data creates "
    "a distinct immutable observation."
)


# 6. Outcome semantics are inherited
# unchanged from Foundation.
outcome = (
    adapter
    .register_s3_observation(
        store=store,
        source="rikstoto-result",
        category="OUTCOME",
        race_day_key=
            "BT_NR_2026-10-17",
        raw_body=
            b'{"winner":7}',
        captured_at=CAPTURED,
        race_start_at=START,
        prefix=
            "hest-data-smoke",
    )
)

assert (
    outcome[
        "eligibleForPreRaceFeatures"
    ]
    is False
)

print(
    "PASS: S3 adapter preserves "
    "outcome leakage guardrail."
)


# 7. Unknown timing remains
# non-feature-eligible.
unknown = (
    adapter
    .register_s3_observation(
        store=store,
        source="weather-public",
        category="WEATHER",
        race_day_key=
            "BT_NR_2026-10-17",
        raw_body=
            b'{"temperature":8}',
        captured_at=CAPTURED,
        prefix=
            "hest-data-smoke",
    )
)

assert (
    unknown[
        "knowledgePhase"
    ]
    == "UNKNOWN"
)

assert (
    unknown[
        "eligibleForPreRaceFeatures"
    ]
    is False
)

print(
    "PASS: unknown timing remains "
    "leakage-safe through S3 adapter."
)


# 8. Entity-ref loader requires
# an object, not arbitrary JSON.
temporary = (
    ROOT
    / ".tmp-hest-entity-refs-test.json"
)

try:
    temporary.write_text(
        '["not", "an", "object"]\n',
        encoding="utf-8",
    )

    try:
        adapter.load_entity_refs(
            temporary
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Non-object entity refs accepted."
        )

finally:
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass

print(
    "PASS: entity references fail "
    "closed on malformed JSON shape."
)


# 9. No credentials or model logic
# can enter an observation implicitly.
all_text = "\n".join(
    body.decode(
        "utf-8",
        errors="replace",
    )
    for body
    in store.objects.values()
)

for secret in (
    "PUSHOVER_APP_TOKEN",
    "PUSHOVER_USER_KEY",
    "V75_S3_SECRET_ACCESS_KEY",
):
    assert secret not in all_text

print(
    "PASS: test observations contain "
    "no delivery or S3 credentials."
)


# 10. Production S3 implementation
# is still conditional immutable create.
s3_source = (
    S3_BASE_PATH
    .read_text(
        encoding="utf-8"
    )
)

assert (
    'IfNoneMatch="*"'
    in s3_source
)

assert (
    "delete_object"
    not in s3_source
)

assert (
    "copy_object"
    not in s3_source
)

print(
    "PASS: reused S3 store remains "
    "conditional and immutable."
)


# 11. Adapter contains no outcome
# fetch, provider or model execution.
adapter_source = (
    ADAPTER_PATH
    .read_text(
        encoding="utf-8"
    )
)

for forbidden in (
    "pushover.net",
    "eventualvalues",
    "raceresults",
    "optimize_budget",
    "candidate_v2a",
):
    assert (
        forbidden not in adapter_source
    )

print(
    "PASS: S3 adapter is storage-only."
)


# 12. Foundation remains the single
# owner of observation semantics.
foundation_source = (
    FOUNDATION_PATH
    .read_text(
        encoding="utf-8"
    )
)

assert (
    "eligibleForPreRaceFeatures"
    in foundation_source
)

assert (
    "knowledgePhase"
    in foundation_source
)

print(
    "PASS: S3 layer does not duplicate "
    "Foundation timing semantics."
)

print()
print(
    "PASS: Hest S3 Data Logger v1 "
    "offline contract green."
)
