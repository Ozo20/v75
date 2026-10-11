from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Protocol
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
import deliver_v75_notification_s3_pushover as cloud_delivery
import queue_v75_notification_s3 as cloud_outbox


OSLO = ZoneInfo("Europe/Oslo")


class RuntimeStore(Protocol):
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

    def list_keys(
        self,
        prefix: str,
    ) -> list[str]:
        ...


class Boto3RuntimeStore(
    cloud_outbox.Boto3ObjectStore
):
    def list_keys(
        self,
        prefix: str,
    ) -> list[str]:
        safe_prefix = (
            cloud_outbox
            .normalized_prefix(
                prefix
            )
            + "/"
        )

        paginator = (
            self.client
            .get_paginator(
                "list_objects_v2"
            )
        )

        keys: list[str] = []

        for page in paginator.paginate(
            Bucket=self.bucket,
            Prefix=safe_prefix,
        ):
            for row in (
                page.get("Contents")
                or []
            ):
                key = row.get("Key")

                if (
                    isinstance(
                        key,
                        str,
                    )
                    and key
                ):
                    keys.append(
                        key
                    )

        return sorted(
            set(keys)
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
            f"{name} must be timezone-aware"
        )


def parse_enabled(
    value: str,
) -> bool:
    normalized = (
        value.strip()
        .lower()
    )

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "",
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise ValueError(
        "V75_NOTIFICATION_DELIVERY_ENABLED "
        "must be true or false."
    )


def is_queue_key(
    *,
    key: str,
    prefix: str,
) -> bool:
    safe_prefix = (
        cloud_outbox
        .normalized_prefix(
            prefix
        )
    )

    root = safe_prefix + "/"

    if not key.startswith(
        root
    ):
        return False

    relative = key[
        len(root):
    ]

    parts = relative.split(
        "/"
    )

    if len(parts) != 3:
        return False

    race_day_key, stage, filename = (
        parts
    )

    if filename != "queued.json":
        return False

    try:
        race_day_key = (
            decision_contract
            .safe_race_day_key(
                race_day_key
            )
        )

        decision_contract.notification_key(
            race_day_key,
            stage,
        )

    except ValueError:
        return False

    return True


def discover_queue_keys(
    *,
    store: RuntimeStore,
    prefix: str,
) -> list[str]:
    safe_prefix = (
        cloud_outbox
        .normalized_prefix(
            prefix
        )
    )

    candidates = (
        store.list_keys(
            safe_prefix
        )
    )

    return [
        key
        for key in candidates
        if is_queue_key(
            key=key,
            prefix=safe_prefix,
        )
    ]


def safe_runtime_exception(
    exc: Exception,
) -> dict[str, Any]:
    return {
        "state":
            "RUNTIME_ERROR",
        "errorType":
            type(exc).__name__,
        "reason":
            "DELIVERY_RUNTIME_EXCEPTION",
    }


def runtime_result(
    *,
    state: str,
    enabled: bool,
    prefix: str,
    queued_keys: list[str],
    results: list[dict[str, Any]],
    network_used: bool,
) -> dict[str, Any]:
    counts: dict[str, int] = {}

    for result in results:
        result_state = str(
            result.get(
                "state"
            )
            or "UNKNOWN"
        )

        counts[result_state] = (
            counts.get(
                result_state,
                0,
            )
            + 1
        )

    return {
        "schemaVersion":
            "1.0",
        "runtime":
            "v75-notification-runtime-v1",
        "state":
            state,
        "enabled":
            enabled,
        "prefix":
            prefix,
        "queuedCount":
            len(
                queued_keys
            ),
        "processedCount":
            len(
                results
            ),
        "counts":
            counts,
        "results":
            results,
        "guardrails": {
            "networkUsed":
                network_used,
            "automaticBetSubmission":
                False,
            "outcomeDataUsed":
                False,
            "repoWrites":
                False,
        },
    }


def run_runtime(
    *,
    store: RuntimeStore,
    now: datetime,
    enabled: bool,
    app_token: str = "",
    user_key: str = "",
    prefix: str = "notifications",
    provider_fn=None,
) -> dict[str, Any]:
    require_aware(
        now,
        "now",
    )

    prefix = (
        cloud_outbox
        .normalized_prefix(
            prefix
        )
    )

    queued_keys = (
        discover_queue_keys(
            store=store,
            prefix=prefix,
        )
    )

    network_used = bool(
        getattr(
            store,
            "network_used",
            False,
        )
    )

    if not enabled:
        return runtime_result(
            state="DISABLED",
            enabled=False,
            prefix=prefix,
            queued_keys=
                queued_keys,
            results=[],
            network_used=
                network_used,
        )

    if provider_fn is None:
        if not app_token:
            raise ValueError(
                "Missing PUSHOVER_APP_TOKEN "
                "while delivery is enabled."
            )

        if not user_key:
            raise ValueError(
                "Missing PUSHOVER_USER_KEY "
                "while delivery is enabled."
            )

    results: list[
        dict[str, Any]
    ] = []

    blocking = False
    retryable_failure = False

    for queued_key in queued_keys:
        try:
            delivery_result = (
                cloud_delivery
                .deliver_cloud(
                    queued_key=
                        queued_key,
                    store=store,
                    now=now,
                    app_token=
                        app_token,
                    user_key=
                        user_key,
                    prefix=prefix,
                    provider_fn=
                        provider_fn,
                )
            )

            compact = {
                "queuedKey":
                    queued_key,
                "state":
                    delivery_result.get(
                        "state"
                    ),
                "notificationKey":
                    delivery_result.get(
                        "notificationKey"
                    ),
                "providerInvoked":
                    (
                        delivery_result
                        .get(
                            "guardrails",
                            {},
                        )
                        .get(
                            "providerInvoked"
                        )
                    ),
            }

            results.append(
                compact
            )

            state = str(
                delivery_result.get(
                    "state"
                )
                or ""
            )

            if state in {
                "DELIVERY_UNCERTAIN",
                "DELIVERY_RETRY_LIMIT",
            }:
                blocking = True

            if state == "DELIVERY_FAILED":
                retryable_failure = True

        except Exception as exc:
            compact = {
                "queuedKey":
                    queued_key,
                **safe_runtime_exception(
                    exc
                ),
            }

            results.append(
                compact
            )

            blocking = True

    if blocking:
        state = "DEGRADED"

    elif retryable_failure:
        state = "RETRYABLE_FAILURE"

    else:
        state = "ACTIVE"

    return runtime_result(
        state=state,
        enabled=True,
        prefix=prefix,
        queued_keys=
            queued_keys,
        results=results,
        network_used=
            network_used
            or provider_fn is None,
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--prefix",
        default=os.environ.get(
            "V75_NOTIFICATION_PREFIX",
            "notifications",
        ),
    )

    parser.add_argument(
        "--now",
        help=(
            "Optional deterministic "
            "runtime timestamp."
        ),
    )

    args = parser.parse_args()

    enabled = parse_enabled(
        os.environ.get(
            "V75_NOTIFICATION_DELIVERY_ENABLED",
            "false",
        )
    )

    now = (
        cloud_delivery
        .local_delivery
        .parse_datetime(
            args.now
        )
        if args.now
        else datetime.now(
            OSLO
        )
    )

    app_token = os.environ.get(
        "PUSHOVER_APP_TOKEN",
        "",
    )

    user_key = os.environ.get(
        "PUSHOVER_USER_KEY",
        "",
    )

    store = (
        Boto3RuntimeStore
        .from_env()
    )

    result = run_runtime(
        store=store,
        now=now,
        enabled=enabled,
        app_token=
            app_token,
        user_key=
            user_key,
        prefix=args.prefix,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    if result["state"] in {
        "DEGRADED",
        "RETRYABLE_FAILURE",
    }:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
