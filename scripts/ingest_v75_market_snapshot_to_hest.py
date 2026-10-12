from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPT_DIR),
    )


import hest_data_foundation as foundation
import hest_data_s3


BASE = "https://www.rikstoto.no"

EXPECTED_SCHEMA_VERSION = "1.2"
EXPECTED_COLLECTOR = (
    "v75-market-snapshot-v2"
)


def sha256_bytes(
    body: bytes,
) -> str:
    return hashlib.sha256(
        body
    ).hexdigest()


def load_json_object(
    path: Path,
    *,
    label: str,
) -> dict[str, Any]:
    document = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        document,
        dict,
    ):
        raise ValueError(
            f"{label} must contain "
            "a JSON object."
        )

    return document


def require_false_guardrail(
    guardrails: dict[str, Any],
    key: str,
) -> None:
    if guardrails.get(key) is not False:
        raise ValueError(
            "Collector guardrail must "
            f"explicitly state "
            f"{key}=false."
        )


def validate_collector_run(
    run_dir: Path,
) -> dict[str, Any]:
    resolved = (
        run_dir
        .expanduser()
        .resolve()
    )

    snapshot_path = (
        resolved
        / "snapshot.json"
    )

    raw_path = (
        resolved
        / "investment-response.json"
    )

    if not snapshot_path.is_file():
        raise ValueError(
            "Missing collector "
            "snapshot.json."
        )

    if not raw_path.is_file():
        raise ValueError(
            "Missing collector "
            "investment-response.json."
        )

    snapshot = load_json_object(
        snapshot_path,
        label="snapshot.json",
    )

    if (
        snapshot.get(
            "schemaVersion"
        )
        != EXPECTED_SCHEMA_VERSION
    ):
        raise ValueError(
            "Unexpected market snapshot "
            "schemaVersion."
        )

    if (
        snapshot.get("collector")
        != EXPECTED_COLLECTOR
    ):
        raise ValueError(
            "Unexpected market collector."
        )

    if (
        snapshot.get("status")
        != "MARKET_AVAILABLE"
    ):
        raise ValueError(
            "Only MARKET_AVAILABLE "
            "collector runs may be "
            "ingested."
        )

    guardrails = (
        snapshot.get(
            "guardrails"
        )
    )

    if not isinstance(
        guardrails,
        dict,
    ):
        raise ValueError(
            "Collector snapshot has no "
            "guardrails object."
        )

    for key in (
        "outcomeEndpointUsed",
        "outcomesUsed",
        "modelUsed",
        "modelRetuned",
    ):
        require_false_guardrail(
            guardrails,
            key,
        )

    meeting = snapshot.get(
        "meeting"
    )

    if not isinstance(
        meeting,
        dict,
    ):
        raise ValueError(
            "Collector snapshot has no "
            "meeting object."
        )

    race_day_key = (
        foundation
        .safe_component(
            str(
                meeting.get(
                    "raceDayKey"
                )
                or ""
            ),
            "raceDayKey",
        )
    )

    try:
        first_race_number = int(
            meeting[
                "firstRaceNumber"
            ]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "Collector meeting has no "
            "valid firstRaceNumber."
        ) from exc

    captured_raw = (
        snapshot.get(
            "capturedAt"
        )
    )

    if not isinstance(
        captured_raw,
        str,
    ):
        raise ValueError(
            "Collector snapshot has no "
            "capturedAt."
        )

    captured_at = (
        foundation
        .parse_datetime(
            captured_raw
        )
    )

    timing = (
        snapshot.get(
            "timing"
        )
    )

    if not isinstance(
        timing,
        dict,
    ):
        raise ValueError(
            "Collector snapshot has no "
            "timing object."
        )

    start_raw = timing.get(
        "firstV75StartAt"
    )

    race_start_at = (
        foundation
        .parse_datetime(
            start_raw
        )
        if isinstance(
            start_raw,
            str,
        )
        and start_raw.strip()
        else None
    )

    market = snapshot.get(
        "market"
    )

    if not isinstance(
        market,
        dict,
    ):
        raise ValueError(
            "Collector snapshot has no "
            "market object."
        )

    if (
        market.get("available")
        is not True
    ):
        raise ValueError(
            "Collector market is not "
            "marked available."
        )

    endpoint = market.get(
        "endpoint"
    )

    if (
        not isinstance(
            endpoint,
            str,
        )
        or not endpoint.startswith(
            "/api/"
        )
        or "://" in endpoint
    ):
        raise ValueError(
            "Unexpected market endpoint."
        )

    expected_raw_sha = (
        market.get(
            "rawSha256"
        )
    )

    if (
        not isinstance(
            expected_raw_sha,
            str,
        )
        or len(
            expected_raw_sha
        ) != 64
    ):
        raise ValueError(
            "Collector market has no "
            "valid rawSha256."
        )

    raw_body = (
        raw_path.read_bytes()
    )

    actual_raw_sha = (
        sha256_bytes(
            raw_body
        )
    )

    if (
        actual_raw_sha
        != expected_raw_sha
    ):
        raise ValueError(
            "Collector raw market SHA256 "
            "does not match snapshot."
        )

    entity_refs: dict[
        str,
        str,
    ] = {
        "firstRaceNumber":
            str(
                first_race_number
            ),
    }

    pool_key = meeting.get(
        "poolKey"
    )

    if (
        isinstance(
            pool_key,
            str,
        )
        and pool_key.strip()
    ):
        entity_refs[
            "poolKey"
        ] = pool_key.strip()

    return {
        "runDirectory":
            str(
                resolved
            ),
        "snapshotPath":
            str(
                snapshot_path
            ),
        "rawPath":
            str(
                raw_path
            ),
        "raceDayKey":
            race_day_key,
        "capturedAt":
            captured_at,
        "raceStartAt":
            race_start_at,
        "rawBody":
            raw_body,
        "rawSha256":
            actual_raw_sha,
        "sourceLocator":
            BASE + endpoint,
        "entityRefs":
            entity_refs,
        "collector":
            snapshot[
                "collector"
            ],
        "collectorSchemaVersion":
            snapshot[
                "schemaVersion"
            ],
        "collectorTimingStatus":
            timing.get(
                "status"
            ),
        "marketUpdatedTimes":
            market.get(
                "updatedTimes"
            ),
    }


def ingest_collector_run(
    *,
    store,
    run_dir: Path,
    prefix:
        str = "hest-data",
) -> dict[str, Any]:
    source = (
        validate_collector_run(
            run_dir
        )
    )

    result = (
        hest_data_s3
        .register_s3_observation(
            store=store,
            source=
                "rikstoto-market",
            category="MARKET",
            race_day_key=
                source[
                    "raceDayKey"
                ],
            raw_body=
                source[
                    "rawBody"
                ],
            captured_at=
                source[
                    "capturedAt"
                ],
            race_start_at=
                source[
                    "raceStartAt"
                ],
            source_locator=
                source[
                    "sourceLocator"
                ],
            raw_content_type=
                "application/json",
            entity_refs=
                source[
                    "entityRefs"
                ],
            prefix=prefix,
        )
    )

    return {
        **result,
        "ingest":
            "v75-market-to-hest-v1",
        "sourceCollector":
            source[
                "collector"
            ],
        "sourceCollectorSchemaVersion":
            source[
                "collectorSchemaVersion"
            ],
        "sourceRawSha256Verified":
            True,
        "collectorTimingStatus":
            source[
                "collectorTimingStatus"
            ],
        "marketUpdatedTimes":
            source[
                "marketUpdatedTimes"
            ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest one validated "
            "v75-market-snapshot-v2 "
            "collector run into the "
            "immutable Hest data lake."
        )
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--prefix",
        default="hest-data",
    )

    args = parser.parse_args()

    store = (
        hest_data_s3
        .S3ObjectStore
        .from_env()
    )

    result = (
        ingest_collector_run(
            store=store,
            run_dir=
                args.run_dir,
            prefix=args.prefix,
        )
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
