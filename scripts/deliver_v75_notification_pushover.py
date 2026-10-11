from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.resolve()

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPT_DIR),
    )

import decide_v75_notification as decision_contract


OSLO = ZoneInfo("Europe/Oslo")

PUSHOVER_ENDPOINT = (
    "https://api.pushover.net/1/messages.json"
)

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


def validate_runtime_path(
    path: Path,
) -> Path:
    resolved = (
        path.expanduser().resolve()
    )

    if (
        resolved == REPO_ROOT
        or resolved.is_relative_to(
            REPO_ROOT
        )
    ):
        raise ValueError(
            "Notification runtime data "
            "must be outside repository."
        )

    return resolved


def load_json(
    path: Path,
) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save_json_exclusive(
    path: Path,
    payload: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "x",
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
        )

        handle.write("\n")


def validate_queue_record(
    queued_path: Path,
    record: dict[str, Any],
) -> None:
    if queued_path.name != "queued.json":
        raise ValueError(
            "Expected queued.json input."
        )

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
            "outbox record."
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

    expected_key = (
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
        != expected_key
    ):
        raise ValueError(
            "Outbox notification key "
            "does not match stage."
        )

    if (
        queued_path.parent.name
        != stage
        or queued_path.parent.parent.name
        != race_day_key
    ):
        raise ValueError(
            "Outbox path does not match "
            "record identity."
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
            "Queued notification has "
            "no message."
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
            "Queued notification has "
            "no payload hash."
        )


def delivery_profile(
    record: dict[str, Any],
) -> dict[str, Any]:
    stage = record["stage"]
    action = record["action"]

    if stage == "HEADS_UP":
        return {
            "title":
                "Hest V75 – Heads up",
            "priority":
                0,
            "ttl":
                3600,
        }

    if stage == "FINAL":
        title = (
            "Hest V75 – NO BET"
            if action == "NO_BET"
            else "Hest V75 – beslutning"
        )

        return {
            "title":
                title,
            "priority":
                1,
            "ttl":
                1800,
        }

    if stage == "LAST_CALL":
        return {
            "title":
                "Hest V75 – 5 min igjen",
            "priority":
                1,
            "ttl":
                600,
        }

    raise ValueError(
        f"Unsupported stage: {stage}"
    )


def sanitize_error(
    exc: Exception,
    secrets: tuple[str, ...],
) -> str:
    text = str(exc)

    for secret in secrets:
        if secret:
            text = text.replace(
                secret,
                "[REDACTED]",
            )

    return text


def pushover_provider(
    payload: dict[str, Any],
    app_token: str,
    user_key: str,
) -> dict[str, Any]:
    if not app_token:
        raise ValueError(
            "Missing Pushover app token."
        )

    if not user_key:
        raise ValueError(
            "Missing Pushover user key."
        )

    form = {
        "token":
            app_token,
        "user":
            user_key,
        "message":
            str(payload["message"]),
        "title":
            str(payload["title"]),
        "priority":
            str(payload["priority"]),
        "ttl":
            str(payload["ttl"]),
    }

    body = urllib.parse.urlencode(
        form
    ).encode(
        "utf-8"
    )

    request = urllib.request.Request(
        PUSHOVER_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Content-Type":
                "application/x-www-form-urlencoded",
            "Accept":
                "application/json",
            "User-Agent":
                "Hest-V75/1.0",
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=15,
        ) as response:
            raw = response.read()

    except urllib.error.HTTPError as exc:
        try:
            body_text = (
                exc.read()
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )
        except Exception:
            body_text = ""

        error_detail = (
            f"HTTP {exc.code}"
        )

        try:
            parsed = json.loads(
                body_text
            )

            errors = parsed.get(
                "errors"
            )

            if isinstance(
                errors,
                list,
            ):
                error_detail += (
                    ": "
                    + "; ".join(
                        str(item)
                        for item in errors
                    )
                )
        except Exception:
            pass

        raise RuntimeError(
            error_detail
        ) from None

    except urllib.error.URLError as exc:
        raise RuntimeError(
            "Pushover network error: "
            f"{exc.reason}"
        ) from None

    result = json.loads(
        raw.decode("utf-8")
    )

    if (
        not isinstance(
            result,
            dict,
        )
        or result.get("status") != 1
    ):
        raise RuntimeError(
            "Pushover did not accept "
            "the message."
        )

    return result


def delivery_result(
    *,
    state: str,
    record: dict[str, Any],
    delivered_path: Path,
    network_used: bool,
    provider_invoked: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "schemaVersion":
            "1.0",
        "delivery":
            "v75-pushover-delivery-v1",
        "state":
            state,
        "notificationKey":
            record.get(
                "notificationKey"
            ),
        "deliveredPath":
            str(delivered_path),
        "guardrails": {
            "networkUsed":
                network_used,
            "providerInvoked":
                provider_invoked,
            "repoWrites":
                False,
        },
    }

    if extra:
        result.update(
            extra
        )

    return result


def unresolved_attempts(
    attempts_root: Path,
) -> list[Path]:
    if not attempts_root.is_dir():
        return []

    unresolved: list[Path] = []

    for attempt in sorted(
        attempts_root.iterdir()
    ):
        if not attempt.is_dir():
            continue

        started = (
            attempt
            / "attempt.json"
        )

        if not started.is_file():
            continue

        if (
            (
                attempt
                / "failure.json"
            ).is_file()
            or (
                attempt
                / "provider-result.json"
            ).is_file()
        ):
            continue

        unresolved.append(
            attempt
        )

    return unresolved


def deliver(
    *,
    queued_json: Path,
    now: datetime,
    app_token: str,
    user_key: str,
    provider_fn: ProviderFn | None = None,
) -> dict[str, Any]:
    require_aware(
        now,
        "now",
    )

    queued_path = (
        validate_runtime_path(
            queued_json
        )
    )

    record = load_json(
        queued_path
    )

    if not isinstance(
        record,
        dict,
    ):
        raise ValueError(
            "queued.json must contain "
            "an object."
        )

    validate_queue_record(
        queued_path,
        record,
    )

    stage_root = (
        queued_path.parent
    )

    delivered_path = (
        stage_root
        / "delivered.json"
    )

    network_used = (
        provider_fn is None
    )

    if delivered_path.is_file():
        existing = load_json(
            delivered_path
        )

        if (
            existing.get(
                "notificationKey"
            )
            != record.get(
                "notificationKey"
            )
        ):
            raise RuntimeError(
                "Delivered receipt identity "
                "does not match queue."
            )

        return delivery_result(
            state=
                "ALREADY_DELIVERED",
            record=
                record,
            delivered_path=
                delivered_path,
            network_used=
                False,
            provider_invoked=
                False,
        )

    attempts_root = (
        stage_root
        / "delivery-attempts"
    )

    unresolved = (
        unresolved_attempts(
            attempts_root
        )
    )

    if unresolved:
        return delivery_result(
            state=
                "DELIVERY_UNCERTAIN",
            record=
                record,
            delivered_path=
                delivered_path,
            network_used=
                False,
            provider_invoked=
                False,
            extra={
                "unresolvedAttempts":
                    [
                        str(path)
                        for path
                        in unresolved
                    ],
            },
        )

    lock_path = (
        stage_root
        / ".delivery.lock"
    )

    try:
        lock_handle = lock_path.open(
            "x",
            encoding="utf-8",
        )

    except FileExistsError:
        return delivery_result(
            state=
                "DELIVERY_IN_PROGRESS",
            record=
                record,
            delivered_path=
                delivered_path,
            network_used=
                False,
            provider_invoked=
                False,
        )

    provider_invoked = False

    try:
        now_oslo = now.astimezone(
            OSLO
        )

        lock_handle.write(
            now_oslo.isoformat()
            + "\n"
        )
        lock_handle.close()

        stamp = (
            now_oslo.strftime(
                "%Y%m%dT%H%M%S%f%z"
            )
        )

        attempt_dir = (
            attempts_root
            / stamp
        )

        attempt_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        profile = (
            delivery_profile(
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

        attempt = {
            "schemaVersion":
                "1.0",
            "delivery":
                "v75-pushover-delivery-v1",
            "state":
                "STARTED",
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

        save_json_exclusive(
            attempt_dir
            / "attempt.json",
            attempt,
        )

        actual_provider = (
            provider_fn
            if provider_fn is not None
            else pushover_provider
        )

        provider_invoked = True

        try:
            response = (
                actual_provider(
                    provider_payload,
                    app_token,
                    user_key,
                )
            )

        except Exception as exc:
            failure = {
                "schemaVersion":
                    "1.0",
                "state":
                    "DELIVERY_FAILED",
                "notificationKey":
                    record[
                        "notificationKey"
                    ],
                "failedAt":
                    datetime.now(
                        OSLO
                    ).isoformat(),
                "errorType":
                    type(exc).__name__,
                "error":
                    sanitize_error(
                        exc,
                        (
                            app_token,
                            user_key,
                        ),
                    ),
                "retryable":
                    True,
                "guardrails": {
                    "credentialsPersisted":
                        False,
                    "repoWrites":
                        False,
                },
            }

            save_json_exclusive(
                attempt_dir
                / "failure.json",
                failure,
            )

            return delivery_result(
                state=
                    "DELIVERY_FAILED",
                record=
                    record,
                delivered_path=
                    delivered_path,
                network_used=
                    network_used,
                provider_invoked=
                    True,
                extra={
                    "attemptDirectory":
                        str(
                            attempt_dir
                        ),
                    "errorType":
                        failure[
                            "errorType"
                        ],
                    "error":
                        failure[
                            "error"
                        ],
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
            "provider":
                "pushover",
            "status":
                1,
            "request":
                response.get(
                    "request"
                ),
            "acceptedAt":
                datetime.now(
                    OSLO
                ).isoformat(),
        }

        save_json_exclusive(
            attempt_dir
            / "provider-result.json",
            provider_result,
        )

        delivered = {
            "schemaVersion":
                "1.0",
            "delivery":
                "v75-pushover-delivery-v1",
            "state":
                "DELIVERED",
            "notificationKey":
                record[
                    "notificationKey"
                ],
            "deliveredAt":
                datetime.now(
                    OSLO
                ).isoformat(),
            "provider":
                "pushover",
            "providerRequest":
                provider_result.get(
                    "request"
                ),
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

        save_json_exclusive(
            delivered_path,
            delivered,
        )

        return delivery_result(
            state=
                "DELIVERED",
            record=
                record,
            delivered_path=
                delivered_path,
            network_used=
                network_used,
            provider_invoked=
                True,
            extra={
                "providerRequest":
                    provider_result.get(
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

    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--queued-json",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--now",
        help=(
            "Optional deterministic "
            "delivery time."
        ),
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
        parse_datetime(
            args.now
        )
        if args.now
        else datetime.now(
            OSLO
        )
    )

    result = deliver(
        queued_json=
            args.queued_json,
        now=now,
        app_token=
            app_token,
        user_key=
            user_key,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    if (
        result.get("state")
        in {
            "DELIVERY_FAILED",
            "DELIVERY_UNCERTAIN",
        }
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
