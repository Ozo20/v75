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


EXPECTED_SCHEMA_VERSION = "1.0"
EXPECTED_COLLECTOR = (
    "v75-stalltips-cloud-v2"
)
EXPECTED_CAPTURE_TYPE = (
    "v75-stalltips-byte-exact"
)
EXPECTED_SAMPLE_COUNT = 20

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
        or parts[0] != "stalltips"
        or parts[-1] != "raw-manifest.json"
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
            "Unexpected Stalltips "
            f"raw manifest key: {key!r}"
        )

    return candidate


def validate_raw_object_key(
    *,
    manifest_key: str,
    raw_key: str,
) -> str:
    manifest_key = (
        validate_manifest_key(
            manifest_key
        )
    )

    candidate = (
        raw_key.strip()
        .strip("/")
    )

    parent = manifest_key.rsplit(
        "/",
        1,
    )[0]

    expected_prefix = (
        f"{parent}/raw/"
    )

    parts = candidate.split(
        "/"
    )

    if (
        not candidate.startswith(
            expected_prefix
        )
        or not candidate.endswith(
            ".json"
        )
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
            "Unexpected Stalltips raw "
            f"object key: {raw_key!r}"
        )

    return candidate


def require_false(
    value: dict[str, Any],
    key: str,
) -> None:
    if value.get(key) is not False:
        raise ValueError(
            "Stalltips collector guardrail "
            f"must explicitly state "
            f"{key}=false."
        )


def validate_raw_payload(
    *,
    document: dict[str, Any],
    race_day_key: str,
) -> None:
    if document.get(
        "success"
    ) is not True:
        raise ValueError(
            "Stalltips raw response "
            "must have success=true."
        )

    result = document.get(
        "result"
    )

    if not isinstance(
        result,
        dict,
    ):
        raise ValueError(
            "Stalltips raw response "
            "has no result object."
        )

    if result.get(
        "product"
    ) != "V75":
        raise ValueError(
            "Stalltips raw response "
            "is not V75."
        )

    if str(
        result.get(
            "raceDayKey"
        )
        or ""
    ) != race_day_key:
        raise ValueError(
            "Stalltips raw response "
            "raceDayKey mismatch."
        )

    selections = result.get(
        "selections"
    )

    if (
        not isinstance(
            selections,
            list,
        )
        or len(
            selections
        ) != 7
    ):
        raise ValueError(
            "Stalltips raw response "
            "must contain seven selections."
        )

    legs: list[int] = []

    for selection in selections:
        if not isinstance(
            selection,
            dict,
        ):
            raise ValueError(
                "Stalltips selection "
                "must be an object."
            )

        try:
            leg_number = int(
                selection[
                    "legNumber"
                ]
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Stalltips selection has "
                "invalid legNumber."
            ) from exc

        marks = selection.get(
            "marks"
        )

        if (
            not isinstance(
                marks,
                list,
            )
            or not marks
        ):
            raise ValueError(
                "Stalltips selection has "
                "no marks."
            )

        normalized: list[int] = []

        for mark in marks:
            try:
                normalized.append(
                    int(mark)
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    "Stalltips mark must "
                    "be numeric."
                ) from exc

        if len(
            normalized
        ) != len(
            set(
                normalized
            )
        ):
            raise ValueError(
                "Stalltips selection "
                "contains duplicate marks."
            )

        legs.append(
            leg_number
        )

    if sorted(
        legs
    ) != list(
        range(
            1,
            8,
        )
    ):
        raise ValueError(
            "Stalltips selections must "
            "cover legs 1..7 exactly."
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

    manifest_body = store.get_bytes(
        manifest_key
    )

    if manifest_body is None:
        raise ValueError(
            "Stalltips raw manifest "
            f"not found: {manifest_key}"
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
            "Unexpected Stalltips "
            "schemaVersion."
        )

    if (
        manifest.get(
            "collector"
        )
        != EXPECTED_COLLECTOR
    ):
        raise ValueError(
            "Unexpected Stalltips "
            "collector identity."
        )

    if (
        manifest.get(
            "captureType"
        )
        != EXPECTED_CAPTURE_TYPE
    ):
        raise ValueError(
            "Unexpected Stalltips "
            "captureType."
        )

    guardrails = manifest.get(
        "guardrails"
    )

    if not isinstance(
        guardrails,
        dict,
    ):
        raise ValueError(
            "Stalltips raw manifest has "
            "no guardrails object."
        )

    for key in (
        "rawResponseBytesPreserved",
        "descriptiveOnly",
        "noAutomaticBetSubmission",
    ):
        if guardrails.get(
            key
        ) is not True:
            raise ValueError(
                "Stalltips collector "
                "guardrail must explicitly "
                f"state {key}=true."
            )

    for key in (
        "responseBodyReserialized",
        "outcomesUsed",
        "marketUsed",
        "coreModelUsed",
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

    track_code = (
        foundation
        .safe_component(
            str(
                manifest.get(
                    "trackCode"
                )
                or ""
            ),
            "trackCode",
        )
    )

    if manifest.get(
        "product"
    ) != "V75":
        raise ValueError(
            "Stalltips manifest "
            "product is not V75."
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
            "https://www.rikstoto.no/"
        )
        or (
            "/api/lyntoto/draft"
            not in endpoint
        )
    ):
        raise ValueError(
            "Unexpected Stalltips endpoint."
        )

    start_raw = manifest.get(
        "startTime"
    )

    if (
        not isinstance(
            start_raw,
            str,
        )
        or not start_raw.strip()
    ):
        raise ValueError(
            "Stalltips manifest has "
            "no startTime."
        )

    race_start_at = (
        foundation
        .parse_datetime(
            start_raw
        )
    )

    samples = manifest.get(
        "samples"
    )

    if (
        not isinstance(
            samples,
            list,
        )
        or len(
            samples
        ) != EXPECTED_SAMPLE_COUNT
    ):
        raise ValueError(
            "Stalltips raw manifest must "
            f"contain exactly "
            f"{EXPECTED_SAMPLE_COUNT} samples."
        )

    if (
        manifest.get(
            "sampleCount"
        )
        != len(
            samples
        )
    ):
        raise ValueError(
            "Stalltips sampleCount "
            "does not match samples."
        )

    loaded_samples: list[
        dict[str, Any]
    ] = []

    seen_numbers: set[int] = set()
    capture_times = []

    for sample in samples:
        if not isinstance(
            sample,
            dict,
        ):
            raise ValueError(
                "Stalltips sample metadata "
                "must be an object."
            )

        try:
            sample_number = int(
                sample[
                    "sampleNumber"
                ]
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Stalltips sample has "
                "invalid sampleNumber."
            ) from exc

        if (
            sample_number < 1
            or sample_number
            > EXPECTED_SAMPLE_COUNT
            or sample_number
            in seen_numbers
        ):
            raise ValueError(
                "Stalltips sampleNumber "
                "set is invalid."
            )

        seen_numbers.add(
            sample_number
        )

        captured_raw = sample.get(
            "capturedAt"
        )

        if not isinstance(
            captured_raw,
            str,
        ):
            raise ValueError(
                "Stalltips sample has "
                "no capturedAt."
            )

        captured_at = (
            foundation
            .parse_datetime(
                captured_raw
            )
        )

        if sample.get(
            "httpStatus"
        ) != 200:
            raise ValueError(
                "Stalltips sample HTTP "
                "status is not 200."
            )

        content_type = sample.get(
            "contentType"
        )

        if (
            not isinstance(
                content_type,
                str,
            )
            or "json"
            not in content_type.lower()
        ):
            raise ValueError(
                "Stalltips sample has "
                "unexpected contentType."
            )

        expected_sha = sample.get(
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
                "Stalltips sample has "
                "no valid responseSha256."
            )

        byte_length = sample.get(
            "byteLength"
        )

        if (
            not isinstance(
                byte_length,
                int,
            )
            or byte_length < 1
        ):
            raise ValueError(
                "Stalltips sample has "
                "invalid byteLength."
            )

        raw_key = sample.get(
            "objectKey"
        )

        if not isinstance(
            raw_key,
            str,
        ):
            raise ValueError(
                "Stalltips sample has "
                "no objectKey."
            )

        raw_key = (
            validate_raw_object_key(
                manifest_key=
                    manifest_key,
                raw_key=raw_key,
            )
        )

        raw_body = store.get_bytes(
            raw_key
        )

        if raw_body is None:
            raise ValueError(
                "Stalltips exact raw "
                f"response not found: "
                f"{raw_key}"
            )

        actual_sha = sha256_bytes(
            raw_body
        )

        if actual_sha != expected_sha:
            raise ValueError(
                "Stalltips raw SHA256 "
                "does not match manifest."
            )

        if len(
            raw_body
        ) != byte_length:
            raise ValueError(
                "Stalltips raw byteLength "
                "does not match manifest."
            )

        payload = decode_json_object(
            raw_body,
            label=raw_key,
        )

        validate_raw_payload(
            document=payload,
            race_day_key=
                race_day_key,
        )

        loaded_samples.append(
            {
                "sampleNumber":
                    sample_number,
                "capturedAt":
                    captured_at,
                "rawKey":
                    raw_key,
                "rawBody":
                    raw_body,
                "rawSha256":
                    actual_sha,
                "contentType":
                    content_type,
            }
        )

        capture_times.append(
            captured_at
        )

    if seen_numbers != set(
        range(
            1,
            EXPECTED_SAMPLE_COUNT + 1,
        )
    ):
        raise ValueError(
            "Stalltips sampleNumber set "
            "must be exactly 1..20."
        )

    loaded_samples.sort(
        key=lambda row:
            row[
                "sampleNumber"
            ]
    )

    for earlier, later in zip(
        capture_times,
        capture_times[1:],
    ):
        if later < earlier:
            raise ValueError(
                "Stalltips sample capture "
                "times are not monotonic."
            )

    first_raw = manifest.get(
        "firstCapturedAt"
    )
    last_raw = manifest.get(
        "lastCapturedAt"
    )

    if (
        not isinstance(
            first_raw,
            str,
        )
        or not isinstance(
            last_raw,
            str,
        )
    ):
        raise ValueError(
            "Stalltips manifest capture "
            "window is incomplete."
        )

    first_at = (
        foundation
        .parse_datetime(
            first_raw
        )
    )
    last_at = (
        foundation
        .parse_datetime(
            last_raw
        )
    )

    if (
        first_at
        != loaded_samples[
            0
        ][
            "capturedAt"
        ]
        or last_at
        != loaded_samples[
            -1
        ][
            "capturedAt"
        ]
    ):
        raise ValueError(
            "Stalltips manifest capture "
            "window does not match samples."
        )

    return {
        "manifestKey":
            manifest_key,
        "manifest":
            manifest,
        "raceDayKey":
            race_day_key,
        "trackCode":
            track_code,
        "raceStartAt":
            race_start_at,
        "sourceLocator":
            endpoint,
        "samples":
            loaded_samples,
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

    registered = 0
    already_registered = 0
    results: list[
        dict[str, Any]
    ] = []

    for sample in source[
        "samples"
    ]:
        result = (
            hest_data_s3
            .register_s3_observation(
                store=store,
                source=
                    "rikstoto-stalltips-cloud",
                category="STALLTIPS",
                race_day_key=
                    source[
                        "raceDayKey"
                    ],
                raw_body=
                    sample[
                        "rawBody"
                    ],
                captured_at=
                    sample[
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
                    sample[
                        "contentType"
                    ],
                entity_refs={
                    "sampleNumber":
                        str(
                            sample[
                                "sampleNumber"
                            ]
                        ),
                    "trackCode":
                        source[
                            "trackCode"
                        ],
                },
                prefix=prefix,
            )
        )

        state = result.get(
            "state"
        )

        if state == "REGISTERED":
            registered += 1
        elif (
            state
            == "ALREADY_REGISTERED"
        ):
            already_registered += 1
        else:
            raise RuntimeError(
                "Unexpected Hest ingest "
                "state for Stalltips "
                f"sample "
                f"{sample['sampleNumber']}: "
                f"{state!r}"
            )

        results.append(
            {
                **result,
                "sampleNumber":
                    sample[
                        "sampleNumber"
                    ],
                "sourceRawKey":
                    sample[
                        "rawKey"
                    ],
                "sourceRawSha256Verified":
                    True,
            }
        )

    return {
        "schemaVersion":
            "1.0",
        "ingest":
            "v75-stalltips-cloud-to-hest-v1",
        "state":
            (
                "REGISTERED"
                if registered > 0
                else "ALREADY_REGISTERED"
            ),
        "sourceCollector":
            EXPECTED_COLLECTOR,
        "sourceManifestKey":
            source[
                "manifestKey"
            ],
        "sampleCount":
            len(
                source[
                    "samples"
                ]
            ),
        "registeredSamples":
            registered,
        "alreadyRegisteredSamples":
            already_registered,
        "samples":
            results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest one existing Railway "
            "v75-stalltips-cloud-v2 "
            "byte-exact capture from S3 "
            "into the immutable Hest "
            "data lake."
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
