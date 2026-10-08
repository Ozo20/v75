from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


BASE = "https://www.rikstoto.no"


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def unwrap(payload: Any) -> Any:
    if (
        isinstance(payload, dict)
        and payload.get("success") is True
        and "result" in payload
    ):
        return payload["result"]

    return payload


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def month_chunks(
    start: date,
    end: date,
):
    current = start

    while current <= end:
        candidate = current + timedelta(days=30)
        chunk_end = min(candidate, end)

        yield current, chunk_end

        current = chunk_end + timedelta(days=1)


def race_number(race_key: str) -> int:
    return int(
        race_key.rsplit("#", 1)[1]
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--from-date",
        required=True,
        type=parse_date,
    )

    parser.add_argument(
        "--to-date",
        required=True,
        type=parse_date,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    if args.from_date > args.to_date:
        raise ValueError(
            "--from-date must be <= --to-date"
        )

    meetings: dict[
        tuple[str, str],
        dict[str, Any],
    ] = {}

    with sync_playwright() as p:
        request = p.request.new_context(
            base_url=BASE,
            extra_http_headers={
                "Accept": "application/json",
                "Accept-Language":
                    "nb-NO,nb;q=0.9",
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/140.0.0.0 Safari/537.36"
                ),
            },
        )

        for chunk_start, chunk_end in month_chunks(
            args.from_date,
            args.to_date,
        ):
            path = (
                "/api/racedays/dates/"
                f"{chunk_start.isoformat()}/"
                f"{chunk_end.isoformat()}"
            )

            response = request.get(path)

            print(
                f"{response.status:3}  "
                f"{chunk_start} -> {chunk_end}"
            )

            if not response.ok:
                raise RuntimeError(
                    f"GET failed: "
                    f"{response.status} {path}"
                )

            race_days = unwrap(
                response.json()
            )

            if not isinstance(
                race_days,
                list,
            ):
                raise RuntimeError(
                    "Unexpected race-day response"
                )

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
                        "raceDayKey"
                    )
                )

                if not race_day_key:
                    continue

                race_date = (
                    race_day_key.rsplit(
                        "_",
                        1,
                    )[-1]
                )

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

                    if not races:
                        continue

                    single_track = (
                        pool.get(
                            "isMultiTrack"
                        )
                        is not True
                        and all(
                            race_key.startswith(
                                race_day_key
                                + "#"
                            )
                            for race_key
                            in races
                        )
                    )

                    key = (
                        race_day_key,
                        str(
                            pool.get(
                                "poolKey"
                            )
                        ),
                    )

                    meetings[key] = {
                        "date": race_date,
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
                            pool.get(
                                "isMultiTrack"
                            ),
                        "singleTrack":
                            single_track,
                        "raceKeys":
                            races,
                        "raceNumbers": [
                            race_number(
                                race_key
                            )
                            for race_key
                            in races
                        ],
                        "legCount":
                            len(races),
                    }

            # Be intentionally gentle with
            # the public site.
            time.sleep(0.25)

        request.dispose()

    result = sorted(
        meetings.values(),
        key=lambda item: (
            item["date"],
            item["raceDayKey"],
        ),
    )

    save_json(
        args.output,
        {
            "schemaVersion": "1.0",
            "fromDate":
                args.from_date.isoformat(),
            "toDate":
                args.to_date.isoformat(),
            "meetings": result,
        },
    )

    print()
    print(
        "=== NORWEGIAN V75 DISCOVERY ==="
    )

    print(
        f"Period: "
        f"{args.from_date} -> "
        f"{args.to_date}"
    )

    print(
        f"V75 pools found: "
        f"{len(result)}"
    )

    print()

    single_track_count = 0

    for item in result:
        kind = (
            "SINGLE"
            if item["singleTrack"]
            else "MULTI"
        )

        if item["singleTrack"]:
            single_track_count += 1

        races = ",".join(
            str(value)
            for value
            in item["raceNumbers"]
        )

        print(
            f"{item['date']}  "
            f"{item['raceDayName']:<18} "
            f"{item['raceDayKey']:<22} "
            f"{kind:<6} "
            f"legs={item['legCount']} "
            f"races={races}"
        )

    print()
    print(
        f"Single-track Norwegian V75: "
        f"{single_track_count}"
    )

    print(
        f"Saved: {args.output}"
    )


if __name__ == "__main__":
    main()
