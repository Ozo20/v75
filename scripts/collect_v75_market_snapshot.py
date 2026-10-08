from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


BASE = "https://www.rikstoto.no"
OSLO = ZoneInfo("Europe/Oslo")

USER_AGENT = (
    "Mozilla/5.0 "
    "(Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_bytes(
    path: Path,
    payload: bytes,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_bytes(payload)


def save_json(
    path: Path,
    payload: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )


def unwrap(payload: Any) -> Any:
    if (
        isinstance(payload, dict)
        and payload.get("success") is True
        and "result" in payload
    ):
        return payload["result"]

    return payload


def get_json_bytes(
    path: str,
) -> tuple[
    int,
    bytes,
    Any,
]:
    url = BASE + path

    request = urllib.request.Request(
        url,
        headers={
            "Accept":
                "application/json",
            "Accept-Language":
                "nb-NO,nb;q=0.9",
            "Referer":
                BASE + "/",
            "User-Agent":
                USER_AGENT,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            status = int(
                response.status
            )
            raw = response.read()

    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()

    print(
        f"{status:3}  {path}"
    )

    try:
        payload = json.loads(
            raw.decode(
                "utf-8"
            )
        )
    except Exception as exc:
        raise RuntimeError(
            f"Non-JSON response from "
            f"{path}: {exc}"
        ) from exc

    return (
        status,
        raw,
        payload,
    )


def race_number(
    race_key: str,
) -> int:
    return int(
        race_key.rsplit(
            "#",
            1,
        )[1]
    )


def discover_v75(
    from_date: date,
    to_date: date,
) -> tuple[
    bytes,
    Any,
    list[dict[str, Any]],
]:
    path = (
        "/api/racedays/dates/"
        f"{from_date.isoformat()}/"
        f"{to_date.isoformat()}"
    )

    (
        status,
        raw,
        payload,
    ) = get_json_bytes(path)

    if status != 200:
        raise RuntimeError(
            f"Discovery failed: "
            f"HTTP {status}"
        )

    race_days = unwrap(payload)

    if not isinstance(
        race_days,
        list,
    ):
        raise RuntimeError(
            "Unexpected race-day "
            "response shape"
        )

    meetings: list[
        dict[str, Any]
    ] = []

    for race_day in race_days:
        race_day_key = (
            race_day.get(
                "raceDayKey"
            )
        )

        if not race_day_key:
            continue

        for pool in (
            race_day.get("pools")
            or []
        ):
            if (
                pool.get("product")
                != "V75"
            ):
                continue

            races = (
                pool.get("races")
                or []
            )

            if len(races) != 7:
                continue

            is_multi_track = (
                pool.get(
                    "isMultiTrack"
                )
                is True
            )

            single_track = (
                not is_multi_track
                and all(
                    race_key.startswith(
                        race_day_key
                        + "#"
                    )
                    for race_key
                    in races
                )
            )

            numbers = [
                race_number(
                    race_key
                )
                for race_key
                in races
            ]

            meetings.append(
                {
                    "raceDayKey":
                        race_day_key,
                    "raceDayName":
                        race_day.get(
                            "raceDayName"
                        ),
                    "countryIsoCode":
                        race_day.get(
                            "countryIsoCode"
                        ),
                    "isDomestic":
                        race_day.get(
                            "isDomestic"
                        ),
                    "poolKey":
                        pool.get(
                            "poolKey"
                        ),
                    "isMultiTrack":
                        is_multi_track,
                    "singleTrack":
                        single_track,
                    "raceKeys":
                        races,
                    "raceNumbers":
                        numbers,
                    "firstRaceNumber":
                        min(numbers),
                }
            )

    meetings.sort(
        key=lambda row: (
            row["raceDayKey"],
            str(
                row.get(
                    "poolKey"
                )
            ),
        )
    )

    return (
        raw,
        payload,
        meetings,
    )


def find_values(
    value: Any,
    key_name: str,
    found: list[Any],
) -> None:
    if isinstance(
        value,
        dict,
    ):
        for key, child in (
            value.items()
        ):
            if (
                str(key).lower()
                == key_name.lower()
            ):
                found.append(
                    child
                )

            find_values(
                child,
                key_name,
                found,
            )

    elif isinstance(
        value,
        list,
    ):
        for child in value:
            find_values(
                child,
                key_name,
                found,
            )


def collect_market(
    race_day_key: str,
    first_race_number: int,
) -> tuple[
    str,
    bytes,
    Any,
]:
    query = (
        urllib.parse.urlencode(
            {
                "raceNumber":
                    first_race_number
            }
        )
    )

    path = (
        f"/api/game/"
        f"{race_day_key}/"
        "betdistribution/"
        "investment/V75"
        f"?{query}"
    )

    (
        status,
        raw,
        payload,
    ) = get_json_bytes(path)

    if status != 200:
        raise RuntimeError(
            f"Investment distribution "
            f"failed: HTTP {status}"
        )

    return (
        path,
        raw,
        payload,
    )


def main() -> None:
    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--output-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--date",
        type=parse_date,
        help=(
            "Discovery start date. "
            "Defaults to current date "
            "in Europe/Oslo."
        ),
    )

    parser.add_argument(
        "--lookahead-days",
        type=int,
        default=7,
    )

    parser.add_argument(
        "--race-day-key",
    )

    parser.add_argument(
        "--first-race-number",
        type=int,
    )

    args = parser.parse_args()

    if args.lookahead_days < 0:
        raise ValueError(
            "--lookahead-days must "
            "be >= 0"
        )

    direct = (
        args.race_day_key
        is not None
        or args.first_race_number
        is not None
    )

    if direct and (
        args.race_day_key
        is None
        or args.first_race_number
        is None
    ):
        raise ValueError(
            "Direct mode requires both "
            "--race-day-key and "
            "--first-race-number"
        )

    captured_at = (
        datetime.now(OSLO)
    )

    stamp = (
        captured_at.strftime(
            "%Y%m%dT%H%M%S%f%z"
        )
    )

    run_dir = (
        args.output_root
        / stamp
    )

    if run_dir.exists():
        raise SystemExit(
            "REFUSING: run directory "
            f"already exists: {run_dir}"
        )

    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    summary: dict[str, Any] = {
        "schemaVersion":
            "1.0",
        "collector":
            "v75-market-snapshot-v1",
        "capturedAt":
            captured_at.isoformat(),
        "guardrails": {
            "resultsEndpointUsed":
                False,
            "outcomesUsed":
                False,
            "modelUsed":
                False,
            "modelRetuned":
                False,
        },
    }

    if direct:
        meeting = {
            "raceDayKey":
                args.race_day_key,
            "firstRaceNumber":
                args.first_race_number,
        }

        summary["mode"] = (
            "direct"
        )

    else:
        from_date = (
            args.date
            or captured_at.date()
        )

        to_date = (
            from_date
            + timedelta(
                days=args.lookahead_days
            )
        )

        (
            discovery_raw,
            _discovery_payload,
            meetings,
        ) = discover_v75(
            from_date,
            to_date,
        )

        save_bytes(
            run_dir
            / "discovery-response.json",
            discovery_raw,
        )

        summary[
            "discovery"
        ] = {
            "fromDate":
                from_date.isoformat(),
            "toDate":
                to_date.isoformat(),
            "v75PoolsFound":
                len(meetings),
            "rawSha256":
                sha256_bytes(
                    discovery_raw
                ),
        }

        single_track = [
            row
            for row in meetings
            if row.get(
                "singleTrack"
            )
            is True
        ]

        if not single_track:
            summary["status"] = (
                "NO_SINGLE_TRACK_"
                "V75_POOL"
            )

            summary[
                "meetings"
            ] = meetings

            save_json(
                run_dir
                / "snapshot.json",
                summary,
            )

            print()
            print(
                "STATUS: "
                "NO_SINGLE_TRACK_"
                "V75_POOL"
            )
            print(
                f"Saved: {run_dir}"
            )
            return

        meeting = (
            single_track[0]
        )

        summary["mode"] = (
            "discovery"
        )
        summary[
            "meetings"
        ] = meetings

    race_day_key = str(
        meeting[
            "raceDayKey"
        ]
    )

    first_race_number = int(
        meeting[
            "firstRaceNumber"
        ]
    )

    summary["meeting"] = (
        meeting
    )

    (
        market_path,
        market_raw,
        market_payload,
    ) = collect_market(
        race_day_key,
        first_race_number,
    )

    save_bytes(
        run_dir
        / "investment-response.json",
        market_raw,
    )

    market_result = unwrap(
        market_payload
    )

    updated_times: list[Any] = []

    find_values(
        market_result,
        "updatedTime",
        updated_times,
    )

    percentages: list[Any] = []

    find_values(
        market_result,
        "percentage",
        percentages,
    )

    rankings: list[Any] = []

    find_values(
        market_result,
        "ranking",
        rankings,
    )

    investments: list[Any] = []

    find_values(
        market_result,
        "investment",
        investments,
    )

    market_present = bool(
        market_result
    )

    summary["market"] = {
        "endpoint":
            market_path,
        "available":
            market_present,
        "rawSha256":
            sha256_bytes(
                market_raw
            ),
        "updatedTimes":
            sorted(
                {
                    str(value)
                    for value
                    in updated_times
                }
            ),
        "percentageValueCount":
            len(percentages),
        "rankingValueCount":
            len(rankings),
        "investmentValueCount":
            len(investments),
    }

    summary["status"] = (
        "MARKET_AVAILABLE"
        if market_present
        else
        "V75_FOUND_MARKET_"
        "NOT_AVAILABLE"
    )

    save_json(
        run_dir
        / "snapshot.json",
        summary,
    )

    print()
    print(
        "STATUS:",
        summary["status"],
    )
    print(
        "Race day:",
        race_day_key,
    )
    print(
        "First race:",
        first_race_number,
    )
    print(
        "Updated times:",
        summary[
            "market"
        ][
            "updatedTimes"
        ],
    )
    print(
        "Percentage values:",
        len(percentages),
    )
    print(
        f"Saved: {run_dir}"
    )


if __name__ == "__main__":
    main()
