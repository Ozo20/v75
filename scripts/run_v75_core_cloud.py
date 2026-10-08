from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
OSLO = ZoneInfo("Europe/Oslo")

DEFAULT_BUDGET_NOK = 400.0
DEFAULT_ROW_PRICE_NOK = 0.50
DEFAULT_STATE_KEY = "state/upcoming.json"
DEFAULT_CORE_PREFIX = "core"


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def env_required(name: str) -> str:
    value = os.environ.get(name)

    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}"
        )

    return value


def make_s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=env_required("V75_S3_ENDPOINT"),
        region_name=env_required("V75_S3_REGION"),
        aws_access_key_id=env_required(
            "V75_S3_ACCESS_KEY_ID"
        ),
        aws_secret_access_key=env_required(
            "V75_S3_SECRET_ACCESS_KEY"
        ),
    )


def read_s3_json(
    client,
    *,
    bucket: str,
    key: str,
) -> Any:
    response = client.get_object(
        Bucket=bucket,
        Key=key,
    )

    body = response["Body"].read()

    return json.loads(
        body.decode("utf-8")
    )


def extract_target(
    state: dict[str, Any],
) -> dict[str, Any] | None:
    target = state.get("target")

    if target is None:
        return None

    if not isinstance(target, dict):
        raise RuntimeError(
            "state.target must be an object or null"
        )

    if target.get("countryIsoCode") != "NO":
        raise RuntimeError(
            "Refusing non-Norwegian V75 target"
        )

    if target.get("singleTrack") is not True:
        raise RuntimeError(
            "Refusing non-single-track V75 target"
        )

    race_date = target.get("raceDate")
    race_day_key = target.get("raceDayKey")

    if not isinstance(race_date, str):
        raise RuntimeError(
            "Target is missing raceDate"
        )

    if not isinstance(race_day_key, str):
        raise RuntimeError(
            "Target is missing raceDayKey"
        )

    return target


def parse_datetime(
    value: str | None,
) -> datetime | None:
    if not value:
        return None

    text = value.strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is None:
        raise RuntimeError(
            "startTime must contain timezone information"
        )

    return parsed


def pre_race_allowed(
    target: dict[str, Any],
    *,
    now: datetime,
) -> tuple[bool, str]:
    race_date = str(
        target["raceDate"]
    )

    today = now.astimezone(
        OSLO
    ).date().isoformat()

    if race_date < today:
        return False, "TARGET_DATE_PASSED"

    start_time = parse_datetime(
        target.get("startTime")
    )

    if start_time is not None:
        if now >= start_time:
            return False, "TARGET_ALREADY_STARTED"

        return True, "PRE_RACE_CONFIRMED"

    if race_date == today:
        return False, "TARGET_START_TIME_UNKNOWN"

    return True, "FUTURE_RACE_DATE"


def newest_run_directory(
    output_root: Path,
    race_date: str,
) -> Path:
    race_root = (
        output_root
        / race_date
    )

    candidates = sorted(
        (
            path
            for path in race_root.iterdir()
            if path.is_dir()
        ),
        key=lambda path: path.name,
    )

    if not candidates:
        raise RuntimeError(
            "Core pipeline produced no run directory"
        )

    return candidates[-1]


def upload_directory(
    client,
    *,
    bucket: str,
    source: Path,
    prefix: str,
) -> int:
    count = 0

    for path in sorted(
        source.rglob("*")
    ):
        if not path.is_file():
            continue

        relative = path.relative_to(
            source
        )

        key = (
            prefix.rstrip("/")
            + "/"
            + relative.as_posix()
        )

        extra_args = {}

        if path.suffix.lower() == ".json":
            extra_args["ContentType"] = (
                "application/json"
            )

        client.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs=extra_args or None,
        )

        count += 1

    return count


def put_json(
    client,
    *,
    bucket: str,
    key: str,
    payload: Any,
) -> None:
    body = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")

    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )


def run_core(
    *,
    target: dict[str, Any],
    output_root: Path,
    budget_nok: float,
    row_price_nok: float,
) -> Path:
    race_date = str(
        target["raceDate"]
    )

    race_day_key = str(
        target["raceDayKey"]
    )

    command = [
        sys.executable,
        str(
            ROOT
            / "scripts"
            / "run_live_v75.py"
        ),
        "--date",
        race_date,
        "--race-day-key",
        race_day_key,
        "--budget-nok",
        str(budget_nok),
        "--row-price-nok",
        str(row_price_nok),
        "--output-root",
        str(output_root),
    ]

    print("=== RUN FROZEN V75 CORE V1 ===")
    print(" ".join(command))

    subprocess.run(
        command,
        cwd=ROOT,
        check=True,
    )

    return newest_run_directory(
        output_root,
        race_date,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run frozen V75 Core v1 from the "
            "upcoming V75 target stored by the "
            "market collector."
        )
    )

    parser.add_argument(
        "--budget-nok",
        type=float,
        default=DEFAULT_BUDGET_NOK,
    )

    parser.add_argument(
        "--row-price-nok",
        type=float,
        default=DEFAULT_ROW_PRICE_NOK,
    )

    parser.add_argument(
        "--state-key",
        default=DEFAULT_STATE_KEY,
    )

    parser.add_argument(
        "--state-file",
        type=Path,
        default=None,
        help=(
            "Local state JSON for dry-run/testing. "
            "Avoids S3 access."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    args = parser.parse_args()

    if args.budget_nok <= 0:
        raise ValueError(
            "--budget-nok must be > 0"
        )

    if args.row_price_nok <= 0:
        raise ValueError(
            "--row-price-nok must be > 0"
        )

    now = datetime.now().astimezone()

    if args.state_file is not None:
        state = load_json(
            args.state_file
        )
        client = None
        bucket = None
    else:
        client = make_s3_client()
        bucket = env_required(
            "V75_S3_BUCKET"
        )

        state = read_s3_json(
            client,
            bucket=bucket,
            key=args.state_key,
        )

    target = extract_target(
        state
    )

    if target is None:
        print(
            "STATUS: NO_V75_TARGET"
        )
        return

    allowed, reason = (
        pre_race_allowed(
            target,
            now=now,
        )
    )

    print(
        "Target:",
        target["raceDayKey"],
    )
    print(
        "Race date:",
        target["raceDate"],
    )
    print(
        "Pre-race gate:",
        reason,
    )

    if not allowed:
        print(
            f"STATUS: {reason}"
        )
        return

    if args.dry_run:
        print(
            "STATUS: DRY_RUN_READY"
        )
        return

    assert client is not None
    assert bucket is not None

    with tempfile.TemporaryDirectory(
        prefix="v75-core-"
    ) as temp_dir:
        output_root = (
            Path(temp_dir)
            / "runs"
        )

        run_dir = run_core(
            target=target,
            output_root=output_root,
            budget_nok=args.budget_nok,
            row_price_nok=args.row_price_nok,
        )

        race_date = str(
            target["raceDate"]
        )

        run_id = run_dir.name

        prefix = (
            f"{DEFAULT_CORE_PREFIX}/"
            f"{race_date}/"
            f"{run_id}"
        )

        uploaded = upload_directory(
            client,
            bucket=bucket,
            source=run_dir,
            prefix=prefix,
        )

        current = {
            "schemaVersion": "1.0",
            "package": "v75-core-current",
            "displayName": "V75 Core v1",
            "createdAt":
                datetime.now()
                .astimezone()
                .isoformat(),
            "raceDate":
                race_date,
            "raceDayKey":
                target["raceDayKey"],
            "raceDayName":
                target.get("raceDayName"),
            "sourceStateKey":
                args.state_key,
            "runPrefix":
                prefix,
            "filesUploaded":
                uploaded,
            "selectedBudgetNok":
                args.budget_nok,
            "rowPriceNok":
                args.row_price_nok,
            "guardrails": {
                "preRaceOnly": True,
                "marketUsed": False,
                "outcomesUsed": False,
                "modelRetuned": False,
            },
        }

        put_json(
            client,
            bucket=bucket,
            key=(
                f"{DEFAULT_CORE_PREFIX}/"
                "current.json"
            ),
            payload=current,
        )

    print(
        f"Uploaded files: {uploaded}"
    )
    print(
        f"Run prefix: {prefix}"
    )
    print(
        "STATUS: CORE_SNAPSHOT_AVAILABLE"
    )


if __name__ == "__main__":
    main()
