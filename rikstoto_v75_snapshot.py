from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


BASE = "https://www.rikstoto.no"
DATE = "2026-09-19"

OUT = (
    Path.home()
    / "Downloads"
    / f"rikstoto-v75-{DATE}"
)


def save_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
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


def get_json(request, path: str) -> Any:
    url = f"{BASE}{path}"

    response = request.get(
        url,
        headers={
            "Accept": "application/json",
            "Referer": f"{BASE}/",
        },
    )

    print(f"{response.status:3}  {path}")

    if not response.ok:
        raise RuntimeError(
            f"GET failed: {response.status} {url}"
        )

    return response.json()


def find_v75_candidates(race_days: list[dict]) -> list[dict]:
    candidates = []

    for race_day in race_days:
        for pool in race_day.get("pools", []):
            if pool.get("product") != "V75":
                continue

            candidates.append(
                {
                    "race_day": race_day,
                    "pool": pool,
                }
            )

    return candidates


def describe_candidate(candidate: dict) -> None:
    race_day = candidate["race_day"]
    pool = candidate["pool"]

    print(
        f"\n{race_day.get('raceDayKey')}  "
        f"{race_day.get('raceDayName')}  "
        f"{race_day.get('countryIsoCode')}"
    )

    print(
        f"  domestic={race_day.get('isDomestic')} "
        f"multiTrack={pool.get('isMultiTrack')}"
    )

    print("  V75 races:")

    for i, race_key in enumerate(pool.get("races", []), 1):
        print(f"    V75-{i}: {race_key}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        request = p.request.new_context(
            base_url=BASE,
            extra_http_headers={
                "Accept-Language": "nb-NO,nb;q=0.9",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0.0.0 Safari/537.36"
                ),
            },
        )

        print("\n=== 1. LOOK UP RACE DAYS ===")

        dates_payload = get_json(
            request,
            f"/api/racedays/dates/{DATE}/{DATE}",
        )

        save_json(
            OUT / "race-days-raw.json",
            dates_payload,
        )

        race_days = unwrap(dates_payload)

        if not isinstance(race_days, list):
            raise RuntimeError(
                "Unexpected race-days response."
            )

        candidates = find_v75_candidates(race_days)

        print(
            f"\nFound {len(candidates)} V75 candidate(s)."
        )

        for candidate in candidates:
            describe_candidate(candidate)

        norwegian = [
            candidate
            for candidate in candidates
            if candidate["race_day"].get("countryIsoCode") == "NO"
            and candidate["race_day"].get("isDomestic") is True
        ]

        # For første snapshot ønsker vi én ren norsk,
        # single-track V75 med syv avdelinger.
        suitable = []

        for candidate in norwegian:
            race_day = candidate["race_day"]
            pool = candidate["pool"]
            race_day_key = race_day["raceDayKey"]
            races = pool.get("races", [])

            same_meeting = (
                len(races) == 7
                and all(
                    race_key.startswith(race_day_key + "#")
                    for race_key in races
                )
            )

            if same_meeting and not pool.get("isMultiTrack", False):
                suitable.append(candidate)

        if len(suitable) != 1:
            print("\nNo unique single-track Norwegian V75 found.")
            print(
                "This is not an error in the API; "
                "inspect candidates above."
            )
            raise SystemExit(2)

        candidate = suitable[0]
        race_day = candidate["race_day"]
        pool = candidate["pool"]

        race_day_key = race_day["raceDayKey"]
        race_name = race_day["raceDayName"]

        print("\n=== 2. SELECTED MEETING ===")
        print(f"Race day: {race_day_key}")
        print(f"Track:    {race_name}")

        v75_race_keys = pool["races"]

        v75_races = []

        for leg, race_key in enumerate(v75_race_keys, 1):
            race_number = int(race_key.rsplit("#", 1)[1])

            v75_races.append(
                {
                    "leg": leg,
                    "raceKey": race_key,
                    "raceNumber": race_number,
                }
            )

        save_json(
            OUT / "v75-pool.json",
            {
                "date": DATE,
                "raceDayKey": race_day_key,
                "raceDayName": race_name,
                "pool": pool,
                "legs": v75_races,
            },
        )

        print("\n=== 3. RACE INFO ===")

        race_info = get_json(
            request,
            f"/api/racedays/{race_day_key}/raceInfo",
        )

        save_json(
            OUT / "race-info.json",
            race_info,
        )

        print("\n=== 4. START LISTS ===")

        starts = get_json(
            request,
            f"/api/racedays/{race_day_key}/starts",
        )

        save_json(
            OUT / "starts.json",
            starts,
        )

        print("\n=== 5. FULL FORM HISTORY ===")

        form_rows = get_json(
            request,
            f"/api/game/program/"
            f"{race_day_key}/formrowstrot",
        )

        save_json(
            OUT / "form-rows-trot.json",
            form_rows,
        )

        print("\n=== 6. V75 PROGRAM DATA ===")

        program_dir = OUT / "program"
        program_dir.mkdir(exist_ok=True)

        program_summary = []

        for race in v75_races:
            leg = race["leg"]
            race_number = race["raceNumber"]

            payload = get_json(
                request,
                f"/api/game/program/"
                f"{race_day_key}/V/trot/{race_number}",
            )

            save_json(
                program_dir / f"v75-{leg}.json",
                payload,
            )

            result = unwrap(payload)

            starts_count = 0

            if isinstance(result, list) and result:
                starts_count = len(
                    result[0].get("starts", [])
                )

            program_summary.append(
                {
                    **race,
                    "starts": starts_count,
                }
            )

        print("\n=== 7. WIN ODDS ===")

        try:
            odds = get_json(
                request,
                f"/api/game/{race_day_key}/"
                "betdistribution/winodds",
            )

            save_json(
                OUT / "win-odds.json",
                odds,
            )

        except Exception as exc:
            print(f"WARNING: win odds unavailable: {exc}")

        request.dispose()

    print("\n" + "=" * 72)
    print("SNAPSHOT COMPLETE")
    print("=" * 72)

    print(f"Date:     {DATE}")
    print(f"Track:    {race_name}")
    print(f"Race day: {race_day_key}")

    print("\nV75:")

    for race in program_summary:
        print(
            f"  V75-{race['leg']}: "
            f"race {race['raceNumber']} "
            f"({race['starts']} starters)"
        )

    form_path = OUT / "form-rows-trot.json"

    print(
        f"\nForm-history file: "
        f"{form_path.stat().st_size:,} bytes"
    )

    print(f"\nSaved to:\n{OUT}")
    print("=" * 72)


if __name__ == "__main__":
    main()
