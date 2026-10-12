from __future__ import annotations

import argparse
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
import ingest_v75_stalltips_cloud_to_hest as bridge


DEFAULT_STATE_KEY = (
    "state/current-pre-race.json"
)

DEFAULT_HEST_PREFIX = (
    "hest-data"
)

DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}$"
)


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


def load_target(
    *,
    store,
    state_key: str,
) -> dict[str, str] | None:
    body = store.get_bytes(
        state_key
    )

    if body is None:
        return None

    state = decode_json_object(
        body,
        label=state_key,
    )

    target = state.get(
        "target"
    )

    if target is None:
        return None

    if not isinstance(
        target,
        dict,
    ):
        raise ValueError(
            "state.target must be "
            "an object or null."
        )

    race_day_key = (
        foundation.safe_component(
            str(
                target.get(
                    "raceDayKey"
                )
                or ""
            ),
            "raceDayKey",
        )
    )

    race_date = str(
        target.get(
            "raceDate"
        )
        or ""
    ).strip()

    if (
        DATE_RE.fullmatch(
            race_date
        )
        is None
    ):
        raise ValueError(
            "Target has invalid raceDate."
        )

    return {
        "raceDayKey":
            race_day_key,
        "raceDate":
            race_date,
    }


def validate_source_prefix(
    prefix: str,
) -> str:
    candidate = (
        prefix.strip()
        .strip("/")
    )

    if (
        not candidate
        or any(
            part in {
                "",
                ".",
                "..",
            }
            for part
            in candidate.split("/")
        )
        or (
            candidate != "stalltips"
            and not candidate.startswith(
                "stalltips/"
            )
        )
    ):
        raise ValueError(
            "Unsafe or unexpected "
            "Stalltips source prefix: "
            f"{prefix!r}"
        )

    return candidate + "/"


def target_source_prefix(
    target: dict[str, str],
) -> str:
    return validate_source_prefix(
        (
            "stalltips/"
            f"{target['raceDate']}/"
            f"{target['raceDayKey']}"
        )
    )


def list_object_keys(
    *,
    store,
    prefix: str,
) -> list[str]:
    prefix = (
        validate_source_prefix(
            prefix
        )
    )

    custom = getattr(
        store,
        "list_keys",
        None,
    )

    if callable(custom):
        values = custom(
            prefix
        )

        return sorted(
            {
                str(value)
                for value in values
                if isinstance(
                    value,
                    str,
                )
                and value.startswith(
                    prefix
                )
            }
        )

    client = getattr(
        store,
        "client",
        None,
    )

    bucket = getattr(
        store,
        "bucket",
        None,
    )

    if (
        client is None
        or not isinstance(
            bucket,
            str,
        )
        or not bucket
    ):
        raise RuntimeError(
            "Object store does not "
            "support S3 key listing."
        )

    paginator = (
        client.get_paginator(
            "list_objects_v2"
        )
    )

    keys: list[str] = []

    for page in paginator.paginate(
        Bucket=bucket,
        Prefix=prefix,
    ):
        if not isinstance(
            page,
            dict,
        ):
            continue

        for item in (
            page.get(
                "Contents"
            )
            or []
        ):
            if not isinstance(
                item,
                dict,
            ):
                continue

            key = item.get(
                "Key"
            )

            if (
                isinstance(
                    key,
                    str,
                )
                and key.startswith(
                    prefix
                )
            ):
                keys.append(
                    key
                )

    return sorted(
        set(
            keys
        )
    )


def discover_manifest_keys(
    *,
    store,
    prefix: str,
) -> list[str]:
    prefix = (
        validate_source_prefix(
            prefix
        )
    )

    output: list[str] = []

    for key in list_object_keys(
        store=store,
        prefix=prefix,
    ):
        if not key.endswith(
            "/raw-manifest.json"
        ):
            continue

        validated = (
            bridge
            .validate_manifest_key(
                key
            )
        )

        if not validated.startswith(
            prefix
        ):
            raise ValueError(
                "Manifest escaped "
                "requested source prefix."
            )

        output.append(
            validated
        )

    return sorted(
        set(
            output
        )
    )


def run_sync(
    *,
    store,
    state_key:
        str = DEFAULT_STATE_KEY,
    hest_prefix:
        str = DEFAULT_HEST_PREFIX,
    all_stalltips:
        bool = False,
) -> dict[str, Any]:
    target = None

    if all_stalltips:
        source_prefix = (
            validate_source_prefix(
                "stalltips"
            )
        )

    else:
        target = load_target(
            store=store,
            state_key=
                state_key,
        )

        if target is None:
            return {
                "schemaVersion":
                    "1.0",
                "runner":
                    "hest-stalltips-cloud-ingest-v1",
                "state":
                    "NO_TARGET",
                "mode":
                    "TARGET",
                "sourcePrefix":
                    None,
                "sourceManifestCount":
                    0,
                "sampleCount":
                    0,
                "registeredSamples":
                    0,
                "alreadyRegisteredSamples":
                    0,
                "guardrails": {
                    "rikstotoNetworkUsed":
                        False,
                    "sourceObjectsModified":
                        False,
                    "automaticBetting":
                        False,
                },
            }

        source_prefix = (
            target_source_prefix(
                target
            )
        )

    manifest_keys = (
        discover_manifest_keys(
            store=store,
            prefix=source_prefix,
        )
    )

    sample_count = 0
    registered = 0
    already_registered = 0
    ingested_keys: list[str] = []

    for manifest_key in manifest_keys:
        result = (
            bridge
            .ingest_cloud_capture(
                store=store,
                manifest_key=
                    manifest_key,
                prefix=
                    hest_prefix,
            )
        )

        sample_count += int(
            result[
                "sampleCount"
            ]
        )

        registered += int(
            result[
                "registeredSamples"
            ]
        )

        already_registered += int(
            result[
                "alreadyRegisteredSamples"
            ]
        )

        ingested_keys.append(
            manifest_key
        )

    return {
        "schemaVersion":
            "1.0",
        "runner":
            "hest-stalltips-cloud-ingest-v1",
        "state":
            "SYNC_COMPLETE",
        "mode":
            (
                "ALL_STALLTIPS"
                if all_stalltips
                else "TARGET"
            ),
        "target":
            target,
        "sourcePrefix":
            source_prefix,
        "sourceManifestCount":
            len(
                manifest_keys
            ),
        "sampleCount":
            sample_count,
        "registeredSamples":
            registered,
        "alreadyRegisteredSamples":
            already_registered,
        "ingestedManifestKeys":
            ingested_keys,
        "guardrails": {
            "rikstotoNetworkUsed":
                False,
            "sourceObjectsModified":
                False,
            "automaticBetting":
                False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize existing "
            "byte-exact Railway Stalltips "
            "capture objects into the "
            "immutable Hest data lake."
        )
    )

    parser.add_argument(
        "--state-key",
        default=
            DEFAULT_STATE_KEY,
    )

    parser.add_argument(
        "--hest-prefix",
        default=
            DEFAULT_HEST_PREFIX,
    )

    parser.add_argument(
        "--all-stalltips",
        action="store_true",
        help=(
            "Backfill all byte-exact "
            "stalltips/* captures instead "
            "of only the current target."
        ),
    )

    args = parser.parse_args()

    store = (
        hest_data_s3
        .S3ObjectStore
        .from_env()
    )

    result = run_sync(
        store=store,
        state_key=
            args.state_key,
        hest_prefix=
            args.hest_prefix,
        all_stalltips=
            args.all_stalltips,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
