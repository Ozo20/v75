from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


OSLO = ZoneInfo("Europe/Oslo")

SLOTS: tuple[
    tuple[str, float],
    ...,
] = (
    ("T-12H", 720.0),
    ("T-6H", 360.0),
    ("T-4H", 240.0),
    ("T-3H", 180.0),
    ("T-2H", 120.0),
    ("T-1H", 60.0),
    ("T-30M", 30.0),
    ("T-15M", 15.0),
    ("T-5M", 5.0),
)

SLOT_LABELS = tuple(
    label
    for label, _offset
    in SLOTS
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


def current_slot(
    minutes_to_start: float,
) -> tuple[
    str,
    float,
    float,
] | None:
    candidates = [
        (
            index,
            label,
            offset,
        )
        for index, (
            label,
            offset,
        )
        in enumerate(SLOTS)
        if offset
        >= minutes_to_start
    ]

    if not candidates:
        return None

    (
        index,
        label,
        offset,
    ) = min(
        candidates,
        key=lambda row: row[2],
    )

    if index + 1 < len(SLOTS):
        lower_boundary = (
            SLOTS[
                index + 1
            ][1]
        )
    else:
        lower_boundary = 0.0

    return (
        label,
        offset,
        lower_boundary,
    )


def decide_snapshot_slot(
    *,
    now: datetime,
    first_v75_start_at: (
        datetime | None
    ),
    captured_slots: set[str],
) -> dict[str, Any]:
    require_aware(
        now,
        "now",
    )

    unknown_slots = (
        captured_slots
        - set(SLOT_LABELS)
    )

    if unknown_slots:
        raise ValueError(
            "Unknown captured slots: "
            + ", ".join(
                sorted(
                    unknown_slots
                )
            )
        )

    now_oslo = now.astimezone(
        OSLO
    )

    base: dict[str, Any] = {
        "schemaVersion":
            "1.0",
        "scheduler":
            "v75-market-snapshot-scheduler-v1",
        "now":
            now_oslo.isoformat(),
        "firstV75StartAt":
            None,
        "minutesToStart":
            None,
        "state":
            None,
        "slot":
            None,
        "guardrails": {
            "networkUsed":
                False,
            "collectorInvoked":
                False,
            "repoWrites":
                False,
        },
    }

    if first_v75_start_at is None:
        base["state"] = (
            "NO_UPCOMING_V75"
        )

        return base

    require_aware(
        first_v75_start_at,
        "first_v75_start_at",
    )

    start_oslo = (
        first_v75_start_at
        .astimezone(OSLO)
    )

    minutes_to_start = (
        (
            start_oslo
            - now_oslo
        ).total_seconds()
        / 60.0
    )

    base[
        "firstV75StartAt"
    ] = start_oslo.isoformat()

    base[
        "minutesToStart"
    ] = minutes_to_start

    if minutes_to_start < 0:
        base["state"] = (
            "TOO_LATE"
        )

        return base

    if (
        minutes_to_start
        > SLOTS[0][1]
    ):
        base["state"] = (
            "TOO_EARLY"
        )

        base[
            "nextSlot"
        ] = {
            "label":
                SLOTS[0][0],
            "targetMinutesToStart":
                SLOTS[0][1],
        }

        return base

    slot = current_slot(
        minutes_to_start
    )

    if slot is None:
        raise RuntimeError(
            "No current slot resolved "
            "inside scheduling horizon."
        )

    (
        label,
        target_minutes,
        lower_boundary,
    ) = slot

    base["slot"] = {
        "label":
            label,
        "targetMinutesToStart":
            target_minutes,
        "window": {
            "upperMinutesToStartInclusive":
                target_minutes,
            "lowerMinutesToStart":
                lower_boundary,
            "lowerBoundaryInclusive":
                (
                    lower_boundary
                    == 0.0
                ),
        },
        "latenessMinutes":
            max(
                0.0,
                target_minutes
                - minutes_to_start,
            ),
    }

    if label in captured_slots:
        base["state"] = (
            "ALREADY_CAPTURED"
        )
    else:
        base["state"] = (
            "DUE"
        )

    return base


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--first-v75-start-at",
        help=(
            "Scheduled V75-1 start. "
            "If omitted, scheduler returns "
            "NO_UPCOMING_V75."
        ),
    )

    parser.add_argument(
        "--now",
        help=(
            "Evaluation time. Defaults to "
            "current Europe/Oslo time."
        ),
    )

    parser.add_argument(
        "--captured-slot",
        action="append",
        default=[],
        choices=SLOT_LABELS,
    )

    args = parser.parse_args()

    now = (
        parse_datetime(
            args.now
        )
        if args.now
        else datetime.now(
            OSLO
        )
    )

    first_start = (
        parse_datetime(
            args.first_v75_start_at
        )
        if args.first_v75_start_at
        else None
    )

    result = decide_snapshot_slot(
        now=now,
        first_v75_start_at=
            first_start,
        captured_slots=set(
            args.captured_slot
        ),
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
