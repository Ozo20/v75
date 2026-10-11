from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPT_DIR),
    )

import decide_v75_notification as notification_decision
import queue_v75_notification as local_outbox


OSLO = ZoneInfo("Europe/Oslo")


class ObjectStore(Protocol):
    network_used: bool

    def get_bytes(
        self,
        key: str,
    ) -> bytes | None:
        ...

    def put_if_absent(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str,
    ) -> bool:
        ...


class Boto3ObjectStore:
    network_used = True

    def __init__(
        self,
        *,
        bucket: str,
        endpoint: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        if not bucket:
            raise ValueError(
                "Missing S3 bucket."
            )

        if not endpoint:
            raise ValueError(
                "Missing S3 endpoint."
            )

        if not region:
            raise ValueError(
                "Missing S3 region."
            )

        if not access_key_id:
            raise ValueError(
                "Missing S3 access key."
            )

        if not secret_access_key:
            raise ValueError(
                "Missing S3 secret key."
            )

        self.bucket = bucket

        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=
                access_key_id,
            aws_secret_access_key=
                secret_access_key,
            config=Config(
                s3={
                    "addressing_style":
                        "path",
                }
            ),
        )

    @classmethod
    def from_env(
        cls,
    ) -> Boto3ObjectStore:
        return cls(
            bucket=os.environ.get(
                "V75_S3_BUCKET",
                "",
            ),
            endpoint=os.environ.get(
                "V75_S3_ENDPOINT",
                "",
            ),
            region=os.environ.get(
                "V75_S3_REGION",
                "",
            ),
            access_key_id=os.environ.get(
                "V75_S3_ACCESS_KEY_ID",
                "",
            ),
            secret_access_key=
                os.environ.get(
                    "V75_S3_SECRET_ACCESS_KEY",
                    "",
                ),
        )

    def get_bytes(
        self,
        key: str,
    ) -> bytes | None:
        try:
            response = (
                self.client.get_object(
                    Bucket=self.bucket,
                    Key=key,
                )
            )

        except ClientError as exc:
            response_meta = (
                exc.response
                if isinstance(
                    exc.response,
                    dict,
                )
                else {}
            )

            error = (
                response_meta.get(
                    "Error"
                )
                or {}
            )

            metadata = (
                response_meta.get(
                    "ResponseMetadata"
                )
                or {}
            )

            code = str(
                error.get(
                    "Code"
                )
                or ""
            )

            status = (
                metadata.get(
                    "HTTPStatusCode"
                )
            )

            if (
                code
                in {
                    "NoSuchKey",
                    "404",
                    "NotFound",
                }
                or status == 404
            ):
                return None

            raise

        body = response.get(
            "Body"
        )

        if body is None:
            return b""

        return body.read()

    def put_if_absent(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str,
    ) -> bool:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=
                    content_type,
                IfNoneMatch="*",
            )

            return True

        except ClientError as exc:
            response_meta = (
                exc.response
                if isinstance(
                    exc.response,
                    dict,
                )
                else {}
            )

            error = (
                response_meta.get(
                    "Error"
                )
                or {}
            )

            metadata = (
                response_meta.get(
                    "ResponseMetadata"
                )
                or {}
            )

            code = str(
                error.get(
                    "Code"
                )
                or ""
            )

            status = (
                metadata.get(
                    "HTTPStatusCode"
                )
            )

            if (
                code
                in {
                    "PreconditionFailed",
                    "412",
                }
                or status == 412
            ):
                return False

            raise


def parse_datetime(
    value: str,
) -> datetime:
    candidate = value.strip()

    if candidate.endswith("Z"):
        candidate = (
            candidate[:-1]
            + "+00:00"
        )

    parsed = datetime.fromisoformat(
        candidate
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=OSLO
        )

    return parsed.astimezone(
        OSLO
    )


def require_aware(
    value: datetime,
    name: str,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset()
        is None
    ):
        raise ValueError(
            f"{name} must be "
            "timezone-aware"
        )


def normalized_prefix(
    value: str,
) -> str:
    prefix = (
        value.strip()
        .strip("/")
    )

    if (
        not prefix
        or ".." in prefix.split("/")
    ):
        raise ValueError(
            "Unsafe or empty S3 prefix."
        )

    return prefix


def queue_key(
    *,
    prefix: str,
    race_day_key: str,
    stage: str,
) -> str:
    safe_prefix = (
        normalized_prefix(
            prefix
        )
    )

    safe_race_day_key = (
        notification_decision
        .safe_race_day_key(
            race_day_key
        )
    )

    notification_decision.notification_key(
        safe_race_day_key,
        stage,
    )

    return (
        f"{safe_prefix}/"
        f"{safe_race_day_key}/"
        f"{stage}/queued.json"
    )


def json_bytes(
    payload: Any,
) -> bytes:
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


def decode_json_object(
    body: bytes,
    *,
    key: str,
) -> dict[str, Any]:
    try:
        document = json.loads(
            body.decode(
                "utf-8"
            )
        )

    except Exception as exc:
        raise RuntimeError(
            f"Malformed JSON at {key}."
        ) from exc

    if not isinstance(
        document,
        dict,
    ):
        raise RuntimeError(
            f"Expected JSON object at {key}."
        )

    return document


def validate_existing_record(
    *,
    record: dict[str, Any],
    expected_key: str,
    expected_notification_key: str,
) -> None:
    if (
        record.get(
            "schemaVersion"
        )
        != "1.0"
        or record.get(
            "outbox"
        )
        != "v75-notification-outbox-v1"
        or record.get(
            "state"
        )
        != "QUEUED"
    ):
        raise RuntimeError(
            "Existing cloud outbox record "
            f"is malformed: {expected_key}"
        )

    if (
        record.get(
            "notificationKey"
        )
        != expected_notification_key
    ):
        raise RuntimeError(
            "Existing cloud outbox record "
            "has wrong notification identity."
        )

    payload_hash = (
        record.get(
            "payloadSha256"
        )
    )

    if (
        not isinstance(
            payload_hash,
            str,
        )
        or not payload_hash
    ):
        raise RuntimeError(
            "Existing cloud outbox record "
            "has no payload hash."
        )


def already_queued_result(
    *,
    record: dict[str, Any],
    object_key: str,
    candidate_hash: str,
    network_used: bool,
) -> dict[str, Any]:
    existing_hash = str(
        record[
            "payloadSha256"
        ]
    )

    return {
        "schemaVersion":
            "1.0",
        "adapter":
            "v75-notification-s3-outbox-v1",
        "state":
            "ALREADY_QUEUED",
        "notificationKey":
            record[
                "notificationKey"
            ],
        "objectKey":
            object_key,
        "queuedPayloadSha256":
            existing_hash,
        "candidatePayloadSha256":
            candidate_hash,
        "samePayload":
            (
                existing_hash
                == candidate_hash
            ),
        "guardrails": {
            "networkUsed":
                network_used,
            "providerInvoked":
                False,
            "notificationSent":
                False,
            "repoWrites":
                False,
        },
    }


def enqueue_cloud(
    *,
    decision: dict[str, Any],
    store: ObjectStore,
    now: datetime,
    prefix: str = "notifications",
) -> dict[str, Any]:
    require_aware(
        now,
        "now",
    )

    local_outbox.validate_source_decision(
        decision
    )

    network_used = bool(
        getattr(
            store,
            "network_used",
            False,
        )
    )

    action = str(
        decision.get(
            "action"
        )
    )

    if action == "SILENT":
        return {
            "schemaVersion":
                "1.0",
            "adapter":
                "v75-notification-s3-outbox-v1",
            "state":
                "SKIPPED_SILENT",
            "notificationKey":
                None,
            "objectKey":
                None,
            "guardrails": {
                "networkUsed":
                    network_used,
                "providerInvoked":
                    False,
                "notificationSent":
                    False,
                "repoWrites":
                    False,
            },
        }

    race_day_key = (
        notification_decision
        .safe_race_day_key(
            str(
                decision[
                    "raceDayKey"
                ]
            )
        )
    )

    stage = str(
        decision[
            "stage"
        ]
    )

    expected_notification_key = (
        notification_decision
        .notification_key(
            race_day_key,
            stage,
        )
    )

    object_key = queue_key(
        prefix=prefix,
        race_day_key=
            race_day_key,
        stage=stage,
    )

    payload = (
        local_outbox
        .normalized_payload(
            decision
        )
    )

    payload_hash = (
        local_outbox
        .sha256_payload(
            payload
        )
    )

    existing_body = (
        store.get_bytes(
            object_key
        )
    )

    if existing_body is not None:
        existing = decode_json_object(
            existing_body,
            key=object_key,
        )

        validate_existing_record(
            record=existing,
            expected_key=
                object_key,
            expected_notification_key=
                expected_notification_key,
        )

        return already_queued_result(
            record=existing,
            object_key=
                object_key,
            candidate_hash=
                payload_hash,
            network_used=
                network_used,
        )

    queued_at = (
        now.astimezone(
            OSLO
        )
    )

    record = {
        "schemaVersion":
            "1.0",
        "outbox":
            "v75-notification-outbox-v1",
        "state":
            "QUEUED",
        "deliveryState":
            "PENDING",
        "notificationKey":
            expected_notification_key,
        "queuedAt":
            queued_at.isoformat(),
        "raceDayKey":
            race_day_key,
        "raceDayName":
            decision.get(
                "raceDayName"
            ),
        "stage":
            stage,
        "action":
            action,
        "minutesToStart":
            decision.get(
                "minutesToStart"
            ),
        "message":
            decision.get(
                "message"
            ),
        "reason":
            decision.get(
                "reason"
            ),
        "payload":
            payload,
        "payloadSha256":
            payload_hash,
        "sourceDecision":
            decision,
        "guardrails": {
            "immutableQueueRecord":
                True,
            "networkUsed":
                network_used,
            "providerInvoked":
                False,
            "notificationSent":
                False,
            "repoWrites":
                False,
        },
    }

    created = (
        store.put_if_absent(
            object_key,
            json_bytes(
                record
            ),
            content_type=
                "application/json",
        )
    )

    if created:
        return {
            "schemaVersion":
                "1.0",
            "adapter":
                "v75-notification-s3-outbox-v1",
            "state":
                "QUEUED",
            "notificationKey":
                expected_notification_key,
            "objectKey":
                object_key,
            "queuedPayloadSha256":
                payload_hash,
            "candidatePayloadSha256":
                payload_hash,
            "samePayload":
                True,
            "guardrails": {
                "networkUsed":
                    network_used,
                "providerInvoked":
                    False,
                "notificationSent":
                    False,
                "repoWrites":
                    False,
            },
        }

    # Another worker won the
    # conditional-create race.
    winner_body = (
        store.get_bytes(
            object_key
        )
    )

    if winner_body is None:
        raise RuntimeError(
            "Conditional S3 create lost "
            "but winner object is missing."
        )

    winner = decode_json_object(
        winner_body,
        key=object_key,
    )

    validate_existing_record(
        record=winner,
        expected_key=
            object_key,
        expected_notification_key=
            expected_notification_key,
    )

    return already_queued_result(
        record=winner,
        object_key=
            object_key,
        candidate_hash=
            payload_hash,
        network_used=
            network_used,
    )


def load_json_file(
    path: Path,
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
            "Decision JSON must contain "
            "an object."
        )

    return document


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--decision-json",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--prefix",
        default="notifications",
    )

    parser.add_argument(
        "--now",
        help=(
            "Optional deterministic "
            "queue time."
        ),
    )

    args = parser.parse_args()

    decision = load_json_file(
        args.decision_json
    )

    now = (
        parse_datetime(
            args.now
        )
        if args.now
        else datetime.now(
            OSLO
        )
    )

    store = (
        Boto3ObjectStore
        .from_env()
    )

    result = enqueue_cloud(
        decision=decision,
        store=store,
        now=now,
        prefix=args.prefix,
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
