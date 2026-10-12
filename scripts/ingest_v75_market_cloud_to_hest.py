from __future__ import annotations

import argparse
import hashlib
import json
import re
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

EXPECTED_SCHEMA_VERSION = "2.0"
EXPECTED_COLLECTOR = (
    "v75-market-cloud-v2"
)

SHA256_RE = re.compile(
    r"^[0-9a-f]{64}$"
)


def sha256_bytes(
    body: bytes,
) -> str:
    return hashlib.sha256(
        body
    ).hexdigest()


def decode_json_object(
    body: bytes,
    *,
    label: str,
) -> dict[str, Any]:
    try:
        document = json.loads(
            body.decode(
                "utf-8"
            )
        )
    except Exception as exc:
        raise ValueError(
            f"Malformed JSON in {label}."
        ) from exc

    if not isinstance(
        document,
        dict,
    ):
        raise ValueError(
            f"{label} must contain "
            "a JSON object."
        )

    return document


def validate_manifest_key(
    key: str,
) -> str:
    candidate = (
        key.strip()
        .strip("/")
    )

    parts = candidate.split(
        "/"
    )

    if (
        len(parts) < 5
        or parts[0] != "market"
        or parts[-1] != "manifest.json"
        or any(
            part in {
                "",
                ".",
                "..",
            }
            for part in parts
        )
    ):
        raise ValueError(
            "Unexpected cloud Market "
            f"manifest key: {key!r}"
        )

    return candidate


def raw_key_for_manifest(
    manifest_key: str,
) -> str:
    validated = (
        validate_manifest_key(
            manifest_key
        )
    )

    parent = validated.rsplit(
        "/",
        1,
    )[0]

    return (
        f"{parent}/"
        "investment-response.json"
    )


def require_false(
    value: dict[str, Any],
    key: str,
) -> None:
    if value.get(key) is not False:
        raise ValueError(
            "Cloud collector guardrail "
            f"must explicitly state "
            f"{key}=false."
        )


def load_source_capture(
    *,
    store,
    manifest_key: str,
) -> dict[str, Any]:
    manifest_key = (
        validate_manifest_key(
            manifest_key
        )
    )

    raw_key = (
        raw_key_for_manifest(
            manifest_key
        )
    )

    manifest_body = store.get_bytes(
        manifest_key
    )

    if manifest_body is None:
        raise ValueError(
            "Cloud Market manifest "
            f"not found: {manifest_key}"
        )

    raw_body = store.get_bytes(
        raw_key
    )

    if raw_body is None:
        raise ValueError(
            "Cloud Market raw response "
            f"not found: {raw_key}"
        )

    manifest = decode_json_object(
        manifest_body,
        label=manifest_key,
    )

    if (
        manifest.get(
            "schemaVersion"
        )
        != EXPECTED_SCHEMA_VERSION
    ):
        raise ValueError(
            "Unexpected cloud Market "
            "schemaVersion."
        )

    if (
        manifest.get(
            "collector"
        )
        != EXPECTED_COLLECTOR
    ):
        raise ValueError(
            "Unexpected cloud Market "
            "collector identity."
        )

    if (
        manifest.get(
            "status"
        )
        != "MARKET_AVAILABLE"
    ):
        raise ValueError(
            "Only MARKET_AVAILABLE "
            "cloud captures may be "
            "ingested."
        )

    guardrails = manifest.get(
        "guardrails"
    )

    if not isinstance(
        guardrails,
        dict,
    ):
        raise ValueError(
            "Cloud Market manifest has "
            "no guardrails object."
        )

    if (
        guardrails.get(
            "preRaceCollectionPurpose"
        )
        is not True
    ):
        raise ValueError(
            "Cloud Market capture is "
            "not explicitly pre-race "
            "collection data."
        )

    for key in (
        "resultOutcomeEndpointUsed",
        "outcomesUsed",
        "modelUsed",
        "modelRetuned",
    ):
        require_false(
            guardrails,
            key,
        )

    race_day_key = (
        foundation
        .safe_component(
            str(
                manifest.get(
                    "raceDayKey"
                )
                or ""
            ),
            "raceDayKey",
        )
    )

    try:
        first_race_number = int(
            manifest[
                "firstRaceNumber"
            ]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "Cloud Market manifest has "
            "no valid firstRaceNumber."
        ) from exc

    captured_raw = manifest.get(
        "capturedAt"
    )

    if not isinstance(
        captured_raw,
        str,
    ):
        raise ValueError(
            "Cloud Market manifest has "
            "no capturedAt."
        )

    captured_at = (
        foundation
        .parse_datetime(
            captured_raw
        )
    )

    start_raw = manifest.get(
        "startTime"
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

    endpoint = manifest.get(
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
            "Unexpected cloud Market "
            "endpoint."
        )

    expected_sha = manifest.get(
        "responseSha256"
    )

    if (
        not isinstance(
            expected_sha,
            str,
        )
        or SHA256_RE.fullmatch(
            expected_sha
        )
        is None
    ):
        raise ValueError(
            "Cloud Market manifest has "
            "no valid responseSha256."
        )

    actual_sha = sha256_bytes(
        raw_body
    )

    if actual_sha != expected_sha:
        raise ValueError(
            "Cloud Market raw SHA256 "
            "does not match manifest."
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

    return {
        "manifestKey":
            manifest_key,
        "rawKey":
            raw_key,
        "manifest":
            manifest,
        "raceDayKey":
            race_day_key,
        "capturedAt":
            captured_at,
        "raceStartAt":
            race_start_at,
        "rawBody":
            raw_body,
        "rawSha256":
            actual_sha,
        "sourceLocator":
            BASE + endpoint,
        "entityRefs":
            entity_refs,
        "updatedTimes":
            manifest.get(
                "updatedTimes"
            ),
        "minutesToStart":
            manifest.get(
                "minutesToStart"
            ),
    }


def ingest_cloud_capture(
    *,
    store,
    manifest_key: str,
    prefix:
        str = "hest-data",
) -> dict[str, Any]:
    source = (
        load_source_capture(
            store=store,
            manifest_key=
                manifest_key,
        )
    )

    result = (
        hest_data_s3
        .register_s3_observation(
            store=store,
            source=
                "rikstoto-market-cloud",
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
            "v75-market-cloud-to-hest-v1",
        "sourceCollector":
            EXPECTED_COLLECTOR,
        "sourceManifestKey":
            source[
                "manifestKey"
            ],
        "sourceRawKey":
            source[
                "rawKey"
            ],
        "sourceRawSha256Verified":
            True,
        "sourceMinutesToStart":
            source[
                "minutesToStart"
            ],
        "marketUpdatedTimes":
            source[
                "updatedTimes"
            ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest one existing Railway "
            "v75-market-cloud-v2 capture "
            "from S3 into the immutable "
            "Hest data lake."
        )
    )

    parser.add_argument(
        "--manifest-key",
        required=True,
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
        ingest_cloud_capture(
            store=store,
            manifest_key=
                args.manifest_key,
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
