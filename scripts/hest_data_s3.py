from __future__ import annotations

import argparse
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
import queue_v75_notification_s3 as s3_base


S3ObjectStore = (
    s3_base.Boto3ObjectStore
)


def load_entity_refs(
    path: Path | None,
) -> dict[str, Any] | None:
    if path is None:
        return None

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
            "Entity refs JSON must "
            "contain an object."
        )

    return document


def register_s3_observation(
    *,
    store,
    source: str,
    category: str,
    race_day_key: str,
    raw_body: bytes,
    captured_at,
    source_published_at=None,
    race_start_at=None,
    source_locator=None,
    raw_content_type:
        str = "application/json",
    entity_refs=None,
    prefix:
        str = "hest-data",
) -> dict[str, Any]:
    result = (
        foundation
        .register_observation(
            store=store,
            source=source,
            category=category,
            race_day_key=
                race_day_key,
            raw_body=raw_body,
            captured_at=
                captured_at,
            source_published_at=
                source_published_at,
            race_start_at=
                race_start_at,
            source_locator=
                source_locator,
            raw_content_type=
                raw_content_type,
            entity_refs=
                entity_refs,
            prefix=prefix,
        )
    )

    return {
        **result,
        "adapter":
            "hest-data-s3-v1",
        "storage":
            "S3",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Register one immutable "
            "Hest observation in S3."
        )
    )

    parser.add_argument(
        "--raw-file",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--source",
        required=True,
    )

    parser.add_argument(
        "--category",
        required=True,
    )

    parser.add_argument(
        "--race-day-key",
        required=True,
    )

    parser.add_argument(
        "--captured-at",
        required=True,
    )

    parser.add_argument(
        "--source-published-at",
    )

    parser.add_argument(
        "--race-start-at",
    )

    parser.add_argument(
        "--source-locator",
    )

    parser.add_argument(
        "--content-type",
        default="application/json",
    )

    parser.add_argument(
        "--entity-refs-json",
        type=Path,
    )

    parser.add_argument(
        "--prefix",
        default="hest-data",
    )

    args = parser.parse_args()

    raw_body = (
        args.raw_file
        .read_bytes()
    )

    entity_refs = (
        load_entity_refs(
            args.entity_refs_json
        )
    )

    store = (
        S3ObjectStore
        .from_env()
    )

    result = (
        register_s3_observation(
            store=store,
            source=args.source,
            category=args.category,
            race_day_key=
                args.race_day_key,
            raw_body=raw_body,
            captured_at=
                foundation
                .parse_datetime(
                    args.captured_at
                ),
            source_published_at=
                (
                    foundation
                    .parse_datetime(
                        args.source_published_at
                    )
                    if args.source_published_at
                    else None
                ),
            race_start_at=
                (
                    foundation
                    .parse_datetime(
                        args.race_start_at
                    )
                    if args.race_start_at
                    else None
                ),
            source_locator=
                args.source_locator,
            raw_content_type=
                args.content_type,
            entity_refs=
                entity_refs,
            prefix=args.prefix,
        )
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
