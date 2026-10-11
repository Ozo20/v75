from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.resolve()

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPT_DIR),
    )

import decide_v75_notification as notification_decision


OSLO = ZoneInfo("Europe/Oslo")

SENDABLE_ACTIONS: dict[
    str,
    str,
] = {
    "HEADS_UP":
        "HEADS_UP",
    "PLAY":
        "FINAL",
    "NO_BET":
        "FINAL",
    "LAST_CALL":
        "LAST_CALL",
}


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


def validate_output_root(
    output_root: Path,
) -> Path:
    resolved = (
        output_root
        .expanduser()
        .resolve()
    )

    if (
        resolved == REPO_ROOT
        or resolved.is_relative_to(
            REPO_ROOT
        )
    ):
        raise ValueError(
            "Outbox root must be outside "
            "the repository."
        )

    return resolved


def canonical_json_bytes(
    payload: Any,
) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )


def sha256_payload(
    payload: Any,
) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            payload
        )
    ).hexdigest()


def load_json(
    path: Path,
) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def validate_source_decision(
    decision: dict[str, Any],
) -> None:
    if (
        decision.get(
            "schemaVersion"
        )
        != "1.0"
    ):
        raise ValueError(
            "Unsupported notification "
            "decision schema."
        )

    if (
        decision.get("decision")
        != "v75-notification-decision-v1"
    ):
        raise ValueError(
            "Unsupported notification "
            "decision source."
        )

    race_day_key = (
        notification_decision
        .safe_race_day_key(
            str(
                decision.get(
                    "raceDayKey"
                )
                or ""
            )
        )
    )

    action = str(
        decision.get(
            "action"
        )
        or ""
    )

    guardrails = (
        decision.get(
            "guardrails"
        )
        or {}
    )

    if not isinstance(
        guardrails,
        dict,
    ):
        raise ValueError(
            "Missing decision guardrails."
        )

    if (
        guardrails.get(
            "notificationSent"
        )
        is not False
    ):
        raise ValueError(
            "Outbox accepts only "
            "pre-delivery decisions."
        )

    if (
        guardrails.get(
            "networkUsed"
        )
        is not False
    ):
        raise ValueError(
            "Source decision unexpectedly "
            "used network."
        )

    if action == "SILENT":
        if (
            decision.get("stage")
            is not None
            or decision.get(
                "notificationKey"
            )
            is not None
            or decision.get(
                "message"
            )
            is not None
        ):
            raise ValueError(
                "SILENT decision contains "
                "sendable notification data."
            )

        return

    expected_stage = (
        SENDABLE_ACTIONS.get(
            action
        )
    )

    if expected_stage is None:
        raise ValueError(
            f"Unsupported notification "
            f"action: {action}"
        )

    stage = decision.get(
        "stage"
    )

    if stage != expected_stage:
        raise ValueError(
            "Notification action/stage "
            "mismatch."
        )

    expected_key = (
        notification_decision
        .notification_key(
            race_day_key,
            expected_stage,
        )
    )

    if (
        decision.get(
            "notificationKey"
        )
        != expected_key
    ):
        raise ValueError(
            "Notification key does not "
            "match race day and stage."
        )

    message = decision.get(
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
            "Sendable decision must "
            "contain a message."
        )

    minutes = decision.get(
        "minutesToStart"
    )

    if (
        not isinstance(
            minutes,
            (int, float),
        )
        or isinstance(
            minutes,
            bool,
        )
    ):
        raise ValueError(
            "Sendable decision must "
            "contain minutesToStart."
        )


def normalized_payload(
    decision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "notificationKey":
            decision.get(
                "notificationKey"
            ),
        "action":
            decision.get(
                "action"
            ),
        "stage":
            decision.get(
                "stage"
            ),
        "raceDayKey":
            decision.get(
                "raceDayKey"
            ),
        "raceDayName":
            decision.get(
                "raceDayName"
            ),
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
    }


def queue_record_path(
    output_root: Path,
    race_day_key: str,
    stage: str,
) -> Path:
    return (
        output_root
        / race_day_key
        / stage
        / "queued.json"
    )


def existing_result(
    *,
    output_root: Path,
    record_path: Path,
    candidate_hash: str,
) -> dict[str, Any]:
    existing = load_json(
        record_path
    )

    if (
        existing.get("state")
        != "QUEUED"
    ):
        raise RuntimeError(
            "Existing outbox record "
            "is not QUEUED."
        )

    existing_key = (
        existing.get(
            "notificationKey"
        )
    )

    existing_hash = (
        existing.get(
            "payloadSha256"
        )
    )

    if (
        not isinstance(
            existing_key,
            str,
        )
        or not existing_key
        or not isinstance(
            existing_hash,
            str,
        )
        or not existing_hash
    ):
        raise RuntimeError(
            "Existing outbox record "
            "is malformed."
        )

    relative = (
        record_path
        .relative_to(
            output_root
        )
        .as_posix()
    )

    return {
        "schemaVersion":
            "1.0",
        "outbox":
            "v75-notification-outbox-v1",
        "state":
            "ALREADY_QUEUED",
        "notificationKey":
            existing_key,
        "recordPath":
            relative,
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
                False,
            "providerInvoked":
                False,
            "repoWrites":
                False,
        },
    }


def enqueue_notification(
    *,
    decision: dict[str, Any],
    output_root: Path,
    now: datetime,
) -> dict[str, Any]:
    require_aware(
        now,
        "now",
    )

    output_root = (
        validate_output_root(
            output_root
        )
    )

    validate_source_decision(
        decision
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
            "outbox":
                "v75-notification-outbox-v1",
            "state":
                "SKIPPED_SILENT",
            "notificationKey":
                None,
            "recordPath":
                None,
            "guardrails": {
                "networkUsed":
                    False,
                "providerInvoked":
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

    expected_key = (
        notification_decision
        .notification_key(
            race_day_key,
            stage,
        )
    )

    payload = (
        normalized_payload(
            decision
        )
    )

    payload_hash = (
        sha256_payload(
            payload
        )
    )

    record_path = (
        queue_record_path(
            output_root,
            race_day_key,
            stage,
        )
    )

    if record_path.exists():
        return existing_result(
            output_root=
                output_root,
            record_path=
                record_path,
            candidate_hash=
                payload_hash,
        )

    record_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    queued_at = (
        now.astimezone(
            OSLO
        )
    )

    relative_path = (
        record_path
        .relative_to(
            output_root
        )
        .as_posix()
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
            expected_key,
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
                False,
            "providerInvoked":
                False,
            "notificationSent":
                False,
            "repoWrites":
                False,
        },
    }

    try:
        with record_path.open(
            "x",
            encoding="utf-8",
        ) as handle:
            json.dump(
                record,
                handle,
                ensure_ascii=False,
                indent=2,
            )

            handle.write("\n")

    except FileExistsError:
        return existing_result(
            output_root=
                output_root,
            record_path=
                record_path,
            candidate_hash=
                payload_hash,
        )

    return {
        "schemaVersion":
            "1.0",
        "outbox":
            "v75-notification-outbox-v1",
        "state":
            "QUEUED",
        "notificationKey":
            expected_key,
        "recordPath":
            relative_path,
        "queuedPayloadSha256":
            payload_hash,
        "candidatePayloadSha256":
            payload_hash,
        "samePayload":
            True,
        "guardrails": {
            "networkUsed":
                False,
            "providerInvoked":
                False,
            "repoWrites":
                False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--decision-json",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--now",
        help=(
            "Optional deterministic "
            "queue time."
        ),
    )

    args = parser.parse_args()

    decision = load_json(
        args.decision_json
    )

    if not isinstance(
        decision,
        dict,
    ):
        raise ValueError(
            "Decision JSON must contain "
            "an object."
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

    result = enqueue_notification(
        decision=decision,
        output_root=
            args.output_root,
        now=now,
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
