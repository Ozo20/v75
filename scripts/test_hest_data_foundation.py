from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

FOUNDATION_PATH = (
    ROOT
    / "scripts"
    / "hest_data_foundation.py"
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


foundation = load_module(
    FOUNDATION_PATH,
    "hest_data_foundation_tested",
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

        self.objects[key] = body
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
    b'{"investmentDistribution":'
    b'[{"startNumber":7,"percentage":18.2}]}'
)


# 1. Ordinary pre-race data is
# eligible for future feature building.
store = FakeStore()

first = foundation.register_observation(
    store=store,
    source="rikstoto-market",
    category="MARKET",
    race_day_key=
        "BT_NR_2026-10-17",
    raw_body=RAW,
    captured_at=CAPTURED,
    race_start_at=START,
    source_locator=(
        "https://www.rikstoto.no/"
        "api/example"
    ),
)

assert (
    first["state"]
    == "REGISTERED"
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
    "PASS: pre-race raw observation "
    "is stored and feature-eligible."
)


# 2. Raw bytes are preserved exactly.
raw_key = first[
    "rawObjectKey"
]

assert (
    store.objects[
        raw_key
    ]
    == RAW
)

expected_sha = (
    foundation.sha256_bytes(
        RAW
    )
)

assert (
    first["rawSha256"]
    == expected_sha
)

print(
    "PASS: exact raw bytes and SHA256 "
    "are preserved."
)


# 3. Same capture is idempotent.
second = foundation.register_observation(
    store=store,
    source="rikstoto-market",
    category="MARKET",
    race_day_key=
        "BT_NR_2026-10-17",
    raw_body=RAW,
    captured_at=CAPTURED,
    race_start_at=START,
    source_locator=(
        "https://www.rikstoto.no/"
        "api/example"
    ),
)

assert (
    second["state"]
    == "ALREADY_REGISTERED"
)

assert len(
    store.objects
) == 2

print(
    "PASS: identical observation "
    "is idempotent."
)


# 4. A changed source payload at the same
# capture time becomes a new immutable
# observation rather than overwriting.
changed = foundation.register_observation(
    store=store,
    source="rikstoto-market",
    category="MARKET",
    race_day_key=
        "BT_NR_2026-10-17",
    raw_body=(
        b'{"investmentDistribution":'
        b'[{"startNumber":7,"percentage":19.1}]}'
    ),
    captured_at=CAPTURED,
    race_start_at=START,
)

assert (
    changed["state"]
    == "REGISTERED"
)

assert (
    changed["rawObjectKey"]
    != first["rawObjectKey"]
)

assert len(
    store.objects
) == 4

print(
    "PASS: changing data creates a "
    "new immutable observation."
)


# 5. Post-start market data may still be
# archived but cannot be used as a
# pre-race feature.
post = foundation.build_observation(
    source="rikstoto-market",
    category="MARKET",
    race_day_key=
        "BT_NR_2026-10-17",
    raw_body=RAW,
    captured_at=datetime(
        2026,
        10,
        17,
        19,
        1,
        tzinfo=OSLO,
    ),
    race_start_at=START,
)

assert (
    post["observation"][
        "knowledgePhase"
    ]
    == "POST_START"
)

assert (
    post["dataUse"][
        "eligibleForPreRaceFeatures"
    ]
    is False
)

print(
    "PASS: post-start observations "
    "are retained but leakage-blocked."
)


# 6. Outcome is never feature-eligible,
# even when supplied with an odd timestamp.
outcome = foundation.build_observation(
    source="rikstoto-result",
    category="OUTCOME",
    race_day_key=
        "BT_NR_2026-10-17",
    raw_body=b'{"winner":7}',
    captured_at=CAPTURED,
    race_start_at=START,
)

assert (
    outcome["dataUse"][
        "outcomeData"
    ]
    is True
)

assert (
    outcome["dataUse"][
        "eligibleForPreRaceFeatures"
    ]
    is False
)

print(
    "PASS: outcome data is structurally "
    "excluded from pre-race features."
)


# 7. Effective-known-time is conservative.
# A source claiming publication after the
# race cannot become pre-race evidence
# merely because capture time was earlier.
future_published = (
    foundation.build_observation(
        source="expert-public",
        category="EXPERT_TIPS",
        race_day_key=
            "BT_NR_2026-10-17",
        raw_body=b'{"tip":"7"}',
        captured_at=CAPTURED,
        source_published_at=
            datetime(
                2026,
                10,
                17,
                19,
                5,
                tzinfo=OSLO,
            ),
        race_start_at=START,
    )
)

assert (
    future_published[
        "observation"
    ][
        "sourceClockAnomaly"
    ]
    is True
)

assert (
    future_published[
        "observation"
    ][
        "knowledgePhase"
    ]
    == "POST_START"
)

assert (
    future_published[
        "dataUse"
    ][
        "eligibleForPreRaceFeatures"
    ]
    is False
)

print(
    "PASS: source timing anomalies "
    "fail closed against leakage."
)


# 8. Unknown race time remains archived
# but is not silently assumed pre-race.
unknown = foundation.build_observation(
    source="weather-public",
    category="WEATHER",
    race_day_key=
        "BT_NR_2026-10-17",
    raw_body=b'{"temperature":8}',
    captured_at=CAPTURED,
)

assert (
    unknown["observation"][
        "knowledgePhase"
    ]
    == "UNKNOWN"
)

assert (
    unknown["dataUse"][
        "eligibleForPreRaceFeatures"
    ]
    is False
)

print(
    "PASS: unknown timing is retained "
    "without fabricated pre-race status."
)


# 9. Entity references are descriptive
# identities only. No injury inference
# exists in the foundation layer.
entity = foundation.build_observation(
    source="rikstoto-program",
    category="RACE_PROGRAM",
    race_day_key=
        "BT_NR_2026-10-17",
    raw_body=b'{"daysSinceLastStart":126}',
    captured_at=CAPTURED,
    race_start_at=START,
    entity_refs={
        "horseId":
            "horse-123",
        "raceKey":
            "BT_NR_2026-10-17-5",
    },
)

assert (
    entity["subject"][
        "entities"
    ][
        "horseId"
    ]
    == "horse-123"
)

source_text = (
    FOUNDATION_PATH
    .read_text(
        encoding="utf-8"
    )
    .lower()
)

assert (
    "return_from_injury"
    not in source_text
)

assert (
    "injury" not in source_text
)

print(
    "PASS: data foundation records "
    "facts without inventing injury state."
)


# 10. Unsafe paths fail closed.
for bad in (
    "../market",
    "market/source",
    "",
):
    try:
        foundation.safe_component(
            bad,
            "test",
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            f"Unsafe component accepted: "
            f"{bad!r}"
        )

print(
    "PASS: storage identity rejects "
    "unsafe path components."
)


# 11. Immutable collision is fatal.
collision_store = FakeStore()

record = foundation.build_observation(
    source="stalltips-public",
    category="STALLTIPS",
    race_day_key=
        "BT_NR_2026-10-17",
    raw_body=b'{"horse":7}',
    captured_at=CAPTURED,
    race_start_at=START,
)

collision_key = (
    record[
        "raw"
    ][
        "objectKey"
    ]
)

collision_store.objects[
    collision_key
] = b"corrupt"

try:
    foundation.register_observation(
        store=collision_store,
        source="stalltips-public",
        category="STALLTIPS",
        race_day_key=
            "BT_NR_2026-10-17",
        raw_body=b'{"horse":7}',
        captured_at=CAPTURED,
        race_start_at=START,
    )
except RuntimeError:
    pass
else:
    raise AssertionError(
        "Immutable collision did not fail."
    )

print(
    "PASS: immutable object collision "
    "fails closed."
)


# 12. Contract explicitly covers the
# intended broad source families.
required_categories = {
    "MARKET",
    "START_LIST",
    "HORSE_HISTORY",
    "DRIVER_HISTORY",
    "TRAINER_HISTORY",
    "EQUIPMENT",
    "STALLTIPS",
    "EXPERT_TIPS",
    "WEATHER",
    "TRACK_CONDITION",
    "OUTCOME",
}

assert required_categories.issubset(
    foundation.SOURCE_CATEGORIES
)

print(
    "PASS: foundation supports broad "
    "future data collection."
)


# 13. No model, payout optimization,
# notification or outcome endpoint is
# embedded in the logger.
source = (
    FOUNDATION_PATH
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
        forbidden not in source
    )

print(
    "PASS: data logger is model- and "
    "notification-independent."
)

print()
print(
    "PASS: Hest Data Foundation v1 "
    "offline contract green."
)
