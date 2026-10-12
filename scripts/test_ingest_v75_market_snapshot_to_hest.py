from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

INGEST_PATH = (
    ROOT
    / "scripts"
    / "ingest_v75_market_snapshot_to_hest.py"
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


ingest = load_module(
    INGEST_PATH,
    "market_to_hest_tested",
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


def make_run(
    root: Path,
    *,
    captured_at:
        str = "2026-10-17T18:00:00+02:00",
    start_at:
        str | None = "2026-10-17T19:00:00+02:00",
    status:
        str = "MARKET_AVAILABLE",
    collector:
        str = "v75-market-snapshot-v2",
    raw_body:
        bytes = RAW,
    stored_sha:
        str | None = None,
    outcomes_used:
        bool = False,
) -> Path:
    run_dir = (
        root
        / "run"
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    (
        run_dir
        / "investment-response.json"
    ).write_bytes(
        raw_body
    )

    actual_sha = hashlib.sha256(
        raw_body
    ).hexdigest()

    snapshot = {
        "schemaVersion":
            "1.2",
        "collector":
            collector,
        "capturedAt":
            captured_at,
        "guardrails": {
            "scheduleDiscoveryUsed":
                True,
            "resultsNamespaceScheduleEndpointUsed":
                True,
            "outcomeEndpointUsed":
                False,
            "outcomesUsed":
                outcomes_used,
            "modelUsed":
                False,
            "modelRetuned":
                False,
        },
        "meeting": {
            "raceDayKey":
                "BT_NR_2026-10-17",
            "raceDayName":
                "Bergen",
            "poolKey":
                "V75_TEST_POOL",
            "singleTrack":
                True,
            "firstRaceNumber":
                5,
            "firstRaceStartTime":
                start_at,
        },
        "timing": {
            "firstV75StartAt":
                start_at,
            "sourceValue":
                start_at,
            "minutesToStart":
                60.0,
            "status":
                (
                    "KNOWN"
                    if start_at
                    is not None
                    else "UNKNOWN"
                ),
        },
        "market": {
            "endpoint":
                (
                    "/api/game/"
                    "BT_NR_2026-10-17/"
                    "betdistribution/"
                    "investment/V75"
                    "?raceNumber=5"
                ),
            "available":
                True,
            "rawSha256":
                (
                    stored_sha
                    if stored_sha
                    is not None
                    else actual_sha
                ),
            "updatedTimes": [
                (
                    "2026-10-17"
                    "T17:59:40+02:00"
                ),
            ],
            "percentageValueCount":
                1,
            "rankingValueCount":
                1,
            "investmentValueCount":
                1,
        },
        "status":
            status,
    }

    (
        run_dir
        / "snapshot.json"
    ).write_text(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return run_dir


# 1. Valid collector run becomes one
# immutable pre-race Hest observation.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    run_dir = make_run(
        root
    )

    store = FakeStore()

    first = (
        ingest
        .ingest_collector_run(
            store=store,
            run_dir=run_dir,
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
        == "v75-market-to-hest-v1"
    )

    assert (
        first["sourceCollector"]
        == "v75-market-snapshot-v2"
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

    assert len(
        store.objects
    ) == 2

    print(
        "PASS: validated collector run "
        "becomes immutable pre-race "
        "Hest observation."
    )


    # 2. Exact source bytes survive
    # ingest unchanged.
    raw_key = first[
        "rawObjectKey"
    ]

    assert (
        store.objects[
            raw_key
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
        "PASS: Market raw bytes and "
        "SHA256 survive ingest exactly."
    )


    # 3. Observation envelope contains
    # source identity and timing.
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
        observation["source"]["name"]
        == "rikstoto-market"
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
            "subject"
        ][
            "entities"
        ][
            "poolKey"
        ]
        == "V75_TEST_POOL"
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
        "PASS: Market provenance, "
        "meeting identity and timing "
        "are retained."
    )


    # 4. Re-ingest is idempotent.
    second = (
        ingest
        .ingest_collector_run(
            store=store,
            run_dir=run_dir,
            prefix=
                "hest-data-test",
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
        "PASS: repeated Market ingest "
        "is idempotent."
    )


# 5. Tampered raw response fails before
# anything reaches object storage.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    wrong_sha = "0" * 64

    run_dir = make_run(
        root,
        stored_sha=wrong_sha,
    )

    store = FakeStore()

    try:
        ingest.ingest_collector_run(
            store=store,
            run_dir=run_dir,
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
            "Tampered Market raw data "
            "was accepted."
        )

    assert (
        store.objects == {}
    )

    print(
        "PASS: raw/snapshot SHA "
        "mismatch fails closed before "
        "storage."
    )


# 6. Collector run carrying an outcome
# contamination flag is rejected.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    run_dir = make_run(
        root,
        outcomes_used=True,
    )

    store = FakeStore()

    try:
        ingest.ingest_collector_run(
            store=store,
            run_dir=run_dir,
            prefix=
                "hest-data-test",
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Outcome-contaminated "
            "collector run was accepted."
        )

    assert (
        store.objects == {}
    )

    print(
        "PASS: outcome-contaminated "
        "Market capture fails closed."
    )


# 7. Wrong collector identity fails
# closed.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    run_dir = make_run(
        root,
        collector="unknown-collector",
    )

    store = FakeStore()

    try:
        ingest.ingest_collector_run(
            store=store,
            run_dir=run_dir,
            prefix=
                "hest-data-test",
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Unknown collector accepted."
        )

    print(
        "PASS: unknown collector "
        "identity is rejected."
    )


# 8. Non-available Market snapshot is
# not promoted into the data lake.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    run_dir = make_run(
        root,
        status=
            "V75_FOUND_MARKET_NOT_AVAILABLE",
    )

    store = FakeStore()

    try:
        ingest.ingest_collector_run(
            store=store,
            run_dir=run_dir,
            prefix=
                "hest-data-test",
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Unavailable market "
            "snapshot accepted."
        )

    print(
        "PASS: unavailable Market "
        "snapshot is rejected."
    )


# 9. Captures after race start may be
# archived but are structurally blocked
# from pre-race feature use.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    run_dir = make_run(
        root,
        captured_at=
            "2026-10-17T19:01:00+02:00",
        start_at=
            "2026-10-17T19:00:00+02:00",
    )

    store = FakeStore()

    result = (
        ingest
        .ingest_collector_run(
            store=store,
            run_dir=run_dir,
            prefix=
                "hest-data-test",
        )
    )

    assert (
        result["knowledgePhase"]
        == "POST_START"
    )

    assert (
        result[
            "eligibleForPreRaceFeatures"
        ]
        is False
    )

    print(
        "PASS: post-start Market "
        "capture is retained but "
        "leakage-blocked."
    )


# 10. Unknown start timing is retained
# but not assumed pre-race.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    run_dir = make_run(
        root,
        start_at=None,
    )

    store = FakeStore()

    result = (
        ingest
        .ingest_collector_run(
            store=store,
            run_dir=run_dir,
            prefix=
                "hest-data-test",
        )
    )

    assert (
        result["knowledgePhase"]
        == "UNKNOWN"
    )

    assert (
        result[
            "eligibleForPreRaceFeatures"
        ]
        is False
    )

    print(
        "PASS: unknown Market timing "
        "is archived without fabricated "
        "pre-race eligibility."
    )


# 11. Adapter itself contains no
# outcome fetch, model execution or
# notification delivery.
source = INGEST_PATH.read_text(
    encoding="utf-8"
)

for forbidden in (
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
    "PASS: Market ingest is "
    "storage-only and model-independent."
)

print()
print(
    "PASS: Market → Hest Data Lake "
    "ingest v1 offline contract green."
)
