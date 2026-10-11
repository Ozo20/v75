from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
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


def parse_race_start_time(
    value: Any,
) -> datetime | None:
    if not isinstance(
        value,
        str,
    ):
        return None

    candidate = value.strip()

    if not candidate:
        return None

    if candidate.endswith("Z"):
        candidate = (
            candidate[:-1]
            + "+00:00"
        )

    try:
        parsed = (
            datetime.fromisoformat(
                candidate
            )
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(
            tzinfo=OSLO
        )

    return parsed.astimezone(
        OSLO
    )


def first_race_start_time(
    race_day: dict[str, Any],
    pool: dict[str, Any],
    first_race_number: int,
) -> str | None:
    # Prefer the exact physical race start.
    # Fall back to pool.startTime only when
    # Rikstoto exposes it directly.
    for race in (
        race_day.get("races")
        or []
    ):
        if not isinstance(
            race,
            dict,
        ):
            continue

        try:
            number = int(
                race.get(
                    "raceNumber"
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if number != first_race_number:
            continue

        value = race.get(
            "startTime"
        )

        if isinstance(
            value,
            str,
        ) and value.strip():
            return value

    value = pool.get(
        "startTime"
    )

    if isinstance(
        value,
        str,
    ) and value.strip():
        return value

    return None


def summarize_turnover(
    market_result: Any,
) -> dict[str, Any]:
    if not isinstance(
        market_result,
        list,
    ):
        return {
            "available":
                False,
            "qualityStatus":
                "UNEXPECTED_MARKET_SHAPE",
            "estimateNok":
                None,
            "legCount":
                0,
            "legs":
                [],
        }

    legs: list[
        dict[str, Any]
    ] = []

    for index, leg in enumerate(
        market_result,
        1,
    ):
        if not isinstance(
            leg,
            dict,
        ):
            continue

        distribution = (
            leg.get(
                "investmentDistribution"
            )
            or []
        )

        if not isinstance(
            distribution,
            list,
        ):
            continue

        values: list[float] = []

        for horse in distribution:
            if not isinstance(
                horse,
                dict,
            ):
                continue

            value = horse.get(
                "investment"
            )

            if isinstance(
                value,
                (int, float),
            ) and not isinstance(
                value,
                bool,
            ):
                numeric = float(
                    value
                )

                if numeric >= 0:
                    values.append(
                        numeric
                    )

        if not values:
            continue

        legs.append(
            {
                "leg":
                    index,
                "raceNumber":
                    leg.get(
                        "raceNumber"
                    ),
                "raceKey":
                    leg.get(
                        "raceKey"
                    ),
                "updatedTime":
                    leg.get(
                        "updatedTime"
                    ),
                "runnerCount":
                    len(
                        distribution
                    ),
                "investmentSumNok":
                    sum(values),
            }
        )

    totals = [
        row[
            "investmentSumNok"
        ]
        for row in legs
        if row[
            "investmentSumNok"
        ] > 0
    ]

    if not totals:
        return {
            "available":
                False,
            "qualityStatus":
                "NO_POSITIVE_INVESTMENT",
            "estimateNok":
                None,
            "legCount":
                len(legs),
            "legs":
                legs,
        }

    estimate = float(
        median(totals)
    )

    minimum = min(totals)
    maximum = max(totals)

    spread_pct = (
        100.0
        * (
            maximum
            - minimum
        )
        / estimate
        if estimate > 0
        else None
    )

    return {
        "available":
            True,
        "qualityStatus":
            (
                "COMPLETE_7_LEGS"
                if len(totals) == 7
                else "INCOMPLETE_LEGS"
            ),
        "estimateNok":
            estimate,
        "minLegSumNok":
            minimum,
        "maxLegSumNok":
            maximum,
        "crossLegSpreadPct":
            spread_pct,
        "legCount":
            len(totals),
        "semantics":
            (
                "Median across V75 legs of "
                "sum(investment) over runners. "
                "investment is interpreted as NOK."
            ),
        "legs":
            legs,
    }


def extract_race_days(
    payload: Any,
) -> list[dict[str, Any]]:
    root = unwrap(payload)

    if not isinstance(
        root,
        list,
    ):
        raise RuntimeError(
            "Unexpected race-day "
            "response shape"
        )

    race_days: list[
        dict[str, Any]
    ] = []

    for item in root:
        if not isinstance(
            item,
            dict,
        ):
            continue

        nested = item.get(
            "raceDays"
        )

        if isinstance(
            nested,
            list,
        ):
            race_days.extend(
                race_day
                for race_day
                in nested
                if isinstance(
                    race_day,
                    dict,
                )
            )
            continue

        if (
            item.get("raceDay")
            or item.get(
                "raceDayKey"
            )
        ):
            race_days.append(
                item
            )

    return race_days


def normalize_v75_meetings(
    payload: Any,
) -> list[dict[str, Any]]:
    race_days = (
        extract_race_days(
            payload
        )
    )

    meetings: list[
        dict[str, Any]
    ] = []

    for race_day in race_days:
        if (
            race_day.get(
                "countryIsoCode"
            )
            != "NO"
        ):
            continue

        if (
            race_day.get(
                "isDomestic"
            )
            is not True
        ):
            continue

        race_day_key = (
            race_day.get(
                "raceDay"
            )
            or race_day.get(
                "raceDayKey"
            )
        )

        if not race_day_key:
            continue

        for pool in (
            race_day.get("pools")
            or []
        ):
            if not isinstance(
                pool,
                dict,
            ):
                continue

            if (
                pool.get("product")
                != "V75"
            ):
                continue

            races = (
                pool.get("races")
                or []
            )

            if not races:
                race_numbers = (
                    pool.get(
                        "raceNumbers"
                    )
                    or []
                )

                try:
                    races = [
                        (
                            f"{race_day_key}#"
                            f"{int(value)}"
                        )
                        for value
                        in race_numbers
                    ]
                except (
                    TypeError,
                    ValueError,
                ):
                    continue

            if len(races) != 7:
                continue

            try:
                numbers = [
                    race_number(
                        str(
                            race_key
                        )
                    )
                    for race_key
                    in races
                ]
            except (
                TypeError,
                ValueError,
                IndexError,
            ):
                continue

            first_number = min(
                numbers
            )

            first_start_time = (
                first_race_start_time(
                    race_day,
                    pool,
                    first_number,
                )
            )

            is_multi_track = (
                pool.get(
                    "isMultiTrack"
                )
                is True
            )

            single_track = (
                not is_multi_track
                and all(
                    str(
                        race_key
                    ).startswith(
                        str(
                            race_day_key
                        )
                        + "#"
                    )
                    for race_key
                    in races
                )
            )

            meetings.append(
                {
                    "raceDayKey":
                        str(
                            race_day_key
                        ),
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
                        first_number,
                    "firstRaceStartTime":
                        first_start_time,
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

    return meetings


def discover_v75(
    from_date: date,
    to_date: date,
) -> tuple[
    bytes,
    Any,
    list[dict[str, Any]],
]:
    path = (
        "/api/results/racedays/"
        f"{from_date.isoformat()}/"
        f"{to_date.isoformat()}/"
        "list"
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

    meetings = (
        normalize_v75_meetings(
            payload
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
            "1.2",
        "collector":
            "v75-market-snapshot-v2",
        "capturedAt":
            captured_at.isoformat(),
        "guardrails": {
            "scheduleDiscoveryUsed":
                not direct,
            "resultsNamespaceScheduleEndpointUsed":
                not direct,
            "outcomeEndpointUsed":
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
            "firstRaceStartTime":
                None,
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

    turnover = summarize_turnover(
        market_result
    )

    first_start_raw = meeting.get(
        "firstRaceStartTime"
    )

    first_start = (
        parse_race_start_time(
            first_start_raw
        )
    )

    minutes_to_start = (
        (
            first_start
            - captured_at
        ).total_seconds()
        / 60.0
        if first_start is not None
        else None
    )

    summary["timing"] = {
        "firstV75StartAt":
            (
                first_start.isoformat()
                if first_start is not None
                else None
            ),
        "sourceValue":
            first_start_raw,
        "minutesToStart":
            minutes_to_start,
        "status":
            (
                "KNOWN"
                if first_start is not None
                else "UNKNOWN"
            ),
    }

    summary["turnover"] = (
        turnover
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
        "Turnover estimate:",
        summary[
            "turnover"
        ][
            "estimateNok"
        ],
        "NOK",
    )
    print(
        "Turnover quality:",
        summary[
            "turnover"
        ][
            "qualityStatus"
        ],
    )
    print(
        "First V75 start:",
        summary[
            "timing"
        ][
            "firstV75StartAt"
        ],
    )
    print(
        "Minutes to start:",
        summary[
            "timing"
        ][
            "minutesToStart"
        ],
    )
    print(
        f"Saved: {run_dir}"
    )


if __name__ == "__main__":
    main()
