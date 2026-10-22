from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
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

import collect_v75_market_snapshot as collector
import schedule_v75_market_snapshot as scheduler


OSLO = ZoneInfo("Europe/Oslo")

COLLECTOR_PATH = (
    SCRIPT_DIR
    / "collect_v75_market_snapshot.py"
)


DiscoveryFn = Callable[
    [Any, Any],
    tuple[
        bytes,
        Any,
        list[dict[str, Any]],
    ],
]

CollectorRunner = Callable[
    [
        dict[str, Any],
        Path,
    ],
    tuple[
        Path,
        dict[str, Any],
    ],
]


def save_json(
    path: Path,
    payload: Any,
    *,
    exclusive: bool = False,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    mode = (
        "x"
        if exclusive
        else "w"
    )

    with path.open(
        mode,
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        handle.write("\n")


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def safe_race_day_key(
    value: Any,
) -> str:
    key = str(value or "")

    if not re.fullmatch(
        r"[A-Za-z0-9_-]+",
        key,
    ):
        raise ValueError(
            "Unsafe or missing raceDayKey: "
            f"{key!r}"
        )

    return key


def meeting_start(
    meeting: dict[str, Any],
) -> datetime | None:
    return collector.parse_race_start_time(
        meeting.get(
            "firstRaceStartTime"
        )
    )


def select_meeting(
    meetings: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any] | None:
    scheduler.require_aware(
        now,
        "now",
    )

    now_oslo = now.astimezone(
        OSLO
    )

    candidates: list[
        tuple[
            datetime,
            str,
            str,
            dict[str, Any],
        ]
    ] = []

    for meeting in meetings:
        if (
            meeting.get(
                "singleTrack"
            )
            is not True
        ):
            continue

        start = meeting_start(
            meeting
        )

        if start is None:
            continue

        candidates.append(
            (
                start,
                str(
                    meeting.get(
                        "raceDayKey"
                    )
                    or ""
                ),
                str(
                    meeting.get(
                        "poolKey"
                    )
                    or ""
                ),
                meeting,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda row: (
            row[0],
            row[1],
            row[2],
        )
    )

    future = [
        row
        for row in candidates
        if row[0] >= now_oslo
    ]

    if future:
        return future[0][3]

    # Never reuse an already-started meeting as the upcoming target.
    # Discovery with no future race must fail closed.
    return None


def same_day_single_track(
    meetings: list[dict[str, Any]],
    selected: dict[str, Any],
) -> list[dict[str, Any]]:
    selected_start = meeting_start(
        selected
    )

    if selected_start is None:
        return []

    selected_date = (
        selected_start
        .astimezone(OSLO)
        .date()
    )

    rows: list[
        dict[str, Any]
    ] = []

    for meeting in meetings:
        if (
            meeting.get(
                "singleTrack"
            )
            is not True
        ):
            continue

        start = meeting_start(
            meeting
        )

        if start is None:
            continue

        if (
            start.astimezone(
                OSLO
            ).date()
            == selected_date
        ):
            rows.append(
                meeting
            )

    return rows


def meeting_root(
    output_root: Path,
    race_day_key: str,
) -> Path:
    return (
        output_root
        / race_day_key
    )


def slot_root(
    output_root: Path,
    race_day_key: str,
    slot_label: str,
) -> Path:
    return (
        meeting_root(
            output_root,
            race_day_key,
        )
        / slot_label
    )


def completed_slots(
    output_root: Path,
    race_day_key: str,
) -> set[str]:
    result: set[str] = set()

    root = meeting_root(
        output_root,
        race_day_key,
    )

    for label in (
        scheduler.SLOT_LABELS
    ):
        if (
            root
            / label
            / "complete.json"
        ).is_file():
            result.add(label)

    return result


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
            "Output root must be outside "
            "the repository."
        )

    return resolved


def actual_collector_runner(
    meeting: dict[str, Any],
    attempt_dir: Path,
) -> tuple[
    Path,
    dict[str, Any],
]:
    start = meeting_start(
        meeting
    )

    if start is None:
        raise RuntimeError(
            "Selected meeting has no "
            "V75 start time."
        )

    expected_key = (
        safe_race_day_key(
            meeting.get(
                "raceDayKey"
            )
        )
    )

    expected_first = int(
        meeting[
            "firstRaceNumber"
        ]
    )

    date_text = (
        start
        .astimezone(OSLO)
        .date()
        .isoformat()
    )

    collector_root = (
        attempt_dir
        / "collector"
    )

    command = [
        sys.executable,
        str(COLLECTOR_PATH),
        "--output-root",
        str(collector_root),
        "--date",
        date_text,
        "--lookahead-days",
        "0",
    ]

    process = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )

    (
        attempt_dir
        / "collector-stdout.txt"
    ).write_text(
        process.stdout,
        encoding="utf-8",
    )

    (
        attempt_dir
        / "collector-stderr.txt"
    ).write_text(
        process.stderr,
        encoding="utf-8",
    )

    if process.returncode != 0:
        raise RuntimeError(
            "Collector failed with "
            f"exit code "
            f"{process.returncode}"
        )

    snapshots = sorted(
        collector_root.glob(
            "*/snapshot.json"
        )
    )

    if len(snapshots) != 1:
        raise RuntimeError(
            "Expected exactly one collector "
            "snapshot, found "
            f"{len(snapshots)}."
        )

    snapshot_path = (
        snapshots[0]
    )

    snapshot = json.loads(
        snapshot_path.read_text(
            encoding="utf-8"
        )
    )

    if (
        snapshot.get("status")
        != "MARKET_AVAILABLE"
    ):
        raise RuntimeError(
            "Collector did not produce "
            "MARKET_AVAILABLE."
        )

    captured_meeting = (
        snapshot.get("meeting")
        or {}
    )

    if (
        captured_meeting.get(
            "raceDayKey"
        )
        != expected_key
    ):
        raise RuntimeError(
            "Collector resolved a different "
            "race day."
        )

    if int(
        captured_meeting.get(
            "firstRaceNumber"
        )
    ) != expected_first:
        raise RuntimeError(
            "Collector resolved a different "
            "first V75 race."
        )

    timing = (
        snapshot.get("timing")
        or {}
    )

    expected_start = (
        start
        .astimezone(OSLO)
        .isoformat()
    )

    if (
        timing.get(
            "firstV75StartAt"
        )
        != expected_start
    ):
        raise RuntimeError(
            "Collector timing does not "
            "match scheduler discovery."
        )

    return (
        snapshot_path,
        snapshot,
    )


def make_base_result(
    *,
    now: datetime,
) -> dict[str, Any]:
    return {
        "schemaVersion":
            "1.0",
        "executor":
            "v75-market-snapshot-execution-v1",
        "now":
            now.astimezone(
                OSLO
            ).isoformat(),
        "state":
            None,
        "meeting":
            None,
        "decision":
            None,
        "capture":
            None,
        "guardrails": {
            "outcomeEndpointUsed":
                False,
            "outcomesUsed":
                False,
            "modelUsed":
                False,
            "modelRetuned":
                False,
            "repoWrites":
                False,
        },
    }


def execute_once(
    *,
    output_root: Path,
    now: datetime,
    lookahead_days: int = 7,
    discover_fn: DiscoveryFn | None = None,
    collector_runner: (
        CollectorRunner | None
    ) = None,
) -> dict[str, Any]:
    scheduler.require_aware(
        now,
        "now",
    )

    if lookahead_days < 0:
        raise ValueError(
            "lookahead_days must be >= 0"
        )

    output_root = (
        validate_output_root(
            output_root
        )
    )

    if discover_fn is None:
        discover_fn = (
            collector.discover_v75
        )

    if collector_runner is None:
        collector_runner = (
            actual_collector_runner
        )

    result = make_base_result(
        now=now
    )

    result["guardrails"][
        "networkUsed"
    ] = True

    result["guardrails"][
        "collectorInvoked"
    ] = False

    now_oslo = now.astimezone(
        OSLO
    )

    (
        discovery_raw,
        _payload,
        meetings,
    ) = discover_fn(
        now_oslo.date(),
        (
            now_oslo.date()
            + timedelta(
                days=lookahead_days
            )
        ),
    )

    selected = select_meeting(
        meetings,
        now_oslo,
    )

    if selected is None:
        # Surface the distinction between an empty calendar, an
        # expired race and a race with no verifiable V75-1 start.
        single_track = [
            item
            for item in meetings
            if item.get("singleTrack") is True
        ]
        start_times = [
            meeting_start(item)
            for item in single_track
        ]
        result["discovery"] = {
            "singleTrackCandidateCount": len(single_track),
            "missingStartTimeCount": sum(
                value is None for value in start_times
            ),
            "alreadyStartedCount": sum(
                value is not None and value < now_oslo
                for value in start_times
            ),
        }

        decision = (
            scheduler
            .decide_snapshot_slot(
                now=now_oslo,
                first_v75_start_at=None,
                captured_slots=set(),
            )
        )

        result["state"] = (
            "NO_UPCOMING_V75"
        )
        result["decision"] = (
            decision
        )

        return result

    selected_start = meeting_start(
        selected
    )

    if selected_start is None:
        raise RuntimeError(
            "Selected meeting unexpectedly "
            "has no start time."
        )

    race_day_key = (
        safe_race_day_key(
            selected.get(
                "raceDayKey"
            )
        )
    )

    same_day = (
        same_day_single_track(
            meetings,
            selected,
        )
    )

    result["meeting"] = {
        "raceDayKey":
            race_day_key,
        "raceDayName":
            selected.get(
                "raceDayName"
            ),
        "poolKey":
            selected.get(
                "poolKey"
            ),
        "firstRaceNumber":
            selected.get(
                "firstRaceNumber"
            ),
        "firstV75StartAt":
            selected_start
            .astimezone(OSLO)
            .isoformat(),
    }

    if len(same_day) != 1:
        result["state"] = (
            "AMBIGUOUS_V75_DAY"
        )

        result[
            "sameDaySingleTrackCount"
        ] = len(same_day)

        return result

    captured = completed_slots(
        output_root,
        race_day_key,
    )

    decision = (
        scheduler
        .decide_snapshot_slot(
            now=now_oslo,
            first_v75_start_at=
                selected_start,
            captured_slots=captured,
        )
    )

    result["decision"] = (
        decision
    )

    state = str(
        decision.get("state")
    )

    if state != "DUE":
        result["state"] = state
        return result

    slot = (
        decision.get("slot")
        or {}
    )

    slot_label = str(
        slot.get("label")
        or ""
    )

    if (
        slot_label
        not in scheduler.SLOT_LABELS
    ):
        raise RuntimeError(
            "Decision layer returned "
            "an invalid slot."
        )

    root = slot_root(
        output_root,
        race_day_key,
        slot_label,
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    complete_path = (
        root
        / "complete.json"
    )

    if complete_path.exists():
        result["state"] = (
            "ALREADY_CAPTURED"
        )
        return result

    lock_path = (
        root
        / ".capture.lock"
    )

    try:
        lock_handle = (
            lock_path.open(
                "x",
                encoding="utf-8",
            )
        )
    except FileExistsError:
        result["state"] = (
            "CAPTURE_IN_PROGRESS"
        )
        return result

    try:
        lock_handle.write(
            now_oslo.isoformat()
            + "\n"
        )
        lock_handle.close()

        attempt_stamp = (
            datetime.now(OSLO)
            .strftime(
                "%Y%m%dT%H%M%S%f%z"
            )
        )

        attempt_dir = (
            root
            / "attempts"
            / attempt_stamp
        )

        attempt_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        (
            attempt_dir
            / "discovery-response.json"
        ).write_bytes(
            discovery_raw
        )

        save_json(
            attempt_dir
            / "scheduler-decision.json",
            decision,
        )

        try:
            (
                snapshot_path,
                snapshot,
            ) = collector_runner(
                selected,
                attempt_dir,
            )

        except Exception as exc:
            failure = {
                "schemaVersion":
                    "1.0",
                "state":
                    "CAPTURE_FAILED",
                "raceDayKey":
                    race_day_key,
                "slot":
                    slot_label,
                "errorType":
                    type(exc).__name__,
                "error":
                    str(exc),
            }

            save_json(
                attempt_dir
                / "failure.json",
                failure,
            )

            result["state"] = (
                "CAPTURE_FAILED"
            )

            result["capture"] = {
                "attemptDirectory":
                    str(
                        attempt_dir
                    ),
                "errorType":
                    type(exc).__name__,
                "error":
                    str(exc),
            }

            return result

        resolved_snapshot = (
            snapshot_path
            .resolve()
        )

        if not resolved_snapshot.is_relative_to(
            attempt_dir.resolve()
        ):
            raise RuntimeError(
                "Collector returned snapshot "
                "outside attempt directory."
            )

        relative_snapshot = (
            resolved_snapshot
            .relative_to(
                output_root
            )
            .as_posix()
        )

        receipt = {
            "schemaVersion":
                "1.0",
            "state":
                "COMPLETE",
            "raceDayKey":
                race_day_key,
            "slot":
                slot_label,
            "targetMinutesToStart":
                slot.get(
                    "targetMinutesToStart"
                ),
            "actualMinutesToStart":
                decision.get(
                    "minutesToStart"
                ),
            "latenessMinutes":
                slot.get(
                    "latenessMinutes"
                ),
            "evaluationTime":
                now_oslo.isoformat(),
            "firstV75StartAt":
                selected_start
                .astimezone(OSLO)
                .isoformat(),
            "snapshotPath":
                relative_snapshot,
            "snapshotSha256":
                sha256_file(
                    resolved_snapshot
                ),
            "snapshotCapturedAt":
                snapshot.get(
                    "capturedAt"
                ),
            "turnoverEstimateNok":
                (
                    snapshot.get(
                        "turnover"
                    )
                    or {}
                ).get(
                    "estimateNok"
                ),
        }

        save_json(
            complete_path,
            receipt,
            exclusive=True,
        )

        result["state"] = (
            "CAPTURED"
        )

        result["capture"] = (
            receipt
        )

        result["guardrails"][
            "collectorInvoked"
        ] = True

        return result

    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--lookahead-days",
        type=int,
        default=7,
    )

    parser.add_argument(
        "--now",
        help=(
            "Optional deterministic "
            "evaluation time."
        ),
    )

    args = parser.parse_args()

    now = (
        scheduler.parse_datetime(
            args.now
        )
        if args.now
        else datetime.now(OSLO)
    )

    result = execute_once(
        output_root=
            args.output_root,
        now=now,
        lookahead_days=
            args.lookahead_days,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

    if (
        result.get("state")
        == "CAPTURE_FAILED"
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
