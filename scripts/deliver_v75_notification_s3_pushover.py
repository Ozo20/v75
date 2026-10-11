from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo


SCRIPT_DIR = __import__("pathlib").Path(
    __file__
).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPT_DIR),
    )

import decide_v75_notification as decision_contract
import deliver_v75_notification_pushover as local_delivery
import queue_v75_notification_s3 as cloud_outbox


OSLO = ZoneInfo("Europe/Oslo")

MAX_ATTEMPTS = 10

ProviderFn = Callable[
    [
        dict[str, Any],
        str,
        str,
    ],
    dict[str, Any],
]


def require_aware(
    value: datetime,
    name: str,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            f"{name} must be timezone-aware"
        )


def normalize_key(
    value: str,
) -> str:
    key = value.strip().strip("/")

    if (
        not key
        or ".." in key.split("/")
    ):
        raise ValueError(
            "Unsafe or empty S3 object key."
        )

    return key


def validate_cloud_queue_record(
    *,
    queued_key: str,
    record: dict[str, Any],
    prefix: str,
) -> None:
    if (
        record.get("schemaVersion")
        != "1.0"
        or record.get("outbox")
        != "v75-notification-outbox-v1"
        or record.get("state")
        != "QUEUED"
        or record.get("deliveryState")
        != "PENDING"
    ):
        raise ValueError(
            "Unsupported or non-pending "
            "cloud outbox record."
        )

    race_day_key = (
        decision_contract
        .safe_race_day_key(
            str(
                record.get(
                    "raceDayKey"
                )
                or ""
            )
        )
    )

    stage = str(
        record.get("stage")
        or ""
    )

    expected_notification_key = (
        decision_contract
        .notification_key(
            race_day_key,
            stage,
        )
    )

    if (
        record.get(
            "notificationKey"
        )
        != expected_notification_key
    ):
        raise ValueError(
            "Cloud outbox notification "
            "identity mismatch."
        )

    expected_queue_key = (
        cloud_outbox.queue_key(
            prefix=prefix,
            race_day_key=
                race_day_key,
            stage=stage,
        )
    )

    if queued_key != expected_queue_key:
        raise ValueError(
            "Cloud queued object path "
            "does not match record identity."
        )

    message = record.get(
        "message"
    )

    if (
        not isinstance(
            message,
            str,
        )
        or not message.strip()
    ):
        raise ValueError(
            "Cloud queued notification "
            "has no message."
        )

    payload_hash = record.get(
        "payloadSha256"
    )

    if (
        not isinstance(
            payload_hash,
            str,
        )
        or not payload_hash
    ):
        raise ValueError(
            "Cloud queued notification "
            "has no payload hash."
        )


def stage_root_from_record(
    *,
    prefix: str,
    record: dict[str, Any],
) -> str:
    safe_prefix = (
        cloud_outbox
        .normalized_prefix(
            prefix
        )
    )

    race_day_key = (
        decision_contract
        .safe_race_day_key(
            str(
                record[
                    "raceDayKey"
                ]
            )
        )
    )

    stage = str(
        record[
            "stage"
        ]
    )

    decision_contract.notification_key(
        race_day_key,
        stage,
    )

    return (
        f"{safe_prefix}/"
        f"{race_day_key}/"
        f"{stage}"
    )


def get_json(
    store,
    key: str,
) -> dict[str, Any] | None:
    body = store.get_bytes(
        key
    )

    if body is None:
        return None

    return (
        cloud_outbox
        .decode_json_object(
            body,
            key=key,
        )
    )


def put_json_if_absent(
    store,
    key: str,
    payload: dict[str, Any],
) -> bool:
    return store.put_if_absent(
        key,
        cloud_outbox.json_bytes(
            payload
        ),
        content_type=
            "application/json",
    )


def validate_delivered(
    *,
    delivered: dict[str, Any],
    record: dict[str, Any],
) -> None:
    if (
        delivered.get(
            "schemaVersion"
        )
        != "1.0"
        or delivered.get(
            "delivery"
        )
        != "v75-s3-pushover-delivery-v1"
        or delivered.get(
            "state"
        )
        != "DELIVERED"
        or delivered.get(
            "notificationKey"
        )
        != record.get(
            "notificationKey"
        )
        or delivered.get(
            "queuedPayloadSha256"
        )
        != record.get(
            "payloadSha256"
        )
    ):
        raise RuntimeError(
            "Existing delivered receipt "
            "is malformed or mismatched."
        )


def validate_attempt(
    *,
    attempt: dict[str, Any],
    record: dict[str, Any],
    attempt_number: int,
) -> None:
    if (
        attempt.get(
            "schemaVersion"
        )
        != "1.0"
        or attempt.get(
            "delivery"
        )
        != "v75-s3-pushover-delivery-v1"
        or attempt.get(
            "state"
        )
        != "STARTED"
        or attempt.get(
            "notificationKey"
        )
        != record.get(
            "notificationKey"
        )
        or attempt.get(
            "queuedPayloadSha256"
        )
        != record.get(
            "payloadSha256"
        )
        or attempt.get(
            "attemptNumber"
        )
        != attempt_number
    ):
        raise RuntimeError(
            "Existing delivery attempt "
            "is malformed or mismatched."
        )


def provider_failure_class(
    exc: Exception,
) -> str:
    text = str(exc)

    # A returned HTTP 4xx response is a
    # definite provider rejection. It is
    # safe to retry later after the cause
    # has been corrected.
    if re.match(
        r"^HTTP 4\d\d(?:\:|$)",
        text,
    ):
        return "DEFINITE_REJECTION"

    # Connection loss, timeout, 5xx or an
    # unexpected exception can occur after
    # the provider received the request.
    # Automatic retry could duplicate a
    # notification, so fail closed.
    return "AMBIGUOUS"


def delivery_result(
    *,
    state: str,
    record: dict[str, Any],
    queued_key: str,
    delivered_key: str,
    storage_network_used: bool,
    provider_network_used: bool,
    provider_invoked: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "schemaVersion":
            "1.0",
        "delivery":
            "v75-s3-pushover-delivery-v1",
        "state":
            state,
        "notificationKey":
            record.get(
                "notificationKey"
            ),
        "queuedKey":
            queued_key,
        "deliveredKey":
            delivered_key,
        "guardrails": {
            "networkUsed":
                (
                    storage_network_used
                    or provider_network_used
                ),
            "storageNetworkUsed":
                storage_network_used,
            "providerNetworkUsed":
                provider_network_used,
            "providerInvoked":
                provider_invoked,
            "credentialsPersisted":
                False,
            "repoWrites":
                False,
        },
    }

    if extra:
        result.update(
            extra
        )

    return result


def delivered_record(
    *,
    record: dict[str, Any],
    profile: dict[str, Any],
    provider_request: Any,
    delivered_at: datetime,
) -> dict[str, Any]:
    return {
        "schemaVersion":
            "1.0",
        "delivery":
            "v75-s3-pushover-delivery-v1",
        "state":
            "DELIVERED",
        "notificationKey":
            record[
                "notificationKey"
            ],
        "deliveredAt":
            delivered_at.isoformat(),
        "provider":
            "pushover",
        "providerRequest":
            provider_request,
        "queuedPayloadSha256":
            record[
                "payloadSha256"
            ],
        "title":
            profile["title"],
        "priority":
            profile["priority"],
        "ttl":
            profile["ttl"],
        "guardrails": {
            "credentialsPersisted":
                False,
            "notificationSent":
                True,
            "repoWrites":
                False,
        },
    }


def deliver_cloud(
    *,
    queued_key: str,
    store,
    now: datetime,
    app_token: str,
    user_key: str,
    prefix: str = "notifications",
    provider_fn: ProviderFn | None = None,
) -> dict[str, Any]:
    require_aware(
        now,
        "now",
    )

    queued_key = normalize_key(
        queued_key
    )

    prefix = (
        cloud_outbox
        .normalized_prefix(
            prefix
        )
    )

    queue_body = store.get_bytes(
        queued_key
    )

    if queue_body is None:
        raise ValueError(
            "Queued S3 object does not exist."
        )

    record = (
        cloud_outbox
        .decode_json_object(
            queue_body,
            key=queued_key,
        )
    )

    validate_cloud_queue_record(
        queued_key=queued_key,
        record=record,
        prefix=prefix,
    )

    stage_root = (
        stage_root_from_record(
            prefix=prefix,
            record=record,
        )
    )

    delivered_key = (
        f"{stage_root}/delivered.json"
    )

    storage_network_used = bool(
        getattr(
            store,
            "network_used",
            False,
        )
    )

    provider_network_used = (
        provider_fn is None
    )

    existing_delivered = get_json(
        store,
        delivered_key,
    )

    if existing_delivered is not None:
        validate_delivered(
            delivered=
                existing_delivered,
            record=record,
        )

        return delivery_result(
            state=
                "ALREADY_DELIVERED",
            record=record,
            queued_key=queued_key,
            delivered_key=
                delivered_key,
            storage_network_used=
                storage_network_used,
            provider_network_used=
                False,
            provider_invoked=
                False,
        )

    profile = (
        local_delivery
        .delivery_profile(
            record
        )
    )

    provider_payload = {
        "message":
            record["message"],
        "title":
            profile["title"],
        "priority":
            profile["priority"],
        "ttl":
            profile["ttl"],
    }

    now_oslo = now.astimezone(
        OSLO
    )

    for attempt_number in range(
        1,
        MAX_ATTEMPTS + 1,
    ):
        attempt_root = (
            f"{stage_root}/"
            "delivery-attempts/"
            f"{attempt_number:04d}"
        )

        attempt_key = (
            f"{attempt_root}/attempt.json"
        )

        failure_key = (
            f"{attempt_root}/failure.json"
        )

        uncertain_key = (
            f"{attempt_root}/uncertain.json"
        )

        provider_result_key = (
            f"{attempt_root}/"
            "provider-result.json"
        )

        attempt = get_json(
            store,
            attempt_key,
        )

        owns_attempt = False

        if attempt is None:
            candidate_attempt = {
                "schemaVersion":
                    "1.0",
                "delivery":
                    "v75-s3-pushover-delivery-v1",
                "state":
                    "STARTED",
                "attemptNumber":
                    attempt_number,
                "notificationKey":
                    record[
                        "notificationKey"
                    ],
                "startedAt":
                    now_oslo.isoformat(),
                "queuedPayloadSha256":
                    record[
                        "payloadSha256"
                    ],
                "provider":
                    "pushover",
                "providerPayload":
                    provider_payload,
                "guardrails": {
                    "credentialsPersisted":
                        False,
                    "notificationSent":
                        False,
                    "repoWrites":
                        False,
                },
            }

            owns_attempt = (
                put_json_if_absent(
                    store,
                    attempt_key,
                    candidate_attempt,
                )
            )

            if owns_attempt:
                attempt = (
                    candidate_attempt
                )
            else:
                attempt = get_json(
                    store,
                    attempt_key,
                )

                if attempt is None:
                    raise RuntimeError(
                        "Lost conditional-create "
                        "race but attempt object "
                        "is missing."
                    )

        validate_attempt(
            attempt=attempt,
            record=record,
            attempt_number=
                attempt_number,
        )

        provider_result = get_json(
            store,
            provider_result_key,
        )

        failure = get_json(
            store,
            failure_key,
        )

        uncertain = get_json(
            store,
            uncertain_key,
        )

        outcome_count = sum(
            item is not None
            for item in (
                provider_result,
                failure,
                uncertain,
            )
        )

        if outcome_count > 1:
            raise RuntimeError(
                "Delivery attempt contains "
                "conflicting terminal states."
            )

        if provider_result is not None:
            if (
                provider_result.get(
                    "state"
                )
                != "PROVIDER_ACCEPTED"
                or provider_result.get(
                    "notificationKey"
                )
                != record.get(
                    "notificationKey"
                )
                or provider_result.get(
                    "attemptNumber"
                )
                != attempt_number
            ):
                raise RuntimeError(
                    "Provider result is "
                    "malformed or mismatched."
                )

            healed = delivered_record(
                record=record,
                profile=profile,
                provider_request=
                    provider_result.get(
                        "request"
                    ),
                delivered_at=
                    now_oslo,
            )

            created = (
                put_json_if_absent(
                    store,
                    delivered_key,
                    healed,
                )
            )

            if not created:
                existing = get_json(
                    store,
                    delivered_key,
                )

                if existing is None:
                    raise RuntimeError(
                        "Lost delivered receipt "
                        "create race but receipt "
                        "is missing."
                    )

                validate_delivered(
                    delivered=existing,
                    record=record,
                )

            return delivery_result(
                state=(
                    "DELIVERED_RECOVERED"
                    if created
                    else
                    "ALREADY_DELIVERED"
                ),
                record=record,
                queued_key=queued_key,
                delivered_key=
                    delivered_key,
                storage_network_used=
                    storage_network_used,
                provider_network_used=
                    False,
                provider_invoked=
                    False,
                extra={
                    "attemptNumber":
                        attempt_number,
                    "providerRequest":
                        provider_result.get(
                            "request"
                        ),
                },
            )

        if uncertain is not None:
            return delivery_result(
                state=
                    "DELIVERY_UNCERTAIN",
                record=record,
                queued_key=queued_key,
                delivered_key=
                    delivered_key,
                storage_network_used=
                    storage_network_used,
                provider_network_used=
                    False,
                provider_invoked=
                    False,
                extra={
                    "attemptNumber":
                        attempt_number,
                    "reason":
                        "AMBIGUOUS_PROVIDER_RESULT",
                },
            )

        if failure is not None:
            if (
                failure.get(
                    "state"
                )
                != "DELIVERY_FAILED"
                or failure.get(
                    "notificationKey"
                )
                != record.get(
                    "notificationKey"
                )
                or failure.get(
                    "attemptNumber"
                )
                != attempt_number
                or failure.get(
                    "failureClass"
                )
                != "DEFINITE_REJECTION"
            ):
                raise RuntimeError(
                    "Failure receipt is "
                    "malformed or mismatched."
                )

            # A definite rejection is safe
            # to retry using the next
            # deterministic attempt slot.
            continue

        if not owns_attempt:
            # Another worker owns this
            # attempt and no terminal
            # receipt exists yet. Do not
            # call the provider again.
            return delivery_result(
                state=
                    "DELIVERY_UNCERTAIN",
                record=record,
                queued_key=queued_key,
                delivered_key=
                    delivered_key,
                storage_network_used=
                    storage_network_used,
                provider_network_used=
                    False,
                provider_invoked=
                    False,
                extra={
                    "attemptNumber":
                        attempt_number,
                    "reason":
                        "ATTEMPT_IN_PROGRESS_OR_CRASHED",
                },
            )

        actual_provider = (
            provider_fn
            if provider_fn is not None
            else local_delivery
            .pushover_provider
        )

        try:
            response = (
                actual_provider(
                    provider_payload,
                    app_token,
                    user_key,
                )
            )

        except Exception as exc:
            failure_class = (
                provider_failure_class(
                    exc
                )
            )

            safe_error = (
                local_delivery
                .sanitize_error(
                    exc,
                    (
                        app_token,
                        user_key,
                    ),
                )
            )

            if (
                failure_class
                == "DEFINITE_REJECTION"
            ):
                receipt = {
                    "schemaVersion":
                        "1.0",
                    "state":
                        "DELIVERY_FAILED",
                    "failureClass":
                        "DEFINITE_REJECTION",
                    "attemptNumber":
                        attempt_number,
                    "notificationKey":
                        record[
                            "notificationKey"
                        ],
                    "failedAt":
                        now_oslo.isoformat(),
                    "errorType":
                        type(exc).__name__,
                    "error":
                        safe_error,
                    "retryable":
                        True,
                    "guardrails": {
                        "credentialsPersisted":
                            False,
                        "notificationSent":
                            False,
                        "repoWrites":
                            False,
                    },
                }

                if not put_json_if_absent(
                    store,
                    failure_key,
                    receipt,
                ):
                    raise RuntimeError(
                        "Failure receipt "
                        "already exists."
                    )

                return delivery_result(
                    state=
                        "DELIVERY_FAILED",
                    record=record,
                    queued_key=
                        queued_key,
                    delivered_key=
                        delivered_key,
                    storage_network_used=
                        storage_network_used,
                    provider_network_used=
                        provider_network_used,
                    provider_invoked=
                        True,
                    extra={
                        "attemptNumber":
                            attempt_number,
                        "failureClass":
                            failure_class,
                        "retryable":
                            True,
                        "error":
                            safe_error,
                    },
                )

            receipt = {
                "schemaVersion":
                    "1.0",
                "state":
                    "DELIVERY_UNCERTAIN",
                "failureClass":
                    "AMBIGUOUS",
                "attemptNumber":
                    attempt_number,
                "notificationKey":
                    record[
                        "notificationKey"
                    ],
                "failedAt":
                    now_oslo.isoformat(),
                "errorType":
                    type(exc).__name__,
                "error":
                    safe_error,
                "retryable":
                    False,
                "guardrails": {
                    "credentialsPersisted":
                        False,
                    "notificationSent":
                        "UNKNOWN",
                    "repoWrites":
                        False,
                },
            }

            if not put_json_if_absent(
                store,
                uncertain_key,
                receipt,
            ):
                raise RuntimeError(
                    "Uncertain receipt "
                    "already exists."
                )

            return delivery_result(
                state=
                    "DELIVERY_UNCERTAIN",
                record=record,
                queued_key=
                    queued_key,
                delivered_key=
                    delivered_key,
                storage_network_used=
                    storage_network_used,
                provider_network_used=
                    provider_network_used,
                provider_invoked=
                    True,
                extra={
                    "attemptNumber":
                        attempt_number,
                    "failureClass":
                        failure_class,
                    "retryable":
                        False,
                    "error":
                        safe_error,
                },
            )

        if (
            not isinstance(
                response,
                dict,
            )
            or response.get(
                "status"
            ) != 1
        ):
            raise RuntimeError(
                "Provider returned an "
                "invalid success response."
            )

        provider_result = {
            "schemaVersion":
                "1.0",
            "state":
                "PROVIDER_ACCEPTED",
            "provider":
                "pushover",
            "attemptNumber":
                attempt_number,
            "notificationKey":
                record[
                    "notificationKey"
                ],
            "request":
                response.get(
                    "request"
                ),
            "acceptedAt":
                now_oslo.isoformat(),
        }

        if not put_json_if_absent(
            store,
            provider_result_key,
            provider_result,
        ):
            raise RuntimeError(
                "Provider result receipt "
                "already exists."
            )

        delivered = delivered_record(
            record=record,
            profile=profile,
            provider_request=
                response.get(
                    "request"
                ),
            delivered_at=
                now_oslo,
        )

        created = (
            put_json_if_absent(
                store,
                delivered_key,
                delivered,
            )
        )

        if not created:
            existing = get_json(
                store,
                delivered_key,
            )

            if existing is None:
                raise RuntimeError(
                    "Lost delivered receipt "
                    "create race but receipt "
                    "is missing."
                )

            validate_delivered(
                delivered=existing,
                record=record,
            )

        return delivery_result(
            state=(
                "DELIVERED"
                if created
                else
                "ALREADY_DELIVERED"
            ),
            record=record,
            queued_key=queued_key,
            delivered_key=
                delivered_key,
            storage_network_used=
                storage_network_used,
            provider_network_used=
                provider_network_used,
            provider_invoked=
                True,
            extra={
                "attemptNumber":
                    attempt_number,
                "providerRequest":
                    response.get(
                        "request"
                    ),
                "priority":
                    profile[
                        "priority"
                    ],
                "title":
                    profile[
                        "title"
                    ],
            },
        )

    return delivery_result(
        state=
            "DELIVERY_RETRY_LIMIT",
        record=record,
        queued_key=queued_key,
        delivered_key=
            delivered_key,
        storage_network_used=
            storage_network_used,
        provider_network_used=
            False,
        provider_invoked=
            False,
        extra={
            "maxAttempts":
                MAX_ATTEMPTS,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--queued-key",
        required=True,
    )

    parser.add_argument(
        "--prefix",
        default="notifications",
    )

    parser.add_argument(
        "--now",
    )

    args = parser.parse_args()

    app_token = os.environ.get(
        "PUSHOVER_APP_TOKEN",
        "",
    )

    user_key = os.environ.get(
        "PUSHOVER_USER_KEY",
        "",
    )

    if not app_token:
        raise SystemExit(
            "Missing PUSHOVER_APP_TOKEN."
        )

    if not user_key:
        raise SystemExit(
            "Missing PUSHOVER_USER_KEY."
        )

    now = (
        local_delivery.parse_datetime(
            args.now
        )
        if args.now
        else datetime.now(
            OSLO
        )
    )

    store = (
        cloud_outbox
        .Boto3ObjectStore
        .from_env()
    )

    result = deliver_cloud(
        queued_key=
            args.queued_key,
        store=store,
        now=now,
        app_token=
            app_token,
        user_key=
            user_key,
        prefix=
            args.prefix,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    if result.get("state") in {
        "DELIVERY_FAILED",
        "DELIVERY_UNCERTAIN",
        "DELIVERY_RETRY_LIMIT",
    }:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
